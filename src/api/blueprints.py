"""
Blueprint registration for the CaseStrainer API
"""
import os
from src.config import DEFAULT_REQUEST_TIMEOUT, COURTLISTENER_TIMEOUT, CASEMINE_TIMEOUT, WEBSEARCH_TIMEOUT, SCRAPINGBEE_TIMEOUT

import sys
import logging
from flask import Blueprint

logger = logging.getLogger(__name__)

def register_blueprints(app):
    """Register all blueprints with the Flask application"""
    logger.info("=== REGISTERING BLUEPRINTS ===")
    logger.info(f"Current working directory: {os.getcwd()}")
    logger.info(f"Python path: {sys.path}")
    
    try:
        logger.info("Attempting to import Vue API blueprint...")
        try:
            # UPDATED: Using vue_api_endpoints_updated.py (has all production routes + syntax fixes)
            from src.vue_api_endpoints_updated import vue_api as vue_api_blueprint
            logger.info("✅ Successfully imported Vue API blueprint from UPDATED endpoints (production version)")
        except ImportError as e1:
            logger.warning(f"Updated endpoints import failed: {e1}, trying legacy fallback...")
            try:
                # Fallback to old endpoints (basic version)
                from src.vue_api_endpoints import vue_api as vue_api_blueprint
                logger.warning("⚠️  Using legacy vue_api_endpoints.py (fallback)")
            except ImportError as e2:
                logger.error(f"All import attempts failed: {e1} / {e2}")
                logger.error(f"Python path: {sys.path}")
                logger.error(f"Current directory contents: {os.listdir(os.path.dirname(__file__))}")
                raise ImportError(f"Could not import Vue API blueprint: {e1} / {e2}")
        
        logger.info(f"Blueprint details: {vue_api_blueprint}")
        logger.info(f"- Name: {vue_api_blueprint.name}")
        logger.info(f"- Import Name: {vue_api_blueprint.import_name}")
        
        logger.info("Registering Vue API blueprint...")
        if 'vue_api' not in app.blueprints:
            app.register_blueprint(
                vue_api_blueprint,
                url_prefix='/casestrainer/api'
            )
            logger.info("✅ Vue API blueprint registered successfully")
        else:
            logger.info("vue_api blueprint already registered, skipping")
        
        logger.info("\n=== CURRENTLY REGISTERED BLUEPRINTS ===")
        for name, bp in app.blueprints.items():
            logger.info(f"- {name}: {bp}")
            logger.info(f"  - URL Prefix: {getattr(bp, 'url_prefix', 'N/A')}")
            logger.info(f"  - Import Name: {getattr(bp, 'import_name', 'N/A')}")
        
        return app
        
    except Exception as e:
        logger.error(f"❌ Error registering blueprints: {e}", exc_info=True)
        raise
