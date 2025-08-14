"""
DEPRECATED: SCOTUS PDF Citation Extractor

This module has been DEPRECATED in favor of the unified input processor architecture.

REASON FOR DEPRECATION:
- Redundant functionality with pdf_extraction_optimized.py
- SCOTUS-specific logic can be integrated into the unified pipeline if needed
- All input types (file, URL, text) now use the same processing pipeline
- Eliminates code duplication and maintenance overhead

REPLACEMENT:
Use src.unified_input_processor.UnifiedInputProcessor instead.

MIGRATION PATH:
1. Replace direct calls to SCOTUSPDFCitationExtractor with UnifiedInputProcessor
2. Any SCOTUS-specific logic can be moved to the unified citation processor
3. All PDF processing now uses pdf_extraction_optimized.py for better performance

This file will be removed in a future version.
"""

# Re-export the original module for backward compatibility during transition
import warnings
from src.scotus_pdf_citation_extractor import *

warnings.warn(
    "scotus_pdf_citation_extractor is deprecated. Use unified_input_processor.UnifiedInputProcessor instead.",
    DeprecationWarning,
    stacklevel=2
)
