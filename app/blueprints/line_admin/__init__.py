from flask import Blueprint

bp = Blueprint("line_admin", __name__, url_prefix="/admin/line_accounts")

from . import routes