# weekly_game_notify
## Description
This API endpoint is designed to be triggered by a cron job. It fetches game information using a crawler API, processes the data, and sends notifications to a LINE group using the LINE Notify service.

## Base URL
The base URL for the API request is:

`https://asia-east1-ntubtob-schedule-405614.cloudfunctions.net/weekly-game-notify`

## Endpoint
`POST /`

Fetches game information, processes it, and sends a notification to a LINE group.

### Parameters
This endpoint does not accept any parameters in the request body.

### Response
This endpoint does not return any data.

### Example
Cron job triggers a POST request:

    POST /

### Functionality
1. Fetches game information from the crawler API.
2. Processes the game data and generates a message.
3. Sends the message to a LINE group using the LINE Notify service.
4. In case of an error, sends an error notification to a different LINE group.

## Errors
This API uses the following error codes:

* `500 Internal Server Error`: An unexpected error occurred during the execution of the function.

## Environment Variables
The function relies on several environment variables which need to be set:

* `game_crawl_api`: The URL of the game crawler API.
* `team_name`: The name of the team for which the schedule is generated.
* `notify_token_id`: The token ID used to authenticate with the LINE Notify API for sending game schedules.
* `notify_api`: The URL of the LINE Notify API.
* `notify_alarm_token_id`: The token ID used to authenticate with the LINE Notify API for sending error notifications.
### Note
Ensure that the required environment variables are properly configured in your deployment environment for the function to work correctly.

## Usage
This endpoint is intended to be invoked by a scheduled task, such as a Google Cloud Scheduler, to automate the notification process without manual intervention.