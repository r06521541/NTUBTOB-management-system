SHARED_LIB_VERSION = 0.0.1
PROJECT_ID = ntubtob-schedule-405614
REGION = asia-east1
IMAGE_TAG ?= $(shell git rev-parse HEAD)

	
DIR_GAME_BROADCAST_SERVICE = game_broadcast_service
GAME_BROADCAST_SERVICE_NAME = game-broadcast-service

update-shared-lib-for-game-broadcast-service:
	make build-and-install-shared-lib
	mkdir -p apps/${DIR_GAME_BROADCAST_SERVICE}/dist
	cp $(SHARED_LIB_DIR)/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz \
		apps/${DIR_GAME_BROADCAST_SERVICE}/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz
		
deploy-game-broadcast-service:
	make build-shared-lib
	mkdir -p apps/${DIR_GAME_BROADCAST_SERVICE}/dist
	cp $(SHARED_LIB_DIR)/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz \
		apps/${DIR_GAME_BROADCAST_SERVICE}/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz

	# copy non-sensitive env settings; secrets are bound by Cloud Run
	grep -vE '^[[:space:]]*(DSN_PASSWORD|CHANNEL_ACCESS_TOKEN|CHANNEL_SECRET|WEATHER_API_KEY)[[:space:]]*:' \
		envs/${DIR_GAME_BROADCAST_SERVICE}/.env.yaml \
		> apps/${DIR_GAME_BROADCAST_SERVICE}/.env.yaml

	@echo "Building Docker image..."
	cd apps/${DIR_GAME_BROADCAST_SERVICE} && gcloud builds submit --region=${REGION} \
		--config cloudbuild.yaml --substitutions=_SERVICE_NAME="${GAME_BROADCAST_SERVICE_NAME}",_REGION="${REGION}",_IMAGE_TAG="${IMAGE_TAG}" .
		
	# delete temp env file
	rm apps/${DIR_GAME_BROADCAST_SERVICE}/.env.yaml

	
	
DIR_NOTIFY_CRONJOB_SERVICE = notify_cronjob_service
NOTIFY_CRONJOB_SERVICE_NAME = notify-cronjob-service
		
update-shared-lib-for-notify-cronjob-service:
	make build-and-install-shared-lib
	mkdir -p apps/${DIR_NOTIFY_CRONJOB_SERVICE}/dist
	cp $(SHARED_LIB_DIR)/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz \
		apps/${DIR_NOTIFY_CRONJOB_SERVICE}/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz

deploy-notify-cronjob-service:
	make build-shared-lib
	mkdir -p apps/${DIR_NOTIFY_CRONJOB_SERVICE}/dist
	cp $(SHARED_LIB_DIR)/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz \
		apps/${DIR_NOTIFY_CRONJOB_SERVICE}/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz

	# copy non-sensitive env settings; secrets are bound by Cloud Run
	grep -vE '^[[:space:]]*(DSN_PASSWORD|CHANNEL_ACCESS_TOKEN|CHANNEL_SECRET)[[:space:]]*:' \
		envs/${DIR_NOTIFY_CRONJOB_SERVICE}/.env.yaml \
		> apps/${DIR_NOTIFY_CRONJOB_SERVICE}/.env.yaml

	@echo "Building Docker image..."
	cd apps/${DIR_NOTIFY_CRONJOB_SERVICE} && gcloud builds submit --region=${REGION} \
		--config cloudbuild.yaml --substitutions=_SERVICE_NAME="${NOTIFY_CRONJOB_SERVICE_NAME}",_REGION="${REGION}",_IMAGE_TAG="${IMAGE_TAG}" .
		
	# delete temp env file
	rm apps/${DIR_NOTIFY_CRONJOB_SERVICE}/.env.yaml

	
DIR_WEB_PORTAL = web_portal
WEB_PORTAL_NAME = web-portal
WEB_PORTAL_LINE_LOGIN_SECRET_REF ?=
WEB_PORTAL_SESSION_SECRET_REF ?=
		
update-shared-lib-for-deploy-web-portal:
	make build-and-install-shared-lib
	mkdir -p apps/${DIR_WEB_PORTAL}/dist
	cp $(SHARED_LIB_DIR)/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz \
		apps/${DIR_WEB_PORTAL}/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz

deploy-web-portal:
	@printf '%s\n' "${WEB_PORTAL_LINE_LOGIN_SECRET_REF}" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9._/-]*:[A-Za-z0-9][A-Za-z0-9._-]*$$' || (echo "WEB_PORTAL_LINE_LOGIN_SECRET_REF must be a resource:version reference" >&2; exit 2)
	@printf '%s\n' "${WEB_PORTAL_SESSION_SECRET_REF}" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9._/-]*:[A-Za-z0-9][A-Za-z0-9._-]*$$' || (echo "WEB_PORTAL_SESSION_SECRET_REF must be a resource:version reference" >&2; exit 2)
	@printf '%s' "${IMAGE_TAG}" | grep -Eq '^[0-9a-f]{40}$$' || (echo "IMAGE_TAG must be a 40-character Git commit SHA" >&2; exit 2)
	make build-shared-lib
	mkdir -p apps/${DIR_WEB_PORTAL}/dist
	cp $(SHARED_LIB_DIR)/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz \
		apps/${DIR_WEB_PORTAL}/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz

	@echo "Building Docker image..."
	@trap 'rm -f apps/${DIR_WEB_PORTAL}/.env.yaml' EXIT; \
		grep -vE '^[[:space:]]*(DSN_PASSWORD|LINE_LOGIN_CHANNEL_SECRET|SECRET_KEY)[[:space:]]*:' \
			envs/${DIR_WEB_PORTAL}/.env.yaml \
			> apps/${DIR_WEB_PORTAL}/.env.yaml; \
		(cd apps/${DIR_WEB_PORTAL} && gcloud builds submit --region=${REGION} \
			--config cloudbuild.yaml \
			--substitutions=_SERVICE_NAME="${WEB_PORTAL_NAME}",_REGION="${REGION}",_IMAGE_TAG="${IMAGE_TAG}",_WEB_PORTAL_LINE_LOGIN_SECRET_REF="${WEB_PORTAL_LINE_LOGIN_SECRET_REF}",_WEB_PORTAL_SESSION_SECRET_REF="${WEB_PORTAL_SESSION_SECRET_REF}" .)
