SHARED_LIB_DIR = shared_lib

build-and-install-shared-lib:
	@echo "Building shared library..."
	@cd $(SHARED_LIB_DIR) && python setup.py sdist
	pip install shared_lib/dist/shared_lib-0.0.1.tar.gz
