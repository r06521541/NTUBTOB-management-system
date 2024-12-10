SHARED_LIB_VERSION = 0.0.1
SECRET_STRING_DSN_PASSWORD = DSN_PASSWORD=supabase-database-password:latest


DIR_NAME_UPDATE_GAME_SCHEDULE = update_game_schedule
FUNCTION_NAME_UPDATE_GAME_SCHEDULE = update-game-schedule

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
    	--clear-cache


DIR_NAME_LINE_WEBHOOK_HANDLER = line_webhook_handler
FUNCTION_NAME_LINE_WEBHOOK_HANDLER = line-webhook-handler

deploy-line-webhook-handler:
	make build-shared-lib
	mkdir -p functions/${DIR_NAME_LINE_WEBHOOK_HANDLER}/dist
	cp $(SHARED_LIB_DIR)/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz \
		functions/${DIR_NAME_LINE_WEBHOOK_HANDLER}/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz
	gcloud functions deploy ${FUNCTION_NAME_LINE_WEBHOOK_HANDLER} \
		--region asia-east1 \
		--gen2 \
        --set-secrets '${SECRET_STRING_DSN_PASSWORD}' \
		--env-vars-file envs/${DIR_NAME_LINE_WEBHOOK_HANDLER}/.env.yaml \
		--runtime python310 \
		--trigger-http \
		--allow-unauthenticated \
		--entry-point main \
		--source functions/${DIR_NAME_LINE_WEBHOOK_HANDLER}/ \
    	--clear-cache