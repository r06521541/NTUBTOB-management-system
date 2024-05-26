deploy-notify-token-service-add:
	gcloud functions deploy notify_token_service_add \
		--env-vars-file envs/notify_token_service/.env.yaml \
		--runtime python310 \
		--trigger-http \
		--allow-unauthenticated \
		--entry-point add \
		--source functions/notify_token_service/

deploy-notify-token-service-get:
	gcloud functions deploy notify_token_service_get \
		--env-vars-file envs/notify_token_service/.env.yaml \
		--runtime python310 \
		--trigger-http \
		--allow-unauthenticated \
		--entry-point get \
		--source functions/notify_token_service/

deploy-weekly-game-notify:
	gcloud functions deploy weekly_game_notify \
		--env-vars-file envs/weekly_game_notify/.env.yaml \
		--runtime python310 \
		--trigger-http \
		--allow-unauthenticated \
		--entry-point main \
		--source functions/weekly_game_notify/