SHARED_LIB_DIR = shared_lib

build-shared-lib:
	@echo "Building shared library..."
	@cd $(SHARED_LIB_DIR) && python3 setup.py sdist

build-and-install-shared-lib:
	@echo "Building shared library..."
	@cd $(SHARED_LIB_DIR) && python3 setup.py sdist
	@echo "Installing shared library..."
	pip3 install $(SHARED_LIB_DIR)/dist/shared_lib-0.0.1.tar.gz
