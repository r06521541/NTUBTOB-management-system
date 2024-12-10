# app/__init__.py
from flask import Flask

app = Flask(__name__)

# 這裡可以放入應用配置
app.config.from_object('config')

# 導入並註冊 Blueprints
from blueprints.users import users_bp
from blueprints.posts import posts_bp

app.register_blueprint(users_bp)
app.register_blueprint(posts_bp)
