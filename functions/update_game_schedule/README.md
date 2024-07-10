# update-game-schedule
## Description
This Google Cloud Function is used to update the game schedule in the internal database by fetching game information from an crawler API and performing necessary updates. The function is designed to run as a cron job.


## Base URL
The base URL for the API request is:

`https://asia-east1-ntubtob-schedule-405614.cloudfunctions.net/update-game-schedule`

## Endpoint
`POST /`

Fetches game information from an external crawler API, compares it with the internal database, and updates the internal database accordingly.

### Parameters
This endpoint does not require any parameters in the request body.

### Response
This endpoint does not return any data.

### Example
Cron job triggers a POST request:

    POST /

### Functionality
1. Fetch the current datetime and calculate the end time as 30 days from it.
2. Retrieve the game schedule from the crawler API for the specified team and date range.
3. Retrieve the current game schedule from the internal database for the specified date range.
4. Identify games that need to be added and canceled in the internal database.
5. Add new games to the internal database.
6. Update the cancellation time for games that need to be canceled.
7. Notify success or failure.

## Errors
This function uses the following error notifications:

- `爬蟲撈不到比賽`: The crawler API failed to fetch the game schedule.
- `搜不到資料表中的比賽`: Failed to retrieve the current game schedule from the internal database.
- `賽程更新失敗 -- 爬蟲撈不到比賽`: Notification sent when the crawler fails to fetch games.
- `賽程更新失敗 -- 搜不到資料表中的比賽`: Notification sent when there is an issue retrieving games from the internal database.
- `賽程更新 -- 已成功將賽程更新到games資料表`: Notification sent when the schedule update is successful.


## Environment Variables
The function relies on several environment variables which need to be set:

* `game_crawl_api`: The URL of the game crawler API.
* `team_name`: The name of the team for which the schedule is generated.
* `notify_token_id`: The token ID used to authenticate with the LINE Notify API for sending game schedules.
* `notify_api`: The URL of the LINE Notify API.
* `notify_alarm_token_id`: The token ID used to authenticate with the LINE Notify API for sending error notifications.
* `DSN_DATABASE`: The name of the database.
* `DSN_HOSTNAME`: The hostname of the database.
* `DSN_PORT`: The port number on which the database is running.
* `DSN_UID`: The user ID for accessing the database.
* `DSN_PASSWORD`: The password of the above user for accessing the database. It is configured to be exposed from Secret Manager.

### Note
Ensure that the required environment variables are properly configured in your deployment environment for the function to work correctly.

## Usage
This endpoint is intended to be invoked by a scheduled task, such as a Google Cloud Scheduler, to automate the notification process without manual intervention.