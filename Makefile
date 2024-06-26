# Reference: https://gist.github.com/mpneuried/0594963ad38e68917ef189b4e6a269db
.PHONY: help
help:  ## Help
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

include makes/deploy_apps.mk
include makes/deploy_functions.mk
include makes/dev.mk
include makes/shared_lib.mk