.PHONY: build

bundle:
	cd src &&\
	racetrack plugin bundle --out=..

install:
	racetrack plugin install *.zip

build-remote-pub:
	cd build && DOCKER_BUILDKIT=1 docker build \
		-t ghcr.io/theracetrack/plugin-remote-kubernetes/pub-remote:latest \
		-f Dockerfile .

push-image:
	docker push ghcr.io/theracetrack/plugin-remote-kubernetes/pub-remote:latest

retag-image-registry:
	docker tag ghcr.io/theracetrack/plugin-remote-kubernetes/pub-remote:latest localhost:5000/theracetrack/plugin-remote-kubernetes/pub-remote:latest
	docker push localhost:5000/theracetrack/plugin-remote-kubernetes/pub-remote:latest

retag-image-tag:
	docker tag ghcr.io/theracetrack/plugin-remote-kubernetes/pub-remote:latest ghcr.io/theracetrack/plugin-remote-kubernetes/pub-remote:${TAG}
	docker push ghcr.io/theracetrack/plugin-remote-kubernetes/pub-remote:${TAG}

deploy-remote-pub:
	cd build && ./deploy-remote-pub.sh
