SHARED_LIB_VERSION = 0.0.1
PROJECT_ID = ntubtob-schedule-405614
REGION = asia-east1

DIR_LINE_USER_SERVICE = line_user_service
LINE_USER_SERVICE_NAME = line-user-service

deploy-line-user-service:
	make build-shared-lib
	mkdir -p apps/${DIR_LINE_USER_SERVICE}/dist
	cp $(SHARED_LIB_DIR)/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz \
		apps/${DIR_LINE_USER_SERVICE}/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz
		
	# copy temp env file
	cp envs/${DIR_LINE_USER_SERVICE}/.env.yaml \
		apps/${DIR_LINE_USER_SERVICE}/.env.yaml

	@echo "Building Docker image..."
	cd apps/${DIR_LINE_USER_SERVICE} && gcloud builds submit --region=${REGION} \
		--config cloudbuild.yaml --substitutions=_SERVICE_NAME="${LINE_USER_SERVICE_NAME}",_REGION="${REGION}" .
		
	# delete temp env file
	rm apps/${DIR_LINE_USER_SERVICE}/.env.yaml


DIR_GAME_SCHEDULE_SERVICE = game_schedule_service
GAME_SCHEDULE_SERVICE_NAME = game-schedule-service
		
deploy-game-schedule-service:
	make build-shared-lib
	mkdir -p apps/${DIR_GAME_SCHEDULE_SERVICE}/dist
	cp $(SHARED_LIB_DIR)/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz \
		apps/${DIR_GAME_SCHEDULE_SERVICE}/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz

	# copy temp env file
	cp envs/${DIR_GAME_SCHEDULE_SERVICE}/.env.yaml \
		apps/${DIR_GAME_SCHEDULE_SERVICE}/.env.yaml

	@echo "Building Docker image..."
	cd apps/${DIR_GAME_SCHEDULE_SERVICE} && gcloud builds submit --region=${REGION} \
		--config cloudbuild.yaml --substitutions=_SERVICE_NAME="${GAME_SCHEDULE_SERVICE_NAME}",_REGION="${REGION}" .
		
	# delete temp env file
	rm apps/${DIR_GAME_SCHEDULE_SERVICE}/.env.yaml