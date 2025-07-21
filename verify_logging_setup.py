#!/usr/bin/env python3
"""
Script to verify that the JSON response logging is properly set up.
"""

# DEPRECATED: This file has been consolidated into src/test_utilities_consolidated.py
# Please use: from src.test_utilities_consolidated import verify_vue_api_logging, verify_citation_api_logging, etc.
import warnings
warnings.warn(
    "verify_logging_setup.py is deprecated. Use test_utilities_consolidated.py instead.",
    DeprecationWarning,
    stacklevel=2
)

import asyncio
import aiohttp
import logging
from typing import Dict, Any

import os
import sys

# Add the project root to the Python path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

def verify_vue_api_logging():
    """Verify that the vue_api blueprint has the after_request handler registered."""
    try:
        from src.vue_api_endpoints import vue_api
        
        print("Checking vue_api blueprint...")
        print(f"Blueprint name: {vue_api.name}")
        print(f"Blueprint url_prefix: {vue_api.url_prefix}")
        
        # Check if after_request handlers are registered
        # Flask blueprints store after_request handlers in a different way
        after_request_handlers = getattr(vue_api, 'after_request_funcs', {})
        print(f"After request handlers: {len(after_request_handlers)}")
        
        for blueprint_name, handlers in after_request_handlers.items():
            print(f"  - {blueprint_name}: {len(handlers)} handlers")
            for handler in handlers:
                print(f"    - {handler.__name__}")
        
        return len(after_request_handlers) > 0
        
    except Exception as e:
        print(f"Error checking vue_api: {e}")
        return False

def verify_citation_api_logging():
    """Verify that the citation_api blueprint has the after_request handler registered."""
    try:
        from src.citation_api import citation_api
        
        print("\nChecking citation_api blueprint...")
        print(f"Blueprint name: {citation_api.name}")
        print(f"Blueprint url_prefix: {citation_api.url_prefix}")
        
        # Check if after_request handlers are registered
        after_request_handlers = getattr(citation_api, 'after_request_funcs', {})
        print(f"After request handlers: {len(after_request_handlers)}")
        
        for blueprint_name, handlers in after_request_handlers.items():
            print(f"  - {blueprint_name}: {len(handlers)} handlers")
            for handler in handlers:
                print(f"    - {handler.__name__}")
        
        return len(after_request_handlers) > 0
        
    except Exception as e:
        print(f"Error checking citation_api: {e}")
        return False

def verify_app_routes_logging():
    """Verify that the app routes blueprints have the after_request handler registered."""
    print("\nChecking app routes blueprints...")
    print("DEPRECATED: app/routes.py has been removed. All routes are now in src/vue_api_endpoints.py")
    print("✓ No longer checking deprecated app routes")
    return True

def check_logging_function_exists():
    """Check if the log_json_responses function exists in the modules."""
    try:
        from src.vue_api_endpoints import log_json_responses
        print("✓ log_json_responses function found in vue_api_endpoints")
        return True
    except ImportError:
        print("✗ log_json_responses function not found in vue_api_endpoints")
        return False

def main():
    """Main verification function."""
    print("Verifying JSON Response Logging Setup")
    print("=" * 50)
    
    # First check if the function exists
    function_exists = check_logging_function_exists()
    
    vue_ok = verify_vue_api_logging()
    citation_ok = verify_citation_api_logging()
    app_routes_ok = verify_app_routes_logging()
    
    print("\n" + "=" * 50)
    print("Verification Results:")
    print(f"Function exists: {'✓' if function_exists else '✗'}")
    print(f"vue_api logging: {'✓' if vue_ok else '✗'}")
    print(f"citation_api logging: {'✓' if citation_ok else '✗'}")
    print(f"app_routes logging: {'✓' if app_routes_ok else '✗'}")
    
    if function_exists and vue_ok and citation_ok and app_routes_ok:
        print("\n✓ All blueprints have JSON response logging configured!")
        print("\nNote: The application needs to be restarted for changes to take effect.")
        print("After restarting, you should see log entries starting with:")
        print("'JSON RESPONSE BEING SENT TO FRONTEND'")
    else:
        print("\n✗ Some components are missing JSON response logging.")
        print("Please check the implementation and restart the application.")

if __name__ == "__main__":
    main() 