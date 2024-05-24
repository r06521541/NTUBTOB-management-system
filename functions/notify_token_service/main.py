import functions_framework
from flask import jsonify, abort
from shared.orm.line_notify_tokens import LineNotifyToken

response_400 = jsonify(
    {"status": "error", "message": f"Invalid JSON format or missing required fields"}
)


@functions_framework.http
def add(request):
    """
    Args:
        token: 不大於200字元的token字串
        description: 不大於200字元的敘述
    Returns:
        成功，回傳200與成功訊息
        不合法的HTTP method，回傳405
        操作失敗，回傳500
    """
    if not (request.method == "POST"):
        return abort(405)

    try:
        # 解析 POST 請求中的資訊
        request_json = request.get_json(silent=True)
        if not LineNotifyToken.is_add_json_valid(request_json):
            return response_400, 400

        # 寫入資訊到資料庫
        LineNotifyToken().insert(request_json)
        return jsonify({"status": "success", "message": "Token added successfully"})

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"status": "error", "message": f"Failed to add token: {e}"}), 500


@functions_framework.http
def get(request):
    """
    Args:
        token_id
    Returns:
        成功，回傳200與token
        不合法的HTTP method，回傳405
        操作失敗，回傳500
    """
    if not (request.method == "POST"):
        return abort(405)

    try:
        # 解析 POST 請求
        request_json = request.get_json(silent=True)
        if not LineNotifyToken.is_get_json_valid(request_json):
            return response_400, 400

        # 讀取token，輸出
        token = LineNotifyToken().get_token_by_id(request_json)

        return jsonify({"status": "success", "token": token})

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"status": "error", "message": f"Failed to get token: {e}"}), 500
