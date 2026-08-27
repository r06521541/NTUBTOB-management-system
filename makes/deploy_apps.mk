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
WEB_PORTAL_WEATHER_SECRET_REF ?=
WEB_PORTAL_ROLLBACK_REVISION ?=
PORTAL_DATA_PHASE_C_ENABLED ?=
PORTAL_DATA_ROLLOUT_FREEZE_ENABLED ?=
WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED ?=
WEB_IDENTITY_LINK_MODE ?=
WEB_IDENTITY_LINK_GOOGLE_SECRET_REF ?=
WEB_IDENTITY_LINK_LINE_SECRET_REF ?=
WEB_IDENTITY_LINK_GOOGLE_CLIENT_ID ?=
WEB_IDENTITY_LINK_GOOGLE_REDIRECT_URI ?=
WEB_IDENTITY_LINK_LINE_CLIENT_ID ?=
WEB_IDENTITY_LINK_LINE_REDIRECT_URI ?=
		
update-shared-lib-for-deploy-web-portal:
	make build-and-install-shared-lib
	mkdir -p apps/${DIR_WEB_PORTAL}/dist
	cp $(SHARED_LIB_DIR)/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz \
		apps/${DIR_WEB_PORTAL}/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz

deploy-web-portal:
	@set -- \
		--execute \
		--approved-commit "${IMAGE_TAG}" \
		--rollback-revision "${WEB_PORTAL_ROLLBACK_REVISION}" \
		--line-login-secret-ref "${WEB_PORTAL_LINE_LOGIN_SECRET_REF}" \
		--session-secret-ref "${WEB_PORTAL_SESSION_SECRET_REF}" \
		--weather-secret-ref "${WEB_PORTAL_WEATHER_SECRET_REF}" \
		--phase-c-enabled "${PORTAL_DATA_PHASE_C_ENABLED}" \
		--rollout-freeze-enabled "${PORTAL_DATA_ROLLOUT_FREEZE_ENABLED}" \
		--identity-maintenance-enabled "${WEB_PORTAL_IDENTITY_MAINTENANCE_ENABLED}" \
		--identity-link-mode "${WEB_IDENTITY_LINK_MODE}"; \
	if [ -n "${WEB_IDENTITY_LINK_GOOGLE_SECRET_REF}${WEB_IDENTITY_LINK_LINE_SECRET_REF}${WEB_IDENTITY_LINK_GOOGLE_CLIENT_ID}${WEB_IDENTITY_LINK_GOOGLE_REDIRECT_URI}${WEB_IDENTITY_LINK_LINE_CLIENT_ID}${WEB_IDENTITY_LINK_LINE_REDIRECT_URI}" ]; then \
		set -- "$$@" \
			--google-identity-secret-ref "${WEB_IDENTITY_LINK_GOOGLE_SECRET_REF}" \
			--line-identity-secret-ref "${WEB_IDENTITY_LINK_LINE_SECRET_REF}" \
			--google-client-id "${WEB_IDENTITY_LINK_GOOGLE_CLIENT_ID}" \
			--google-redirect-uri "${WEB_IDENTITY_LINK_GOOGLE_REDIRECT_URI}" \
			--line-client-id "${WEB_IDENTITY_LINK_LINE_CLIENT_ID}" \
			--line-redirect-uri "${WEB_IDENTITY_LINK_LINE_REDIRECT_URI}"; \
	fi; \
	python tools/deploy_web_portal.py "$$@"
