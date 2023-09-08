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

3.  Download `kubectl` client and keep it in the working directory:
    ```shell
    mkdir -p ~/racetrack
    cd ~/racetrack
    curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
    ```
    This binary will be mounted to the remote Pub container.

4.  Install Racetrack's PUB gateway on a remote host, which will dispatch the traffic to the local jobs.
    Generate a strong password that will be used as a token to authorize only the requests coming from the main Racetrack:
    ```shell
    REMOTE_GATEWAY_TOKEN='5tr0nG_PA55VoRD'
    IMAGE=ghcr.io/theracetrack/racetrack/pub:latest
    NAMESPACE=racetrack
    
    cat <<EOF | kubectl apply -f -
    apiVersion: apps/v1
    kind: Deployment
    metadata:
      namespace: $NAMESPACE
      name: pub-remote
      labels:
        app.kubernetes.io/name: pub-remote
    spec:
      replicas: 1
      selector:
        matchLabels:
          app.kubernetes.io/name: pub-remote
      template:
        metadata:
          labels:
            app.kubernetes.io/name: pub-remote
        spec:
          securityContext:
            supplementalGroups: [200000]
            fsGroup: 200000
            runAsUser: 100000
            runAsGroup: 100000
          automountServiceAccountToken: false
          imagePullSecrets:
            - name: docker-registry-read-secret
          priorityClassName: high-priority
          hostname: pub-remote
          subdomain: pub-remote
          containers:
            - name: pub-remote
              image: $IMAGE
              imagePullPolicy: Always
              ports:
                - containerPort: 7005
              tty: true
              resources:
                requests:
                  memory: "500Mi"
                  cpu: "25m"
                limits:
                  memory: "1Gi"
                  cpu: "2000m"
              securityContext:
                readOnlyRootFilesystem: false
                allowPrivilegeEscalation: false
                capabilities:
                  drop: ["all"]
                runAsNonRoot: true
              env:
                - name: PUB_PORT
                  value: '7005'
                - name: AUTH_REQUIRED
                  value: 'true'
                - name: AUTH_DEBUG
                  value: 'true'
                - name: REMOTE_GATEWAY_MODE
                  value: 'true'
                - name: REMOTE_GATEWAY_TOKEN
                  value: '$REMOTE_GATEWAY_TOKEN'
              livenessProbe:
                httpGet:
                  path: /live
                  port: 7005
                initialDelaySeconds: 30
                periodSeconds: 10
              readinessProbe:
                httpGet:
                  path: /ready
                  port: 7005
                initialDelaySeconds: 3
                periodSeconds: 10
    ---
    apiVersion: v1
    kind: Service
    metadata:
      namespace: $NAMESPACE
      name: pub-remote
      labels:
        app.kubernetes.io/name: pub-remote
    spec:
      selector:
        app.kubernetes.io/name: pub-remote
      type: ClusterIP
      ports:
        - name: pub-remote
          port: 7005
          targetPort: 7005
    EOF
    ```
    Make sure pods can speak to local Kubernetes API inside the cluster.

5.  Go to Racetrack's Dashboard, Administration, Edit Config of the plugin.
    Prepare the following data:
    
    - Host IP or DNS hostname
    - Credentials to the Docker Registry, where Job images will be located.

    Save the YAML configuration of the plugin:
    ```yaml
    infrastructure_targets:
      remote-k8s:
        remote_gateway_url: 'http://1.2.3.4:7105'
        remote_gateway_token: '5tr0nG_PA55VoRD'

    docker: 
      docker_registry: 'docker.registry.example.com'
      username: 'DOCKER_USERNAME'
      password: 'READ_WRITE_TOKEN'
    ```
