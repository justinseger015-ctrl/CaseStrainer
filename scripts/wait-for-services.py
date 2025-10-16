"""
Wait for critical services to be ready before completing deployment
"""
import redis
import time
import sys
import os
from datetime import datetime

def wait_for_redis(max_wait=60):
    """Wait for Redis to be ready (not loading dataset)"""
    print("🔍 Waiting for Redis to be ready...")
    
    redis_url = os.environ.get('REDIS_URL', 'redis://:caseStrainerRedis123@casestrainer-redis-prod:6379/0')
    start_time = time.time()
    
    while (time.time() - start_time) < max_wait:
        try:
            r = redis.from_url(redis_url)
            r.ping()
            print("  ✅ Redis is ready")
            return True
        except redis.exceptions.BusyLoadingError:
            elapsed = int(time.time() - start_time)
            print(f"  ⏳ Redis loading dataset... ({elapsed}s)", end='\r')
            time.sleep(1)
        except redis.exceptions.ConnectionError:
            elapsed = int(time.time() - start_time)
            print(f"  ⏳ Waiting for Redis connection... ({elapsed}s)", end='\r')
            time.sleep(1)
        except Exception as e:
            print(f"  ⚠️  Redis check error: {e}")
            time.sleep(1)
    
    print(f"\n  ❌ Redis not ready after {max_wait}s")
    return False

def wait_for_rq_workers(max_wait=60):
    """Wait for at least one RQ worker to be processing"""
    print("🔍 Waiting for RQ workers to be ready...")
    
    redis_url = os.environ.get('REDIS_URL', 'redis://:caseStrainerRedis123@casestrainer-redis-prod:6379/0')
    start_time = time.time()
    
    while (time.time() - start_time) < max_wait:
        try:
            r = redis.from_url(redis_url)
            
            # Check if workers are registered
            from rq import Worker
            workers = Worker.all(connection=r)
            
            if workers:
                worker_names = [w.name for w in workers]
                print(f"  ✅ Found {len(workers)} RQ worker(s): {', '.join(worker_names[:3])}")
                return True
            else:
                elapsed = int(time.time() - start_time)
                print(f"  ⏳ Waiting for RQ workers... ({elapsed}s)", end='\r')
                time.sleep(2)
                
        except redis.exceptions.BusyLoadingError:
            # Redis still loading, wait
            time.sleep(1)
        except Exception as e:
            elapsed = int(time.time() - start_time)
            print(f"  ⏳ Workers not ready yet... ({elapsed}s)", end='\r')
            time.sleep(2)
    
    print(f"\n  ⚠️  No RQ workers found after {max_wait}s (workers may still be starting)")
    return False

def check_backend_health(max_wait=40):
    """Check if backend is responding"""
    print("🔍 Checking backend health...")
    
    import urllib.request
    import urllib.error
    start_time = time.time()
    
    # Test backend directly via Docker internal network
    # Backend serves on port 5000 inside Docker
    health_url = 'http://casestrainer-backend-prod:5000/casestrainer/api/health'
    
    while (time.time() - start_time) < max_wait:
        try:
            # Test backend directly
            request = urllib.request.Request(health_url)
            with urllib.request.urlopen(request, timeout=5) as response:
                if response.status == 200:
                    print("  ✅ Backend is healthy")
                    return True
                else:
                    elapsed = int(time.time() - start_time)
                    print(f"  ⏳ Backend not ready... ({elapsed}s)", end='\r')
                    time.sleep(2)
                
        except urllib.error.URLError as e:
            elapsed = int(time.time() - start_time)
            print(f"  ⏳ Backend not ready... ({elapsed}s)", end='\r')
            time.sleep(2)
        except Exception as e:
            elapsed = int(time.time() - start_time)
            print(f"  ⏳ Backend not ready... ({elapsed}s)", end='\r')
            time.sleep(2)
    
    print(f"\n  ⚠️  Backend health check timeout after {max_wait}s")
    return False

def check_courtlistener_rate_limit():
    """Check CourtListener API connectivity"""
    print("🔍 Checking CourtListener API...")
    
    import urllib.request
    import urllib.error
    from datetime import datetime
    
    try:
        # Get API key from environment
        api_key = os.environ.get('COURTLISTENER_API_KEY', '')
        if not api_key:
            print("  ⚠️  CourtListener API key not found")
            return
        
        # Make a simple API request to verify connectivity
        url = 'https://www.courtlistener.com/api/rest/v4/search/'
        request = urllib.request.Request(url)
        request.add_header('Authorization', f'Token {api_key}')
        
        with urllib.request.urlopen(request, timeout=5) as response:
            if response.status == 200:
                print(f"\n  📊 CourtListener API Status:")
                print(f"     ✅ API Key Valid")
                print(f"     ✅ Service Reachable")
                print(f"     ⓘ  Rate Limit: 100 requests/hour (free tier)")
                print(f"     ⓘ  Track usage manually if processing large batches")
            else:
                print(f"  ⚠️  Unexpected response: {response.status}")
                
    except urllib.error.HTTPError as e:
        if e.code == 429:
            # Try to get retry-after header
            retry_after = e.headers.get('Retry-After', 'unknown')
            print(f"\n  📊 CourtListener API Status:")
            print(f"     🚨 RATE LIMIT EXCEEDED")
            print(f"     ⏳ Retry after: {retry_after} seconds" if retry_after != 'unknown' else "     ⏳ Wait ~1 hour for reset")
            print(f"     ⓘ  Free tier: 100 requests/hour")
        elif e.code == 401 or e.code == 403:
            print(f"\n  📊 CourtListener API Status:")
            print(f"     ❌ Authentication Failed (HTTP {e.code})")
            print(f"     ⓘ  Check COURTLISTENER_API_KEY in .env")
        else:
            print(f"  ⚠️  API error: HTTP {e.code}")
    except urllib.error.URLError as e:
        print(f"  ⚠️  Cannot reach CourtListener: {e.reason}")
    except Exception as e:
        print(f"  ⚠️  API check failed: {e}")

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("WAITING FOR SERVICES TO BE READY")
    print("=" * 60 + "\n")
    
    all_ready = True
    
    # Check Redis first (most critical)
    if not wait_for_redis(max_wait=60):
        print("⚠️  Redis not ready - some features may not work")
        all_ready = False
    
    # Check backend health
    if not check_backend_health(max_wait=30):
        print("⚠️  Backend not responding - some features may not work")
        all_ready = False
    
    # Check RQ workers
    if not wait_for_rq_workers(max_wait=60):
        print("⚠️  RQ workers not ready - async processing may be delayed")
        all_ready = False
    
    # Check CourtListener API rate limit (informational, doesn't affect status)
    check_courtlistener_rate_limit()
    
    if all_ready:
        print("\n✅ ALL SERVICES READY")
        sys.exit(0)
    else:
        print("\n⚠️  Some services not fully ready")
        sys.exit(1)  # Exit 1 to indicate services not ready
