# Racetrack Plugin: Remote Kubernetes Infrastructure

A Racetrack plugin allowing to deploy services to remote Kubernetes (running on different host)

## Setup

1.  Install [racetrack client](https://pypi.org/project/racetrack-client/) and generate ZIP plugin by running:
    ```shell
    make bundle
    ```

2.  Activate the plugin in Racetrack Dashboard Admin page by uploading the zipped plugin file:
    ```shell
    racetrack plugin install remote-kubernetes-*.zip
    ```

3.  Install Racetrack's PUB gateway on a remote host, which will dispatch the traffic to the local jobs.
    Generate a strong password that will be used as a token to authorize only the requests coming from the main Racetrack:
    ```shell
    REMOTE_GATEWAY_TOKEN='5tr0nG_PA55VoRD'
    ```
    ```shell
    IMAGE=ghcr.io/theracetrack/racetrack/pub:latest
    cat <<EOF | kubectl apply -f -
    apiVersion: v1
    kind: Deployment
    metadata:
    EOF
    ```

4.  Go to Racetrack's Dashboard, Administration, Edit Config of the plugin.
    Prepare the following data:
    
    - Host IP or DNS hostname
    - Credentials to the Docker Registry, where Job images will be located.
    - Kubernetes API certificate

    Save the YAML configuration of the plugin:
    ```yaml
    infrastructure_targets:
      remote-k8s:
        hostname: 1.2.3.4
        remote_gateway_url: 'http://1.2.3.4:7105'
        remote_gateway_token: '5tr0nG_PA55VoRD'

    docker: 
      docker_registry: 'docker.registry.example.com'
      username: 'DOCKER_USERNAME'
      password: 'READ_WRITE_TOKEN'
    ```
