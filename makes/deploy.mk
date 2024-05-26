SHARED_LIB_VERSION = 0.0.1

deploy-notify-token-service-add:
	make build-shared-lib
	midir -p functions/notify_token_service/dist
	cp $(SHARED_LIB_DIR)/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz \
		functions/notify_token_service/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz
	gcloud functions deploy notify_token_service_add \
		--env-vars-file envs/notify_token_service/.env.yaml \
		--runtime python310 \
		--trigger-http \
		--allow-unauthenticated \
		--entry-point add \
		--source functions/notify_token_service/

deploy-notify-token-service-get:
	make build-shared-lib
	mkdir -p functions/notify_token_service/dist
	cp $(SHARED_LIB_DIR)/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz \
		functions/notify_token_service/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz
	gcloud functions deploy notify_token_service_get \
		--env-vars-file envs/notify_token_service/.env.yaml \
		--runtime python310 \
		--trigger-http \
		--allow-unauthenticated \
		--entry-point get \
		--source functions/notify_token_service/

deploy-weekly-game-notify:
	make build-shared-lib
	mkdir -p functions/weekly_game_notify/dist
	cp $(SHARED_LIB_DIR)/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz \
		functions/weekly_game_notify/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz
	gcloud functions deploy weekly_game_notify \
		--env-vars-file envs/weekly_game_notify/.env.yaml \
		--runtime python310 \
		--trigger-http \
		--allow-unauthenticated \
		--entry-point main \
		--source functions/weekly_game_notify/