#!/usr/bin/env python3
"""Kill the stuck job"""
import redis
from rq import Queue

r = redis.Redis(host='casestrainer-redis-prod', port=6379, password='caseStrainerRedis123', db=0)
q = Queue('casestrainer', connection=r)

job_id = 'client-1761011022112-kk5lt55qz'
job = q.fetch_job(job_id)

if job:
    print(f"🔪 Killing job: {job_id}")
    job.cancel()
    job.delete()
    print("✅ Job killed and deleted")
else:
    print(f"❌ Job {job_id} not found")
