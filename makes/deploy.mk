SHARED_LIB_VERSION = 0.0.1

deploy-notify-token-service-add:
	make build-and-install-shared-lib
	mkdir -p functions/notify_token_service/dist
	cp $(SHARED_LIB_DIR)/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz \
		functions/notify_token_service/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz
	gcloud functions deploy notify_token_service_add \
		--region asia-east1 \
		--gen2 \
		--env-vars-file envs/notify_token_service/.env.yaml \
		--runtime python310 \
		--trigger-http \
		--no-allow-unauthenticated \
		--entry-point add \
		--source functions/notify_token_service/

deploy-notify-token-service-get:
	make build-and-install-shared-lib
	mkdir -p functions/notify_token_service/dist
	cp $(SHARED_LIB_DIR)/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz \
		functions/notify_token_service/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz
	gcloud functions deploy notify_token_service_get \
		--region asia-east1 \
		--gen2 \
		--env-vars-file envs/notify_token_service/.env.yaml \
		--runtime python310 \
		--trigger-http \
		--no-allow-unauthenticated \
		--entry-point get \
		--source functions/notify_token_service/

deploy-weekly-game-notify:
	make build-and-install-shared-lib
	mkdir -p functions/weekly_game_notify/dist
	cp $(SHARED_LIB_DIR)/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz \
		functions/weekly_game_notify/dist/shared_lib-${SHARED_LIB_VERSION}.tar.gz
	gcloud functions deploy weekly_game_notify \
		--region asia-east1 \
		--gen2 \
		--env-vars-file envs/weekly_game_notify/.env.yaml \
		--runtime python310 \
		--trigger-http \
		--no-allow-unauthenticated \
		--entry-point main \
		--source functions/weekly_game_notify/