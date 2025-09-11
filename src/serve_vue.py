from flask import send_from_directory
from src.config import DEFAULT_REQUEST_TIMEOUT, COURTLISTENER_TIMEOUT, CASEMINE_TIMEOUT, WEBSEARCH_TIMEOUT, SCRAPINGBEE_TIMEOUT

import os
import logging

logger = logging.getLogger(__name__)


def add_vue_routes(app):
    """
    Add routes to serve the Vue.js frontend from the Flask application.
    This ensures the Vue.js frontend is accessible through the same URL as the backend.
    """

    @app.route("/vue/<path:path>")
    @app.route("/casestrainer/vue/<path:path>")
    def serve_vue_static(path):
        vue_dist_dir = os.path.join(os.path.dirname(__file__), "static", "vue")
        return send_from_directory(vue_dist_dir, path)

    @app.route("/vue/")
    @app.route("/casestrainer/vue/")
    def serve_vue_index():
        vue_dist_dir = os.path.join(os.path.dirname(__file__), "static", "vue")
        return send_from_directory(vue_dist_dir, "index.html")

    @app.route("/vue")
    @app.route("/casestrainer/vue")
    def redirect_to_vue():
        return serve_vue_index()

    logger.info("Vue.js routes added to Flask application")

    return app
