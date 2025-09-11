#!/usr/bin/env python3
"""
Test Redis connection to verify the verification process can work.
"""

import redis
import sys

def test_redis_connection():
    """Test Redis connection on different endpoints."""
    print("🧪 Testing Redis Connection")
    print("=" * 40)
    
    # Test localhost:6380 (host port) with authentication
    print("🔍 Testing localhost:6380 with authentication...")
    try:
        r = redis.Redis(host='localhost', port=6380, password='caseStrainerRedis123', decode_responses=True)
        r.ping()
        print("✅ Successfully connected to localhost:6380 with authentication")
        
        # Test basic Redis operations
        r.set('test_key', 'test_value')
        value = r.get('test_key')
        print(f"✅ Redis operations working: set/get test_key = {value}")
        
        return True
    except Exception as e:
        print(f"❌ Failed to connect to localhost:6380: {e}")
        return False

if __name__ == "__main__":
    success = test_redis_connection()
    if success:
        print("\n🎉 Redis connection successful! Verification should work.")
    else:
        print("\n💥 Redis connection failed. Verification will not work.")
