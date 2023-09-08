import json
from collections import defaultdict
import os
from datetime import datetime, timezone
from typing import Callable

from pydantic import BaseModel

K8S_NAMESPACE = os.environ.get('JOB_K8S_NAMESPACE', 'racetrack')
K8S_JOB_RESOURCE_LABEL = "racetrack/job"
K8S_JOB_NAME_LABEL = "racetrack/job-name"
K8S_JOB_VERSION_LABEL = "racetrack/job-version"


class JobPod(BaseModel):
    pod_name: str
    resource_name: str
    job_name: str
    job_version: str
    creation_datetime: datetime
    phase: str
    ip: str


class JobDeployment(BaseModel):
    resource_name: str
    pods: list[JobPod] = []


def list_job_deployments(remote_shell: Callable[[str], str]) -> list[JobDeployment]:
    cmd = f"/opt/kubectl -n {K8S_NAMESPACE} get pods --field-selector=status.phase=Running --selector='racetrack/job' -o json"
    output_str = remote_shell(cmd).strip()
    result = json.loads(output_str)

    pods_by_job: dict[str, list[JobPod]] = defaultdict(list)
    for pod_item in result['items']:
        metadata = pod_item.get('metadata', {})
        pod_name = metadata.get('name')
        creation_timestamp: str = metadata.get('creationTimestamp')
        if metadata.get('deletionTimestamp') is not None:  # ignore Terminating pods
            continue
        creation_datetime: datetime = datetime.strptime(creation_timestamp, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
        pod_labels: dict[str, str] = metadata.get('labels')
        job_name = pod_labels.get(K8S_JOB_NAME_LABEL)
        job_version = pod_labels.get(K8S_JOB_VERSION_LABEL)
        resource_name = pod_labels.get(K8S_JOB_RESOURCE_LABEL)
        status = pod_item.get('status', {})
        pod_ip = status.get('podIP')
        phase = status.get('phase')

        job_pod = JobPod(
            pod_name=pod_name,
            resource_name=resource_name,
            job_name=job_name,
            job_version=job_version,
            creation_datetime=creation_datetime,
            phase=phase,
            ip=pod_ip,
        )
        pods_by_job[resource_name].append(job_pod)

    deployments: list[JobDeployment] = []
    for resource_name, pods in pods_by_job.items():
        sorted_pods = sorted(pods, key=lambda pod: pod.creation_datetime)
        job_deployment = JobDeployment(
            resource_name=resource_name,
            pods=sorted_pods,
        )
        deployments.append(job_deployment)

    return sorted(deployments, key=lambda d: d.resource_name)
