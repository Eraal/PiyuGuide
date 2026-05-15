from flask import Blueprint


mobile_bp = Blueprint('mobile', __name__, url_prefix='/api/mobile')


from . import routes  # noqa: E402,F401