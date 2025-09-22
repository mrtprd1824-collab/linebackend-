from flask import Blueprint

bp = Blueprint("chats", __name__, url_prefix="/chats")

from . import routes