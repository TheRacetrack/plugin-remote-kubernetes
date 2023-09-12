FROM ghcr.io/theracetrack/racetrack/pub:latest

RUN apk add curl

# install kubectl, check latest version: curl -L -s https://dl.k8s.io/release/stable.txt
RUN mkdir -p /opt \
    && curl -L "https://dl.k8s.io/release/v1.28.1/bin/linux/amd64/kubectl" -o /opt/kubectl \
    && chmod +x /opt/kubectl
