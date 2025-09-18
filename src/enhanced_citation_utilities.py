"""
Enhanced Citation Utilities - Additional Classes
Contains the StatuteFilter and ExtractionDebugger classes extracted from deprecated files.
This completes the feature extraction from the unified_citation_processor.py and related deprecated files.
"""

import re
from src.config import DEFAULT_REQUEST_TIMEOUT, COURTLISTENER_TIMEOUT, CASEMINE_TIMEOUT, WEBSEARCH_TIMEOUT, SCRAPINGBEE_TIMEOUT

import time
import logging
from typing import List, Dict, Any, Optional


class StatuteFilter:
    """
    Filters out statute citations from legal text processing.
    Extracted from unified_citation_processor.py.
    """
    
    def __init__(self):
        self.statute_patterns = self._init_statute_patterns()
        self.enabled = True
    
    def _init_statute_patterns(self) -> List[str]:
        """Initialize patterns for statute identification."""
        return [
            r'\b\d+\s+U\.?S\.?C\.?\s+§?\s*\d+',
            r'\b\d+\s+USC\s+§?\s*\d+',
            
            r'\bRCW\s+\d+\.\d+\.\d+',
            r'\bWAC\s+\d+\-\d+\-\d+',
            r'\bCal\.?\s+Code\s+§?\s*\d+',
            r'\bTex\.?\s+Code\s+§?\s*\d+',
            r'\bN\.?Y\.?\s+[A-Z]+\.?\s+Law\s+§?\s*\d+',
            
            r'\b\d+\s+C\.?F\.?R\.?\s+§?\s*\d+',
            r'\b\d+\s+CFR\s+§?\s*\d+',
            
            r'\b§\s*\d+[\.\-]\d+',
            r'\bSection\s+\d+[\.\-]\d+',
            r'\bSec\.\s+\d+[\.\-]\d+',
        ]
    
    def is_statute(self, text: str) -> bool:
        """Check if the given text appears to be a statute citation."""
        if not self.enabled:
            return False
        
        for pattern in self.statute_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        return False
    
    def filter_statutes(self, citations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter out statute citations from a list of citations."""
        if not self.enabled:
            return citations
        
        filtered = []
        for citation in citations:
            citation_text = citation.get('citation', '')
            if not self.is_statute(citation_text):
                filtered.append(citation)
            else:
                logger = logging.getLogger(__name__)
        
        return filtered
    
    def enable(self):
        """Enable statute filtering."""
        self.enabled = True
    
    def disable(self):
        """Disable statute filtering."""
        self.enabled = False


class ExtractionDebugger:
    """
    Debugging utilities for citation extraction pipeline.
    Extracted from unified_citation_processor.py.
    """
    
    def __init__(self):
        self.debug_enabled = False
        self.trace_logs = []
        self.extraction_steps = []
    
    def enable_debug(self):
        """Enable debug mode."""
        self.debug_enabled = True
        self.trace_logs = []
        self.extraction_steps = []
    
    def disable_debug(self):
        """Disable debug mode."""
        self.debug_enabled = False
    
    def log_step(self, step_name: str, data: Any, metadata: Optional[Dict] = None):
        """Log an extraction step for debugging."""
        if not self.debug_enabled:
            return
        
        logger = logging.getLogger(__name__)
        
        step_info = {
            'step': step_name,
            'timestamp': time.time(),
            'data_type': type(data).__name__,
            'data_size': len(data) if hasattr(data, '__len__') else 1,
            'metadata': metadata or {}
        }
        
        self.extraction_steps.append(step_info)
    
    def log_citation_processing(self, citation: Dict[str, Any], stage: str, result: Any):
        """Log citation processing details."""
        if not self.debug_enabled:
            return
        
        logger = logging.getLogger(__name__)
        
        log_entry = {
            'citation': citation.get('citation', ''),
            'stage': stage,
            'result_type': type(result).__name__,
            'result': str(result)[:200] if result else None,  # Truncate for readability
            'timestamp': time.time()
        }
        
        self.trace_logs.append(log_entry)
    
    def get_debug_summary(self) -> Dict[str, Any]:
        """Get a summary of debug information."""
        return {
            'debug_enabled': self.debug_enabled,
            'total_steps': len(self.extraction_steps),
            'total_citation_logs': len(self.trace_logs),
            'steps': self.extraction_steps,
            'trace_logs': self.trace_logs
        }
    
    def clear_debug_data(self):
        """Clear all debug data."""
        self.trace_logs = []
        self.extraction_steps = []
    
    def debug_extraction_pipeline(self, text: str, citations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Debug the entire extraction pipeline with detailed logging.
        Extracted from unified_citation_processor.py.
        """
        logger = logging.getLogger(__name__)
        
        self.enable_debug()
        
        debug_info = {
            'input_text_length': len(text),
            'input_citations_count': len(citations),
            'steps': [],
            'errors': [],
            'warnings': []
        }
        
        try:
            self.log_step('analyze_input', text, {'length': len(text)})
            debug_info['steps'].append('analyze_input')
            
            for i, citation in enumerate(citations):
                try:
                    self.log_citation_processing(citation, 'initial_processing', citation)
                    
                    case_name = citation.get('case_name', citation.get('extracted_case_name'))
                    self.log_citation_processing(citation, 'case_name_extraction', case_name)
                    
                    date = citation.get('date', citation.get('extracted_date'))
                    self.log_citation_processing(citation, 'date_extraction', date)
                    
                    try:
                        from src.citation_utils_consolidated import validate_extraction_quality
                        validation = validate_extraction_quality(citation)
                        self.log_citation_processing(citation, 'validation', validation)
                    except ImportError:
                        logger.warning("Could not import validate_extraction_quality for debugging")
                    
                except Exception as e:
                    error_info = f"Error processing citation {i}: {e}"
                    debug_info['errors'].append(error_info)
                    logger.error(error_info)
            
            debug_info['steps'].append('citation_processing')
            
            final_stats = {
                'processed_citations': len(citations),
                'extraction_steps': len(self.extraction_steps),
                'trace_logs': len(self.trace_logs)
            }
            
            self.log_step('final_analysis', final_stats)
            debug_info['steps'].append('final_analysis')
            debug_info['final_stats'] = final_stats
            
        except Exception as e:
            debug_info['errors'].append(f"Pipeline error: {e}")
            logger.error(f"Debug pipeline error: {e}")
        
        return debug_info



def setup_date_tracing():
    """
    Set up date tracing for debugging date extraction.
    Extracted from unified_citation_processor.py.
    """
    date_logger = logging.getLogger('date_tracing')
    date_logger.setLevel(logging.DEBUG)
    
    if not date_logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('[DATE_TRACE] %(asctime)s - %(message)s')
        handler.setFormatter(formatter)
        date_logger.addHandler(handler)
    
    return date_logger


def trace_date_extraction(citation: Dict[str, Any], context: str, result: Optional[str], method: str):
    """
    Trace date extraction for debugging.
    Extracted from unified_citation_processor.py.
    """
    date_logger = logging.getLogger('date_tracing')
    
    citation_text = citation.get('citation', '')
    
    date_logger.debug(f"Citation: {citation_text}")
    date_logger.debug(f"Method: {method}")
    date_logger.debug(f"Context: {context[:100]}..." if len(context) > 100 else f"Context: {context}")
    date_logger.debug(f"Result: {result}")
    date_logger.debug("---")


def extract_year_from_multiple_sources(citation: Dict[str, Any], context: str) -> Optional[str]:
    """
    Extract year from multiple sources with fallback strategies.
    Extracted from unified_citation_processor.py.
    """
    logger = logging.getLogger(__name__)
    
    citation_text = citation.get('citation', '')
    
    year_patterns = [
        r'\(\s*(\d{4})\s*\)',  # (2023)
        r'\(\s*[A-Za-z\s,]+(\d{4})\s*\)',  # (Wash. 2023)
        r'\(\s*(\d{4})\s*[A-Za-z\s,]*\)',  # (2023 Wash.)
    ]
    
    for pattern in year_patterns:
        match = re.search(pattern, context)
        if match:
            year = match.group(1)
            if 1800 <= int(year) <= 2100:
                trace_date_extraction(citation, context, year, f"parentheses_pattern: {pattern}")
                return year
    
    citation_year_match = re.search(r'(\d{4})', citation_text)
    if citation_year_match:
        year = citation_year_match.group(1)
        if 1800 <= int(year) <= 2100:
            trace_date_extraction(citation, context, year, "citation_text")
            return year
    
    context_year_match = re.search(r'\b(\d{4})\b', context)
    if context_year_match:
        year = context_year_match.group(1)
        if 1800 <= int(year) <= 2100:
            trace_date_extraction(citation, context, year, "context_search")
            return year
    
    trace_date_extraction(citation, context, None, "no_year_found")
    return None


def time_function(func):
    """
    Decorator to time function execution.
    Extracted from unified_citation_processor.py.
    """
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        
        logger = logging.getLogger(__name__)
        
        return result
    
    return wrapper


@time_function
def extract_case_info_comprehensive(text: str, start: int, end: int, 
                                  enable_debug: bool = False,
                                  enable_ocr_correction: bool = True,
                                  enable_statute_filtering: bool = True) -> Dict[str, Any]:
    """
    Comprehensive case info extraction with all available enhancements.
    This combines all the extracted features into a single high-level function.
    """
    logger = logging.getLogger(__name__)
    
    statute_filter = StatuteFilter() if enable_statute_filtering else None
    debugger = ExtractionDebugger() if enable_debug else None
    
    try:
        from src.citation_utils_consolidated import (
            OCRCorrector, ConfidenceScorer, extract_case_info_enhanced_with_position, 
            get_adaptive_context
        )
        ocr_corrector = OCRCorrector() if enable_ocr_correction else None
        confidence_scorer = ConfidenceScorer()
    except ImportError as e:
        logger.warning(f"Could not import some citation utilities: {e}")
        ocr_corrector = None
        confidence_scorer = None
    
    if enable_debug and debugger:
        debugger.enable_debug()
        debugger.log_step('start_comprehensive_extraction', {'start': start, 'end': end})
    
    try:
        citation_text = text[start:end]
        
        if ocr_corrector:
            corrected_text = ocr_corrector.correct_text(citation_text)
            if corrected_text != citation_text:
                citation_text = corrected_text
        
        if statute_filter and statute_filter.is_statute(citation_text):
            if enable_debug and debugger:
                debugger.log_step('statute_filtered', citation_text)
            return {'filtered': True, 'reason': 'statute', 'citation_text': citation_text}
        
        citation = {'citation': citation_text}
        
        if 'extract_case_info_enhanced_with_position' in locals():
            enhanced_result = extract_case_info_enhanced_with_position(text, start, end)
        else:
            enhanced_result = {'citation_text': citation_text}
        
        final_confidence = 0.5  # Default confidence
        if confidence_scorer and 'get_adaptive_context' in locals():
            context = get_adaptive_context(text, start, end)
            final_confidence = confidence_scorer.calculate_citation_confidence(enhanced_result, context)
        
        final_result = {
            **enhanced_result,
            'comprehensive_confidence': final_confidence,
            'ocr_corrected': ocr_corrector is not None,
            'statute_filtered': statute_filter is not None,
            'debug_enabled': enable_debug
        }
        
        if enable_debug and debugger:
            debugger.log_step('comprehensive_extraction_complete', final_result)
            final_result['debug_info'] = debugger.get_debug_summary()
        
        return final_result
    
    except Exception as e:
        logger.error(f"Error in comprehensive extraction: {e}")
        return {'error': str(e), 'citation_text': citation_text if 'citation_text' in locals() else ''}


if __name__ == "__main__":
    print("=== Enhanced Citation Utilities Test ===")
    
    statute_filter = StatuteFilter()
    test_statutes = [
        "RCW 2.60.020",
        "28 U.S.C. § 1254",
        "345 P.3d 123",  # Not a statute
        "123 Wn.2d 456"  # Not a statute
    ]
    
    print("\n--- Statute Filter Test ---")
    for test in test_statutes:
        is_statute = statute_filter.is_statute(test)
        print(f"'{test}' -> {'STATUTE' if is_statute else 'CASE LAW'}")
    
    debugger = ExtractionDebugger()
    debugger.enable_debug()
    
    print("\n--- Extraction Debugger Test ---")
    sample_citations = [
        {'citation': '123 Wn.2d 456', 'case_name': 'Test Case'},
        {'citation': '456 P.3d 789', 'case_name': 'Another Case'}
    ]
    
    debug_result = debugger.debug_extraction_pipeline("Sample text", sample_citations)
    print(f"Debug steps: {len(debug_result['steps'])}")
    print(f"Processed citations: {debug_result['final_stats']['processed_citations']}")
    
    print("\n=== Feature Extraction Complete ===")
























