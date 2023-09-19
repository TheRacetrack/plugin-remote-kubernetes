from pydantic import BaseModel, Extra


class InfrastructureConfig(BaseModel, extra=Extra.forbid, arbitrary_types_allowed=True):
    remote_gateway_url: str  # Address of a remote Pub, e.g. "http://host.docker.internal:7107/pub"
    remote_gateway_token: str | None = None


class DockerConfig(BaseModel, extra=Extra.forbid, arbitrary_types_allowed=True):
    docker_registry: str | None = None  # hostname (and port) of docker registry
    username: str | None = None
    password: str | None = None  # read-write token


class PluginConfig(BaseModel, extra=Extra.forbid, arbitrary_types_allowed=True):
    infrastructure_targets: dict[str, InfrastructureConfig] | None = None
    docker: DockerConfig | None = None
