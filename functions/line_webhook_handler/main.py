
import functions_framework

from ingress import handle_webhook_request
import webhook


@functions_framework.http
def main(request):
    return handle_webhook_request(request, webhook.handle_event)
