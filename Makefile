# Convenience make targets for developing and testing inside Docker

.PHONY: build shell

build:
	docker build -t bmctools:dev .

shell:
	docker run --rm -it -v $(PWD):/opt/bmctools bmctools:dev /bin/bash

