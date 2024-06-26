SHARED_LIB_VERSION = 0.0.1
PROJECT_ID = ntubtob-schedule-405614
SERVICE_NAME = line-user-service
REGION = east-asia1  # 选择一个区域
IMAGE = gcr.io/$(PROJECT_ID)/$(SERVICE_NAME)

deploy-line-user-service:
	make build-shared-lib
	mkdir -p apps/line_user_service/dist
	cp $(SHARED_LIB_DIR)/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz \
		apps/line_user_service/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz
		
	# copy temp env file
	cp envs/line_user_service/.env.yaml \
		apps/line_user_service/.env.yaml

	@echo "Building Docker image..."
	cd apps/line_user_service && gcloud builds submit --region=asia-east1 --config cloudbuild.yaml
		
	# delete temp env file
	rm apps/line_user_service/.env.yaml
