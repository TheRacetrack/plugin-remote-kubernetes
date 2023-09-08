import json
import os
import tempfile
from pathlib import Path
from typing import Any
from base64 import b64decode, b64encode

from jinja2 import Template

from lifecycle.auth.subject import get_auth_subject_by_job_family
from lifecycle.config import Config
from lifecycle.deployer.base import JobDeployer
from lifecycle.deployer.secrets import JobSecrets
from lifecycle.infrastructure.infra_target import remote_shell
from lifecycle.job.models_registry import read_job_family_model
from racetrack_client.client.env import merge_env_vars
from racetrack_client.client_config.client_config import Credentials
from racetrack_client.log.logs import get_logger
from racetrack_client.manifest import Manifest
from racetrack_client.manifest.manifest import ResourcesManifest
from racetrack_client.utils.datamodel import convert_to_json, parse_dict_datamodel
from racetrack_client.utils.time import datetime_to_timestamp, now
from racetrack_commons.plugin.core import PluginCore
from racetrack_commons.plugin.engine import PluginEngine
from racetrack_commons.api.debug import debug_mode_enabled
from racetrack_commons.api.tracing import get_tracing_header_name
from racetrack_commons.deploy.image import get_job_image
from racetrack_commons.deploy.resource import job_resource_name
from racetrack_commons.entities.dto import JobDto, JobStatus, JobFamilyDto

from plugin_config import InfrastructureConfig, PluginConfig
from utils import K8S_NAMESPACE

logger = get_logger(__name__)


class KubernetesJobDeployer(JobDeployer):

    def __init__(self, src_dir: Path, infrastructure_name: str, infra_config: InfrastructureConfig, plugin_config: PluginConfig) -> None:
        self.src_dir = src_dir
        self.plugin_config = plugin_config
        self.infra_config = infra_config
        self.infrastructure_name = infrastructure_name

    def deploy_job(
        self,
        manifest: Manifest,
        config: Config,
        plugin_engine: PluginEngine,
        tag: str,
        runtime_env_vars: dict[str, str],
        family: JobFamilyDto,
        containers_num: int = 1,
    ) -> JobDto:
        """Deploy Job on Kubernetes and expose Service accessible by Job name"""
        resource_name = job_resource_name(manifest.name, manifest.version)
        deployment_timestamp = datetime_to_timestamp(now())
        family_model = read_job_family_model(family.name)
        auth_subject = get_auth_subject_by_job_family(family_model)

        common_env_vars = {
            'PUB_URL': config.internal_pub_url,
            'JOB_NAME': manifest.name,
            'AUTH_TOKEN': auth_subject.token,
            'JOB_DEPLOYMENT_TIMESTAMP': deployment_timestamp,
            'REQUEST_TRACING_HEADER': get_tracing_header_name(),
            'JOB_USER_MODULE_HOSTNAME': 'localhost',
        }
        if config.open_telemetry_enabled:
            common_env_vars['OPENTELEMETRY_ENDPOINT'] = config.open_telemetry_endpoint

        plugin_vars_list = plugin_engine.invoke_plugin_hook(PluginCore.job_runtime_env_vars)
        for plugin_vars in plugin_vars_list:
            if plugin_vars:
                common_env_vars = merge_env_vars(common_env_vars, plugin_vars)

        conflicts = common_env_vars.keys() & runtime_env_vars.keys()
        if conflicts:
            raise RuntimeError(f'found illegal runtime env vars, which conflict with reserved names: {conflicts}')
        runtime_env_vars = merge_env_vars(runtime_env_vars, common_env_vars)

        resources = manifest.resources or ResourcesManifest()
        memory_min = resources.memory_min or config.default_job_memory_min
        memory_max = resources.memory_max or config.default_job_memory_max
        cpu_min = resources.cpu_min or config.default_job_cpu_min
        cpu_max = resources.cpu_max or config.default_job_cpu_max
        if resources.memory_max is None and memory_max < memory_min:
            memory_max = memory_min
        if resources.cpu_max is None and cpu_max < cpu_min:
            cpu_max = cpu_min
        if memory_min.plain_number * 4 < memory_max.plain_number:
            memory_min = memory_max / 4
            logger.info(f'minimum memory increased to memory_max/4: {memory_min}')

        assert memory_max <= config.max_job_memory_limit, \
            f'given memory limit {memory_max} is greater than max allowed {config.max_job_memory_limit}'
        assert memory_min, 'memory_min must be greater than zero'
        assert cpu_min, 'cpu_min must be greater than zero'
        assert memory_min <= memory_max, 'memory_min must be less than memory_max'
        assert cpu_min <= cpu_max, 'cpu_min must be less than cpu_max'

        render_vars = {
            'resource_name': resource_name,
            'manifest': manifest,
            'deployment_timestamp': deployment_timestamp,
            'env_vars': runtime_env_vars,
            'memory_min': memory_min,
            'memory_max': memory_max,
            'cpu_min': cpu_min,
            'cpu_max': cpu_max,
            'job_k8s_namespace': K8S_NAMESPACE,
        }
        
        container_vars = []  # list of container tuples: (container_name, image_name, container_port)
        for container_index in range(containers_num):
            container_name = get_container_name(resource_name, container_index)
            image_name = get_job_image(config.docker_registry, config.docker_registry_namespace, manifest.name, tag, container_index)
            container_port = 7000 + container_index
            container_vars.append((container_name, image_name, container_port))
        render_vars['containers'] = container_vars

        self._apply_templated_resource('job_template.yaml', render_vars, self.src_dir)

        internal_name = f'{resource_name}.{K8S_NAMESPACE}.svc:7000'
        return JobDto(
            name=manifest.name,
            version=manifest.version,
            status=JobStatus.RUNNING.value,
            create_time=deployment_timestamp,
            update_time=deployment_timestamp,
            manifest=manifest,
            internal_name=internal_name,
            image_tag=tag,
            infrastructure_target=self.infrastructure_name,
        )

    def delete_job(self, job_name: str, job_version: str):
        resource_name = job_resource_name(job_name, job_version)

        self.remote_shell(f'/opt/kubectl delete deployment/{resource_name} -n {K8S_NAMESPACE}')
        logger.info(f'deleted k8s deployment: {resource_name}')

        self.remote_shell(f'/opt/kubectl delete service/{resource_name} -n {K8S_NAMESPACE}')
        logger.info(f'deleted k8s service: {resource_name}')

        if self._resource_exists(f'secret/{resource_name}'):
            self.remote_shell(f'/opt/kubectl delete secret/{resource_name} -n {K8S_NAMESPACE}')
            logger.info(f'deleted k8s secret: {resource_name}')
        else:
            logger.warning(f'k8s secret "{resource_name}" was not found')

        if self._resource_exists(f'servicemonitors/{resource_name}'):
            self.remote_shell(f'/opt/kubectl delete servicemonitors/{resource_name} -n {K8S_NAMESPACE}')
            logger.info(f'deleted k8s servicemonitor: {resource_name}')
        else:
            logger.warning(f'k8s servicemonitor "{resource_name}" was not found')

    def job_exists(self, job_name: str, job_version: str) -> bool:
        resource_name = job_resource_name(job_name, job_version)
        return self._resource_exists(f'deployment/{resource_name}')

    def save_job_secrets(
        self,
        job_name: str,
        job_version: str,
        job_secrets: JobSecrets,
    ):
        """Create or update secrets needed to build and deploy a job"""
        resource_name = job_resource_name(job_name, job_version)
        render_vars = {
            'resource_name': resource_name,
            'job_name': job_name,
            'job_version': job_version,
            'git_credentials': _encode_secret_key(job_secrets.git_credentials),
            'secret_build_env': _encode_secret_key(job_secrets.secret_build_env),
            'secret_runtime_env': _encode_secret_key(job_secrets.secret_runtime_env),
            'job_k8s_namespace': K8S_NAMESPACE,
        }
        self._apply_templated_resource('secret_template.yaml', render_vars, self.src_dir)

    def get_job_secrets(
        self,
        job_name: str,
        job_version: str,
    ) -> JobSecrets:
        """Retrieve secrets for building and deploying a job"""
        resource_name = job_resource_name(job_name, job_version)
        if not self._resource_exists(f'secret/{resource_name}'):
            raise RuntimeError(f"Can't find secrets associated with job {job_name} v{job_version}")

        output_str = self.remote_shell(f"/opt/kubectl -n {K8S_NAMESPACE} get secret/{resource_name} -o json")
        result = json.loads(output_str.strip())

        secret_data: dict[str, str] = result['data']

        secret_build_env = _decode_secret_key(secret_data, 'secret_build_env') or {}
        secret_runtime_env = _decode_secret_key(secret_data, 'secret_runtime_env') or {}
        git_credentials_dict = _decode_secret_key(secret_data, 'git_credentials')
        git_credentials = parse_dict_datamodel(git_credentials_dict, Credentials) if git_credentials_dict else None

        return JobSecrets(
            git_credentials=git_credentials,
            secret_build_env=secret_build_env,
            secret_runtime_env=secret_runtime_env,
        )

    def _apply_templated_resource(self, template_filename: str, render_vars: dict[str, Any], src_dir: Path):
        """Create resource from YAML template and apply it to kubernetes using kubectl apply"""
        fd, path = tempfile.mkstemp(prefix=template_filename, suffix='.yaml')
        try:
            resource_yaml = _template_resource(template_filename, render_vars, src_dir)
            self.remote_shell(f'''
cat <<EOF | /opt/kubectl apply -f -
{resource_yaml}
EOF
'''.strip())
        finally:
            if not debug_mode_enabled():
                os.remove(path)

    def _resource_exists(self, resource_name: str) -> bool:
        output = self.remote_shell(f"/opt/kubectl -n {K8S_NAMESPACE} get {resource_name} --ignore-not-found -o name")
        return bool(output.strip())

    def remote_shell(self, cmd: str, workdir: str | None = None) -> str:
        return remote_shell(cmd, self.infra_config.remote_gateway_url, self.infra_config.remote_gateway_token, workdir)


def _template_resource(template_filename: str, render_vars: dict[str, Any], src_dir: Path) -> str:
    """Load template from YAML, render templated vars and return as a string"""
    template_path = src_dir / 'templates' / template_filename
    override_template_path = Path('/mnt/templates') / template_filename
    if override_template_path.is_file():
        template_path = override_template_path

    template_content = template_path.read_text()
    template = Template(template_content)
    templated = template.render(**render_vars)
    return templated


def _encode_secret_key(obj: Any) -> str:
    if obj is None:
        return ''
    obj_json: str = convert_to_json(obj)
    obj_encoded: str = b64encode(obj_json.encode()).decode()
    return obj_encoded


def _decode_secret_key(secret_data: dict[str, str], key: str) -> Any | None:
    encoded = secret_data.get(key)
    if not encoded:
        return None
    decoded_json: str = b64decode(encoded.encode()).decode()
    decoded_obj = json.loads(decoded_json)
    return decoded_obj


def get_container_name(resource_name: str, container_index: int) -> str:
    if container_index == 0:
        return resource_name
    else:
        return f'{resource_name}-{container_index}'
