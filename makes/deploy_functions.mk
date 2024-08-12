SHARED_LIB_VERSION = 0.0.1
SECRET_STRING_DSN_PASSWORD = DSN_PASSWORD=supabase-database-password:latest

deploy-notify-token-service-add:
	make build-shared-lib
	mkdir -p functions/notify_token_service/dist
	cp $(SHARED_LIB_DIR)/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz \
		functions/notify_token_service/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz
	gcloud functions deploy notify-token-service-add \
		--region asia-east1 \
		--gen2 \
		--env-vars-file envs/notify_token_service/.env.yaml \
		--runtime python310 \
		--trigger-http \
		--no-allow-unauthenticated \
		--entry-point add \
		--source functions/notify_token_service/

deploy-notify-token-service-get:
	make build-shared-lib
	mkdir -p functions/notify_token_service/dist
	cp $(SHARED_LIB_DIR)/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz \
		functions/notify_token_service/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz
	gcloud functions deploy notify-token-service-get \
		--region asia-east1 \
		--gen2 \
		--env-vars-file envs/notify_token_service/.env.yaml \
		--runtime python310 \
		--trigger-http \
		--no-allow-unauthenticated \
		--entry-point get \
		--source functions/notify_token_service/

deploy-weekly-game-notify:
	make build-shared-lib
	mkdir -p functions/weekly_game_notify/dist
	cp $(SHARED_LIB_DIR)/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz \
		functions/weekly_game_notify/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz
	gcloud functions deploy weekly-game-notify \
		--region asia-east1 \
		--gen2 \
		--env-vars-file envs/weekly_game_notify/.env.yaml \
		--runtime python310 \
		--trigger-http \
		--no-allow-unauthenticated \
		--entry-point main \
		--source functions/weekly_game_notify/
		
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
		--source functions/${DIR_NAME_UPDATE_GAME_SCHEDULE}/
