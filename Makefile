# Convenience make targets for developing and testing inside Docker

.PHONY: build shell run

build:
	docker build --platform linux/amd64 -t bmctools:dev .

shell:
	docker run --platform linux/amd64 --rm -it -v $(PWD):/opt/bmctools bmctools:dev /bin/bash

run:
	docker run --platform linux/amd64 --rm -it bmctools:dev $(ARGS)

