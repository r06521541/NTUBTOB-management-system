SHARED_LIB_VERSION = 0.0.1
SECRET_STRING_DSN_PASSWORD = DSN_PASSWORD=supabase-database-password:latest
SECRET_STRING_WEB_PORTAL_URL = WEB_PORTAL_URL=web-portal-url:latest
SECRET_STRING_CHANNEL_ACCESS_TOKEN = CHANNEL_ACCESS_TOKEN=CHANNEL_ACCESS_TOKEN:2
SECRET_STRING_CHANNEL_SECRET = CHANNEL_SECRET=CHANNEL_SECRET:2


DIR_NAME_UPDATE_GAME_SCHEDULE = update_game_schedule
FUNCTION_NAME_UPDATE_GAME_SCHEDULE = update-game-schedule

update-shared-lib-for-update-game-schedule:
	make build-and-install-shared-lib
	mkdir -p functions/${DIR_NAME_UPDATE_GAME_SCHEDULE}/dist
	cp $(SHARED_LIB_DIR)/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz \
		functions/${DIR_NAME_UPDATE_GAME_SCHEDULE}/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz


deploy-update-game-schedule:
	make build-shared-lib
	mkdir -p functions/${DIR_NAME_UPDATE_GAME_SCHEDULE}/dist
	cp $(SHARED_LIB_DIR)/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz \
		functions/${DIR_NAME_UPDATE_GAME_SCHEDULE}/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz
	gcloud functions deploy ${FUNCTION_NAME_UPDATE_GAME_SCHEDULE} \
		--region asia-east1 \
		--gen2 \
        --set-secrets '${SECRET_STRING_DSN_PASSWORD}' \
		--env-vars-file envs/${DIR_NAME_UPDATE_GAME_SCHEDULE}/.env.yaml \
		--runtime python310 \
		--trigger-http \
		--no-allow-unauthenticated \
		--entry-point main \
		--source functions/${DIR_NAME_UPDATE_GAME_SCHEDULE}/ \
    	--clear-labels


DIR_NAME_LINE_WEBHOOK_HANDLER = line_webhook_handler
FUNCTION_NAME_LINE_WEBHOOK_HANDLER = line-webhook-handler

update-shared-lib-for-line-webhook-handler:
	make build-and-install-shared-lib
	mkdir -p functions/${DIR_NAME_LINE_WEBHOOK_HANDLER}/dist
	cp $(SHARED_LIB_DIR)/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz \
		functions/${DIR_NAME_LINE_WEBHOOK_HANDLER}/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz

deploy-line-webhook-handler:
	make build-shared-lib
	mkdir -p functions/${DIR_NAME_LINE_WEBHOOK_HANDLER}/dist
	cp $(SHARED_LIB_DIR)/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz \
		functions/${DIR_NAME_LINE_WEBHOOK_HANDLER}/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz
	gcloud functions deploy ${FUNCTION_NAME_LINE_WEBHOOK_HANDLER} \
		--region asia-east1 \
		--gen2 \
		--set-secrets '${SECRET_STRING_DSN_PASSWORD},${SECRET_STRING_WEB_PORTAL_URL},${SECRET_STRING_CHANNEL_ACCESS_TOKEN},${SECRET_STRING_CHANNEL_SECRET}' \
		--env-vars-file envs/${DIR_NAME_LINE_WEBHOOK_HANDLER}/.env.yaml \
		--runtime python310 \
		--trigger-http \
		--allow-unauthenticated \
		--entry-point main \
		--source functions/${DIR_NAME_LINE_WEBHOOK_HANDLER}/ \
		--clear-labels
