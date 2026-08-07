# LINE webhook handler

This public Cloud Functions endpoint remains protected by LINE's
`X-Line-Signature`. Both the Functions Framework entry point and the local
Flask route use the same ingress contract:

- missing, blank, or invalid signatures return HTTP 400 without dispatching an
  event or sending an alarm;
- a valid request dispatched successfully returns HTTP 200 with `OK`;
- unexpected dispatch failures remain server errors and are not converted to
  successful responses.

The LINE SDK continues to perform signature verification. No request body,
signature, or credential is included in an error response.

Run the offline ingress tests from the repository root:

```sh
python -m unittest discover -s functions/line_webhook_handler/tests -v
```

The tests use fake requests and dispatchers. They do not require `.env.yaml`,
credentials, a database, or network access.

Attendance postbacks persist the reply and build the LINE acknowledgement in
the same request. They do not call the Web Portal or any cache invalidation
endpoint. The Web Portal attendance page reads current database state on each
page request instead.

`PORTAL_DATA_PHASE_C_ENABLED=true` opts attendance postbacks into Person-based
principal resolution and transactional replies. Active `team_player` and
time-bounded `guest_player` qualifications are evaluated at game start; pending,
disabled, blocked, inactive, expired, and revoked principals fail closed. The
default remains `false`, and enabling it in production is outside TASK-070.
