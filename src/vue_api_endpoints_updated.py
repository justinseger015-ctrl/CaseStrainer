"""
Vue API Endpoints Blueprint
Main API routes for the CaseStrainer application
"""

import os
import sys
import uuid
import logging
import traceback
import time
import json
import copy
from datetime import datetime
from urllib.parse import urlparse
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from src.api.services.citation_service import CitationService
from src.database_manager import get_database_manager
from src.test_environment_safeguard import validate_request, check_test_environment

logger = logging.getLogger(__name__)

# Create the blueprint
vue_api = Blueprint('vue_api', __name__)

# Initialize citation service
citation_service = CitationService()

# Rest of the file content will be copied from the original file...

@vue_api.route('/health', methods=['GET'])
def health_check():
    """Enhanced health check endpoint with detailed diagnostics"""
    health_data = {
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'version': 'unknown',
        'components': {},
        'database_stats': {},
        'environment': {
            'python_version': sys.version.split()[0],
            'platform': sys.platform
        },
        'endpoints': {
            'current': '/casestrainer/api/health',
            'alias': '/health',
            'base_url': request.base_url
        }
    }
    
    try:
        # Try to get version from VERSION file
        try:
            # Look for VERSION file in /app directory (where it's copied in Docker)
            version_path = os.path.join('/app', 'VERSION')
            if os.path.exists(version_path):
                with open(version_path, 'r', encoding='utf-8') as vf:
                    health_data['version'] = vf.read().strip()
            else:
                health_data['version'] = 'development'
                logger.warning("VERSION file not found, using 'development'")
        except Exception as e:
            health_data['version'] = 'error'
            health_data['components']['version_check'] = f'error: {str(e)}'
            logger.warning(f"Could not read VERSION file: {e}")

        # Check database connection
        try:
            db_manager = get_database_manager()
            db_stats = db_manager.get_database_stats()
            health_data['components']['database'] = 'healthy'
            health_data['database_stats'] = {
                'tables': len(db_stats.get('tables', {})),
                'size_mb': round(db_stats.get('database_size_mb', 0), 2),
                'path': os.path.abspath(db_manager.db_path) if hasattr(db_manager, 'db_path') else 'unknown'
            }
        except Exception as e:
            health_data['status'] = 'degraded'
            health_data['components']['database'] = f'error: {str(e)}'
            logger.error(f"Database check failed: {e}")

        # Check upload directory
        try:
            upload_dir = os.path.join(current_app.root_path, 'uploads')
            if os.path.isdir(upload_dir) and os.access(upload_dir, os.W_OK):
                health_data['components']['upload_directory'] = 'healthy'
            else:
                health_data['status'] = 'degraded'
                health_data['components']['upload_directory'] = 'unwritable'
        except Exception as e:
            health_data['status'] = 'degraded'
            health_data['components']['upload_directory'] = f'error: {str(e)}'

        # Check citation processor
        try:
            # Simple check if citation service is importable
            from api.services.citation_service import CitationService
            health_data['components']['citation_processor'] = 'healthy'
        except Exception as e:
            health_data['status'] = 'degraded'
            health_data['components']['citation_processor'] = f'error: {str(e)}'
            logger.error(f"Citation processor check failed: {e}")

        # Set appropriate status code
        status_code = 200 if health_data['status'] == 'healthy' else 207  # 207 for partial content
        
        return jsonify(health_data), status_code

    except Exception as e:
        logger.error(f"Health check failed completely: {e}", exc_info=True)
        health_data.update({
            'status': 'unhealthy',
            'error': str(e),
            'traceback': str(traceback.format_exc()) if 'traceback' in locals() else 'Not available'
        })
        return jsonify(health_data), 500

# Add this alias route for /casestrainer/api/health
@vue_api.route('/casestrainer/api/health', methods=['GET'])
def health_check_alias():
    return health_check()

@vue_api.route('/db_stats', methods=['GET'])
def db_stats():
    """Database statistics endpoint"""
    try:
        db_manager = get_database_manager()
        stats = db_manager.get_database_stats()
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Database stats error: {e}")
        return jsonify({'error': 'Database stats unavailable'}), 503

@vue_api.route('/analyze', methods=['POST'])
async def analyze():
    """
    Main analysis endpoint that handles all types of input (file, JSON, form, URL).
    
    This endpoint routes requests to the appropriate handler based on the input type:
    - File uploads (multipart/form-data with file)
    - JSON payloads (application/json)
    - Form data (application/x-www-form-urlencoded or multipart/form-data)
    - URL parameters (for backward compatibility)
    
    Returns:
        Response with analysis results or task status
    """
    # Generate a unique request ID for tracking
    request_id = str(uuid.uuid4())
    
    # Check for test environment indicators to prevent test code interference
    if _is_test_environment_request(request):
        error_msg = 'Test environment detected. Please use the production interface.'
        logger.warning(f"[Request {request_id}] Test environment request detected and rejected")
        return jsonify({
            'error': error_msg,
            'citations': [],
            'clusters': [],
            'request_id': request_id,
            'success': False,
            'metadata': {
                'rejected_reason': 'test_environment_detected',
                'user_agent': request.headers.get('User-Agent', 'unknown'),
                'referer': request.headers.get('Referer', 'unknown')
            }
        }), 403
    
    # Additional safeguard: Check for test environment and validate request
    try:
        check_test_environment()
        # Validate request data if it's JSON
        if request.is_json:
            json_data = request.get_json(silent=True)
            if json_data:
                # Check for test data/environment (temporarily disabled for file uploads)
                # validate_request(json_data, dict(request.headers))
                pass # Temporarily disable validation for file uploads
    except RuntimeError as e:
        error_msg = f'Test execution blocked: {str(e)}'
        logger.warning(f"[Request {request_id}] {error_msg}")
        return jsonify({
            'error': error_msg,
            'citations': [],
            'clusters': [],
            'request_id': request_id,
            'success': False,
            'metadata': {
                'rejected_reason': 'test_execution_blocked',
                'block_reason': str(e)
            }
        }), 403
    
    # Log request details
    logger.info(f"=== ANALYZE ENDPOINT CALLED [Request ID: {request_id}] ===")
    logger.info(f"[Request {request_id}] Method: {request.method}")
    logger.info(f"[Request {request_id}] URL: {request.url}")
    logger.info(f"[Request {request_id}] Content-Type: {request.content_type}")
    logger.debug(f"[Request {request_id}] Headers: {dict(request.headers)}")
    
    # Initialize response metadata
    start_time = time.time()
    metadata = {
        'request_id': request_id,
        'endpoint': '/analyze',
        'timestamp': datetime.utcnow().isoformat(),
        'processing_mode': 'unknown',
        'input_type': 'unknown',
        'input_size': len(request.data) if request.data else 0,
        'content_type': request.content_type or 'not_specified'
    }
    
    try:
        # Log form data if present
        if request.form:
            logger.debug(f"[Request {request_id}] Form data received: {dict(request.form)}")
        
        # Log files if present
        if request.files:
            logger.info(f"[Request {request_id}] Files received: {[f.filename for f in request.files.values()]}")
        
        # Initialize citation service
        service = CitationService()
        
        # Try to parse JSON data if present
        json_data = None
        if request.data:
            try:
                json_data = request.get_json(silent=True, force=True)
                if json_data:
                    # Sanitize and log JSON data
                    sanitized_data = {}
                    for k, v in json_data.items():
                        if isinstance(v, str) and len(v) > 100:
                            sanitized_data[k] = f"[content of length {len(v)}]"
                        else:
                            sanitized_data[k] = v
                    logger.debug(f"[Request {request_id}] JSON data: {sanitized_data}")
            except Exception as e:
                logger.warning(f"[Request {request_id}] Failed to parse JSON data: {str(e)}")
        
        # Route to appropriate handler based on input type
        # 1. Check for file uploads first
        if 'file' in request.files and request.files['file'].filename:
            logger.info(f"[Request {request_id}] Routing to file upload handler")
            metadata.update({
                'input_type': 'file',
                'filename': request.files['file'].filename,
                'content_type': request.files['file'].content_type or 'application/octet-stream'
            })
            
            try:
                # Temporarily disable test safeguard for file uploads
                # result = await _handle_file_upload(service, request_id)
                result = await _handle_file_upload(service, request_id)
                return _format_response(result, request_id, metadata, start_time)
                
            except Exception as e:
                error_msg = f"Error in file upload handler: {str(e)}"
                logger.error(f"[Request {request_id}] {error_msg}", exc_info=True)
                return _format_error(
                    error_msg, 
                    status_code=500, 
                    request_id=request_id, 
                    metadata={
                        **metadata,
                        'error_type': 'file_upload_error',
                        'error_details': str(e)
                    }
                )
        
        # 2. Check for JSON input
        elif request.is_json or json_data:
            logger.info(f"[Request {request_id}] Routing to JSON input handler")
            metadata.update({
                'input_type': 'json',
                'has_json_data': json_data is not None
            })
            
            try:
                result = await _handle_json_input(service, request_id, json_data or request.get_json())
                # Check if result indicates an error
                if result.get('success') is False or result.get('error'):
                    return _format_error(
                        result.get('error', 'Unknown error'),
                        status_code=400,
                        request_id=request_id,
                        metadata={
                            **metadata,
                            **result.get('metadata', {})
                        }
                    )
                return _format_response(result, request_id, metadata, start_time)
                
            except Exception as e:
                error_msg = f"Error in JSON input handler: {str(e)}"
                logger.error(f"[Request {request_id}] {error_msg}", exc_info=True)
                return _format_error(
                    error_msg,
                    status_code=400,
                    request_id=request_id,
                    metadata={
                        **metadata,
                        'error_type': 'json_parse_error',
                        'error_details': str(e)
                    }
                )
        
        # 3. Check for form data (including URL parameters)
        elif request.form:
            logger.info(f"[Request {request_id}] Routing to form input handler")
            metadata.update({
                'input_type': 'form',
                'form_fields': list(request.form.keys())
            })
            
            try:
                result = await _handle_form_input(service, request_id)
                # Check if result indicates an error
                if result.get('success') is False or result.get('error'):
                    return _format_error(
                        result.get('error', 'Unknown error'),
                        status_code=400,
                        request_id=request_id,
                        metadata={
                            **metadata,
                            **result.get('metadata', {})
                        }
                    )
                return _format_response(result, request_id, metadata, start_time)
                
            except Exception as e:
                error_msg = f"Error in form input handler: {str(e)}"
                logger.error(f"[Request {request_id}] {error_msg}", exc_info=True)
                return _format_error(
                    error_msg,
                    status_code=400,
                    request_id=request_id,
                    metadata={
                        **metadata,
                        'error_type': 'form_parse_error',
                        'error_details': str(e)
                    }
                )
        
        # 4. Check for raw URL in request data (for backward compatibility)
        elif request.data and isinstance(request.data, (str, bytes)):
            try:
                url = request.data.decode('utf-8').strip() if isinstance(request.data, bytes) else request.data.strip()
                if url.startswith(('http://', 'https://')):
                    logger.info(f"[Request {request_id}] Detected raw URL input: {url}")
                    
                    # Validate URL before processing
                    if not _validate_url(url):
                        error_msg = 'Invalid or unsafe URL provided'
                        logger.warning(f"[Request {request_id}] URL validation failed: {url}")
                        return _format_error(
                            error_msg,
                            status_code=400,
                            request_id=request_id,
                            metadata={
                                **metadata,
                                'input_type': 'url',
                                'url': url,
                                'rejected_reason': 'url_validation_failed'
                            }
                        )
                    
                    metadata.update({
                        'input_type': 'url',
                        'url': url
                    })
                    
                    result = await _process_url_input(url)
                    return _format_response(result, request_id, metadata, start_time)
                    
            except Exception as e:
                logger.warning(f"[Request {request_id}] Failed to process as URL: {str(e)}")
        
        # 5. No valid input found
        content_type = request.content_type or 'not specified'
        error_msg = (
            f"Invalid or missing input. No file, JSON, or form data found. "
            f"Content-Type: {content_type}, Data length: {len(request.data) if request.data else 0}"
        )
        logger.error(f"[Request {request_id}] {error_msg}")
        logger.debug(f"[Request {request_id}] Request data: {request.data[:1000] if request.data else 'No data'}")
        
        return _format_error(
            'Invalid or missing input. Please check the Content-Type header and request format.',
            details=error_msg,
            status_code=400,
            request_id=request_id,
            metadata={
                **metadata,
                'error_type': 'invalid_input',
                'error_details': error_msg
            }
        )
        
    except Exception as e:
        error_msg = f"Unexpected error in analyze endpoint: {str(e)}"
        logger.error(f"[Request {request_id}] {error_msg}", exc_info=True)
        
        return _format_error(
            'An unexpected error occurred during analysis',
            details=str(e),
            status_code=500,
            request_id=request_id,
            metadata={
                **metadata,
                'error_type': 'unexpected_error',
                'error_details': str(e)
            }
        )


def _format_response(result, request_id, metadata, start_time):
    """Format a successful response with consistent structure"""
    # Calculate processing time
    processing_time_ms = int((time.time() - start_time) * 1000)
    
    # Ensure metadata is included in the response
    if not isinstance(result, dict):
        result = {}
    
    # Update metadata with timing information
    metadata.update({
        'processing_time_ms': processing_time_ms,
        'processing_mode': result.get('metadata', {}).get('processing_mode', metadata.get('processing_mode', 'unknown')),
        'status': result.get('status', 'completed'),
        'success': result.get('success', True)
    })
    
    # Ensure required fields are present
    response_data = {
        'result': {
            'citations': result.get('citations', []),
            'clusters': result.get('clusters', []),
            'statistics': result.get('statistics', {}),
        },
        'request_id': request_id,
        'success': result.get('success', True),
        'metadata': {**result.get('metadata', {}), **metadata}
    }
    
    # Include task information if this is an async task
    if 'task_id' in result:
        response_data.update({
            'task_id': result['task_id'],
            'status': result.get('status', 'processing'),
            'message': result.get('message', 'Request is being processed')
        })
    
    # Include any additional fields from the result
    for key in ['message', 'warnings', 'debug']:
        if key in result and key not in response_data:
            response_data[key] = result[key]
    
    # Log successful response (without large data)
    log_data = copy.deepcopy(response_data)
    if 'result' in log_data:
        result_data = log_data['result']
        if 'citations' in result_data and len(result_data['citations']) > 5:
            result_data['citations'] = f"[list of {len(result_data['citations'])} citations]"
        if 'clusters' in result_data and len(result_data['clusters']) > 3:
            result_data['clusters'] = f"[list of {len(result_data['clusters'])} clusters]"
    
    logger.info(f"[Request {request_id}] Request completed successfully in {processing_time_ms}ms")
    logger.debug(f"[Request {request_id}] Response data: {log_data}")

    # Write full API response to a log file for debugging
    try:
        with open('/app/logs/frontend_api_results.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(response_data, ensure_ascii=False) + '\n')
    except Exception as e:
        logger.error(f"Failed to write API response to log file: {e}")

    return jsonify(response_data)


def _format_error(message, details=None, status_code=400, request_id=None, metadata=None):
    """Format an error response with consistent structure"""
    error_data = {
        'error': message,
        'details': details or message,
        'request_id': request_id or str(uuid.uuid4()),
        'success': False,
        'citations': [],
        'clusters': [],
        'metadata': metadata or {}
    }
    
    # Ensure metadata has required fields
    if 'request_id' not in error_data['metadata'] and request_id:
        error_data['metadata']['request_id'] = request_id
    
    if 'status' not in error_data['metadata']:
        error_data['metadata']['status'] = 'error'
    
    logger.error(f"[Request {request_id or 'unknown'}] Error: {message}")
    if details and details != message:
        logger.error(f"[Request {request_id or 'unknown'}] Details: {details}")
    
    return jsonify(error_data), status_code

@vue_api.route('/analyze_enhanced', methods=['POST'])
async def analyze_enhanced():
    """Enhanced analyze endpoint with better citation extraction, clustering, and verification"""
    logger.info("=== ENHANCED_ANALYZE ENDPOINT CALLED ===")
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided', 'citations': [], 'clusters': []}), 400
        
        input_type = data.get('type', 'text')
        
        if input_type == 'text':
            text = data.get('text', '')
            if not text:
                return jsonify({'error': 'No text provided', 'citations': [], 'clusters': []}), 400
            
            # Check if this should be processed immediately
            if citation_service.should_process_immediately({'type': 'text', 'text': text}):
                logger.info("Processing text immediately")
                result = citation_service.process_immediately({'type': 'text', 'text': text})
            else:
                logger.info("Processing text asynchronously")
                # Generate task ID and process
                task_id = str(uuid.uuid4())
                result = await citation_service.process_citation_task(
                    task_id, 
                    'text', 
                    {'text': text}
                )
            
            # Handle the result
            if isinstance(result, dict) and result.get('status') == 'completed':
                return jsonify({
                    'citations': result.get('citations', []),
                    'clusters': result.get('clusters', []),
                    'success': True,
                    'statistics': result.get('statistics', {}),
                    'metadata': result.get('metadata', {})
                })
            else:
                return jsonify({
                    'error': result.get('message', 'Processing failed') if isinstance(result, dict) else 'Processing failed',
                    'success': False
                }), 500
        
        else:
            return jsonify({'error': 'File upload processing not implemented in this endpoint', 'citations': [], 'clusters': []}), 501
            
    except Exception as e:
        logger.error(f"Error in enhanced analyze endpoint: {e}", exc_info=True)
        return jsonify({'error': 'Analysis failed', 'details': str(e), 'citations': [], 'clusters': []}), 500

@vue_api.route('/task_status/<task_id>', methods=['GET'])
def task_status(task_id):
    """Check the status of a queued task"""
    logger.info(f"Checking status for task_id: {task_id}")
    
    try:
        from rq import Queue, Worker
        from redis import Connection
        from redis import Redis
        
        # Get Redis connection from environment (required)
        redis_url = os.environ.get('REDIS_URL')
        if not redis_url:
            logger.error("REDIS_URL environment variable not set")
            return jsonify({
                'error': 'Server configuration error',
                'details': 'Redis URL not configured',
                'task_id': task_id,
                'citations': [],
                'clusters': []
            }), 500
            
        logger.info(f"Connecting to Redis at: {redis_url}")
        
        redis_conn = Redis.from_url(redis_url, socket_connect_timeout=5, socket_timeout=5)
        
        # Test the connection
        try:
            redis_conn.ping()
            logger.info("Successfully connected to Redis")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            return jsonify({
                'error': 'Failed to connect to task queue',
                'details': str(e),
                'task_id': task_id,
                'citations': [],
                'clusters': []
            }), 500
        
        # Get the queue
        queue = Queue('casestrainer', connection=redis_conn)
        
        # Log all job IDs in the queue for debugging
        job_ids = queue.job_ids
        logger.info(f"Found {len(job_ids)} jobs in queue. Job IDs: {job_ids}")
        
        # Get the job
        job = queue.fetch_job(task_id)
        
        if not job:
            logger.warning(f"Job {task_id} not found in queue")
            return jsonify({
                'error': 'Task not found',
                'task_id': task_id,
                'citations': [],
                'clusters': []
            }), 404
        
        # Log job details
        logger.info(f"Job {task_id} status: {job.get_status()}")
        logger.info(f"Job {task_id} meta: {job.meta}")
        
        # Get job result if available
        result = None
        if job.is_finished:
            try:
                result = job.result
                logger.info(f"Job {task_id} result type: {type(result)}")
            except Exception as e:
                logger.error(f"Error getting job result: {e}")
        
        # Check job status
        if job.is_finished:
            # Job completed successfully
            if result and isinstance(result, dict) and (result.get('status') in ['success', 'completed'] or result.get('success') is True):
                return jsonify({
                    'status': 'completed',
                    'task_id': task_id,
                    'result': {
                        'citations': result.get('citations', []),
                        'clusters': result.get('clusters', []),
                        'statistics': result.get('statistics', {}),
                        'metadata': result.get('metadata', {})
                    },
                    'success': True
                })
            else:
                error_msg = 'Unknown error'
                if result and isinstance(result, dict):
                    error_msg = result.get('error', 'Processing failed')
                elif job.exc_info:
                    error_msg = f"Job failed with exception: {job.exc_info}"
                
                logger.error(f"Job {task_id} failed: {error_msg}")
                return jsonify({
                    'status': 'failed',
                    'task_id': task_id,
                    'error': error_msg,
                    'success': False,
                    'citations': [],
                    'clusters': []
                })
        
        elif job.is_failed:
            # Job failed
            error_msg = str(job.exc_info) if job.exc_info else 'Job failed without exception info'
            logger.error(f"Job {task_id} failed: {error_msg}")
            return jsonify({
                'status': 'failed',
                'task_id': task_id,
                'error': error_msg,
                'success': False,
                'citations': [],
                'clusters': []
            })
        
        elif job.is_started:
            # Job is currently running
            return jsonify({
                'status': 'processing',
                'task_id': task_id,
                'message': 'Task is currently being processed',
                'success': True,
                'citations': [],
                'clusters': []
            })
        
        else:
            # Job is queued but not started yet
            try:
                position = queue.get_job_position(task_id)
            except Exception as e:
                logger.warning(f"Could not get job position: {e}")
                position = -1
                
            return jsonify({
                'status': 'queued',
                'task_id': task_id,
                'message': f'Task is queued and waiting to be processed (position: {position})',
                'position': position,
                'success': True,
                'citations': [],
                'clusters': []
            })
            
    except Exception as e:
        error_msg = f"Error checking task status for {task_id}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({
            'error': 'Failed to check task status',
            'details': str(e),
            'task_id': task_id,
            'citations': [],
            'clusters': []
        }), 500

@vue_api.route('/processing_progress', methods=['GET'])
def processing_progress():
    """Legacy endpoint for processing progress - redirects to task_status."""
    task_id = request.args.get('task_id')
    if not task_id:
        return jsonify({'error': 'Missing task_id parameter'}), 400

    # Redirect to the existing task_status endpoint
    return task_status(task_id)

async def _handle_file_upload(service, request_id):
    """
    Handle file upload with proper async processing and CitationService integration
    
    Args:
        service: Instance of CitationService
        request_id: Unique ID for request tracking
        
    Returns:
        Response with analysis results or task status
    """
    logger.info(f"[File Upload {request_id}] Starting file upload handler")
    
    try:
        if 'file' not in request.files:
            error_msg = 'No file provided in request.files'
            logger.error(f"[File Upload {request_id}] {error_msg}")
            return {
                'error': error_msg,
                'citations': [],
                'clusters': [],
                'request_id': request_id,
                'success': False,
                'metadata': {}
            }
        
        file = request.files['file']
        if not file or file.filename == '':
            error_msg = 'No file selected or empty file'
            logger.error(f"[File Upload {request_id}] {error_msg}")
            return {
                'error': error_msg,
                'citations': [],
                'clusters': [],
                'request_id': request_id,
                'success': False,
                'metadata': {}
            }
        
        # Log file details
        filename = secure_filename(file.filename) if file.filename else 'unknown_file'
        logger.info(f"[File Upload {request_id}] Processing file: {filename}")
        logger.info(f"[File Upload {request_id}] Content type: {file.content_type}")
        
        # Validate file type
        allowed_extensions = {'pdf', 'txt', 'doc', 'docx', 'rtf', 'md', 'html', 'htm', 'xml', 'xhtml'}
        file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        
        if file_ext not in allowed_extensions:
            error_msg = f'File type not allowed. Allowed types: {", ".join(allowed_extensions)}. Got: {file_ext}'
            logger.error(f"[File Upload {request_id}] {error_msg}")
            return {
                'error': error_msg,
                'citations': [],
                'clusters': [],
                'request_id': request_id,
                'success': False,
                'metadata': {}
            }
        
        # Generate unique filename
        unique_filename = f"{uuid.uuid4()}_{filename}"
        logger.info(f"[File Upload {request_id}] Generated secure filename: {unique_filename}")
        
        # Ensure uploads directory exists with proper permissions
        uploads_dir = os.path.join('/app', 'uploads')
        os.makedirs(uploads_dir, exist_ok=True)
        logger.info(f"[File Upload {request_id}] Upload directory: {uploads_dir}")
        
        # Save the file with proper error handling
        file_path = os.path.join(uploads_dir, unique_filename)
        logger.info(f"[File Upload {request_id}] Saving file to: {file_path}")
        
        try:
            file.save(file_path)
            
            # Verify file was saved
            if not os.path.exists(file_path):
                raise IOError("File was not saved successfully")
                
            logger.info(f"[File Upload {request_id}] File saved successfully")
            
            # Get options from form data if provided
            options = {}
            if 'options' in request.form:
                try:
                    options = json.loads(request.form['options'])
                    logger.info(f"[File Upload {request_id}] Parsed options: {options}")
                except json.JSONDecodeError as e:
                    logger.warning(f"[File Upload {request_id}] Failed to parse options JSON: {e}")
            
            # Process the file using CitationService
            logger.info(f"[File Upload {request_id}] Starting file processing with CitationService")
            
            # Check if we should process immediately or queue using CitationService logic
            file_size = os.path.getsize(file_path)
            input_data = {'type': 'file', 'file_path': file_path, 'filename': filename, 'file_size': file_size}
            should_process_immediately = service.should_process_immediately(input_data)
            
            if not should_process_immediately:
                # Enqueue for background processing using the proper RQ system
                from rq import Queue
                from redis import Redis
                from src.rq_worker import process_citation_task_direct
                
                # Connect to Redis using environment variable or default
                redis_url = os.environ.get('REDIS_URL', 'redis://:caseStrainerRedis123@redis:6379/0')
                redis_conn = Redis.from_url(redis_url)
                queue = Queue('casestrainer', connection=redis_conn)
                
                # Enqueue the file processing task using the wrapper function
                job = queue.enqueue(
                    process_citation_task_direct,
                    args=[request_id, 'file', {'file_path': file_path, 'filename': filename}],
                    job_id=request_id,
                    job_timeout='10m'
                )
                
                logger.info(f"[File Upload {request_id}] File processing task enqueued with job_id: {job.id}")
                
                return {
                    'task_id': request_id,
                    'status': 'processing',
                    'message': 'File processing started',
                    'request_id': request_id,
                    'success': True,
                    'citations': [],
                    'clusters': [],
                    'metadata': {
                        'filename': filename,
                        'file_size': os.path.getsize(file_path),
                        'content_type': file.content_type,
                        'processing_mode': 'queued'
                    }
                }
            else:
                # Process synchronously
                logger.info(f"[File Upload {request_id}] Processing file synchronously")
                
                # Read file content based on type
                if file_ext == 'pdf':
                    import PyPDF2
                    text = ''
                    with open(file_path, 'rb') as f:
                        pdf_reader = PyPDF2.PdfReader(f)
                        text = '\n'.join(page.extract_text() for page in pdf_reader.pages)
                elif file_ext == 'docx':
                    try:
                        from docx import Document
                        doc = Document(file_path)
                        text = '\n'.join(paragraph.text for paragraph in doc.paragraphs)
                    except ImportError:
                        # Fallback if python-docx is not available
                        text = f"[DOCX file content could not be extracted - {filename}]"
                        logger.warning(f"[File Upload {request_id}] python-docx not available for DOCX processing")
                    except Exception as e:
                        text = f"[Error extracting DOCX content: {str(e)}]"
                        logger.error(f"[File Upload {request_id}] DOCX processing error: {e}")
                elif file_ext == 'doc':
                    # DOC files are not supported - legacy format
                    text = f"[DOC files are not supported - {filename}. Please convert to DOCX or PDF.]"
                    logger.warning(f"[File Upload {request_id}] DOC file not supported: {filename}")
                elif file_ext in ['html', 'htm', 'xhtml']:
                    try:
                        from bs4 import BeautifulSoup
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            html_content = f.read()
                        soup = BeautifulSoup(html_content, 'html.parser')
                        # Remove script and style elements
                        for script in soup(["script", "style"]):
                            script.decompose()
                        text = soup.get_text(separator='\n', strip=True)
                        logger.info(f"[File Upload {request_id}] Successfully extracted {len(text)} characters from HTML")
                    except ImportError:
                        # Fallback if BeautifulSoup is not available
                        text = f"[HTML file content could not be extracted - {filename}]"
                        logger.warning(f"[File Upload {request_id}] BeautifulSoup not available for HTML processing")
                    except Exception as e:
                        text = f"[Error extracting HTML content: {str(e)}]"
                        logger.error(f"[File Upload {request_id}] HTML processing error: {e}")
                elif file_ext == 'xml':
                    try:
                        from bs4 import BeautifulSoup
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            xml_content = f.read()
                        soup = BeautifulSoup(xml_content, 'xml')
                        # Remove script and style elements
                        for script in soup(["script", "style"]):
                            script.decompose()
                        text = soup.get_text(separator='\n', strip=True)
                        logger.info(f"[File Upload {request_id}] Successfully extracted {len(text)} characters from XML")
                    except ImportError:
                        # Fallback if BeautifulSoup is not available
                        text = f"[XML file content could not be extracted - {filename}]"
                        logger.warning(f"[File Upload {request_id}] BeautifulSoup not available for XML processing")
                    except Exception as e:
                        text = f"[Error extracting XML content: {str(e)}]"
                        logger.error(f"[File Upload {request_id}] XML processing error: {e}")
                else:
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                        text = f.read()
                
                # Process the text synchronously (for files, we want immediate processing)
                logger.info(f"[File Upload {request_id}] Processing extracted text synchronously")
                result = await service.process_citations_from_text(text)
                
                # Format the result for consistency
                formatted_result = {
                    'citations': result.get('citations', []),
                    'clusters': result.get('clusters', []),
                    'statistics': result.get('statistics', {}),
                    'request_id': request_id,
                    'success': True,
                    'metadata': {
                        'source': filename,
                        'text_length': len(text),
                        'processing_time': time.time(),
                        'processing_mode': 'sync'
                    }
                }
                
                # Add file metadata to formatted result
                formatted_result['metadata'].update({
                    'filename': filename,
                    'file_size': os.path.getsize(file_path),
                    'content_type': file.content_type,
                    'processing_mode': 'sync'
                })
                
                return formatted_result
                
        except IOError as e:
            error_msg = f"Failed to process file: {str(e)}"
            logger.error(f"[File Upload {request_id}] {error_msg}", exc_info=True)
            return {
                'error': error_msg,
                'citations': [],
                'clusters': [],
                'request_id': request_id,
                'success': False,
                'metadata': {}
            }
            
        except Exception as e:
                error_msg = f"Failed to enqueue task: {str(e)}"
                logger.error(f"[File Upload {request_id}] {error_msg}", exc_info=True)
                
                # Clean up the uploaded file if task creation failed
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        logger.info(f"[File Upload {request_id}] Cleaned up file after task enqueue failure")
                except Exception as cleanup_error:
                    logger.error(f"[File Upload {request_id}] Failed to clean up file: {str(cleanup_error)}")
                
                return jsonify({
                    'error': error_msg,
                    'citations': [],
                    'clusters': [],
                    'request_id': request_id
                }), 500
            
    except Exception as e:
        logger.error(f"File upload error: {e}", exc_info=True)
        return jsonify({'error': f'Failed to process file: {str(e)}', 'citations': [], 'clusters': []}), 500

async def _handle_json_input(service, request_id, data=None):
    """
    Handle JSON input processing with CitationService integration
    
    Args:
        service: Instance of CitationService
        request_id: Unique ID for request tracking
        data: Optional pre-parsed JSON data (for testing or direct call)
        
    Returns:
        Dictionary with analysis results or error information
    """
    logger.info(f"[JSON Input {request_id}] Starting JSON input processing")
    
    try:
        # Log request details
        logger.info(f"[JSON Input {request_id}] Request URL: {request.url}")
        logger.info(f"[JSON Input {request_id}] Request method: {request.method}")
        logger.info(f"[JSON Input {request_id}] Content-Type: {request.content_type}")
        
        # Get JSON data if not provided
        if data is None:
            # Log raw request data for debugging
            try:
                raw_data = request.get_data(as_text=True)
                logger.info(f"[JSON Input {request_id}] Raw request data (first 1000 chars): {raw_data[:1000]}")
            except Exception as e:
                logger.warning(f"[JSON Input {request_id}] Could not read raw request data: {e}")
            
            # Parse JSON data
            try:
                data = request.get_json(force=True, silent=True)
                if data is None:
                    error_msg = "Failed to parse JSON data"
                    logger.error(f"[JSON Input {request_id}] {error_msg}")
                    return {
                        'error': error_msg,
                        'citations': [],
                        'clusters': [],
                        'request_id': request_id,
                        'success': False,
                        'metadata': {}
                    }
            except Exception as e:
                error_msg = f"Error parsing JSON: {str(e)}"
                logger.error(f"[JSON Input {request_id}] {error_msg}", exc_info=True)
                return {
                    'error': 'Invalid JSON data',
                    'details': str(e),
                    'citations': [],
                    'clusters': [],
                    'request_id': request_id,
                    'success': False,
                    'metadata': {}
                }
        
        # Log sanitized data (truncate long text fields)
        sanitized_data = {}
        for k, v in data.items():
            if isinstance(v, str):
                sanitized_data[k] = v[:100] + '...' if len(v) > 100 else v
            else:
                sanitized_data[k] = str(v)[:200] + '...' if len(str(v)) > 200 else v
        
        logger.info(f"[JSON Input {request_id}] Processing data with keys: {list(data.keys())}")
        logger.debug(f"[JSON Input {request_id}] Sanitized data: {sanitized_data}")
        
        # Process based on input type
        input_type = data.get('type', 'text')
        logger.info(f"[JSON Input {request_id}] Input type: {input_type}")
        
        if input_type == 'text':
            text = data.get('text', '')
            logger.info(f"[JSON Input {request_id}] Text input received. Length: {len(text)}")
            
            if not text:
                error_msg = 'No text provided in JSON data'
                logger.error(f"[JSON Input {request_id}] {error_msg}")
                return {
                    'error': error_msg,
                    'citations': [],
                    'clusters': [],
                    'request_id': request_id,
                    'success': False,
                    'metadata': {}
                }
            
            # Check for test citations to prevent test data processing
            if _is_test_citation_text(text):
                error_msg = 'Test citation detected. Please provide actual document content.'
                logger.warning(f"[JSON Input {request_id}] Test citation detected and rejected: {text[:100]}...")
                return {
                    'error': error_msg,
                    'citations': [],
                    'clusters': [],
                    'request_id': request_id,
                    'success': False,
                    'metadata': {
                        'rejected_reason': 'test_citation_detected',
                        'test_pattern_found': _extract_test_pattern(text)
                    }
                }
                
            logger.info(f"[JSON Input {request_id}] Processing text input...")
            try:
                result = await _process_text_input(
                    service=service,
                    request_id=request_id,
                    text=text,
                    source_name="api-input"
                )
                logger.info(f"[_handle_json_input] [Request {request_id}] Text processing completed successfully")
                return result
            except Exception as e:
                logger.error(f"[_handle_json_input] [Request {request_id}] Error in _process_text_input: {str(e)}", exc_info=True)
                raise
            
        elif input_type == 'url':
            url = data.get('url', '')
            logger.info(f"[_handle_json_input] [Request {request_id}] URL input received: {url}")
            
            if not url:
                logger.error(f"[_handle_json_input] [Request {request_id}] No URL provided")
                return {
                    'error': 'No URL provided', 
                    'citations': [], 
                    'clusters': [],
                    'request_id': request_id,
                    'success': False
                }
            
            # Validate URL before processing
            if not _validate_url(url):
                error_msg = 'Invalid or unsafe URL provided'
                logger.warning(f"[_handle_json_input] [Request {request_id}] URL validation failed: {url}")
                return {
                    'error': error_msg,
                    'citations': [],
                    'clusters': [],
                    'request_id': request_id,
                    'success': False,
                    'metadata': {
                        'rejected_reason': 'url_validation_failed',
                        'url': url
                    }
                }
                
            logger.info(f"[_handle_json_input] [Request {request_id}] Processing URL input...")
            try:
                result = await _process_url_input(url, request_id)
                logger.info(f"[_handle_json_input] [Request {request_id}] URL processing completed successfully")
                return result
            except Exception as e:
                logger.error(f"[_handle_json_input] [Request {request_id}] Error in _process_url_input: {str(e)}", exc_info=True)
                raise
            
        else:
            error_msg = f"Invalid input type: {input_type}"
            logger.error(f"[_handle_json_input] [Request {request_id}] {error_msg}")
            return {
                'error': error_msg,
                'citations': [], 
                'clusters': [],
                'request_id': request_id,
                'success': False
            }
            
    except Exception as e:
        error_msg = f"Error processing JSON input: {str(e)}"
        logger.error(f"[_handle_json_input] [Request {request_id}] {error_msg}", exc_info=True)
        
        # Include more detailed error information for debugging
        error_details = {
            'error': 'Internal server error',
            'type': type(e).__name__,
            'message': str(e),
            'request_id': request_id,
            'citations': [],
            'clusters': []
        }
        
        # Include traceback in the response in development mode
        if current_app.config.get('DEBUG', False):
            import traceback
            error_details['traceback'] = traceback.format_exc()
        
        return jsonify(error_details), 500

async def _handle_form_input(service, request_id):
    """
    Handle form input processing with CitationService integration
    
    Args:
        service: Instance of CitationService
        request_id: Unique ID for request tracking
    """
    try:
        # Handle form data processing
        form_data = request.form.to_dict()
        text = form_data.get('text', '')
        url = form_data.get('url', '')
        
        # Check for URL input first
        if url:
            logger.info(f"[Form Input {request_id}] Processing URL from form: {url}")
            
            # Validate URL before processing
            if not _validate_url(url):
                error_msg = 'Invalid or unsafe URL provided'
                logger.warning(f"[Form Input {request_id}] URL validation failed: {url}")
                return {
                    'error': error_msg,
                    'citations': [],
                    'clusters': [],
                    'request_id': request_id,
                    'success': False,
                    'metadata': {
                        'rejected_reason': 'url_validation_failed',
                        'url': url
                    }
                }
            
            # Process URL input
            result = await _process_url_input(url)
            return result
        
        # Check for text input
        if not text:
            return {
                'error': 'No text or URL provided in form data',
                'citations': [],
                'clusters': [],
                'request_id': request_id,
                'success': False
            }
        
        # Process text input
        result = await _process_text_input(service, request_id, text)
        return result
        
    except Exception as e:
        logger.error(f"[Form Input {request_id}] Error: {str(e)}", exc_info=True)
        return {
            'error': f'Error processing form input: {str(e)}',
            'citations': [],
            'clusters': [],
            'request_id': request_id,
            'success': False
        }

async def _process_text_input(service, request_id, text, source_name="form-input"):
    """Process text input with citation service using async queue."""
    try:
        logger.info(f"[Text Input {request_id}] Processing text of length: {len(text)}")
        
        # Check for test citations to prevent test data processing
        if _is_test_citation_text(text):
            error_msg = 'Test citation detected. Please provide actual document content.'
            logger.warning(f"[Text Input {request_id}] Test citation detected and rejected: {text[:100]}...")
            return {
                'error': error_msg,
                'citations': [],
                'clusters': [],
                'request_id': request_id,
                'success': False,
                'metadata': {
                    'source': source_name,
                    'rejected_reason': 'test_citation_detected',
                    'test_pattern_found': _extract_test_pattern(text),
                    'text_length': len(text)
                }
            }
        
        # Check if we should process immediately or queue
        input_data = {'type': 'text', 'text': text}
        if service.should_process_immediately(input_data):
            logger.info(f"[Text Input {request_id}] Processing text immediately (short text)")
            result = await service.process_immediately(input_data)
            
            return {
                'citations': result.get('citations', []),
                'clusters': result.get('clusters', []),
                'request_id': request_id,
                'success': True,
                'metadata': {
                    'source': source_name,
                    'text_length': len(text),
                    'processing_time': time.time(),
                    'processing_mode': 'immediate'
                }
            }
        else:
            logger.info(f"[Text Input {request_id}] Queuing text for async processing")
            
            # Import RQ for async task processing
            from rq import Queue
            from redis import Redis
            
            # Connect to Redis using environment variable or default
            redis_url = os.environ.get('REDIS_URL', 'redis://:caseStrainerRedis123@redis:6379/0')
            redis_conn = Redis.from_url(redis_url)
            queue = Queue('casestrainer', connection=redis_conn)
            
            # Enqueue the text processing task
            job = queue.enqueue(
                'src.rq_worker.process_citation_task_direct',
                args=[request_id, 'text', {'text': text}],
                job_id=request_id,
                job_timeout='10m'
            )
            
            logger.info(f"[Text Input {request_id}] Text processing task enqueued with job_id: {job.id}")
            
            # Return task_id for frontend polling
            return {
                'task_id': request_id,
                'status': 'processing',
                'message': 'Text processing started',
                'request_id': request_id,
                'success': True,
                'metadata': {
                    'source': source_name,
                    'text_length': len(text),
                    'processing_mode': 'queued'
                }
            }
            
    except Exception as e:
        logger.error(f"[Text Input {request_id}] Error: {str(e)}", exc_info=True)
        raise

def _is_test_citation_text(text: str) -> bool:
    """Check if text contains known test citations that should be rejected."""
    # Disabled test detection to allow all legitimate cases
    # Users should be able to research any legal case without restrictions
    return False

def _extract_test_pattern(text: str) -> str:
    """Extract the test pattern that was detected."""
    if not text:
        return "no_text"
    
    text_norm = text.strip().lower()
    
    # Check for specific patterns
    if "smith v. jones" in text_norm and "123 f.3d 456" in text_norm:
        return "smith_v_jones_123_f3d_456"
    elif "123 f.3d 456" in text_norm:
        return "123_f3d_456_pattern"
    elif "999 u.s. 999" in text_norm:
        return "999_us_999_pattern"
    elif "test citation" in text_norm:
        return "test_citation_string"
    elif "sample citation" in text_norm:
        return "sample_citation_string"
    
    return "unknown_test_pattern"

def _is_test_environment_request(request) -> bool:
    """Check if the request appears to be from a test environment."""
    # Disabled test environment detection to allow all legitimate requests
    # Users should be able to access the system from any environment
    return False

def _is_test_url(url: str) -> bool:
    """Check if a URL is a test URL that should be rejected."""
    if not url:
        return False
    
    url_lower = url.lower()
    
    # Test URL patterns
    test_url_patterns = [
        'example.com',
        'test.com',
        'localhost',
        '127.0.0.1',
        '0.0.0.0',
        '::1',
        'test.local',
        'dev.local',
        'staging.local',
        'mock.com',
        'fake.com',
        'dummy.com',
        'sample.com'
    ]
    
    # Check for test URL patterns
    for pattern in test_url_patterns:
        if pattern in url_lower:
            logger.warning(f"Test URL detected: {url} (pattern: {pattern})")
            return True
    
    # Check for potentially problematic protocols
    problematic_protocols = [
        'file://',
        'ftp://',
        'mailto:',
        'tel:',
        'javascript:',
        'data:',
        'chrome://',
        'about:',
        'moz-extension://'
    ]
    
    for protocol in problematic_protocols:
        if url_lower.startswith(protocol):
            logger.warning(f"Problematic URL protocol detected: {url} (protocol: {protocol})")
            return True
    
    return False

def _validate_url(url: str) -> bool:
    """Validate that a URL is safe and properly formatted."""
    if not url or not isinstance(url, str):
        return False
    
    if len(url) > 2048:
        logger.warning(f"URL too long: {len(url)} characters")
        return False
    
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        
        # Check protocol
        if parsed.scheme not in ['http', 'https']:
            logger.warning(f"Unsupported protocol: {parsed.scheme}")
            return False
        
        # Check for test URLs
        if _is_test_url(url):
            return False
        
        return True
    except Exception as e:
        logger.warning(f"URL validation error: {str(e)}")
        return False

async def _process_url_input(url, request_id=None):
    """Process URL input by fetching content and processing it with citation service."""
    try:
        # Generate request_id if not provided
        if request_id is None:
            request_id = f"url_{int(time.time())}"
        
        logger.info(f"[URL Input {request_id}] Processing URL: {url}")
        
        # Validate URL first
        if not _validate_url(url):
            error_msg = 'Invalid or unsafe URL provided'
            logger.warning(f"[URL Input {request_id}] URL validation failed: {url}")
            return {
                'citations': [],
                'clusters': [],
                'success': False,
                'error': error_msg,
                'metadata': {
                    'source': 'url-input',
                    'url': url,
                    'rejected_reason': 'url_validation_failed'
                }
            }
        
        # Import required modules
        from src.api.services.citation_service import CitationService
        from src.progress_manager import fetch_url_content
        
        service = CitationService()
        
        # Fetch content from URL
        logger.info(f"[URL Input {request_id}] Fetching content from URL: {url}")
        try:
            content = fetch_url_content(url)
            logger.info(f"[URL Input {request_id}] Successfully fetched {len(content)} characters from URL")
        except Exception as fetch_error:
            error_msg = f'Failed to fetch content from URL: {str(fetch_error)}'
            logger.error(f"[URL Input {request_id}] {error_msg}", exc_info=True)
            return {
                'citations': [],
                'clusters': [],
                'success': False,
                'error': error_msg,
                'metadata': {
                    'source': 'url-input',
                    'url': url,
                    'rejected_reason': 'url_fetch_failed',
                    'fetch_error': str(fetch_error)
                }
            }
        
        # Check if content is empty or too short
        if not content or len(content.strip()) < 10:
            error_msg = 'URL returned empty or insufficient content for analysis'
            logger.warning(f"[URL Input {request_id}] {error_msg} - Content length: {len(content)}")
            return {
                'citations': [],
                'clusters': [],
                'success': False,
                'error': error_msg,
                'metadata': {
                    'source': 'url-input',
                    'url': url,
                    'rejected_reason': 'insufficient_content',
                    'content_length': len(content)
                }
            }
        
        # Process the fetched content using the queue system
        logger.info(f"[URL Input {request_id}] Processing fetched content with citation service")
        
        # Check if we should process immediately or queue
        input_data = {'type': 'text', 'text': content}
        if service.should_process_immediately(input_data):
            logger.info(f"[URL Input {request_id}] Processing URL content immediately (short content)")
            result = await service.process_immediately(input_data)
            
            return {
                'citations': result.get('citations', []),
                'clusters': result.get('clusters', []),
                'request_id': request_id,
                'success': True,
                'metadata': {
                    'source': 'url-input',
                    'url': url,
                    'url_domain': urlparse(url).netloc,
                    'content_length': len(content),
                    'processing_time': time.time(),
                    'processing_mode': 'immediate'
                }
            }
        else:
            logger.info(f"[URL Input {request_id}] Queuing URL content for async processing")
            
            # Import RQ for async task processing
            from rq import Queue
            from redis import Redis
            
            # Connect to Redis using environment variable or default
            redis_url = os.environ.get('REDIS_URL', 'redis://:caseStrainerRedis123@redis:6379/0')
            redis_conn = Redis.from_url(redis_url)
            queue = Queue('casestrainer', connection=redis_conn)
            
            # Enqueue the URL processing task
            job = queue.enqueue(
                'src.rq_worker.process_citation_task_direct',
                args=[request_id, 'url', {'url': url, 'content': content}],
                job_id=request_id,
                job_timeout='10m'
            )
            
            logger.info(f"[URL Input {request_id}] URL processing task enqueued with job_id: {job.id}")
            
            # Return task_id for frontend polling
            return {
                'task_id': request_id,
                'status': 'processing',
                'message': 'URL processing started',
                'request_id': request_id,
                'success': True,
                'metadata': {
                    'source': 'url-input',
                    'url': url,
                    'url_domain': urlparse(url).netloc,
                    'content_length': len(content),
                    'processing_mode': 'queued'
                }
            }
        
    except Exception as e:
        logger.error(f"[URL Input {request_id}] Error: {str(e)}", exc_info=True)
        raise