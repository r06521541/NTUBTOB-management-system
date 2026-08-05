# Notify Cronjob Service

Private Cloud Run service for scheduled team announcements and attendance
summaries.

## Health check

`GET /healthz` returns a process-level JSON health response. It does not query
the database or call LINE, Discord, the crawler, weather, or other external
services. The endpoint therefore confirms only that Flask is serving routes;
it does not prove that business dependencies are available.

The Cloud Run service remains private. Calling this endpoint after deployment
requires an identity token for an authorized identity. Do not use the existing
notification trigger routes as smoke tests.
