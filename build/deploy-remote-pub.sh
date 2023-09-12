#!/bin/bash
REMOTE_GATEWAY_TOKEN='5tr0nG_PA55VoRD'
IMAGE=kind-registry:5000/theracetrack/plugin-remote-kubernetes/pub-remote:latest
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
  type: NodePort
  ports:
    - name: pub-remote
      nodePort: 30005
      port: 7005
      targetPort: 7005
EOF
