#!/bin/bash
DOCKER_BUILDKIT=1 docker build \
  -t ghcr.io/theracetrack/plugin-remote-kubernetes/pub-remote:latest \
  -f Dockerfile .

docker tag ghcr.io/theracetrack/plugin-remote-kubernetes/pub-remote:latest localhost:5000/theracetrack/plugin-remote-kubernetes/pub-remote:latest
docker push localhost:5000/theracetrack/plugin-remote-kubernetes/pub-remote:latest
