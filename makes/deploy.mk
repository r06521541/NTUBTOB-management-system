deploy-notify-token-service:
	gcloud functions deploy notify_token_service_add \
		--env-vars-file functions/notify_token_service/.env.yaml \
		--runtime python310 \
		--trigger-http \
		--allow-unauthenticated \
		--entry-point notify_token_service_add \
		--source .
