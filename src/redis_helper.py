"""
Redis connection helper for CaseStrainer
Handles both Docker and local development environments
"""

import os
import socket
from redis import Redis
from rq import Queue

def get_redis_url():
    """
    Get the appropriate Redis URL for the current environment.
    
    Returns:
        str: Redis URL appropriate for the current environment
    """
    # Check if REDIS_URL is explicitly set in environment
    redis_url = os.environ.get('REDIS_URL')
    if redis_url:
        return redis_url
    
    # Auto-detect environment
    try:
        # Try to resolve Docker hostname - if this works, we're inside Docker
        socket.gethostbyname('casestrainer-redis-prod')
        return 'redis://casestrainer-redis-prod:6379/0'  # Inside Docker
    except socket.gaierror:
        # Docker hostname doesn't resolve, we're running locally
        return 'redis://localhost:6380/0'  # Outside Docker, use mapped port

def get_redis_connection():
    """
    Get a Redis connection for the current environment.
    
    Returns:
        Redis: Redis connection object
    """
    redis_url = get_redis_url()
    return Redis.from_url(redis_url)

def get_rq_queue(queue_name='casestrainer'):
    """
    Get an RQ queue for the current environment.
    
    Args:
        queue_name (str): Name of the queue
        
    Returns:
        Queue: RQ Queue object
    """
    redis_conn = get_redis_connection()
    return Queue(queue_name, connection=redis_conn)
