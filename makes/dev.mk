.PHONY: format test-game-broadcast-service
format:
	isort .
	black .

test-game-broadcast-service:
	python3 -m unittest discover -s apps/game_broadcast_service/tests -v
