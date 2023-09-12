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
	docker tag ghcr.io/theracetrack/plugin-remote-kubernetes/pub-remote:latest localhost:5000/theracetrack/plugin-remote-kubernetes/pub-remote:latest
	docker push localhost:5000/theracetrack/plugin-remote-kubernetes/pub-remote:latest

deploy-remote-pub:
	cd build && ./deploy-remote-pub.sh
