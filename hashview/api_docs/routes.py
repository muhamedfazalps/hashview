"""Flask routes serving the interactive API documentation.

The OpenAPI spec lives next to this module (hashview/api_docs/openapi.yaml)
rather than in hashview/static/ because /static/ is publicly served — these
routes keep the API reference behind the web login. The spec is kept in sync
with the /v1 routes by tests/unit/test_openapi_spec.py.
"""
import os

from flask import Blueprint, current_app, render_template, send_from_directory
from flask_login import login_required

api_docs = Blueprint('api_docs', __name__)


@api_docs.route('/api/docs', methods=['GET'])
@login_required
def docs_page():
    """Swagger UI page for the Hashview REST API."""
    return render_template('api_docs.html.j2', title='API Docs')


@api_docs.route('/api/docs/openapi.yaml', methods=['GET'])
@login_required
def openapi_spec():
    """Serve the committed OpenAPI spec (404s automatically if absent)."""
    return send_from_directory(
        os.path.join(current_app.root_path, 'api_docs'),
        'openapi.yaml',
        mimetype='application/yaml',
    )
