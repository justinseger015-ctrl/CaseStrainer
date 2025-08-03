#!/usr/bin/env python3
"""
Robust RQ Worker for CaseStrainer with memory management and auto-restart
This script starts an RQ worker with better error handling and resource management
"""

import os
import sys
import logging
import signal
import time
import psutil
from rq import Worker, Queue
from redis import Redis
from src.redis_distributed_processor import extract_pdf_pages, extract_pdf_optimized

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get Redis connection with authentication
redis_url = os.environ.get('REDIS_URL', 'redis://:caseStrainerRedis123@casestrainer-redis-prod:6379/0')
redis_conn = Redis.from_url(redis_url)

# Create queue
queue = Queue('casestrainer', connection=redis_conn)

# Register worker functions
def register_worker_functions():
    """Register all worker functions with RQ."""
    # These functions will be available to workers
    worker_functions = [
        'extract_pdf_pages',
        'extract_pdf_optimized',
        'process_citation_task_direct',
        'src.redis_distributed_processor.DockerOptimizedProcessor.process_document'
    ]
    
    logger.info(f"Registered worker functions: {worker_functions}")
    return worker_functions

def process_citation_task_direct(task_id: str, input_type: str, input_data: dict):
    """Direct wrapper function to create CitationService instance and call process_citation_task."""
    from src.api.services.citation_service import CitationService
    import asyncio
    
    service = CitationService()
    
    # Create event loop for async processing
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Process the task
        result = loop.run_until_complete(service.process_citation_task(task_id, input_type, input_data))
        logger.info(f"Task {task_id} completed successfully")
        return result
    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}")
        raise
    finally:
        loop.close()

class RobustWorker(Worker):
    """Enhanced RQ worker with memory management and graceful shutdown."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_memory_mb = 2048  # 2GB memory limit
        self.job_count = 0
        self.max_jobs = 100  # Restart after 100 jobs
        
    def perform_job(self, job, queue):
        """Override to add memory management and job counting."""
        try:
            # Check memory usage
            memory_usage = psutil.Process().memory_info().rss / 1024 / 1024  # MB
            if memory_usage > self.max_memory_mb:
                logger.warning(f"Memory usage high ({memory_usage:.1f}MB), restarting worker")
                sys.exit(0)  # Graceful shutdown
                return
            
            # Increment job count
            self.job_count += 1
            if self.job_count >= self.max_jobs:
                logger.info(f"Processed {self.job_count} jobs, restarting worker")
                sys.exit(0)  # Graceful shutdown
                return
            
            # Perform the job
            logger.info(f"Processing job {job.id} (job #{self.job_count})")
            result = super().perform_job(job, queue)
            
            # Log memory usage after job
            memory_after = psutil.Process().memory_info().rss / 1024 / 1024
            logger.info(f"Job {job.id} completed. Memory: {memory_after:.1f}MB")
            
            return result
            
        except Exception as e:
            logger.error(f"Job {job.id} failed: {e}")
            raise

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    sys.exit(0)

def main():
    import logging
    logging.basicConfig(level=logging.INFO)
    logging.info('[DEBUG] ENTERED rq_worker.py main() - worker is starting up')
    # Set up signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Register worker functions
    register_worker_functions()
    
    # Create worker
    worker = RobustWorker([queue], connection=redis_conn)
    
    logger.info("Starting RQ worker...")
    logger.info(f"Redis URL: {redis_url}")
    logger.info(f"Queue: casestrainer")
    logger.info(f"Worker ID: {worker.key}")
    
    try:
        # Start the worker
        worker.work(
            with_scheduler=True,
            max_jobs=100  # Restart after 100 jobs
        )
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error(f"Worker error: {e}")
        raise
    finally:
        logger.info("Worker shutdown complete")

if __name__ == '__main__':
    main() 