# notify-token-service
## Description
These API provides endpoints to interact with the `line-notify-tokens` database, allowing you to add new tokens and retrieve existing tokens by their IDs.

## Endpoint 1 - add
URL: `https://asia-east2-ntubtob-schedule-405614.cloudfunctions.net/notify-token-service-add`

`POST /`

Adds a new token to the `line-notify-tokens` database.

## Parameters
* `token` (required): A string token not exceeding 200 characters.
* `description` (required): A string description not exceeding 200 characters.
## Response
Returns a JSON object with the following properties:

* `status`: The status of the request (e.g., "success").
* `message`: A message describing the outcome of the request.
## Example
Request:

    POST /add
    Content-Type: application/json

    {
        "token": "sample_token",
        "description": "This is a sample token"
    }
Response:

    {
        "status": "success",
        "message": "Token added successfully"
    }
## Errors
* 400 Bad Request: The request was malformed or missing required parameters.
* 405 Method Not Allowed: The HTTP method used was not POST.
* 500 Internal Server Error: An unexpected error occurred on the server.


## Endpoint 2 - get
URL: `https://asia-east2-ntubtob-schedule-405614.cloudfunctions.net/notify-token-service-get`

`POST /`

Retrieves a token from the `line-notify-tokens` database by its ID.

## Parameters
* token_id (required): The ID of the token to retrieve.
## Response
Returns a JSON object with the following properties:

* status: The status of the request (e.g., "success").
* token: The token object if found.
## Example
Request:

    POST /get
    Content-Type: application/json

    {
        "token_id": "12345"
    }
Response:

    {
        "status": "success",
        "token": "sample_token"
    }
## Errors
* 400 Bad Request: The request was malformed or missing required parameters.
* 405 Method Not Allowed: The HTTP method used was not POST.
* 500 Internal Server Error: An unexpected error occurred on the server.


