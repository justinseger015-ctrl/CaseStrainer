#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Run CaseStrainer in production mode with proper configuration.
This script combines the functionality of run_vue_production.py and deployment/run_production.py.
"""

import os
import sys
import logging
import argparse
import socket
import traceback
from datetime import datetime
from waitress import serve
from werkzeug.middleware.proxy_fix import ProxyFix

# Add the current directory to Python path to help with imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging first
def setup_logging():
    # Ensure logs directory exists
    os.makedirs('logs', exist_ok=True)
    
    # Configure logging
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join('logs', f'casestrainer_{timestamp}.log')
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

# Initialize logger
logger = setup_logging()

# Import DispatcherMiddleware with fallback for different Werkzeug versions
try:
    from werkzeug.middleware.dispatcher import DispatcherMiddleware
    logger.info("Using DispatcherMiddleware from werkzeug.middleware.dispatcher")
except ImportError:
    try:
        from werkzeug.wsgi import DispatcherMiddleware
        logger.info("Using DispatcherMiddleware from werkzeug.wsgi (legacy)")
    except ImportError as e:
        logger.error(f"Failed to import DispatcherMiddleware: {e}")
        sys.exit(1)

from werkzeug.exceptions import NotFound
from src.app_final_vue import create_app

def get_server_info():
    """Get server information for logging."""
    try:
        hostname = socket.gethostname()
        ip_address = socket.gethostbyname(hostname)
        return {
            'hostname': hostname,
            'ip_address': ip_address
        }
    except Exception as e:
        logger.error(f"Error getting server info: {e}")
        return {
            'hostname': 'unknown',
            'ip_address': 'unknown'
        }

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Run CaseStrainer in production mode')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=5000, help='Port to bind to')
    parser.add_argument('--debug', action='store_true', help='Run in debug mode')
    parser.add_argument('--threads', type=int, default=10, help='Number of threads for the server')
    parser.add_argument('--env', choices=['development', 'production'], default='production', help='Environment to run in')
    parser.add_argument('--url-prefix', help='URL prefix for the application')
    args = parser.parse_args()

    # Set environment variables
    os.environ['FLASK_ENV'] = args.env
    if args.url_prefix:
        os.environ['APPLICATION_ROOT'] = args.url_prefix

    try:
        # Create the Flask app
        logger.info("Creating Flask application...")
        app = create_app()
        
        # Configure for reverse proxy
        app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1, x_prefix=1)
        
        # Set the application root if URL prefix is specified
        if args.url_prefix:
            app.config['APPLICATION_ROOT'] = args.url_prefix
        
        # Verify it's a Flask app
        from flask import Flask
        if not isinstance(app, Flask):
            logger.error(f"create_app() returned {type(app)}, not a Flask instance")
            sys.exit(1)
        
        logger.info("Flask application created successfully")

        # Get server information
        server_info = get_server_info()
        
        # Log startup information
        logger.info("=" * 50)
        logger.info("Starting CaseStrainer in production mode")
        logger.info(f"Server: {server_info['hostname']} ({server_info['ip_address']})")
        logger.info(f"Host: {args.host}")
        logger.info(f"Port: {args.port}")
        logger.info(f"Threads: {args.threads}")
        logger.info(f"Environment: {args.env}")
        if args.url_prefix:
            logger.info(f"URL Prefix: {args.url_prefix}")
        logger.info("=" * 50)

        # Apply URL prefix middleware if specified
        if args.url_prefix:
            logger.info(f"Applying URL prefix middleware: {args.url_prefix}")
            
            # Create a simple WSGI app for handling 404 responses
            def not_found(environ, start_response):
                start_response('404 Not Found', [('Content-Type', 'text/plain')])
                return [b'Not Found']
            
            # Create dispatcher middleware with proper URL prefix handling
            application = DispatcherMiddleware(
                not_found,  # Default app for non-matching paths
                {
                    args.url_prefix.rstrip('/'): app  # Remove trailing slash to avoid double slashes
                }
            )
            
            logger.info("Dispatcher middleware created successfully")
            
            # Serve the wrapped application
            logger.info(f"Starting Waitress server with DispatcherMiddleware on http://{args.host}:{args.port}{args.url_prefix}")
            serve(application, host=args.host, port=args.port, threads=args.threads)
        else:
            # Serve Flask app directly without middleware
            logger.info(f"Starting Waitress server on http://{args.host}:{args.port}")
            serve(app, host=args.host, port=args.port, threads=args.threads)

    except Exception as e:
        logger.error(f"Error starting server: {e}")
        logger.error(f"Error details: {traceback.format_exc()}")
        sys.exit(1)

if __name__ == '__main__':
    print("Starting CaseStrainer in production mode...")
    
    # Check if Waitress is installed
    try:
        import waitress
        print("Waitress is already installed.")
    except ImportError:
        print("Installing Waitress...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "waitress"])
        print("Waitress installed successfully.")
    
    main()