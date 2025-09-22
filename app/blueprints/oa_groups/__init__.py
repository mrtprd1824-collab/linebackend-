from flask import Blueprint

bp = Blueprint('oa_groups', __name__, url_prefix='/oa-groups')

from . import routes