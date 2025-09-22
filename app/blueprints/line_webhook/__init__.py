from flask import Blueprint

bp = Blueprint("line_webhook", __name__)

from . import routes
