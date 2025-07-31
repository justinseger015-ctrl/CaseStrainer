"""
Vue API Endpoints Blueprint
Main API routes for the CaseStrainer application
"""

import os
import sys
import uuid
import logging
import traceback
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from .api.services.citation_service import CitationService
from .database_manager import get_database_manager

logger = logging.getLogger(__name__)

# Create the blueprint
vue_api = Blueprint('vue_api', __name__)

# Initialize citation service
citation_service = CitationService()

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
            version_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'VERSION')
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
            from .api.services.citation_service import CitationService
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
def analyze():
    print("[DEBUG PRINT] /analyze endpoint called")
    logger.info("=== ANALYZE ENDPOINT CALLED ===")
    logger.info(f"Request method: {request.method}")
    logger.info(f"Content type: {request.content_type}")
    try:
        if 'file' in request.files:
            logger.info("File upload detected in request.files")
            return _handle_file_upload()
        elif request.is_json:
            logger.info("JSON input detected in request")
            return _handle_json_input()
        elif request.form:
            logger.info("Form input detected in request.form")
            return _handle_form_input()
        else:
            logger.error("Invalid or missing input. No file, JSON, or form data found.")
            return jsonify({'error': 'Invalid or missing input. Please provide text, file, or URL.', 'citations': [], 'clusters': []}), 400
    except Exception as e:
        logger.error(f"Error in analyze endpoint: {e}", exc_info=True)
        return jsonify({'error': 'Analysis failed', 'details': str(e), 'citations': [], 'clusters': []}), 500

@vue_api.route('/analyze_enhanced', methods=['POST'])
def analyze_enhanced():
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
                # Type: ignore for coroutine access
                result = citation_service.process_citation_task(
                    task_id, 
                    'text', 
                    {'text': text}
                )  # type: ignore
            
            # Type: ignore for coroutine access
            if result['status'] == 'completed':  # type: ignore
                # Type: ignore for coroutine access
                return jsonify({
                    'citations': result['citations'],  # type: ignore
                    'clusters': result.get('clusters', []),  # type: ignore
                    'success': True,
                    'statistics': result.get('statistics', {}),  # type: ignore
                    'metadata': result.get('metadata', {})  # type: ignore
                })
            else:
                return jsonify({
                    'error': result.get('message', 'Processing failed'),
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
    try:
        from rq import Queue
        from redis import Redis
        
        # Get Redis connection
        # Use correct Redis URL for local development (Docker port mapping)
        redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6380/0')
        redis_conn = Redis.from_url(redis_url)
        queue = Queue('casestrainer', connection=redis_conn)
        
        # Get the job
        job = queue.fetch_job(task_id)
        
        if not job:
            return jsonify({
                'error': 'Task not found',
                'task_id': task_id,
                'citations': [],
                'clusters': []
            }), 404
        
        # Check job status
        if job.is_finished:
            # Job completed successfully
            result = job.result
            if result and result.get('status') in ['success', 'completed']:
                return jsonify({
                    'status': 'completed',
                    'task_id': task_id,
                    'citations': result.get('citations', []),
                    'clusters': result.get('clusters', []),
                    'statistics': result.get('statistics', {}),
                    'metadata': result.get('metadata', {}),
                    'success': True
                })
            else:
                return jsonify({
                    'status': 'failed',
                    'task_id': task_id,
                    'error': result.get('error', 'Processing failed') if result else 'Unknown error',
                    'success': False,
                    'citations': [],
                    'clusters': []
                })
        
        elif job.is_failed:
            # Job failed
            return jsonify({
                'status': 'failed',
                'task_id': task_id,
                'error': str(job.exc_info) if job.exc_info else 'Job failed',
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
            return jsonify({
                'status': 'queued',
                'task_id': task_id,
                'message': 'Task is queued and waiting to be processed',
                'position': queue.get_job_position(task_id),
                'success': True,
                'citations': [],
                'clusters': []
            })
            
    except Exception as e:
        logger.error(f"Error checking task status for {task_id}: {e}", exc_info=True)
        return jsonify({
            'error': 'Failed to check task status',
            'details': str(e),
            'task_id': task_id,
            'citations': [],
            'clusters': []
        }), 500

def _handle_file_upload():
    """Handle file upload with proper async RQ worker processing"""
    try:
        # Get Redis connection for async processing
        from rq import Queue
        from redis import Redis
        
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided', 'citations': [], 'clusters': []}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected', 'citations': [], 'clusters': []}), 400
        
        # Validate file type
        allowed_extensions = {'pdf', 'txt', 'doc', 'docx', 'rtf'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        
        if file_ext not in allowed_extensions:
            return jsonify({'error': f'File type not allowed. Allowed types: {", ".join(allowed_extensions)}', 'citations': [], 'clusters': []}), 400
        
        # Generate unique filename
        filename = file.filename
        unique_filename = f"{uuid.uuid4()}_{filename}"
        
        # Ensure uploads directory exists
        uploads_dir = os.path.join(os.getcwd(), 'uploads')
        os.makedirs(uploads_dir, exist_ok=True)
        
        # Save file temporarily
        temp_file_path = os.path.join(uploads_dir, unique_filename)
        file.save(temp_file_path)
        
        try:
            # Generate task ID for async processing
            task_id = str(uuid.uuid4())
            
            # Get Redis connection
            # Use correct Redis URL for local development (Docker port mapping)
            redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6380/0')
            redis_conn = Redis.from_url(redis_url)
            queue = Queue('casestrainer', connection=redis_conn)
            
            # Queue the task for background processing
            job = queue.enqueue(
                citation_service.process_citation_task,
                task_id,
                'file',
                {
                    'file_path': temp_file_path,
                    'filename': filename,
                    'file_ext': file_ext
                },
                job_id=task_id,
                job_timeout='10m',
                result_ttl=3600  # Keep results for 1 hour
            )
            
            logger.info(f"Queued file processing task {task_id} for background processing")
            
            # Return immediately with task ID for polling
            return jsonify({
                'status': 'processing',
                'task_id': task_id,
                'message': 'File uploaded and queued for processing',
                'job_id': job.id,
                'success': True
            }), 202  # 202 Accepted
            
        except Exception as e:
            # Ensure cleanup even if queuing fails
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            raise
            
    except Exception as e:
        logger.error(f"File upload error: {e}", exc_info=True)
        return jsonify({'error': f'Failed to process file: {str(e)}', 'citations': [], 'clusters': []}), 500

def _handle_json_input():
    logger.info("_handle_json_input called")
    data = request.get_json()
    logger.info(f"JSON data received: {data}")
    if not data:
        logger.error("No JSON data provided")
        return jsonify({'error': 'No JSON data provided', 'citations': [], 'clusters': []}), 400
    input_type = data.get('type', 'text')
    logger.info(f"Input type: {input_type}")
    if input_type == 'text':
        text = data.get('text', '')
        print(f"[DEBUG PRINT] Received text at /analyze, length: {len(text)}")
        logger.info(f"Text input received: {text[:100]}... (length: {len(text)})")
        if not text:
            logger.error("No text provided in JSON input")
            return jsonify({'error': 'No text provided', 'citations': [], 'clusters': []}), 400
        return _process_text_input(text)
    elif input_type == 'url':
        url = data.get('url', '')
        logger.info(f"URL input received: {url}")
        if not url:
            logger.error("No URL provided in JSON input")
            return jsonify({'error': 'No URL provided', 'citations': [], 'clusters': []}), 400
        return _process_url_input(url)
    else:
        logger.error(f"Invalid input type: {input_type}")
        return jsonify({'error': 'Invalid input type. Use \"text\" or \"url\"', 'citations': [], 'clusters': []}), 400

def _handle_form_input():
    """Handle form input processing"""
    data = request.form.to_dict()
    input_type = data.get('type', 'text')
    
    if input_type == 'text':
        text = data.get('text', '')
        if not text:
            return jsonify({'error': 'No text provided', 'citations': [], 'clusters': []}), 400
        return _process_text_input(text)
        
    elif input_type == 'url':
        url = data.get('url', '')
        if not url:
            return jsonify({'error': 'No URL provided', 'citations': [], 'clusters': []}), 400
        return _process_url_input(url)
        
    else:
        return jsonify({'error': 'Invalid input type. Use "text" or "url"', 'citations': [], 'clusters': []}), 400

def _process_text_input(text, source_name="pasted_text"):
    """Process text input with citation extraction and verification"""
    try:
        logger.info(f"Processing text input: {text[:100]}... (length: {len(text)})")
        
        # Use real citation service for processing
        if citation_service.should_process_immediately({'type': 'text', 'text': text}):
            logger.info("Processing short text immediately")
            result = citation_service.process_immediately({'type': 'text', 'text': text})
            logger.info(f"Immediate processing result: {result}")
            
            if result['status'] in ['completed', 'success']:
                logger.info("Returning successful immediate processing result")
                return jsonify({
                    'citations': result['citations'],
                    'clusters': result.get('clusters', []),
                    'success': True,
                    'statistics': result.get('statistics', {}),
                    'metadata': result.get('metadata', {})
                })
            else:
                logger.error(f"Immediate processing failed: {result.get('message', 'Text processing failed')}")
                return jsonify({'error': result.get('message', 'Text processing failed'), 'success': False, 'citations': [], 'clusters': []}), 500
        else:
            logger.info("Processing longer text asynchronously with RQ workers")
            task_id = str(uuid.uuid4())
            
            # Queue the task for RQ worker processing
            from rq import Queue
            from redis import Redis
            
            # Get Redis connection
            # Use correct Redis URL for local development (Docker port mapping)
            redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6380/0')
            redis_conn = Redis.from_url(redis_url)
            queue = Queue('casestrainer', connection=redis_conn)
            
            # Queue the task for background processing
            job = queue.enqueue(
                citation_service.process_citation_task,
                task_id,
                'text',
                {'text': text, 'source_name': source_name},
                job_id=task_id,
                job_timeout='10m',
                result_ttl=3600  # Keep results for 1 hour
            )
            
            logger.info(f"Queued text processing task {task_id} for background processing (job id: {job.id})")
            
            # Return immediately with task ID for polling
            return jsonify({
                'status': 'processing',
                'task_id': task_id,
                'message': 'Text queued for processing',
                'job_id': job.id,
                'success': True
            }), 202  # 202 Accepted
            
    except Exception as e:
        logger.error(f"Error processing text input: {e}", exc_info=True)
        return jsonify({
            'error': 'Text processing failed', 
            'details': str(e), 
            'citations': [], 
            'validation_results': [],
            'success': False
        }), 500

def _process_url_input(url):
    """Process URL input with proper async RQ worker processing"""
    try:
        # Generate task ID for async processing
        task_id = str(uuid.uuid4())
        
        # Queue the task for RQ worker processing
        from rq import Queue
        from redis import Redis
        
        # Get Redis connection
        # Use correct Redis URL for local development (Docker port mapping)
        redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6380/0')
        redis_conn = Redis.from_url(redis_url)
        queue = Queue('casestrainer', connection=redis_conn)
        
        # Queue the task for background processing
        job = queue.enqueue(
            citation_service.process_citation_task,
            task_id,
            'url',
            {'url': url},
            job_id=task_id,
            job_timeout='10m',
            result_ttl=3600  # Keep results for 1 hour
        )
        
        logger.info(f"Queued URL processing task {task_id} for background processing")
        
        # Return immediately with task ID for polling
        return jsonify({
            'status': 'processing',
            'task_id': task_id,
            'message': 'URL queued for processing',
            'job_id': job.id,
            'success': True
        }), 202  # 202 Accepted
        
    except Exception as e:
        logger.error(f"Error queuing URL input: {e}", exc_info=True)


@vue_api.route('/processing_progress', methods=['GET'])
def processing_progress():
    """
    Legacy processing progress endpoint for frontend compatibility.
    Since we now use immediate processing for small texts and RQ tasks for large files,
    this endpoint provides appropriate responses for both cases.
    """
    try:
        # Get query parameters
        total_param = request.args.get('total', '0')
        task_id = request.args.get('task_id', None)
        
        # If we have a task_id, check the RQ task status
        if task_id:
            try:
                from rq import Queue
                from redis import Redis
                
                # Use correct Redis URL for local development (Docker port mapping)
                redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6380/0')
                redis_conn = Redis.from_url(redis_url)
                queue = Queue('casestrainer', connection=redis_conn)
                
                job = queue.fetch_job(task_id)
                if job:
                    if job.is_finished:
                        result = job.result
                        if result and result.get('status') in ['success', 'completed']:
                            citation_count = len(result.get('citations', []))
                            return jsonify({
                                'status': 'success',
                                'processed_citations': citation_count,
                                'total_citations': citation_count,
                                'is_complete': True,
                                'task_id': task_id
                            })
                    elif job.is_failed:
                        return jsonify({
                            'status': 'error',
                            'processed_citations': 0,
                            'total_citations': int(total_param) if total_param.isdigit() else 0,
                            'is_complete': False,
                            'error': str(job.exc_info) if job.exc_info else 'Processing failed',
                            'task_id': task_id
                        })
                    else:
                        # Still processing
                        estimated_total = int(total_param) if total_param.isdigit() else 100
                        return jsonify({
                            'status': 'success',
                            'processed_citations': 0,
                            'total_citations': estimated_total,
                            'is_complete': False,
                            'task_id': task_id
                        })
            except Exception as e:
                logger.warning(f"Error checking RQ task {task_id}: {e}")
        
        # For immediate processing (no task_id), return completed state
        # This handles the case where small texts are processed immediately
        estimated_total = int(total_param) if total_param.isdigit() else 0
        
        return jsonify({
            'status': 'success',
            'processed_citations': estimated_total,
            'total_citations': estimated_total,
            'is_complete': True,
            'message': 'Immediate processing completed'
        })
        
    except Exception as e:
        logger.error(f"Error in processing_progress endpoint: {e}")
        return jsonify({
            'status': 'error',
            'processed_citations': 0,
            'total_citations': 0,
            'is_complete': False,
            'error': str(e)
        }), 500


# Citation Export Endpoints

@vue_api.route('/export', methods=['POST'])
def export_citations():
    """
    Export citations in various formats (text, bibtex, endnote, csv, json).
    
    Expected JSON payload:
    {
        "citations": [...],  // Array of citation objects
        "format": "bibtex",  // Export format
        "filename": "optional_filename"  // Optional custom filename
    }
    """
    try:
        from .citation_export import CitationExporter
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        citations = data.get('citations', [])
        format_type = data.get('format', 'json').lower()
        filename = data.get('filename')
        
        if not citations:
            return jsonify({'error': 'No citations provided'}), 400
        
        # Validate format
        valid_formats = ['text', 'txt', 'bibtex', 'bib', 'endnote', 'ris', 'csv', 'json']
        if format_type not in valid_formats:
            return jsonify({
                'error': f'Unsupported format: {format_type}',
                'supported_formats': valid_formats
            }), 400
        
        # Create exporter and export citations
        exporter = CitationExporter()
        filepath = exporter.export_citations(citations, format_type, filename)
        
        # Read the exported file content for download
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Determine MIME type
        mime_types = {
            'text': 'text/plain',
            'txt': 'text/plain',
            'bibtex': 'application/x-bibtex',
            'bib': 'application/x-bibtex',
            'endnote': 'application/x-research-info-systems',
            'ris': 'application/x-research-info-systems',
            'csv': 'text/csv',
            'json': 'application/json'
        }
        
        response_data = {
            'success': True,
            'format': format_type,
            'filename': os.path.basename(filepath),
            'content': content,
            'mime_type': mime_types.get(format_type, 'text/plain'),
            'citation_count': len(citations)
        }
        
        logger.info(f"Successfully exported {len(citations)} citations to {format_type} format")
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Error exporting citations: {e}")
        return jsonify({
            'error': 'Export failed',
            'details': str(e)
        }), 500


@vue_api.route('/export/formats', methods=['GET'])
def get_export_formats():
    """
    Get available export formats and their descriptions.
    """
    formats = {
        'text': {
            'name': 'Plain Text',
            'extension': 'txt',
            'description': 'Human-readable text format with citation details',
            'mime_type': 'text/plain'
        },
        'bibtex': {
            'name': 'BibTeX',
            'extension': 'bib',
            'description': 'LaTeX bibliography format for academic papers',
            'mime_type': 'application/x-bibtex'
        },
        'endnote': {
            'name': 'EndNote/RIS',
            'extension': 'ris',
            'description': 'Reference manager format (EndNote, Zotero, Mendeley)',
            'mime_type': 'application/x-research-info-systems'
        },
        'csv': {
            'name': 'CSV',
            'extension': 'csv',
            'description': 'Comma-separated values for spreadsheet analysis',
            'mime_type': 'text/csv'
        },
        'json': {
            'name': 'JSON',
            'extension': 'json',
            'description': 'Structured data format for programmatic use',
            'mime_type': 'application/json'
        }
    }
    
    return jsonify({
        'success': True,
        'formats': formats
    })
