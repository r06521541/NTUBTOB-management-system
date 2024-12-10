SHARED_LIB_VERSION = 0.0.1
PROJECT_ID = ntubtob-schedule-405614
REGION = asia-east1

	
DIR_GAME_BROADCAST_SERVICE = game_broadcast_service
GAME_BROADCAST_SERVICE_NAME = game-broadcast-service
		
deploy-game-broadcast-service:
	make build-shared-lib
	mkdir -p apps/${DIR_GAME_BROADCAST_SERVICE}/dist
	cp $(SHARED_LIB_DIR)/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz \
		apps/${DIR_GAME_BROADCAST_SERVICE}/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz

	# copy temp env file
	cp envs/${DIR_GAME_BROADCAST_SERVICE}/.env.yaml \
		apps/${DIR_GAME_BROADCAST_SERVICE}/.env.yaml

	@echo "Building Docker image..."
	cd apps/${DIR_GAME_BROADCAST_SERVICE} && gcloud builds submit --region=${REGION} \
		--config cloudbuild.yaml --substitutions=_SERVICE_NAME="${GAME_BROADCAST_SERVICE_NAME}",_REGION="${REGION}" .
		
	# delete temp env file
	rm apps/${DIR_GAME_BROADCAST_SERVICE}/.env.yaml
	
	
DIR_NOTIFY_CRONJOB_SERVICE = notify_cronjob_service
NOTIFY_CRONJOB_SERVICE_NAME = notify-cronjob-service
		
deploy-notify-cronjob-service:
	make build-shared-lib
	mkdir -p apps/${DIR_NOTIFY_CRONJOB_SERVICE}/dist
	cp $(SHARED_LIB_DIR)/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz \
		apps/${DIR_NOTIFY_CRONJOB_SERVICE}/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz

	# copy temp env file
	cp envs/${DIR_NOTIFY_CRONJOB_SERVICE}/.env.yaml \
		apps/${DIR_NOTIFY_CRONJOB_SERVICE}/.env.yaml

	@echo "Building Docker image..."
	cd apps/${DIR_NOTIFY_CRONJOB_SERVICE} && gcloud builds submit --region=${REGION} \
		--config cloudbuild.yaml --substitutions=_SERVICE_NAME="${NOTIFY_CRONJOB_SERVICE_NAME}",_REGION="${REGION}" .
		
	# delete temp env file
	rm apps/${DIR_NOTIFY_CRONJOB_SERVICE}/.env.yaml

	
DIR_WEB_PORTAL = web_portal
WEB_PORTAL_NAME = web-portal
		
deploy-web-portal:
	make build-shared-lib
	mkdir -p apps/${DIR_WEB_PORTAL}/dist
	cp $(SHARED_LIB_DIR)/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz \
		apps/${DIR_WEB_PORTAL}/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz

	# copy temp env file
	cp envs/${DIR_WEB_PORTAL}/.env.yaml \
		apps/${DIR_WEB_PORTAL}/.env.yaml

	@echo "Building Docker image..."
	cd apps/${DIR_WEB_PORTAL} && gcloud builds submit --region=${REGION} \
		--config cloudbuild.yaml --substitutions=_SERVICE_NAME="${WEB_PORTAL_NAME}",_REGION="${REGION}" .
		
	# delete temp env file
	rm apps/${DIR_WEB_PORTAL}/.env.yaml