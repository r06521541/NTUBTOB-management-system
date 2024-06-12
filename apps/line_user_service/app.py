from flask import Flask, request, jsonify, abort
from shared_module.line_users import LineUser

app = Flask(__name__)

with app.app_context():
    response_400 = jsonify({'status': 'error', 'message': f'Invalid JSON format or missing required fields'})

@app.route('/add_user', methods=['POST'])
def add_user():
    try:
        request_json = request.get_json(silent=True)
        if (not LineUser.is_add_json_valid(request_json)):
            return response_400, 400
        
        LineUser().insert(request_json)
        return jsonify({'status': 'success', 'message': 'New LINE user added successfully'})

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'status': 'error', 'message': f'Failed to add New LINE user: {e}'}), 500

@app.route('/search_user_by_id', methods=['POST'])
def search_user():
    try:
        line_user_id = request.get_json(silent=True)
        user = LineUser().get_user_by_id(str(line_user_id))
        print(user)
        return jsonify({'status': 'success', 'user': user})

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'status': 'error', 'message': f'Failed to search user: {e}'}), 500
    
@app.route('/update_member_id', methods=['POST'])
def update_member():
    try:
        # 解析 POST 請求中的比賽資訊
        request_json = request.get_json(silent=True)

        # 寫入比賽資訊到資料庫
        LineUser().update_member_id(request_json['line_user_id'], request_json['new_member_id'])
        return jsonify({'status': 'success', 'message': 'Update member ID successfully'})

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'status': 'error', 'message': f'Failed to update member ID: {e}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
