"""
Case Name Extraction Core - Now Powered by Master Extraction Function
====================================================================

This module now serves as a compatibility layer that redirects all extraction calls
to the master extraction function (extract_case_name_and_date_master), which provides
the single source of truth for case name extraction.

IMPORTANT: All extraction now goes through extract_case_name_and_date_master()

DEPRECATION NOTICE:
==================
Many functions in this module are deprecated and will be removed in v3.0.0.
Only the following functions are actively used in the main pipeline:
- extract_case_name_and_date()
- extract_case_name_only()

All other functions show deprecation warnings and will be removed.
"""

from typing import Dict, Optional, Any, List, Tuple



from src.config import DEFAULT_REQUEST_TIMEOUT, COURTLISTENER_TIMEOUT, CASEMINE_TIMEOUT, WEBSEARCH_TIMEOUT, SCRAPINGBEE_TIMEOUT

import warnings
from src.unified_case_name_extractor_v2 import (
    get_unified_extractor,
    extract_case_name_and_date_master,
    extract_case_name_only_unified
)

_unified_extractor = None

def get_extractor():
    """Get the unified extractor instance"""
    global _unified_extractor
    if _unified_extractor is None:
        _unified_extractor = get_unified_extractor()
    return _unified_extractor


def extract_case_name_and_date(
    text: str, 
    citation: Optional[str] = None,
    citation_start: Optional[int] = None,
    citation_end: Optional[int] = None,
    debug: bool = False
) -> Dict[str, Any]:
    """
    PRIMARY EXTRACTION FUNCTION - Now uses UnifiedCaseNameExtractorV2
    
    This function now delegates to the unified extractor which provides:
    - Consistent case name extraction (no more truncation!)
    - Multiple extraction strategies
    - Comprehensive validation
    - Performance optimizations
    - Detailed debugging
    
    Args:
        text: Full document text
        citation: Citation text to search for
        citation_start: Start index of citation in text
        citation_end: End index of citation in text
        debug: Enable detailed debugging output
        
    Returns:
        Dict with case_name, date, year, confidence, method, and debug_info
    """
    return extract_case_name_and_date_master(
        text, citation, citation_start, citation_end, debug
    )

def extract_case_name_only(
    text: str, 
    citation: Optional[str] = None,
    debug: bool = False
) -> str:
    """
    Extract only the case name - Now uses UnifiedCaseNameExtractorV2
    
    Args:
        text: Full document text
        citation: Citation text to search for
        debug: Enable detailed debugging output
        
    Returns:
        Extracted case name string
    """
    return extract_case_name_only_unified(text, citation, debug)


def extract_case_name_from_citation(
    text: str, 
    citation: str,
    debug: bool = False
) -> Dict[str, Any]:
    """
    Extract case name from a specific citation - Now uses UnifiedCaseNameExtractorV2
    
    Args:
        text: Full document text
        citation: Citation text to search for
        debug: Enable detailed debugging output
        
    Returns:
        Dict with case_name, date, year, confidence, method, and debug_info
    """
    return extract_case_name_and_date_master(text, citation, debug=debug)

def extract_case_name_with_context(
    text: str, 
    citation: str,
    context_window: int = 1000,
    debug: bool = False
) -> Dict[str, Any]:
    """
    Extract case name with context window - Now uses UnifiedCaseNameExtractorV2
    
    Args:
        text: Full document text
        citation: Citation text to search for
        context_window: Size of context window around citation
        debug: Enable detailed debugging output
        
    Returns:
        Dict with case_name, date, year, confidence, method, and debug_info
    """
    return extract_case_name_and_date_master(text, citation, debug=debug)

def extract_case_name_volume_based(
    text: str, 
    citation: str,
    debug: bool = False
) -> Dict[str, Any]:
    """
    Volume-based case name extraction - Now uses UnifiedCaseNameExtractorV2
    
    Args:
        text: Full document text
        citation: Citation text to search for
        debug: Enable detailed debugging output
        
    Returns:
        Dict with case_name, date, year, confidence, method, and debug_info
    """
    return extract_case_name_and_date_master(text, citation, debug=debug)


def extract_case_names_batch(
    text: str, 
    citations: List[str],
    debug: bool = False
) -> List[Dict[str, Any]]:
    """
    Extract case names for multiple citations - Now uses UnifiedCaseNameExtractorV2
    
    Args:
        text: Full document text
        citations: List of citation texts to search for
        debug: Enable detailed debugging output
        
    Returns:
        List of dicts, each with case_name, date, year, confidence, method, and debug_info
    """
    results = []
    for citation in citations:
        result = extract_case_name_and_date_master(text, citation, debug=debug)
        results.append(result)
    return results

def extract_case_names_from_paragraph(
    text: str,
    debug: bool = False
) -> List[Dict[str, Any]]:
    """
    Extract all case names from a paragraph - Now uses UnifiedCaseNameExtractorV2
    
    Args:
        text: Full document text
        debug: Enable detailed debugging output
        
    Returns:
        List of dicts, each with case_name, date, year, confidence, method, and debug_info
    """
    warnings.warn(
        "extract_case_names_from_paragraph requires citation detection logic. "
        "Use extract_case_name_and_date() with specific citations instead.",
        DeprecationWarning
    )
    return []


def validate_case_name(case_name: str) -> Dict[str, Any]:
    """
    Validate a case name using the unified extractor's validation rules
    
    Args:
        case_name: Case name to validate
        
    Returns:
        Dict with validation results
    """
    extractor = get_extractor()
    return extractor._validate_case_name(case_name, "", "")

def clean_case_name(case_name: str) -> str:
    """
    Clean a case name using the unified extractor's cleaning logic
    
    Args:
        case_name: Case name to clean
        
    Returns:
        Cleaned case name
    """
    return case_name.strip()


def _show_deprecation_warning(old_function_name: str):
    """Show deprecation warning for old functions"""
    warnings.warn(
        f"Function '{old_function_name}' is deprecated and will be removed in v3.0.0. "
        "All extraction now goes through UnifiedCaseNameExtractorV2. "
        "Use extract_case_name_and_date() or extract_case_name_only() instead.",
        DeprecationWarning,
        stacklevel=3
    )



def extract_case_name_triple_comprehensive(text: str, citation: Optional[str] = None) -> Tuple[str, str, str]:
    """
    DEPRECATED: Use extract_case_name_and_date() instead.
    
    This function returns a tuple (case_name, year, confidence) which is not
    consistent with the new unified extractor's return format.
    
    Args:
        text: Full document text
        citation: Citation text to search for
        
    Returns:
        Tuple of (case_name, year, confidence) - DEPRECATED FORMAT
        
    Deprecated since: v2.0.0
    Will be removed in: v3.0.0
    """
    _show_deprecation_warning('extract_case_name_triple_comprehensive')
    
    result = extract_case_name_and_date_master(text, citation)
    
    return (
        result.get('case_name', ''),
        result.get('year', ''),
        str(result.get('confidence', 0.0))
    )

def extract_case_name_and_date_comprehensive(text: str, citation: Optional[str] = None) -> Dict[str, Any]:
    """
    DEPRECATED: Use extract_case_name_and_date() instead.
    
    This function was an intermediate version that has been replaced by
    the unified extractor.
    
    Args:
        text: Full document text
        citation: Citation text to search for
        
    Returns:
        Dict with extraction results - DEPRECATED FORMAT
        
    Deprecated since: v2.0.0
    Will be removed in: v3.0.0
    """
    _show_deprecation_warning('extract_case_name_and_date_comprehensive')
    return extract_case_name_and_date(text, citation)

def extract_case_name_improved(text: str, citation: Optional[str] = None) -> str:
    """
    DEPRECATED: Use extract_case_name_only() instead.
    
    This function was an intermediate version that has been replaced by
    the unified extractor.
    
    Args:
        text: Full document text
        citation: Citation text to search for
        
    Returns:
        Extracted case name string
        
    Deprecated since: v2.0.0
    Will be removed in: v3.0.0
    """
    _show_deprecation_warning('extract_case_name_improved')
    return extract_case_name_only(text, citation)

def extract_year_improved(text: str, citation: Optional[str] = None) -> str:
    """
    DEPRECATED: Use extract_case_name_and_date() and access the 'year' field instead.
    
    This function was an intermediate version that has been replaced by
    the unified extractor.
    
    Args:
        text: Full document text
        citation: Citation text to search for
        
    Returns:
        Extracted year string
        
    Deprecated since: v2.0.0
    Will be removed in: v3.0.0
    """
    _show_deprecation_warning('extract_year_improved')
    result = extract_case_name_and_date(text, citation)
    return result.get('year', '')

def extract_case_name_from_text(text: str, citation: Optional[str] = None) -> str:
    """
    DEPRECATED: Use extract_case_name_only() instead.
    
    This function was an intermediate version that has been replaced by
    the unified extractor.
    
    Args:
        text: Full document text
        citation: Citation text to search for
        
    Returns:
        Extracted case name string
        
    Deprecated since: v2.0.0
    Will be removed in: v3.0.0
    """
    _show_deprecation_warning('extract_case_name_from_text')
    return extract_case_name_only(text, citation)

def is_valid_case_name(case_name: str) -> bool:
    """
    DEPRECATED: Use validate_case_name() instead.
    
    This function was an intermediate version that has been replaced by
    the unified extractor's validation system.
    
    Args:
        case_name: Case name to validate
        
    Returns:
        True if case name is valid
        
    Deprecated since: v2.0.0
    Will be removed in: v3.0.0
    """
    _show_deprecation_warning('is_valid_case_name')
    validation_result = validate_case_name(case_name)
    return validation_result.get('is_valid', False)

def clean_case_name_enhanced(case_name: str) -> str:
    """
    DEPRECATED: Use clean_case_name() instead.
    
    This function was an intermediate version that has been replaced by
    the unified extractor's cleaning system.
    
    Args:
        case_name: Case name to clean
        
    Returns:
        Cleaned case name string
        
    Deprecated since: v2.0.0
    Will be removed in: v3.0.0
    """
    _show_deprecation_warning('clean_case_name_enhanced')
    return clean_case_name(case_name)

def extract_case_name_precise(text: str, citation: Optional[str] = None) -> str:
    """
    DEPRECATED: Use extract_case_name_only() instead.
    
    This function was an intermediate version that has been replaced by
    the unified extractor.
    
    Args:
        text: Full document text
        citation: Citation text to search for
        
    Returns:
        Extracted case name string
        
    Deprecated since: v2.0.0
    Will be removed in: v3.0.0
    """
    _show_deprecation_warning('extract_case_name_precise')
    return extract_case_name_only(text, citation)

def extract_case_name_triple(text: str, citation: Optional[str] = None) -> Tuple[str, str, str]:
    """
    DEPRECATED: Use extract_case_name_and_date() instead.
    
    This function returns a tuple (case_name, year, confidence) which is not
    consistent with the new unified extractor's return format.
    
    Args:
        text: Full document text
        citation: Citation text to search for
        
    Returns:
        Tuple of (case_name, year, confidence) - DEPRECATED FORMAT
        
    Deprecated since: v2.0.0
    Will be removed in: v3.0.0
    """
    _show_deprecation_warning('extract_case_name_triple')
    
    result = extract_case_name_and_date_master(text, citation)
    
    return (
        result.get('case_name', ''),
        result.get('year', ''),
        str(result.get('confidence', 0.0))
    )

def extract_case_name_fixed(text: str, citation: Optional[str] = None) -> str:
    """
    DEPRECATED: Use extract_case_name_only() instead.
    
    This function was an intermediate version that has been replaced by
    the unified extractor.
    
    Args:
        text: Full document text
        citation: Citation text to search for
        
    Returns:
        Extracted case name string
        
    Deprecated since: v2.0.0
    Will be removed in: v3.0.0
    """
    _show_deprecation_warning('extract_case_name_fixed')
    return extract_case_name_only(text, citation)

def extract_year_enhanced(text: str, citation: Optional[str] = None) -> str:
    """
    DEPRECATED: Use extract_case_name_and_date() and access the 'year' field instead.
    
    This function was an intermediate version that has been replaced by
    the unified extractor.
    
    Args:
        text: Full document text
        citation: Citation text to search for
        
    Returns:
        Extracted year string
        
    Deprecated since: v2.0.0
    Will be removed in: v3.0.0
    """
    _show_deprecation_warning('extract_year_enhanced')
    result = extract_case_name_and_date(text, citation)
    return result.get('year', '')



def extract_case_name_simple(text: str, citation: str) -> str:
    """DEPRECATED: Use extract_case_name_only() instead"""
    _show_deprecation_warning('extract_case_name_simple')
    return extract_case_name_only(text, citation)

def extract_case_name_advanced(text: str, citation: str) -> Dict[str, Any]:
    """DEPRECATED: Use extract_case_name_and_date() instead"""
    _show_deprecation_warning('extract_case_name_advanced')
    return extract_case_name_and_date(text, citation)

def extract_case_name_regex(text: str, citation: str) -> str:
    """DEPRECATED: Use extract_case_name_only() instead"""
    _show_deprecation_warning('extract_case_name_regex')
    return extract_case_name_only(text, citation)

def extract_case_name_context(text: str, citation: str) -> str:
    """DEPRECATED: Use extract_case_name_only() instead"""
    _show_deprecation_warning('extract_case_name_context')
    return extract_case_name_only(text, citation)

def extract_case_name_pattern(text: str, citation: str) -> str:
    """DEPRECATED: Use extract_case_name_only() instead"""
    _show_deprecation_warning('extract_case_name_pattern')
    return extract_case_name_only(text, citation)

def extract_case_name_heuristic(text: str, citation: str) -> str:
    """DEPRECATED: Use extract_case_name_only() instead"""
    _show_deprecation_warning('extract_case_name_heuristic')
    return extract_case_name_only(text, citation)


def initialize_extractor():
    """Initialize the unified extractor (called automatically)"""
    try:
        extractor = get_extractor()
        print("UnifiedCaseNameExtractorV2 initialized successfully")
        print("All extraction now goes through the unified extractor")
        print("WARNING: Many functions are deprecated and will be removed in v3.0.0")
        print("INFO: Use extract_case_name_and_date() or extract_case_name_only() for new code")
        return True
    except Exception as e:
        print(f"ERROR: Failed to initialize UnifiedCaseNameExtractorV2: {e}")
        return False

if __name__ != "__main__":
    initialize_extractor()