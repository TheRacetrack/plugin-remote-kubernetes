import threading
from typing import DefaultDict, Dict
from typing import List

from kubernetes import client
from kubernetes.client import V1Pod
from kubernetes.watch import Watch

from lifecycle.monitor.base import LogsStreamer
from racetrack_commons.deploy.resource import job_resource_name

from plugin_config import InfrastructureConfig
from utils import get_job_pod_names, k8s_api_client, K8S_NAMESPACE, K8S_JOB_RESOURCE_LABEL


class KubernetesLogsStreamer(LogsStreamer):
    """Source of a Job logs retrieved from a Kubernetes pod"""

    def __init__(self, infrastructure_name: str, infra_config: InfrastructureConfig):
        super().__init__()
        self.infra_config = infra_config
        self.infrastructure_name = infrastructure_name
        self.sessions: Dict[str, List[Watch]] = DefaultDict(list)

    def create_session(self, session_id: str, resource_properties: Dict[str, str]):
        """Start a session transmitting messages to a client."""
        job_name = resource_properties.get('job_name')
        job_version = resource_properties.get('job_version')
        tail = resource_properties.get('tail')
        resource_name = job_resource_name(job_name, job_version)

        k8s_client = k8s_api_client()
        core_api = client.CoreV1Api(k8s_client)
        ret = core_api.list_namespaced_pod(K8S_NAMESPACE,
                                           label_selector=f'{K8S_JOB_RESOURCE_LABEL}={resource_name}')
        pods: List[V1Pod] = ret.items
        pod_names = get_job_pod_names(pods)

        for pod_name in pod_names:
            watch = Watch()
            self.sessions[session_id].append(watch)

            def watch_output(streamer):
                for line in watch.stream(core_api.read_namespaced_pod_log, name=pod_name, namespace=K8S_NAMESPACE,
                                         container=resource_name, tail_lines=tail, follow=True):
                    streamer.broadcast(session_id, line)

            threading.Thread(
                target=watch_output,
                args=(self,),
                daemon=True,
            ).start()

    def close_session(self, session_id: str):
        watches = self.sessions[session_id]
        for watch in watches:
            watch.stop()
        del self.sessions[session_id]
