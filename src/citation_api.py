"""
API wrapper for integrating enhanced citation processing with Flask routes
"""

import logging
from src.config import DEFAULT_REQUEST_TIMEOUT, COURTLISTENER_TIMEOUT, CASEMINE_TIMEOUT, WEBSEARCH_TIMEOUT, SCRAPINGBEE_TIMEOUT

from flask import Blueprint, request, jsonify, current_app
from typing import Dict, Any, Optional
import asyncio
from dataclasses import dataclass

from unified_citation_processor_v2 import UnifiedCitationProcessorV2 as UnifiedCitationProcessor

logger = logging.getLogger(__name__)

citation_api = Blueprint('citation_api', __name__)

@dataclass
class ExtractionConfig:
    min_confidence_threshold: float = 0.5

_processor = None

def get_citation_processor() -> UnifiedCitationProcessor:
    """Get the citation processor instance."""
    global _processor
    if _processor is None:
        _processor = UnifiedCitationProcessor()
    return _processor

@citation_api.route('/citations/analyze', methods=['POST'])
def analyze_document_citations():
    """API endpoint for analyzing citations in documents"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        document_text = data.get('text', '')
        document_type = data.get('document_type', 'legal_brief')
        user_context = data.get('context', {})
        
        if not document_text:
            return jsonify({'error': 'No document text provided'}), 400
        
        processor = get_citation_processor()
        
        # Use modern process_text instead of deprecated extract_citations_from_text
        result = processor.process_text(document_text)
        citations = result.get('citations', [])
        
        results = {
            'citations': [citation.__dict__ for citation in citations] if citations else [],
            'total_count': len(citations) if citations else 0,
            'status': 'success'
        }
        
        return jsonify(results)
        
    except Exception as e:
        logger.error(f"Error in citation analysis API: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error', 'details': str(e)}), 500

@citation_api.route('/citations/validate', methods=['POST'])
def validate_single_citation():
    """API endpoint for validating a single citation"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        citation_text = data.get('citation', '')
        
        if not citation_text:
            return jsonify({'error': 'No citation provided'}), 400
        
        processor = get_citation_processor()
        
        # Use modern process_text instead of deprecated extract_citations_from_text
        result = processor.process_text(citation_text)
        citations = result.get('citations', [])
        
        if citations:
            citation = citations[0]
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                validation_status = loop.run_until_complete(
                    processor._verify_citations([citation])
                )
                enhanced_data = citation  # Use the citation directly
            finally:
                loop.close()
            
            result = {
                'valid': validation_status == 'valid',
                'validation_status': validation_status,
                'citation_data': {
                    'canonical_name': citation.canonical_name,
                    'year': citation.year,
                    'court': citation.court,
                    'reporter': citation.reporter,
                    'confidence_score': citation.confidence_score
                },
                'enhancements': enhanced_data
            }
        else:
            result = {
                'valid': False,
                'validation_status': 'not_found',
                'error': 'Could not extract citation from provided text'
            }
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in citation validation API: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error', 'details': str(e)}), 500

@citation_api.route('/citations/extract', methods=['POST'])
def extract_citations():
    """API endpoint for extracting citations from text"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        text = data.get('text', '')
        config_data = data.get('config', {})
        
        if not text:
            return jsonify({'error': 'No text provided'}), 400
        
        config = ExtractionConfig(**config_data) if config_data else ExtractionConfig()
        
        processor = get_citation_processor()
        # Use modern process_text instead of deprecated extract_citations_from_text
        result = processor.process_text(text)
        citations = result.get('citations', [])
        
        citation_data = []
        for citation in citations:
            citation_data.append({
                'raw_text': citation.raw_text,
                'canonical_name': citation.canonical_name,
                'year': citation.year,
                'court': citation.court,
                'reporter': citation.reporter,
                'volume': citation.volume,
                'page': citation.page,
                'confidence_score': citation.confidence_score,
                'citation_type': citation.citation_type,
                'bluebook_format': citation.get_bluebook_format()
            })
        
        return jsonify({
            'success': True,
            'citations': citation_data,
            'count': len(citation_data)
        })
        
    except Exception as e:
        logger.error(f"Error in citation extraction API: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error', 'details': str(e)}), 500

@citation_api.route('/citations/stats', methods=['POST'])
def get_citation_statistics():
    """API endpoint for getting citation statistics"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        text = data.get('text', '')
        
        if not text:
            return jsonify({'error': 'No text provided'}), 400
        
        processor = get_citation_processor()
        # Use modern process_text instead of deprecated extract_citations_from_text
        result = processor.process_text(text)
        citations = result.get('citations', [])
        
        stats = {
            'total_citations': len(citations) if citations else 0,
            'citations_by_type': {},
            'citations_by_court': {},
            'citations_by_year': {}
        }
        
        if citations:
            for citation in citations:
                citation_type = getattr(citation, 'citation_type', 'unknown')
                stats['citations_by_type'][citation_type] = stats['citations_by_type'].get(citation_type, 0) + 1
                
                court = getattr(citation, 'court', 'unknown')
                stats['citations_by_court'][court] = stats['citations_by_court'].get(court, 0) + 1
                
                year = getattr(citation, 'year', 'unknown')
                stats['citations_by_year'][year] = stats['citations_by_year'].get(year, 0) + 1
        
        return jsonify({
            'success': True,
            'statistics': stats
        })
        
    except Exception as e:
        logger.error(f"Error in citation statistics API: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error', 'details': str(e)}), 500

@citation_api.route('/citations/health', methods=['GET'])
def citation_health_check():
    """Health check endpoint for citation services"""
    try:
        processor = get_citation_processor()
        
        test_text = "See Brown v. Board of Education, 347 U.S. 483 (1954)."
        # Use modern process_text instead of deprecated extract_citations_from_text
        result = processor.process_text(test_text)
        test_citations = result.get('citations', [])
        
        health_status = {
            'status': 'healthy',
            'services': {
                'citation_extraction': len(test_citations) > 0,
                'citation_processor': processor is not None,
                'citation_service': True  # Service is available through the processor
            },
            'test_citation_count': len(test_citations)
        }
        
        if all(health_status['services'].values()):
            return jsonify(health_status), 200
        else:
            health_status['status'] = 'degraded'
            return jsonify(health_status), 503
            
    except Exception as e:
        logger.error(f"Error in citation health check: {e}", exc_info=True)
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 503

# def enhanced_analyze():
#     try:
#         data = request.get_json()
#         if not data:
#             return jsonify({'error': 'No JSON data provided'}), 400
#         input_type = data.get('type', 'text')
#         if input_type == 'text':
#             text = data.get('text', '')
#             document_type = data.get('document_type', 'legal_brief')
#             if not text:
#                 return jsonify({'error': 'No text provided'}), 400
#             processor = get_citation_processor()
#             loop = asyncio.new_event_loop()
#             asyncio.set_event_loop(loop)
#             try:
#                 citation_results = loop.run_until_complete(
#                     processor.process_document_citations(text, document_type)
#             finally:
#                 loop.close()
#             legacy_format = {
#                     for c in citation_results['citations']
#             return jsonify(legacy_format)
#         else:
#             return jsonify({'error': 'File upload processing not implemented in this endpoint'}), 501
#     except Exception as e:
#         logger.error(f"Error in enhanced analyze endpoint: {e}", exc_info=True)
#         return jsonify({'error': 'Analysis failed', 'details': str(e)}), 500
