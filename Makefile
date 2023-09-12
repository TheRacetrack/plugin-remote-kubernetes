.PHONY: build

bundle:
	cd src &&\
	racetrack plugin bundle --out=..

install:
	racetrack plugin install *.zip

build-remote-pub:
	cd build && ./build-k8s-remote-pub.sh

deploy-remote-pub:
	cd build && ./deploy-remote-pub.sh
