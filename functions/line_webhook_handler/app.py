from flask import Flask, request

from ingress import handle_webhook_request
import webhook


app = Flask(__name__)


@app.route("/", methods=["POST"])
def callback():
    return handle_webhook_request(request, webhook.handle_event)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
