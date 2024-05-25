deploy-notify-token-service-add:
	gcloud functions deploy notify_token_service_add \
		--env-vars-file functions/notify_token_service/.env.yaml \
		--runtime python310 \
		--trigger-http \
		--allow-unauthenticated \
		--entry-point notify_token_service_add \
		--source .

deploy-notify-token-service-get:
	gcloud functions deploy notify_token_service_get \
		--env-vars-file functions/notify_token_service/.env.yaml \
		--runtime python310 \
		--trigger-http \
		--allow-unauthenticated \
		--entry-point notify_token_service_get \
		--source .

deploy-weekly-game-notify:
	gcloud functions deploy weekly_game_notify \
		--env-vars-file functions/weekly_game_notify/.env.yaml \
		--runtime python310 \
		--trigger-http \
		--allow-unauthenticated \
		--entry-point weekly_game_notify \
		--source .