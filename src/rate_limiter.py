#!/usr/bin/env python3
"""
Rate Limiter for CaseStrainer API endpoints
Provides protection against abuse and DoS attacks
"""

import time
import threading
from collections import defaultdict
from functools import wraps
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """Thread-safe rate limiter for API endpoints"""
    
    def __init__(self):
        self.calls: Dict[str, List[float]] = defaultdict(list)
        self.lock = threading.RLock()
        self._cleanup_interval = 3600  # Clean up old entries every hour
        self._last_cleanup = time.time()
    
    def limit(self, max_calls: int = 100, window: int = 3600, key_func=None):
        """
        Rate limiting decorator
        
        Args:
            max_calls: Maximum number of calls allowed in the window
            window: Time window in seconds
            key_func: Function to extract rate limit key (defaults to IP address)
        """
        def decorator(f):
            @wraps(f)
            def wrapper(*args, **kwargs):
                # Get rate limit key
                if key_func:
                    key = key_func(*args, **kwargs)
                else:
                    # Default to IP address
                    from flask import request
                    key = request.remote_addr or 'unknown'
                
                # Check rate limit
                if not self._check_rate_limit(key, max_calls, window):
                    from flask import jsonify
                    logger.warning(f"Rate limit exceeded for {key}: {max_calls} calls in {window}s")
                    return jsonify({
                        'error': 'Rate limit exceeded',
                        'message': f'Maximum {max_calls} requests per {window} seconds',
                        'retry_after': window
                    }), 429
                
                return f(*args, **kwargs)
            return wrapper
        return decorator
    
    def _check_rate_limit(self, key: str, max_calls: int, window: int) -> bool:
        """Check if the key is within rate limits"""
        with self.lock:
            now = time.time()
            
            # Clean up old entries periodically
            if now - self._last_cleanup > self._cleanup_interval:
                self._cleanup_old_entries()
                self._last_cleanup = now
            
            # Get calls for this key
            calls = self.calls[key]
            
            # Remove calls outside the window
            calls[:] = [call_time for call_time in calls if now - call_time < window]
            
            # Check if limit exceeded
            if len(calls) >= max_calls:
                return False
            
            # Add current call
            calls.append(now)
            return True
    
    def _cleanup_old_entries(self):
        """Remove old rate limit entries to prevent memory leaks"""
        now = time.time()
        old_keys = []
        
        for key, calls in self.calls.items():
            # Remove calls older than 24 hours
            calls[:] = [call_time for call_time in calls if now - call_time < 86400]
            
            # Remove empty keys
            if not calls:
                old_keys.append(key)
        
        for key in old_keys:
            del self.calls[key]
        
        logger.debug(f"Rate limiter cleanup: removed {len(old_keys)} empty keys")


class AdvancedRateLimiter:
    """Enhanced rate limiter with IP blocking and advanced features"""
    
    def __init__(self):
        self.calls: Dict[str, List[float]] = defaultdict(list)
        self.blocked_ips: set = set()
        self.lock = threading.RLock()
        self._cleanup_interval = 3600  # Clean up old entries every hour
        self._last_cleanup = time.time()
        self._block_duration = 3600  # Block IPs for 1 hour after violation
    
    def is_allowed(self, ip: str, limit: int = 100, window: int = 3600) -> bool:
        """Check if IP is allowed to make requests"""
        now = time.time()
        
        # Check if IP is blocked
        if ip in self.blocked_ips:
            logger.warning(f"Blocked IP {ip} attempted access")
            return False
        
        with self.lock:
            # Clean up old entries periodically
            if now - self._last_cleanup > self._cleanup_interval:
                self._cleanup_old_entries()
                self._last_cleanup = now
            
            # Get calls for this IP
            calls = self.calls[ip]
            
            # Remove calls outside the window
            calls[:] = [call_time for call_time in calls if now - call_time < window]
            
            # Check if limit exceeded
            if len(calls) >= limit:
                self.blocked_ips.add(ip)
                logger.warning(f"IP {ip} blocked for rate limit violation")
                return False
            
            # Add current call
            calls.append(now)
            return True
    
    def unblock_ip(self, ip: str):
        """Unblock an IP address"""
        with self.lock:
            self.blocked_ips.discard(ip)
            logger.info(f"IP {ip} unblocked")
    
    def get_blocked_ips(self) -> set:
        """Get list of currently blocked IPs"""
        with self.lock:
            return self.blocked_ips.copy()
    
    def _cleanup_old_entries(self):
        """Remove old rate limit entries to prevent memory leaks"""
        now = time.time()
        old_keys = []
        
        for key, calls in self.calls.items():
            # Remove calls older than 24 hours
            calls[:] = [call_time for call_time in calls if now - call_time < 86400]
            
            # Remove empty keys
            if not calls:
                old_keys.append(key)
        
        for key in old_keys:
            del self.calls[key]
        
        logger.debug(f"Rate limiter cleanup: removed {len(old_keys)} empty keys")


class InputValidator:
    """Input validation utilities"""
    
    @staticmethod
    def validate_citation_input(citation: str) -> bool:
        """Validate citation input for security"""
        if not citation or len(citation) > 1000:
            return False
        
        # Check for suspicious patterns
        import re
        suspicious_patterns = [
            r'<script[^>]*>',
            r'javascript:',
            r'data:',
            r'vbscript:',
            r'<iframe[^>]*>',
            r'on\w+\s*=',
        ]
        
        for pattern in suspicious_patterns:
            if re.search(pattern, citation, re.IGNORECASE):
                logger.warning(f"Suspicious pattern detected in citation: {pattern}")
                return False
        
        return True
    
    @staticmethod
    def validate_text_input(text: str, max_length: int = 1000000) -> bool:
        """Validate text input"""
        if not text or len(text) > max_length:
            return False
        
        # Check for null bytes and other problematic characters
        if '\x00' in text:
            return False
        
        return True
    
    @staticmethod
    def validate_url_input(url: str) -> bool:
        """Validate URL input"""
        if not url or len(url) > 2000:
            return False
        
        # Basic URL validation
        import re
        url_pattern = r'^https?://[^\s/$.?#].[^\s]*$'
        if not re.match(url_pattern, url):
            return False
        
        # Check for suspicious patterns
        suspicious_patterns = [
            r'javascript:',
            r'data:',
            r'vbscript:',
            r'file://',
        ]
        
        for pattern in suspicious_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                logger.warning(f"Suspicious URL pattern detected: {pattern}")
                return False
        
        return True


# Global instances
rate_limiter = RateLimiter()
advanced_rate_limiter = AdvancedRateLimiter()

# Convenience decorators
def rate_limit(max_calls: int = 100, window: int = 3600):
    """Convenience decorator for rate limiting"""
    return rate_limiter.limit(max_calls, window)

def validate_input(input_type: str = 'citation'):
    """Convenience decorator for input validation"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            from flask import request, jsonify
            
            # Get input data
            if request.is_json:
                data = request.get_json()
                if input_type == 'citation':
                    citation = data.get('citation', '')
                    if not InputValidator.validate_citation_input(citation):
                        return jsonify({'error': 'Invalid citation input'}), 400
                elif input_type == 'text':
                    text = data.get('text', '')
                    if not InputValidator.validate_text_input(text):
                        return jsonify({'error': 'Invalid text input'}), 400
                elif input_type == 'url':
                    url = data.get('url', '')
                    if not InputValidator.validate_url_input(url):
                        return jsonify({'error': 'Invalid URL input'}), 400
            
            return f(*args, **kwargs)
        return wrapper
    return decorator 