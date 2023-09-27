from typing import Callable, Iterable

from lifecycle.config import Config
from lifecycle.infrastructure.infra_target import remote_shell
from lifecycle.monitor.base import JobMonitor
from lifecycle.monitor.health import check_until_job_is_operational, quick_check_job_condition
from lifecycle.monitor.metric_parser import read_last_call_timestamp_metric, scrape_metrics
from racetrack_client.log.context_error import wrap_context
from racetrack_client.log.exception import short_exception_details
from racetrack_client.utils.time import datetime_to_timestamp
from racetrack_client.utils.url import join_paths
from racetrack_commons.deploy.resource import job_resource_name
from racetrack_commons.entities.dto import JobDto, JobStatus
from racetrack_client.log.logs import get_logger

from plugin_config import InfrastructureConfig
from utils import K8S_JOB_RESOURCE_LABEL, list_job_deployments, JobDeployment

logger = get_logger(__name__)


class KubernetesMonitor(JobMonitor):
    """Discovers Job resources in a k8s cluster and monitors their condition"""

    def __init__(self, infrastructure_name: str, infra_config: InfrastructureConfig) -> None:
        self.infra_config = infra_config
        self.infrastructure_name = infrastructure_name
        self.k8s_namespace = infra_config.job_k8s_namespace

    def list_jobs(self, config: Config) -> Iterable[JobDto]:

        with wrap_context('listing Kubernetes API'):
            job_deployments: list[JobDeployment] = list_job_deployments(self.k8s_namespace, self.remote_shell)

        for deployment in job_deployments:
            recent_pod = deployment.pods[-1]
            job_name = recent_pod.job_name
            job_version = recent_pod.job_version
            if not (recent_pod.job_name and job_version):
                continue

            start_timestamp = datetime_to_timestamp(recent_pod.creation_datetime)
            internal_name = f'{deployment.resource_name}.{self.k8s_namespace}.svc:7000'

            replica_internal_names: list[str] = []
            for pod in deployment.pods:
                pod_ip_dns: str = pod.ip.replace('.', '-')
                replica_internal_names.append(
                    f'{pod_ip_dns}.{deployment.resource_name}.{self.k8s_namespace}.svc:7000'
                )
            replica_internal_names.sort()

            job = JobDto(
                name=job_name,
                version=job_version,
                status=JobStatus.RUNNING.value,
                create_time=start_timestamp,
                update_time=start_timestamp,
                manifest=None,
                internal_name=internal_name,
                error=None,
                infrastructure_target=self.infrastructure_name,
                replica_internal_names=replica_internal_names,
            )
            try:
                job_url, request_headers = self.get_remote_job_address(job)
                quick_check_job_condition(job_url, request_headers)
                job_metrics = scrape_metrics(f'{job_url}/metrics', request_headers)
                job.last_call_time = read_last_call_timestamp_metric(job_metrics)
            except Exception as e:
                error_details = short_exception_details(e)
                job.error = error_details
                job.status = JobStatus.ERROR.value
                logger.warning(f'Job {job} is in bad condition: {error_details}')
            yield job

    def check_job_condition(
        self,
        job: JobDto,
        deployment_timestamp: int = 0,
        on_job_alive: Callable = None,
        logs_on_error: bool = True,
    ):
        job_url, request_headers = self.get_remote_job_address(job)
        try:
            check_until_job_is_operational(job_url, deployment_timestamp, on_job_alive, request_headers)
        except Exception as e:
            if logs_on_error:
                logs = self.read_recent_logs(job)
                raise RuntimeError(f'{e}\nJob logs:\n{logs}') from e
            else:
                raise RuntimeError(str(e)) from e

    def get_remote_job_address(self, job: JobDto) -> tuple[str, dict[str, str]]:
        if not self.infra_config.remote_gateway_url:
            return f'http://{job.internal_name}', {}
        request_headers = {
            'X-Racetrack-Gateway-Token': self.infra_config.remote_gateway_token,
            'X-Racetrack-Job-Internal-Name': job.internal_name,
        }
        remote_url = join_paths(self.infra_config.remote_gateway_url, "/remote/forward/", job.name, job.version)
        return remote_url, request_headers

    def read_recent_logs(self, job: JobDto, tail: int = 20) -> str:
        resource_name = job_resource_name(job.name, job.version)
        return self.remote_shell(f'/opt/kubectl logs'
                                 f' --selector {K8S_JOB_RESOURCE_LABEL}={resource_name}'
                                 f' -n {self.k8s_namespace}'
                                 f' --tail={tail}'
                                 f' --container={resource_name}')

    def remote_shell(self, cmd: str) -> str:
        return remote_shell(cmd, self.infra_config.remote_gateway_url, self.infra_config.remote_gateway_token)
