SHARED_LIB_DIR = shared_lib

build-shared-lib:
	@echo "Building shared library..."
	@cd $(SHARED_LIB_DIR) && python setup.py sdist
