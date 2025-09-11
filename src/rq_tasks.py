"""
RQ Task wrapper functions for CaseStrainer
"""
import asyncio
from src.config import DEFAULT_REQUEST_TIMEOUT, COURTLISTENER_TIMEOUT, CASEMINE_TIMEOUT, WEBSEARCH_TIMEOUT, SCRAPINGBEE_TIMEOUT

import logging

logger = logging.getLogger(__name__)

def process_citation_task_wrapper(task_id: str, input_type: str, input_data: dict):
    """Wrapper function to create CitationService instance and call process_citation_task."""
    from src.api.services.citation_service import CitationService
    
    service = CitationService()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        result = loop.run_until_complete(service.process_citation_task(task_id, input_type, input_data))
        logger.info(f"Task {task_id} completed successfully")
        return result
    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}")
        raise
    finally:
        loop.close() 