from flask import Blueprint

bp = Blueprint('quick_replies', __name__, url_prefix='/quick-replies')

from . import routes