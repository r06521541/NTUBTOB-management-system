.PHONY: format quality test-game-broadcast-service
format:
	python3 -m tools.repository_quality format --all

quality:
	python3 -m tools.repository_quality check --all

test-game-broadcast-service:
	python3 -m unittest discover -s apps/game_broadcast_service/tests -v
