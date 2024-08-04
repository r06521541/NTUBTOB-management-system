from flask import Flask, request, jsonify, abort
from shared_module.models.line_users import LineUser

app = Flask(__name__)

@app.errorhandler(400)
def bad_request(error):
    return jsonify({'status': 'error', 'message': 'Invalid JSON format or missing required fields'}), 400

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'status': 'error', 'message': f'Internal server error: {error}'}), 500

@app.route('/add_user', methods=['POST'])
def add_user():
    try:
        request_json = request.get_json(silent=True)
        if (not LineUser.is_add_json_valid(request_json)):
            abort(400)
        
        user = LineUser.search_by_id(str(request_json['line_user_id']))
        if user:
            return jsonify({'status': 'success', 'message': 'LINE user of the same ID already exists'})
        else:
            LineUser.add(LineUser.from_dict(request_json))
            return jsonify({'status': 'success', 'message': 'New LINE user added successfully'})

    except Exception as e:
        print(f"Failed to add New LINE user. Error: {e}")
        abort(500, description=str(e))
       
@app.route('/search_user_by_id', methods=['POST'])
def search_user():
    try:
        line_user_id = request.get_json(silent=True)
        user = LineUser.search_by_id(str(line_user_id))
        if user:
            return jsonify({'status': 'success', 'user': user.as_dict()})
        else:
            return jsonify({'status': 'success', 'user': None})


    except Exception as e:
        print(f"Failed to search user. Error: {e}")
        abort(500, description=str(e))
    
@app.route('/update_member_id', methods=['POST'])
def update_member():
    try:
        # 解析 POST 請求中的比賽資訊
        request_json = request.get_json(silent=True)

        # 寫入比賽資訊到資料庫
        LineUser.update_member_id(request_json['line_user_id'], request_json['new_member_id'])
        return jsonify({'status': 'success', 'message': 'Update member ID successfully'})

    except Exception as e:
        print(f"Failed to update member ID. Error: {e}")
        abort(500, description=str(e))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
