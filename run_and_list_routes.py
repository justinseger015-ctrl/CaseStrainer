from flask import Flask
import os
import sys
import time
import requests
import logging
from threading import Thread

# Setup logging
logger = logging.getLogger(__name__)

# Add the src directory to the Python path
src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

def run_flask_app():
    """Run the Flask application in a separate thread."""
    from app_final_vue import create_app
    app = create_app()
    app.run(port=5000, debug=False, use_reloader=False)

def list_routes():
    """List all routes from the running Flask application."""
    try:
        # Give the Flask app a moment to start
        time.sleep(2)
        
        # Get the routes from the running app
        response = requests.get('http://localhost:5000/routes')
        if response.status_code == 200:
            logger.info("\n" + "="*80)
            logger.info("AVAILABLE ROUTES:")
            logger.info("="*80)
            logger.info(response.text)
            logger.info("="*80)
        else:
            logger.error(f"Failed to get routes. Status code: {response.status_code}")
            logger.error(response.text)
    except Exception as e:
        logger.error(f"Error: {str(e)}")
    finally:
        # Stop the Flask app
        try:
            requests.get('http://localhost:5000/shutdown')
        except:
            pass

if __name__ == "__main__":
    # Start Flask in a separate thread
    flask_thread = Thread(target=run_flask_app)
    flask_thread.daemon = True
    flask_thread.start()
    
    # List routes
    list_routes()
