
import os

from flask import Blueprint

from restapis.versions.v1 import apply_namespaces as apply_namespaces_v1

def register_rest_blueprints(app, prefix):

    bp = Blueprint(prefix, __name__, url_prefix="/%s" % prefix)

    apply_namespaces_v1(bp)

    app.register_blueprint(bp)

    return