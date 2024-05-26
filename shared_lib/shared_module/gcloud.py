import google.auth.transport.requests
import google.oauth2.id_token

auth_req = google.auth.transport.requests.Request()


def get_id_token(target_audience):
    return google.oauth2.id_token.fetch_id_token(auth_req, target_audience)
