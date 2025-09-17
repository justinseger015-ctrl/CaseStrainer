"""
Robust RQ Worker for CaseStrainer with memory management and auto-restart
This script starts an RQ worker with better error handling and resource management
"""

import os
from src.config import DEFAULT_REQUEST_TIMEOUT, COURTLISTENER_TIMEOUT, CASEMINE_TIMEOUT, WEBSEARCH_TIMEOUT, SCRAPINGBEE_TIMEOUT

import sys
import logging
import signal
import time

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logging.warning("psutil not available - memory monitoring disabled")

from rq import Worker, Queue
from redis import Redis
from src.redis_distributed_processor import extract_pdf_pages, extract_pdf_optimized
from src.optimized_pdf_processor import extract_pdf_optimized_v2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

redis_url = os.environ.get('REDIS_URL', 'redis://:caseStrainerRedis123@casestrainer-redis-prod:6379/0')
redis_conn = Redis.from_url(redis_url)

queue = Queue('casestrainer', connection=redis_conn)

def register_worker_functions():
    """Register all worker functions with RQ."""
    worker_functions = [
        'extract_pdf_pages',
        'extract_pdf_optimized',
        'extract_pdf_optimized_v2',
        'process_citation_task_direct',
        'src.redis_distributed_processor.DockerOptimizedProcessor.process_document',
        'src.async_verification_worker.verify_citations_enhanced',
        'src.async_verification_worker.verify_citations_basic',
        'src.async_verification_worker.verify_citations_async'
    ]
    
    logger.info(f"Registered worker functions: {worker_functions}")
    return worker_functions

__all__ = [
    'process_citation_task_direct', 
    'extract_pdf_pages', 
    'extract_pdf_optimized', 
    'extract_pdf_optimized_v2',
    'verify_citations_enhanced'
]

def process_citation_task_direct(task_id: str, input_type: str, input_data: dict):
    """Direct wrapper function to create CitationService instance and call process_citation_task."""
    import traceback
    from src.api.services.citation_service import CitationService
    import asyncio
    import time
    import json
    import os
    
    # Log detailed environment information
    logger.info(f"[TASK:{task_id}] Starting task processing")
    logger.info(f"[TASK:{task_id}] Environment: Python {platform.python_version()}, PID: {os.getpid()}")
    logger.info(f"[TASK:{task_id}] Input type: {input_type}, Input data keys: {list(input_data.keys())}")
    
    # Log Redis connection info
    try:
        redis_url = os.environ.get('REDIS_URL', 'redis://:caseStrainerRedis123@casestrainer-redis-prod:6379/0')
        logger.info(f"[TASK:{task_id}] Using Redis URL: {redis_url}")
    except Exception as e:
        logger.error(f"[TASK:{task_id}] Error getting Redis URL: {str(e)}")
    
    service = CitationService()
    
    # Setup timeout handler for non-Windows systems
    timeout_set = False
    if platform.system() != 'Windows':
        try:
            def timeout_handler(signum, frame):
                error_msg = f"Task {task_id} timed out after 10 minutes"
                logger.error(f"[TASK:{task_id}] {error_msg}")
                raise TimeoutError(error_msg)
            
            signal.signal(signal.SIGALRM, timeout_handler)  # type: ignore[attr-defined]
            signal.alarm(600)  # type: ignore[attr-defined]
            timeout_set = True
            logger.info(f"[TASK:{task_id}] Timeout handler set for 10 minutes")
        except (AttributeError, OSError) as e:
            logger.warning(f"[TASK:{task_id}] Could not set signal handler: {str(e)}")
    
    try:
        start_time = time.time()
        logger.info(f"[TASK:{task_id}] Starting processing of type: {input_type}")
        
        # Log input data (truncated if too large)
        input_data_str = str(input_data)
        if len(input_data_str) > 500:
            input_data_str = input_data_str[:500] + "... [truncated]"
        logger.info(f"[TASK:{task_id}] Input data: {input_data_str}")
        
        # Process the task using UnifiedSyncProcessor (which has deduplication and works with text)
        logger.info(f"[TASK:{task_id}] Using UnifiedSyncProcessor for async text processing")
        
        if input_type == 'text':
            text = input_data.get('text', '')
            logger.info(f"[TASK:{task_id}] Processing text of length {len(text)}")
            
            from src.unified_sync_processor import UnifiedSyncProcessor, ProcessingOptions
            
            # Create processor with simplified config for async processing
            # Disable verification to prevent hanging in container environment
            options = ProcessingOptions(
                enable_verification=False,  # DISABLED: Likely cause of container hanging
                enable_clustering=False,    # DISABLED: Simplify processing
                enable_caching=True,
                force_ultra_fast=True,      # ENABLED: Use fastest processing path
                skip_clustering_threshold=300,
                ultra_fast_threshold=500,
                sync_threshold=5 * 1024,
                max_citations_for_skip_clustering=3
            )
            processor = UnifiedSyncProcessor(options)
            
            # Process the text using simplified ultra-fast processing
            logger.info(f"[TASK:{task_id}] Starting ultra-fast async processing (no verification, no clustering)")
            
            try:
                result = processor.process_text_unified(text, {'request_id': task_id})
                logger.info(f"[TASK:{task_id}] Ultra-fast processing completed successfully")
            except Exception as e:
                logger.error(f"[TASK:{task_id}] Ultra-fast processing failed: {e}")
                result = {
                    'success': False,
                    'error': f'Ultra-fast processing failed: {str(e)}'
                }
            
            # Ensure result has the expected format for async
            if result.get('success', False):
                result = {
                    'status': 'completed',
                    'task_id': task_id,
                    'citations': result.get('citations', []),
                    'clusters': result.get('clusters', []),
                    'metadata': {
                        'processing_strategy': result.get('processing_strategy', 'async_unified'),
                        'text_length': len(text)
                    }
                }
            else:
                result = {
                    'status': 'failed',
                    'task_id': task_id,
                    'error': result.get('error', 'Processing failed')
                }
            
        else:
            # For non-text inputs, fall back to the original method
            logger.info(f"[TASK:{task_id}] Using CitationService for non-text input type: {input_type}")
            result = asyncio.run(service.process_citation_task(task_id, input_type, input_data))
        
        # Ensure the result is JSON serializable
        processing_time = time.time() - start_time
        logger.info(f"[TASK:{task_id}] Task completed in {processing_time:.2f} seconds")
        
        try:
            # Log result summary (truncated if too large)
            result_str = str(result)
            if len(result_str) > 500:
                result_str = result_str[:500] + "... [truncated]"
            logger.info(f"[TASK:{task_id}] Task result: {result_str}")
            
            # Test serialization
            json.dumps(result)
            logger.info(f"[TASK:{task_id}] Result is JSON serializable")
            
            # Log success with metrics if available
            if isinstance(result, dict):
                status = result.get('status', 'unknown')
                num_citations = len(result.get('citations', []))
                num_clusters = len(result.get('clusters', []))
                logger.info(f"[TASK:{task_id}] Task completed with status '{status}'. Citations: {num_citations}, Clusters: {num_clusters}")
            
            # Ensure the result is properly stored in Redis
            try:
                from redis import Redis
                import json
                redis_url = os.environ.get('REDIS_URL', 'redis://:caseStrainerRedis123@casestrainer-redis-prod:6379/0')
                redis_conn = Redis.from_url(redis_url)
                
                # Store the result with a 24-hour TTL
                result_key = f'rq:job:{task_id}:result'
                redis_conn.setex(result_key, 86400, json.dumps(result))
                logger.info(f"[TASK:{task_id}] Result stored in Redis with key: {result_key}")
                
                # Also store in the job hash for RQ compatibility
                job_key = f'rq:job:{task_id}'
                redis_conn.hset(job_key, 'result', json.dumps(result))
                redis_conn.expire(job_key, 86400)
                logger.info(f"[TASK:{task_id}] Result stored in job hash")
                
            except Exception as e:
                logger.error(f"[TASK:{task_id}] Error storing result in Redis: {str(e)}", exc_info=True)
            
            return result
            
        except (TypeError, OverflowError) as e:
            error_msg = f"Result for task {task_id} is not JSON serializable: {e}"
            logger.error(f"[TASK:{task_id}] {error_msg}", exc_info=True)
            
            # Create a safe result with error information
            safe_result = {
                'status': 'failed',
                'error': 'Result serialization failed',
                'task_id': task_id,
                'processing_time': processing_time,
                'original_status': result.get('status') if isinstance(result, dict) else str(type(result)),
                'error_details': str(e)
            }
            
            # Try to include basic result info if available
            if isinstance(result, dict):
                safe_result.update({
                    'result_type': 'dict',
                    'result_keys': list(result.keys())
                })
            else:
                safe_result['result_type'] = str(type(result))
            
            logger.info(f"[TASK:{task_id}] Returning safe result after serialization error")
            return safe_result
        
    except TimeoutError as e:
        error_msg = f"Task {task_id} timed out after 10 minutes"
        logger.error(f"[TASK:{task_id}] {error_msg}", exc_info=True)
        return {
            'status': 'failed',
            'error': error_msg,
            'task_id': task_id,
            'processing_time': time.time() - start_time if 'start_time' in locals() else None,
            'error_type': 'timeout',
            'stack_trace': traceback.format_exc()
        }
    except Exception as e:
        error_msg = f"Task {task_id} failed: {str(e)}"
        logger.error(f"[TASK:{task_id}] {error_msg}", exc_info=True)
        return {
            'status': 'failed',
            'error': error_msg,
            'task_id': task_id,
            'processing_time': time.time() - start_time if 'start_time' in locals() else None,
            'error_type': type(e).__name__,
            'stack_trace': traceback.format_exc(),
            'task_id': task_id,
            'exception_type': type(e).__name__
        }
    finally:
        if platform.system() != 'Windows' and timeout_set:
            try:
                signal.alarm(0)  # type: ignore[attr-defined]
            except (AttributeError, OSError):
                pass

def verify_citations_enhanced(citations: list, text: str, request_id: str, input_type: str, metadata: dict):
    """Enhanced async verification of citations using the fallback verifier."""
    try:
        from src.async_verification_worker import verify_citations_enhanced as verify_enhanced
        
        result = verify_enhanced(citations, text, request_id, input_type, metadata)
        
        logger.info(f"Verification completed for request {request_id}: {len(citations)} citations processed")
        return result
        
    except Exception as e:
        logger.error(f"Verification failed for request {request_id}: {e}", exc_info=True)
        return {
            'success': False,
            'error': f'Verification failed: {str(e)}',
            'citations': citations,
            'request_id': request_id,
            'input_type': input_type,
            'metadata': metadata
        }

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
            if PSUTIL_AVAILABLE:
                memory_usage = psutil.Process().memory_info().rss / 1024 / 1024  # MB
                if memory_usage > self.max_memory_mb:
                    logger.warning(f"Memory usage high ({memory_usage:.1f}MB), restarting worker")
                    sys.exit(0)  # Graceful shutdown
                    return
            
            self.job_count += 1
            if self.job_count >= self.max_jobs:
                logger.info(f"Processed {self.job_count} jobs, restarting worker")
                sys.exit(0)  # Graceful shutdown
                return
            
            logger.info(f"Processing job {job.id} (job #{self.job_count})")
            result = super().perform_job(job, queue)
            
            if PSUTIL_AVAILABLE:
                memory_after = psutil.Process().memory_info().rss / 1024 / 1024
                logger.info(f"Job {job.id} completed. Memory: {memory_after:.1f}MB")
            else:
                logger.info(f"Job {job.id} completed. Memory monitoring disabled")
            
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
    
    if PSUTIL_AVAILABLE:
        logger.info("psutil available - memory monitoring enabled")
    else:
        logger.warning("psutil not available - memory monitoring disabled")
    
    signal.signal(signal.SIGTERM, signal_handler)  # type: ignore[attr-defined]
    signal.signal(signal.SIGINT, signal_handler)  # type: ignore[attr-defined]
    
    register_worker_functions()
    
    worker = RobustWorker([queue], connection=redis_conn)
    
    logger.info("Starting RQ worker...")
    logger.info(f"Redis URL: {redis_url}")
    logger.info(f"Queue: casestrainer")
    logger.info(f"Worker ID: {worker.key}")
    
    try:
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