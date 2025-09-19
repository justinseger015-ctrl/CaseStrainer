"""
Enhanced Sync Processor with Async Verification

DEPRECATED: This processor is deprecated and will be removed in v3.0.0.
Use UnifiedCitationProcessorV2 with progress_callback parameter instead.

The features from this processor have been integrated into the main pipeline:
- Progress callbacks: Use UnifiedCitationProcessorV2(progress_callback=callback)
- False positive prevention: Integrated into main processing pipeline
- Enhanced verification: Use unified clustering with verification enabled

This processor provides:
1. Immediate results with local citation extraction, normalization, and clustering
2. Background async verification using fallback verifier
3. Support for text, files, and URLs
4. No timeouts or blocking operations
"""

import warnings
import os
from src.config import DEFAULT_REQUEST_TIMEOUT, COURTLISTENER_TIMEOUT, CASEMINE_TIMEOUT, WEBSEARCH_TIMEOUT, SCRAPINGBEE_TIMEOUT

import sys
import time
import logging
import hashlib
import tempfile
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass
from pathlib import Path
import re

def _deprecated_warning():
    """Issue deprecation warning for EnhancedSyncProcessor."""
    warnings.warn(
        "EnhancedSyncProcessor is deprecated and will be removed in v3.0.0. "
        "Use UnifiedCitationProcessorV2 with progress_callback parameter instead.",
        DeprecationWarning,
        stacklevel=3
    )

try:
    from src.enhanced_courtlistener_verification import EnhancedCourtListenerVerifier
    enhanced_verification_available = True
except ImportError:
    enhanced_verification_available = False
    logger = logging.getLogger(__name__)
    logger.warning("Enhanced verification not available, using fallback verifier")

try:
    from src.citation_utils_consolidated import ConfidenceScorer
    confidence_scoring_available = True
except ImportError:
    confidence_scoring_available = False
    logger = logging.getLogger(__name__)
    logger.warning("Confidence scoring not available")

logger = logging.getLogger(__name__)

@dataclass
class ProcessingOptions:
    """Configuration options for enhanced processing."""
    
    enable_local_processing: bool = True
    enable_async_verification: bool = True
    
    enhanced_sync_threshold: int = 80 * 1024  # 80KB for enhanced sync to handle PDF content
    ultra_fast_threshold: int = 500  # 500 chars for ultra-fast
    clustering_threshold: int = 300  # 300 chars for clustering
    max_citations_for_local_clustering: int = 10
    
    enable_enhanced_verification: bool = True
    enable_cross_validation: bool = True
    enable_false_positive_prevention: bool = True
    enable_confidence_scoring: bool = True
    
    min_confidence_threshold: float = 0.7
    cross_validation_confidence_boost: float = 0.15
    false_positive_filter_strictness: str = "medium"  # low, medium, high
    
    courtlistener_api_key: Optional[str] = None

class EnhancedSyncProcessor:
    """
    Enhanced processor that provides immediate results with local processing
    and queues verification for background async processing.
    """
    
    def __init__(self, options: Optional[ProcessingOptions] = None, progress_callback: Optional[Any] = None):
        """Initialize the enhanced sync processor with configuration options."""
        _deprecated_warning()  # Issue deprecation warning
        from src.config import get_citation_config
        
        # Get default configuration
        config = get_citation_config()
        
        # Initialize with default options if none provided
        if options is None:
            options = ProcessingOptions()
            
            # Apply default configuration from config.py
            options.enable_enhanced_verification = config.get('enable_verification', True)
            options.enable_confidence_scoring = config.get('verification_options', {}).get('enable_confidence_scoring', True)
            options.cross_validation_confidence_boost = 0.15  # Default value
            
            # Set API key from environment if not already set
            if not hasattr(options, 'courtlistener_api_key') or not options.courtlistener_api_key:
                from src.config import get_config_value
                options.courtlistener_api_key = get_config_value('COURTLISTENER_API_KEY')
        
        self.options = options
        self.progress_callback = progress_callback  # Progress callback function
        
        # Log configuration
        logger.info(f"[EnhancedSyncProcessor] Initializing with verification enabled: {self.options.enable_enhanced_verification}")
        if self.options.enable_enhanced_verification and self.options.courtlistener_api_key:
            logger.info(f"[EnhancedSyncProcessor] Using CourtListener API key: {self.options.courtlistener_api_key[:8]}...{self.options.courtlistener_api_key[-8:] if self.options.courtlistener_api_key else 'None'}")
        
        # Initialize verifier if enabled
        self.enhanced_verifier = None
        if self.options.enable_enhanced_verification and enhanced_verification_available:
            try:
                if self.options.courtlistener_api_key:
                    self.enhanced_verifier = EnhancedCourtListenerVerifier(self.options.courtlistener_api_key)
                    logger.info("Enhanced verification initialized successfully")
                else:
                    logger.warning("CourtListener API key not provided, enhanced verification disabled")
            except Exception as e:
                logger.warning(f"Failed to initialize enhanced verification: {e}")
                self.enhanced_verifier = None
        
        self.confidence_scorer = None
        if self.options.enable_confidence_scoring and confidence_scoring_available:
            try:
                self.confidence_scorer = ConfidenceScorer()
                logger.info("Confidence scoring initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize confidence scorer: {e}")
                self.confidence_scorer = None
        
        logger.info(f"EnhancedSyncProcessor initialized with options: {self.options}")
        logger.info(f"Enhanced verification: {'Available' if self.enhanced_verifier else 'Not available'}")
        logger.info(f"Confidence scoring: {'Available' if self.confidence_scorer else 'Not available'}")
        
        self.cache = {}
        self.cache_ttl = 3600  # 1 hour cache TTL
        self._cache_cleanup_interval = 300  # Clean cache every 5 minutes
        self._last_cache_cleanup = time.time()
        
        self.enhanced_sync_threshold = self.options.enhanced_sync_threshold
        self.ultra_fast_threshold = self.options.ultra_fast_threshold
        self.clustering_threshold = self.options.clustering_threshold
        self.max_citations_for_local_clustering = self.options.max_citations_for_local_clustering
        
        logger.info(f"[EnhancedSyncProcessor] Initialized with thresholds: "
                   f"enhanced_sync={self.enhanced_sync_threshold}, "
                   f"ultra_fast={self.ultra_fast_threshold}, "
                   f"clustering={self.clustering_threshold}")
    
    def process_any_input_enhanced(self, input_data: Any, input_type: str, options: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Process any input type (text, file, URL) with enhanced sync processing.
        
        Args:
            input_data: The input data (text string, file path, or URL string)
            input_type: Type of input ('text', 'file', 'url')
            options: Optional processing options
            
        Returns:
            Dictionary with immediate processing results and async verification status
        """
        start_time = time.time()
        request_id = f"enhanced_{int(start_time * 1000)}"
        
        try:
            logger.info(f"[EnhancedSyncProcessor {request_id}] Processing {input_type} input")
            
            text_result = self._extract_text_from_input(input_data, input_type, request_id)
            
            if not text_result['success']:
                return text_result
            
            text = text_result['text']
            metadata = text_result.get('metadata', {})
            
            if self._should_use_enhanced_sync(text):
                logger.info(f"[EnhancedSyncProcessor {request_id}] Using enhanced sync processing")
                try:
                    result = self._process_enhanced_sync(text, request_id, options)
                    result['processing_mode'] = 'enhanced_sync'  # Set processing mode for frontend
                    logger.info(f"[EnhancedSyncProcessor {request_id}] Enhanced sync result: {result.get('processing_mode', 'NOT_SET')}")
                    logger.info(f"[EnhancedSyncProcessor {request_id}] Result keys: {list(result.keys())}")
                except Exception as e:
                    logger.error(f"[EnhancedSyncProcessor {request_id}] Enhanced sync failed, falling back to basic: {e}")
                    result = self._process_basic_sync(text, request_id)
                    result['processing_mode'] = 'basic_sync'  # Set processing mode for frontend
                    logger.info(f"[EnhancedSyncProcessor {request_id}] Basic sync fallback result: {result.get('processing_mode', 'NOT_SET')}")
            else:
                logger.info(f"[EnhancedSyncProcessor {request_id}] Text too long, redirecting to async")
                return self._redirect_to_full_async(text, request_id, input_type, metadata)
            
            if (result.get('success') and 
                result.get('citations')):
                
                try:
                    logger.info(f"[EnhancedSyncProcessor {request_id}] Using synchronous verification (no caching)")
                    
                    verification_status = self._perform_synchronous_verification(
                        result['citations'], text, request_id, input_type, metadata
                    )
                    result['verification_status'] = verification_status
                    result['async_verification_queued'] = False
                    result['processing_mode'] = 'enhanced_sync_synchronous'  # Set the processing mode for frontend
                    
                    logger.info(f"[EnhancedSyncProcessor {request_id}] Synchronous verification completed")
                    
                    if verification_status.get('verification_completed') and verification_status.get('verification_results'):
                        logger.info(f"[EnhancedSyncProcessor {request_id}] Updating citations with verification results...")
                        
                        for citation in result['citations']:
                            citation_text = citation.get('citation', str(citation))
                            cleaned_citation = citation_text.replace('\n', ' ').replace('\r', ' ').strip()
                            cleaned_citation = ' '.join(cleaned_citation.split())
                            
                            for verif_result in verification_status['verification_results']:
                                if verif_result.get('citation') == cleaned_citation:
                                    canonical_url = verif_result.get('canonical_url') or verif_result.get('url')
                                    citation.update({
                                        'verified': verif_result.get('verified', False),
                                        'canonical_name': verif_result.get('canonical_name'),
                                        'canonical_date': verif_result.get('canonical_date'),
                                        'canonical_url': canonical_url,
                                        'url': canonical_url,  # Also set url field
                                        'verification_source': verif_result.get('source'),
                                        'verification_confidence': verif_result.get('confidence', 0.0),
                                        'verification_method': verif_result.get('validation_method'),
                                        'verification_completed': True,
                                        'verification_timestamp': time.time()
                                    })
                                    
                                    logger.info(f"[EnhancedSyncProcessor {request_id}] Citation '{citation_text}' - Extracted: '{citation.get('extracted_case_name')}' ({citation.get('extracted_date')}), Canonical: '{verif_result.get('canonical_name')}' ({verif_result.get('canonical_date')})")
                                    break
                        
                        # CRITICAL: Update cluster verification status after individual citations are verified
                        self._update_cluster_verification_status(result.get('clusters', []), result.get('citations', []))
                        
                        logger.info(f"[EnhancedSyncProcessor {request_id}] Citations updated with verification data")
                        
                        if result.get('clusters'):
                            logger.info(f"[EnhancedSyncProcessor {request_id}] Updating clusters with verification data...")
                            self._update_clusters_with_verification(result['clusters'], verification_status['verification_results'], request_id, result.get('citations', []))
                    else:
                        logger.warning(f"[EnhancedSyncProcessor {request_id}] No verification results to apply")
                    
                except Exception as e:
                    logger.warning(f"[EnhancedSyncProcessor {request_id}] Failed to perform synchronous verification: {e}")
                    result['verification_status'] = {
                        'verification_queued': False,
                        'verification_completed': False,
                        'error': str(e),
                        'message': 'Synchronous verification failed'
                    }
                    result['async_verification_queued'] = False
            
            if result.get('success') and result.get('citations'):
                result['citations'] = self._ensure_full_names_from_master(result['citations'], text)
            
            result.update({
                'processing_mode': 'enhanced_sync',
                'processing_time': time.time() - start_time,
                'request_id': request_id,
                'text_length': len(text),
                'input_type': input_type,
                'metadata': metadata
            })
            
            logger.info(f"[EnhancedSyncProcessor {request_id}] Enhanced processing completed in {result['processing_time']:.3f}s")
            return result
            
        except Exception as e:
            logger.error(f"[EnhancedSyncProcessor {request_id}] Error in enhanced processing: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': f'Enhanced processing failed: {str(e)}',
                'citations': [],
                'clusters': [],
                'processing_mode': 'enhanced_sync_error',
                'processing_time': time.time() - start_time,
                'request_id': request_id,
                'input_type': input_type
            }
        finally:
            self._cleanup_cache()
    
    def _should_use_enhanced_sync(self, text: str) -> bool:
        """Determine if text should use enhanced sync processing."""
        should_use = len(text) < self.enhanced_sync_threshold
        logger.info(f"[EnhancedSyncProcessor] _should_use_enhanced_sync: text_length={len(text)}, threshold={self.enhanced_sync_threshold}, result={should_use}")
        return should_use
    
    def _extract_text_from_input(self, input_data: Any, input_type: str, request_id: str) -> Dict[str, Any]:
        """Extract text from any input type."""
        try:
            if input_type == 'text':
                return self._extract_from_text(input_data, request_id)
            elif input_type == 'file':
                return self._extract_from_file(input_data, request_id)
            elif input_type == 'url':
                return self._extract_from_url(input_data, request_id)
            else:
                return {
                    'success': False,
                    'error': f'Unsupported input type: {input_type}',
                    'text': '',
                    'metadata': {'input_type': input_type}
                }
        except Exception as e:
            logger.error(f"[EnhancedSyncProcessor {request_id}] Text extraction failed: {e}")
            return {
                'success': False,
                'error': f'Text extraction failed: {str(e)}',
                'text': '',
                'metadata': {'input_type': input_type}
            }
    
    def _extract_from_text(self, text: str, request_id: str) -> Dict[str, Any]:
        """Extract text from text input."""
        return {
            'success': True,
            'text': text,
            'metadata': {'input_type': 'text', 'extraction_method': 'direct'}
        }
    
    def _extract_from_file(self, file_path: str, request_id: str) -> Dict[str, Any]:
        """Extract text from file input."""
        try:
            from src.pdf_extraction_optimized import extract_text_from_pdf_smart
            
            path_obj = Path(file_path)
            if not path_obj.exists():
                return {
                    'success': False,
                    'error': f'File not found: {file_path}',
                    'text': '',
                    'metadata': {'input_type': 'file', 'file_path': file_path}
                }
            
            if path_obj.suffix.lower() == '.pdf':
                text = extract_text_from_pdf_smart(file_path)
            else:
                with open(path_obj, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
            
            return {
                'success': True,
                'text': text,
                'metadata': {
                    'input_type': 'file',
                    'file_path': file_path,
                    'file_size': path_obj.stat().st_size,
                    'extraction_method': 'file_reader'
                }
            }
            
        except Exception as e:
            logger.error(f"[EnhancedSyncProcessor {request_id}] File extraction failed: {e}")
            return {
                'success': False,
                'error': f'File extraction failed: {str(e)}',
                'text': '',
                'metadata': {'input_type': 'file', 'file_path': file_path}
            }
    
    def _extract_from_url(self, url: str, request_id: str) -> Dict[str, Any]:
        """Extract text from URL input."""
        try:
            from src.progress_manager import fetch_url_content
            
            text = fetch_url_content(url)
            
            if not text:
                return {
                    'success': False,
                    'error': 'URL fetch returned empty content',
                    'text': '',
                    'metadata': {'input_type': 'url', 'url': url}
                }
            
            return {
                'success': True,
                'text': text,
                'metadata': {
                    'input_type': 'url',
                    'url': url,
                    'content_length': len(text),
                    'extraction_method': 'url_fetch'
                }
            }
            
        except Exception as e:
            logger.error(f"[EnhancedSyncProcessor {request_id}] URL extraction failed: {e}")
            return {
                'success': False,
                'error': f'URL extraction failed: {str(e)}',
                'text': '',
                'metadata': {'input_type': 'url', 'url': url}
            }
    
    def _process_enhanced_sync(self, text: str, request_id: str, options: Optional[Dict]) -> Dict[str, Any]:
        """Enhanced sync processing with local normalization and clustering."""
        try:
            logger.info(f"[EnhancedSyncProcessor {request_id}] Enhanced sync processing for {len(text)} characters")
            
            self._update_progress(0, "Initializing...", "Starting enhanced sync processing")
            
            self._update_progress(20, "Extract", "Extracting citations from text")
            citations = self._extract_citations_fast(text)
            
            self._update_progress(40, "Analyze", "Normalizing citations locally")
            normalized_citations = self._normalize_citations_local(citations, text)
            
            self._update_progress(60, "Extract Names", "Extracting case names and years")
            enhanced_citations = self._extract_names_years_local(normalized_citations, text)
            
            self._update_progress(75, "Pre-verify", "Updating citations with canonical data")
            self._apply_canonical_names_to_objects(enhanced_citations)
            
            self._update_progress(80, "Cluster", "Clustering citations locally")
            logger.info(f"[EnhancedSyncProcessor {request_id}] About to call _cluster_citations_local with {len(enhanced_citations)} citations")
            try:
                clusters = self._cluster_citations_local(enhanced_citations, text, request_id)
                logger.info(f"[EnhancedSyncProcessor {request_id}] _cluster_citations_local completed, returned {len(clusters)} clusters")
            except Exception as e:
                logger.error(f"[EnhancedSyncProcessor {request_id}] Error in _cluster_citations_local: {e}")
                import traceback
                logger.error(f"[EnhancedSyncProcessor {request_id}] Traceback: {traceback.format_exc()}")
                clusters = []
            
            self._update_progress(85, "Post-process", "Updating all citations with full names")
            enhanced_citations = self._ensure_full_names_from_master(enhanced_citations, text)
            
            self._update_progress(90, "Verify", "Preparing results")
            citations_list = self._convert_citations_to_dicts_simplified(enhanced_citations, clusters)
            clusters_list = self._convert_clusters_to_dicts(clusters)
            
            self._update_progress(100, "Complete", "Processing completed successfully")
            
            return {
                'success': True,
                'citations': citations_list,
                'clusters': clusters_list,
                'processing_mode': 'enhanced_sync',  # Frontend expects this field name
                'processing_strategy': 'enhanced_sync',
                'extraction_method': 'enhanced_local',
                'verification_status': 'pending_async',
                'local_processing_complete': True,
                'citations_found': len(citations_list),
                'clusters_created': len(clusters_list)
            }
            
        except Exception as e:
            logger.error(f"[EnhancedSyncProcessor {request_id}] Enhanced sync failed: {e}")
            self._update_progress(-1, "Error", f"Processing failed: {str(e)}")
            return self._process_basic_sync(text, request_id)
    
    def _update_progress(self, progress: int, step: str, message: str):
        """Update progress if callback is available."""
        if self.progress_callback and callable(self.progress_callback):
            try:
                self.progress_callback(progress, step, message)
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")
    
    def _extract_citations_fast(self, text: str) -> List:
        """UPDATED: Use master extraction function with enhanced error handling."""
        import re
        import traceback
        from src.models import CitationResult
        
        logger.info("Starting citation extraction...")
        
        try:
            # First try the unified extraction architecture
            try:
                from src.unified_extraction_architecture import extract_case_name_and_year_unified
                
                # Normalize text to handle newlines and extra spaces
                normalized_text = ' '.join(text.split())
                
                # Try to extract citations using the unified extractor
                result = extract_case_name_and_year_unified(
                    text=normalized_text,
                    citation="",  # Will be extracted from text
                    debug=True
                )
                
                if result and 'citations' in result:
                    logger.info(f"Found {len(result['citations'])} citations using unified extractor")
                    return result['citations']
                    
            except Exception as e:
                logger.warning(f"Unified extraction failed, falling back to regex: {str(e)}")
                logger.debug(traceback.format_exc())
            
            # Fall back to regex-based extraction if unified extraction fails
            return self._extract_citations_basic_regex(text)
            
        except Exception as e:
            logger.error(f"Critical error in citation extraction: {str(e)}")
            logger.error(traceback.format_exc())
            # Last resort: basic regex fallback
            return self._extract_citations_basic_regex(text)
    
    def _filter_false_positive_citations(self, citations: List, text: str) -> List:
        """Filter out false positive citations like standalone page numbers."""
        import re
        
        valid_citations = []
        
        for citation in citations:
            citation_text = str(citation) if not hasattr(citation, 'citation') else citation.citation
            
            if self._is_standalone_page_number(citation_text, text):
                continue
            
            if self._is_volume_without_reporter(citation_text):
                continue
            
            if len(citation_text.strip()) < 8:
                continue
            
            valid_citations.append(citation)
        
        return valid_citations
    
    def _is_standalone_page_number(self, citation_text: str, text: str) -> bool:
        """Check if citation is just a standalone page number."""
        import re
        
        if re.match(r'^\d+$', citation_text):
            pos = text.find(citation_text)
            if pos != -1:
                context_before = text[max(0, pos-50):pos]
                context_after = text[pos+len(citation_text):min(len(text), pos+len(citation_text)+50)]
                
                reporter_patterns = [
                    r'\bWn\.\d*d?\b',  # Wn.2d, Wn.3d
                    r'\bP\.\d*d?\b',   # P.2d, P.3d
                    r'\bU\.S\.\b',     # U.S.
                    r'\bS\.Ct\.\b',    # S.Ct.
                    r'\bWn\.\s*App\.\b',  # Wn. App.
                ]
                
                for pattern in reporter_patterns:
                    if (re.search(pattern, context_before) or 
                        re.search(pattern, context_after)):
                        return False
                
                return True
        
        return False
    
    def _is_volume_without_reporter(self, citation_text: str) -> bool:
        """Check if citation is just a volume number without reporter."""
        import re
        
        if re.match(r'^\d+$', citation_text):
            return True
        
        if citation_text.lower() == "volume reporter page":
            return True
        
        parts = citation_text.split()
        if len(parts) == 2 and all(part.isdigit() for part in parts):
            return True
        
        return False
    
    def _extract_citations_basic_regex(self, text: str) -> List:
        """Basic regex extraction as fallback."""
        import re
        
        patterns = [
            # Washington State citations - comprehensive patterns
            r'\b\d+\s+Wn\.\s*2d\s+\d+',  # 200 Wn.2d 72
            r'\b\d+\s+Wn\.\s*3d\s+\d+',  # 200 Wn.3d 72
            r'\b\d+\s+Wn\.\s*App\.\s*\d+',  # 136 Wn. App. 104
            r'\b\d+\s+Wn\.\s*App\.\s*\d+d\s+\d+',  # 33 Wn. App. 2d 75 (matches both 2d and 3d)
            
            # Pacific Reporter citations
            r'\b\d+\s+P\.\s*2d\s+\d+',   # 514 P.2d 643
            r'\b\d+\s+P\.\s*3d\s+\d+',   # 514 P.3d 643
            
            # Federal citations
            r'\b\d+\s+F\.\s*2d\s+\d+',  # Federal 2d
            r'\b\d+\s+F\.\s*3d\s+\d+',  # Federal 3d
            r'\b\d+\s+F\.\s*Supp\.\s*\d+',  # Federal Supp
            
            # Supreme Court citations
            r'\b\d+\s+S\.\s*Ct\.\s*\d+',  # Supreme Court citations
            r'\b\d+\s+U\.S\.\s*\d+',  # U.S. Supreme Court citations
            r'\b\d+\s+L\.\s*Ed\.\s*\d+',  # Lawyers Edition
            r'\b\d+\s+L\.\s*Ed\.\s*2d\s+\d+',  # Lawyers Edition 2d
        ]
        
        citations = []
        for pattern in patterns:
            matches = re.findall(pattern, text)
            citations.extend(matches)
        
        logger.info(f"[EnhancedSyncProcessor] Basic regex found {len(citations)} citations")
        return citations
    
    def _normalize_citations_local(self, citations: List, text: str) -> List:
        """Local citation normalization without API calls."""
        try:
            normalized = []
            for citation in citations:
                if (not isinstance(citation, dict) and 
                    hasattr(citation, 'citation')):
                    normalized.append(citation)
                    continue
                
                if isinstance(citation, dict) and 'citation' in citation:
                    citation_text = citation['citation']
                else:
                    citation_text = str(citation).strip()
                
                parts = citation_text.split()
                if len(parts) >= 3:
                    volume = parts[0]
                    reporter = parts[1]
                    page = parts[2]
                    
                    normalized.append({
                        'citation': citation_text,
                        'volume': volume,
                        'reporter': reporter,
                        'page': page,
                        'normalized': True
                    })
                else:
                    normalized.append({
                        'citation': citation_text,
                        'normalized': False
                    })
            
            logger.info(f"[EnhancedSyncProcessor] Local normalization completed for {len(normalized)} citations")
            return normalized
            
        except Exception as e:
            logger.warning(f"[EnhancedSyncProcessor] Local normalization failed: {e}")
            return citations
    
    def _extract_names_years_local(self, citations: List, text: str) -> List[Dict]:
        """Enhanced local name/year extraction with verification and confidence scoring."""
        try:
            enhanced_citations = []
            
            for citation in citations:
                if isinstance(citation, dict) and 'citation' in citation:
                    citation_text = citation['citation']
                elif hasattr(citation, 'citation'):
                    citation_text = getattr(citation, 'citation', '')
                else:
                    citation_text = str(citation)
                
                if (not isinstance(citation, dict) and 
                    hasattr(citation, 'extracted_case_name') and 
                    getattr(citation, 'extracted_case_name', None)):
                    case_name = getattr(citation, 'extracted_case_name', None)
                    year = getattr(citation, 'extracted_date', None) or getattr(citation, 'extracted_year', None)
                    confidence_score = getattr(citation, 'confidence', 0.7)
                elif isinstance(citation, dict) and citation.get('extracted_case_name'):
                    case_name = citation.get('extracted_case_name')
                    year = citation.get('extracted_date') or citation.get('extracted_year')
                    confidence_score = citation.get('confidence_score', 0.7)
                else:
                    case_name = self._extract_case_name_local(text, citation_text)
                    year = self._extract_year_local(text, citation_text)
                    
                    confidence_score = 0.7  # Start with good confidence
                    if case_name:
                        confidence_score += 0.1  # Bonus for case name
                    if year:
                        confidence_score += 0.1  # Bonus for year
                
                verification_result = None
                
                if self.enhanced_verifier and self.options.enable_enhanced_verification:
                    try:
                        verification_result = self.enhanced_verifier.verify_citation_enhanced(
                            citation_text, case_name
                        )
                        
                        if verification_result.get('verified'):
                            confidence_score = verification_result.get('confidence', 0.7)
                            canonical_name = verification_result.get('canonical_name')
                            canonical_date = verification_result.get('canonical_date')
                            # case_name = case_name  # Keep original extracted name
                            if canonical_date:
                                year = canonical_date
                        else:
                            confidence_score = 0.3
                            
                    except Exception as e:
                        logger.warning(f"Enhanced verification failed for {citation_text}: {e}")
                        verification_result = None
                
                if self.confidence_scorer and self.options.enable_confidence_scoring:
                    try:
                        citation_dict = {
                            'citation': citation_text,
                            'extracted_case_name': case_name,
                            'extracted_date': year,
                            'verified': verification_result.get('verified', False) if verification_result else False,
                            'method': 'enhanced_local_extraction'
                        }
                        
                        calculated_confidence = self.confidence_scorer.calculate_citation_confidence(
                            citation_dict, text
                        )
                        
                        if calculated_confidence < 0.3:
                            calculated_confidence = confidence_score
                        
                        if verification_result:
                            confidence_score = (confidence_score + calculated_confidence) / 2
                        else:
                            confidence_score = calculated_confidence
                            
                    except Exception as e:
                        logger.warning(f"Confidence scoring failed for {citation_text}: {e}")
                
                if self.options.enable_false_positive_prevention:
                    if not self._is_valid_citation(citation_text, case_name, year, confidence_score):
                        continue
                
                if (not isinstance(citation, dict) and 
                    hasattr(citation, 'extracted_case_name')):
                    enhanced_citation = citation
                    setattr(enhanced_citation, 'confidence_score', confidence_score)
                    setattr(enhanced_citation, 'verification_result', verification_result)
                    setattr(enhanced_citation, 'extraction_method', 'enhanced_local')
                    setattr(enhanced_citation, 'false_positive_filtered', False)
                    if case_name:
                        setattr(enhanced_citation, 'extracted_case_name', case_name)
                    if year:
                        setattr(enhanced_citation, 'extracted_date', year)
                    if 'canonical_name' in locals():
                        setattr(enhanced_citation, 'canonical_name', canonical_name)
                    if 'canonical_date' in locals():
                        setattr(enhanced_citation, 'canonical_date', canonical_date)
                else:
                    enhanced_citation = {
                        'citation': citation_text,
                        'extracted_case_name': case_name,
                        'extracted_date': year,
                        'confidence_score': confidence_score,
                        'verification_result': verification_result,
                        'extraction_method': 'enhanced_local',
                        'false_positive_filtered': False
                    }
                    if 'canonical_name' in locals():
                        enhanced_citation['canonical_name'] = canonical_name
                    if 'canonical_date' in locals():
                        enhanced_citation['canonical_date'] = canonical_date
                
                enhanced_citations.append(enhanced_citation)
            
            logger.info(f"Enhanced local extraction completed: {len(enhanced_citations)} citations")
            return enhanced_citations
            
        except Exception as e:
            logger.error(f"Enhanced local extraction failed: {e}")
            return self._extract_names_years_basic(citations, text)
    
    def _extract_case_name_local(self, text: str, citation: str) -> Optional[str]:
        """Extract case name from text context around citation using MASTER extraction function."""
        try:
            from src.unified_case_name_extractor_v2 import extract_case_name_and_date_master
            
            citation_start = text.find(citation)
            if citation_start == -1:
                citation_with_newline = citation.replace(' ', '\n', 1)
                citation_start = text.find(citation_with_newline)
                if citation_start != -1:
                    citation = citation_with_newline
            
            citation_end = citation_start + len(citation) if citation_start != -1 else None
            
            result = extract_case_name_and_date_master(
                text=text, 
                citation=citation, 
                citation_start=citation_start if citation_start != -1 else None,
                citation_end=citation_end,
                debug=False
            )
            case_name = result.get('case_name')
            return case_name
        except Exception as e:
            return None
    
    def _ensure_full_names_from_master(self, citations: List, text: str) -> List:
        """Ensure ALL citations have full names from master extraction function."""
        try:
            from src.unified_case_name_extractor_v2 import extract_case_name_and_date_master
            
            
            for citation in citations:
                if isinstance(citation, dict):
                    citation_text = citation.get('citation', '')
                    current_name = citation.get('extracted_case_name', '')
                elif hasattr(citation, 'citation'):
                    citation_text = getattr(citation, 'citation', '')
                    current_name = getattr(citation, 'extracted_case_name', '')
                else:
                    continue
                
                # Remove the problematic filter that was skipping cases with "Fish & Wildlife"
                # This was preventing proper case name extraction for Spokane County cases
                # if "Farms" in current_name or "Fish & Wildlife" in current_name:
                #     continue
                
                try:
                    citation_start = None
                    citation_end = None
                    
                    if isinstance(citation, dict):
                        citation_start = citation.get('start_index')
                        citation_end = citation.get('end_index')
                    else:
                        citation_start = getattr(citation, 'start_index', None)
                        citation_end = getattr(citation, 'end_index', None)
                    
                    
                    result = extract_case_name_and_date_master(
                        text=text,
                        citation=citation_text,
                        citation_start=citation_start if citation_start != -1 else None,
                        citation_end=citation_end,
                        debug=False
                    )
                    
                    full_name = result.get('case_name', '')
                    if full_name and full_name != 'N/A' and full_name != current_name:
                        # Decide if master name is clearly better than current
                        master_tokens = ["dep't", "department", "dept", "fish", "wildlife", "bros.", "farms", "inc", "llc", "corp", "ltd", "co."]
                        current_lower = (current_name or '').lower()
                        full_lower = full_name.lower()
                        is_truncated = current_lower.endswith(' v. dep') or current_lower.endswith(" v. dep't") or current_lower.endswith(' v. dept')
                        contains_key_tokens = any(t in full_lower for t in master_tokens)
                        is_clearly_longer = len(full_name) >= len(current_name or '') + 4
                        names_share_prefix = (current_name or '').split(' v.')[0] == full_name.split(' v.')[0]

                        should_replace = False
                        if not current_name or current_name == 'N/A':
                            should_replace = True
                        elif names_share_prefix and (is_truncated or contains_key_tokens or is_clearly_longer):
                            should_replace = True

                        if should_replace:
                            # Normalize via shared cleaner for consistency with V2
                            try:
                                from src.unified_citation_processor_v2 import UnifiedCitationProcessorV2
                                cleaner = getattr(UnifiedCitationProcessorV2, '_clean_extracted_case_name', None)
                                if callable(cleaner):
                                    full_name = cleaner(self=None, case_name=full_name)  # static-like usage
                            except Exception:
                                pass

                            if isinstance(citation, dict):
                                citation['extracted_case_name'] = full_name
                            elif hasattr(citation, 'extracted_case_name'):
                                setattr(citation, 'extracted_case_name', full_name)
                        else:
                            pass  # Keep existing name
                        
                except Exception as e:
                    continue
            
            return citations
            
        except Exception as e:
            return citations
    
    def _extract_year_local(self, text: str, citation: str) -> Optional[str]:
        """Extract year from citation text or surrounding context."""
        import re
        
        year_match = re.search(r'\((\d{4})\)', citation)
        if year_match:
            return year_match.group(1)
        
        pos = text.find(citation)
        if pos != -1:
            context_start = max(0, pos - 50)
            context_end = min(len(text), pos + len(citation) + 50)
            context = text[context_start:context_end]
            
            year_patterns = [
                r'\((\d{4})\)',  # (2022)
                r'(\d{4})',      # 2022
                r'(\d{2})',      # 22 (for recent years)
            ]
            
            for pattern in year_patterns:
                matches = re.findall(pattern, context)
                for match in matches:
                    year = match
                    if len(year) == 4 and 1900 <= int(year) <= 2030:
                        return year
                    elif len(year) == 2 and 20 <= int(year) <= 30:
                        return f"20{year}"
        
        return None
    
    def _extract_names_years_basic(self, citations: List, text: str) -> List[Dict]:
        """Basic name and year extraction as fallback."""
        try:
            basic_citations = []
            
            for citation in citations:
                if isinstance(citation, dict) and 'citation' in citation:
                    citation_text = citation['citation']
                elif hasattr(citation, 'citation'):
                    citation_text = getattr(citation, 'citation', '')
                else:
                    citation_text = str(citation)
                
                case_name = self._extract_case_name_local(text, citation_text)
                year = self._extract_year_local(text, citation_text)
                
                basic_citation = {
                    'citation': citation_text,
                    'extracted_case_name': case_name,
                    'extracted_date': year,
                    'confidence_score': 0.5,  # Default confidence
                    'verification_result': None,
                    'extraction_method': 'basic_fallback',
                    'false_positive_filtered': False
                }
                
                basic_citations.append(basic_citation)
            
            logger.info(f"Basic extraction completed: {len(basic_citations)} citations")
            return basic_citations
            
        except Exception as e:
            logger.error(f"Basic extraction failed: {e}")
            return [{'citation': str(c), 'extracted_case_name': None, 'extracted_date': None, 
                    'confidence_score': 0.0, 'verification_result': None, 
                    'extraction_method': 'error_fallback', 'false_positive_filtered': False} 
                   for c in citations]

    def _is_valid_citation(self, citation: str, case_name: Optional[str], year: Optional[str], confidence: float) -> bool:
        """
        Apply false positive prevention logic.
        This is a placeholder and can be enhanced with more sophisticated rules.
        """
        if not self.options.enable_false_positive_prevention:
            return True

        # even if case names or years aren't extracted yet
        if confidence >= 0.5:  # Lower threshold for initial extraction
            return True

        if confidence < 0.3:
            if not case_name and not year:
                return False
            
            if case_name and len(case_name.split()) < 2:
                return False

        return True
    
    def _cluster_citations_local(self, citations: List, text: str, request_id: str) -> List:
        """
        Enhanced citation clustering using the new EnhancedCitationClusterer.
        This replaces the old case-name-year clustering with proximity-based parallel detection.
        """
        try:
            logger.info(f"[EnhancedSyncProcessor {request_id}] _cluster_citations_local called with {len(citations)} citations")
            logger.info(f"[EnhancedSyncProcessor {request_id}] Starting enhanced clustering for {len(citations)} citations")
            
            # Use the unified clustering system that we already fixed
            from src.unified_citation_clustering import cluster_citations_unified
            
            # Get verification flag from instance options with proper fallback (default to True for better results)
            enable_verification = getattr(self.options, 'enable_enhanced_verification', True)
            
            # Log the verification setting
            logger.info(f"[EnhancedSyncProcessor {request_id}] Using unified clustering with enable_verification={enable_verification}")
            
            try:
                # Use the same clustering function that works for sync processing
                clusters = cluster_citations_unified(
                    citations, 
                    text, 
                    enable_verification=bool(enable_verification)
                )
                logger.info(f"[EnhancedSyncProcessor {request_id}] Clustering completed with {len(clusters)} clusters")
            except Exception as e:
                logger.error(f"[EnhancedSyncProcessor {request_id}] Error in cluster_citations: {str(e)}")
                logger.error(f"[EnhancedSyncProcessor {request_id}] Citations being clustered: {[str(c) for c in citations]}")
                raise
            
            logger.info(f"[EnhancedSyncProcessor {request_id}] Enhanced clustering created {len(clusters)} clusters")
            
            # self._propagate_cluster_data_to_citations(citations, clusters, request_id)
            
            logger.info(f"[EnhancedSyncProcessor {request_id}] About to call _propagate_true_by_parallel_only")
            try:
                self._propagate_true_by_parallel_only(citations, clusters, request_id)
                logger.info(f"[EnhancedSyncProcessor {request_id}] _propagate_true_by_parallel_only completed successfully")
            except Exception as e:
                logger.error(f"[EnhancedSyncProcessor {request_id}] Error in _propagate_true_by_parallel_only: {e}")
                import traceback
                logger.error(f"[EnhancedSyncProcessor {request_id}] Traceback: {traceback.format_exc()}")
            
            return clusters
            
        except Exception as e:
            logger.error(f"[EnhancedSyncProcessor {request_id}] Enhanced clustering failed: {e}")
            return self._cluster_citations_basic_fallback(citations, text, request_id)
    
    def _propagate_cluster_data_to_citations(self, citations: List, clusters: List, request_id: str):
        """
        Propagate cluster data to citations for frontend display.
        This method is used to maintain backward compatibility with the old clustering method.
        """
        for cluster in clusters:
            cluster_case_name = cluster.get('case_name')
            cluster_year = cluster.get('year')
            cluster_citations = cluster.get('citations', [])
            
            if cluster_case_name and cluster_case_name != 'Unknown Case':
                cleaned_case_name = self._clean_case_name_for_clustering(cluster_case_name)
                if cleaned_case_name:
                    cluster_case_name = cleaned_case_name
                
                for citation in citations:
                    citation_text = None
                    if isinstance(citation, dict):
                        citation_text = citation.get('citation', str(citation))
                    else:
                        citation_text = getattr(citation, 'citation', str(citation))
                    
                    if citation_text in cluster_citations:
                        if isinstance(citation, dict):
                            citation['extracted_case_name'] = cluster_case_name
                            citation['extracted_date'] = cluster_year
                        elif hasattr(citation, 'extracted_case_name'):
                            setattr(citation, 'extracted_case_name', cluster_case_name)
                            setattr(citation, 'extracted_date', cluster_year)

    def _propagate_true_by_parallel_only(self, citations: List, clusters: List, request_id: str):
        """
        Propagate only true_by_parallel values from clusters to citations.
        This prevents contamination by not overriding extracted names.
        """
        try:
            logger.info(f"[EnhancedSyncProcessor {request_id}] _propagate_true_by_parallel_only called with {len(citations)} citations and {len(clusters)} clusters")
            
            for i, citation in enumerate(citations):
                logger.info(f"[EnhancedSyncProcessor {request_id}] Citation {i}: type={type(citation)}, citation={getattr(citation, 'citation', citation.get('citation', 'N/A') if isinstance(citation, dict) else 'N/A')}")
            
            for cluster in clusters:
                cluster_citations = cluster.get('citations', [])
                cluster_has_verified = cluster.get('cluster_has_verified', False)
                
                logger.info(f"[EnhancedSyncProcessor {request_id}] Processing cluster: {cluster.get('cluster_id', 'unknown')}")
                logger.info(f"[EnhancedSyncProcessor {request_id}]   Cluster citations: {cluster_citations}")
                logger.info(f"[EnhancedSyncProcessor {request_id}]   Cluster has verified: {cluster_has_verified}")
                
                # ALWAYS process clusters to propagate extracted case names - verification is independent
                if cluster_citations:  # Process any cluster that has citations
                    for citation in citations:
                        citation_text = None
                        if isinstance(citation, dict):
                            citation_text = citation.get('citation', str(citation))
                        else:
                            citation_text = getattr(citation, 'citation', str(citation))
                        
                        if citation_text in cluster_citations:
                            logger.info(f"[EnhancedSyncProcessor {request_id}] Found citation '{citation_text}' in cluster")
                            
                            # Propagate extracted case name from cluster to individual citation
                            cluster_case_name = cluster.get('case_name') or cluster.get('extracted_case_name')
                            if cluster_case_name and cluster_case_name != 'N/A':
                                # Clean the case name to remove trailing punctuation
                                from src.utils.case_name_cleaner import clean_extracted_case_name
                                cleaned_case_name = clean_extracted_case_name(cluster_case_name)
                                
                                if isinstance(citation, dict):
                                    if not citation.get('extracted_case_name') or citation.get('extracted_case_name') == 'N/A':
                                        citation['extracted_case_name'] = cleaned_case_name
                                        logger.info(f"[EnhancedSyncProcessor {request_id}] Propagated cleaned case name '{cleaned_case_name}' to citation '{citation_text}'")
                                elif hasattr(citation, 'extracted_case_name'):
                                    if not getattr(citation, 'extracted_case_name', None) or getattr(citation, 'extracted_case_name', None) == 'N/A':
                                        setattr(citation, 'extracted_case_name', cleaned_case_name)
                                        logger.info(f"[EnhancedSyncProcessor {request_id}] Propagated cleaned case name '{cleaned_case_name}' to CitationResult '{citation_text}'")
                            
                            # Set true_by_parallel for unverified citations ONLY if cluster has verified citations
                            if cluster_has_verified:  # Only if cluster has at least one verified citation
                                if isinstance(citation, dict):
                                    verified_status = citation.get('verified', False)
                                    logger.info(f"[EnhancedSyncProcessor {request_id}]   Citation is dict, verified: {verified_status}")
                                    if not verified_status:
                                        citation['true_by_parallel'] = True
                                        logger.info(f"[EnhancedSyncProcessor {request_id}] Set true_by_parallel=True for unverified citation '{citation_text}' in verified cluster")
                                elif hasattr(citation, 'verified'):
                                    verified_status = getattr(citation, 'verified', False)
                                    logger.info(f"[EnhancedSyncProcessor {request_id}]   Citation is object, verified: {verified_status}")
                                    if not verified_status:
                                        setattr(citation, 'true_by_parallel', True)
                                        logger.info(f"[EnhancedSyncProcessor {request_id}] Set true_by_parallel=True for unverified CitationResult '{citation_text}' in verified cluster")
                            else:
                                # Cluster has no verified citations, so no citations should be true_by_parallel
                                if isinstance(citation, dict):
                                    citation['true_by_parallel'] = False
                                    logger.info(f"[EnhancedSyncProcessor {request_id}] Set true_by_parallel=False for citation '{citation_text}' in unverified cluster")
                                elif hasattr(citation, 'true_by_parallel'):
                                    setattr(citation, 'true_by_parallel', False)
                                    logger.info(f"[EnhancedSyncProcessor {request_id}] Set true_by_parallel=False for CitationResult '{citation_text}' in unverified cluster")
        
        except Exception as e:
            logger.error(f"[EnhancedSyncProcessor {request_id}] Error in _propagate_true_by_parallel_only: {e}")
            import traceback
            logger.error(f"[EnhancedSyncProcessor {request_id}] Traceback: {traceback.format_exc()}")
    
    def _cluster_citations_basic_fallback(self, citations: List, text: str, request_id: str) -> List:
        """Basic fallback clustering when enhanced clustering fails."""
        logger.warning(f"[EnhancedSyncProcessor {request_id}] Using basic fallback clustering")
        
        clusters = []
        processed = set()
        
        for i, citation in enumerate(citations):
            if i in processed:
                continue
            
            case_name = self._get_case_name(citation)
            case_year = self._get_case_year(citation)
            
            if case_name and case_year:
                cluster = [citation]
                processed.add(i)
                
                for j, other_citation in enumerate(citations[i+1:], i+1):
                    if j in processed:
                        continue
                    
                    other_case_name = self._get_case_name(other_citation)
                    other_year = self._get_case_year(other_citation)
                    
                    if (other_case_name == case_name and other_year == case_year):
                        cluster.append(other_citation)
                        processed.add(j)
                
                if len(cluster) > 0:
                    clusters.append({
                        'cluster_id': f"fallback_{case_name.replace(' ', '_')}_{case_year}",
                        'case_name': case_name,
                        'year': case_year,
                        'size': len(cluster),
                        'citations': [self._get_citation_text(c) for c in cluster],
                        'citation_objects': cluster,
                        'cluster_type': 'fallback_basic'
                    })
        
        return clusters
    
    def _get_citation_text(self, citation: Any) -> str:
        """Extract citation text from various citation object types."""
        if isinstance(citation, dict):
            return citation.get('citation', str(citation))
        elif hasattr(citation, 'citation'):
            return getattr(citation, 'citation', str(citation))
        else:
            return str(citation)
    
    def _get_case_name(self, citation: Any) -> Optional[str]:
        """Extract case name from citation."""
        if isinstance(citation, dict):
            return citation.get('extracted_case_name')
        elif hasattr(citation, 'extracted_case_name'):
            return getattr(citation, 'extracted_case_name')
        return None
    
    def _get_case_year(self, citation: Any) -> Optional[str]:
        """Extract case year from citation."""
        if isinstance(citation, dict):
            return citation.get('extracted_date')
        elif hasattr(citation, 'extracted_case_name'):
            return getattr(citation, 'extracted_date')
        return None
    
    def _same_reporter(self, citation1: str, citation2: str) -> bool:
        """Check if two citations are from the same reporter."""
        try:
            reporter1 = self._extract_reporter(citation1)
            reporter2 = self._extract_reporter(citation2)
            return reporter1 == reporter2
        except:
            return False
    
    def _extract_reporter(self, citation: str) -> str:
        """Extract reporter from citation."""
        import re
        match = re.search(r'\b(Wn\.|P\.|U\.S\.|S\.Ct\.)', citation)
        return match.group(1) if match else "Unknown"
    
    def _process_basic_sync(self, text: str, request_id: str) -> Dict[str, Any]:
        """Basic sync processing as fallback."""
        try:
            citations = self._extract_citations_basic_regex(text)
            citations_list = [{'citation': c, 'extracted_case_name': None, 'extracted_date': None} for c in citations]
            
            return {
                'success': True,
                'citations': citations_list,
                'clusters': [],
                'processing_strategy': 'basic_sync',
                'extraction_method': 'basic_regex',
                'verification_status': 'pending_async',
                'local_processing_complete': True
            }
            
        except Exception as e:
            logger.error(f"[EnhancedSyncProcessor {request_id}] Basic sync failed: {e}")
            return {
                'success': False,
                'error': f'Basic sync failed: {str(e)}',
                'citations': [],
                'clusters': []
            }
    
    def _queue_async_verification(self, citations: List, text: str, request_id: str, input_type: str, metadata: Dict) -> Dict[str, Any]:
        """Queue citations for async verification using fallback verifier."""
        try:
            from rq import Queue
            from redis import Redis
            
            logger.info(f"[EnhancedSyncProcessor {request_id}] _queue_async_verification called with {len(citations)} citations")
            logger.info(f"[EnhancedSyncProcessor {request_id}] First citation type: {type(citations[0]) if citations else 'None'}")
            if citations:
                logger.info(f"[EnhancedSyncProcessor {request_id}] First citation: {citations[0]}")
            
            serializable_citations = []
            for citation in citations:
                if isinstance(citation, dict):
                    clean_citation = {
                        'citation': citation.get('citation', ''),
                        'extracted_case_name': citation.get('extracted_case_name'),
                        'extracted_date': citation.get('extracted_date'),
                        'confidence_score': citation.get('confidence_score', 0.5),
                        'extraction_method': citation.get('extraction_method', 'unknown'),
                        'false_positive_filtered': citation.get('false_positive_filtered', False),
                        'verified': citation.get('verified', False),
                        'canonical_name': citation.get('canonical_name'),
                        'canonical_date': citation.get('canonical_date'),
                        'canonical_url': citation.get('canonical_url'),
                        'url': citation.get('url'),
                        'source': citation.get('source'),
                        'validation_method': citation.get('validation_method'),
                        'verification_confidence': citation.get('verification_confidence')
                    }
                else:
                    clean_citation = {
                        'citation': getattr(citation, 'citation', ''),
                        'extracted_case_name': getattr(citation, 'extracted_case_name', None),
                        'extracted_date': getattr(citation, 'extracted_date', None),
                        'confidence_score': getattr(citation, 'confidence_score', 0.5),
                        'extraction_method': getattr(citation, 'extraction_method', 'unknown'),
                        'false_positive_filtered': getattr(citation, 'false_positive_filtered', False),
                        'verified': getattr(citation, 'verified', False),
                        'canonical_name': getattr(citation, 'canonical_name', None),
                        'canonical_date': getattr(citation, 'canonical_date', None),
                        'canonical_url': getattr(citation, 'canonical_url', None),
                        'url': getattr(citation, 'url', None),
                        'source': citation.get('source') if hasattr(citation, 'get') else getattr(citation, 'source', None),
                        'validation_method': citation.get('validation_method') if hasattr(citation, 'get') else getattr(citation, 'validation_method', None),
                        'verification_confidence': citation.get('verification_confidence') if hasattr(citation, 'get') else getattr(citation, 'verification_confidence', None)
                    }
                
                clean_citation = {k: v for k, v in clean_citation.items() if v is not None}
                serializable_citations.append(clean_citation)
            
            logger.info(f"[EnhancedSyncProcessor {request_id}] Converted {len(serializable_citations)} citations to serializable format")
            
            clean_metadata = {}
            if metadata:
                for key, value in metadata.items():
                    if isinstance(value, (str, int, float, bool, list, dict)) and not callable(value):
                        if isinstance(value, list):
                            clean_metadata[key] = [str(item) if not isinstance(item, (str, int, float, bool)) else item for item in value]
                        elif isinstance(value, dict):
                            clean_metadata[key] = {str(k): str(v) if not isinstance(v, (str, int, float, bool)) else v for k, v in value.items()}
                        else:
                            clean_metadata[key] = value
            
            redis_url = os.environ.get('REDIS_URL', 'redis://:caseStrainerRedis123@casestrainer-redis-prod:6379/0')
            redis_conn = Redis.from_url(redis_url)
            queue = Queue('casestrainer', connection=redis_conn)
            
            job = queue.enqueue(
                'src.async_verification_worker.verify_citations_enhanced',
                args=(serializable_citations, text, request_id, input_type, clean_metadata),
                job_id=f"verify_enhanced_{request_id}",
                job_timeout=f'{JOB_TIMEOUT_MINUTES}m',
                result_ttl=86400,
                failure_ttl=86400
            )
            
            logger.info(f"[EnhancedSyncProcessor {request_id}] Async verification queued with job_id: {job.id}")
            
            return {
                'verification_queued': True,
                'verification_job_id': job.id,
                'verification_queue': 'casestrainer',
                'message': 'Citations queued for async verification with fallback verifier'
            }
            
        except Exception as e:
            logger.error(f"[EnhancedSyncProcessor {request_id}] Failed to queue verification: {e}")
            return {
                'verification_queued': False,
                'error': str(e),
                'message': 'Failed to queue async verification'
            }
    
    def _perform_synchronous_verification(self, citations: List, text: str, request_id: str, input_type: str, metadata: Dict) -> Dict[str, Any]:
        """Perform synchronous verification without caching."""
        try:
            logger.info(f"[EnhancedSyncProcessor {request_id}] Starting synchronous verification for {len(citations)} citations")
            
            from src.enhanced_courtlistener_verification import EnhancedCourtListenerVerifier
            from src.enhanced_fallback_verifier import EnhancedFallbackVerifier
            
            api_key = os.getenv('COURTLISTENER_API_KEY', '443a87912e4f444fb818fca454364d71e4aa9f91')
            
            courtlistener_verifier = EnhancedCourtListenerVerifier(api_key)
            fallback_verifier = EnhancedFallbackVerifier()
            
            verification_results = []
            
            citation_texts = []
            extracted_case_names = []
            
            for citation in citations:
                citation_text = citation.get('citation', str(citation))
                cleaned_citation = citation_text.replace('\n', ' ').replace('\r', ' ').strip()
                cleaned_citation = ' '.join(cleaned_citation.split())
                
                citation_texts.append(cleaned_citation)
                extracted_case_names.append(citation.get('extracted_case_name'))
                
                logger.info(f"[EnhancedSyncProcessor {request_id}] Cleaned citation: '{citation_text}' -> '{cleaned_citation}'")
            
            logger.info(f"[EnhancedSyncProcessor {request_id}] Attempting individual CourtListener Citation Lookup for each citation")
            courtlistener_results = []
            
            for citation in citations:
                citation_text = citation.get('citation', str(citation))
                cleaned_citation = citation_text.replace('\n', ' ').replace('\r', ' ').strip()
                cleaned_citation = ' '.join(cleaned_citation.split())
                
                logger.info(f"[EnhancedSyncProcessor {request_id}] Processing citation: '{cleaned_citation}'")
                
                individual_result = courtlistener_verifier.verify_citation_enhanced(cleaned_citation, citation.get('extracted_case_name'))
                
                if individual_result:
                    batch_format_result = {
                        'citation': cleaned_citation,
                        'verified': individual_result.get('verified', False),
                        'canonical_name': individual_result.get('canonical_name'),
                        'canonical_date': individual_result.get('canonical_date'),
                        'canonical_url': individual_result.get('url'),
                        'source': individual_result.get('source', 'CourtListener Citation Lookup'),
                        'confidence': individual_result.get('confidence', 0.0)
                    }
                    courtlistener_results.append(batch_format_result)
                    logger.info(f"[EnhancedSyncProcessor {request_id}] Citation Lookup result: {batch_format_result}")
                else:
                    logger.info(f"[EnhancedSyncProcessor {request_id}] No result from Citation Lookup for: '{cleaned_citation}'")
            
            for i, citation in enumerate(citations):
                citation_text = citation.get('citation', str(citation))
                cleaned_citation = citation_text.replace('\n', ' ').replace('\r', ' ').strip()
                cleaned_citation = ' '.join(cleaned_citation.split())
                
                matching_result = None
                for court_result in courtlistener_results:
                    if court_result.get('citation') == cleaned_citation:
                        matching_result = court_result
                        logger.info(f"[EnhancedSyncProcessor {request_id}] Found matching result for '{cleaned_citation}': {matching_result}")
                        break
                
                if not matching_result or not matching_result.get('verified'):
                    logger.info(f"[EnhancedSyncProcessor {request_id}] Citation '{citation_text}' not verified by CourtListener, trying fallback")
                    
                    try:
                        fallback_result = fallback_verifier.verify_citation_sync_optimized(citation_text, citation.get('extracted_case_name'))
                        if fallback_result.get('verified'):
                            logger.info(f"[EnhancedSyncProcessor {request_id}] Found optimized fallback verification: {fallback_result}")
                            matching_result = fallback_result
                        else:
                            logger.info(f"[EnhancedSyncProcessor {request_id}] Optimized fallback verification failed for '{citation_text}'")
                    except Exception as e:
                        logger.warning(f"[EnhancedSyncProcessor {request_id}] Optimized fallback verification failed: {e}")
                        logger.info(f"[EnhancedSyncProcessor {request_id}] Skipping fallback verification due to error")
                
                canonical_url = None
                if matching_result:
                    canonical_url = matching_result.get('canonical_url') or matching_result.get('url')
                
                verification_result = {
                    'citation': cleaned_citation,  # Use cleaned citation for matching
                    'verified': matching_result.get('verified', False) if matching_result else False,
                    'canonical_name': matching_result.get('canonical_name') if matching_result else None,
                    'canonical_date': matching_result.get('canonical_date') if matching_result else None,
                    'canonical_url': canonical_url,
                    'url': canonical_url,  # Also include url field for consistency
                    'source': matching_result.get('source', 'unknown') if matching_result else 'verification_failed',
                    'confidence': matching_result.get('confidence', 0.0) if matching_result else 0.0,
                    'validation_method': matching_result.get('validation_method', 'unknown') if matching_result else 'verification_failed'
                }
                
                
                verification_results.append(verification_result)
            
            logger.info(f"[EnhancedSyncProcessor {request_id}] Synchronous verification completed: {len(verification_results)} results")
            
            return {
                'verification_queued': False,
                'verification_completed': True,
                'verification_method': 'synchronous',
                'message': 'Citations verified synchronously',
                'verification_time': time.time(),
                'verification_results': verification_results
            }
            
        except Exception as e:
            logger.error(f"[EnhancedSyncProcessor {request_id}] Synchronous verification failed: {e}")
            return {
                'verification_queued': False,
                'verification_completed': False,
                'error': str(e),
                'message': 'Synchronous verification failed'
            }
    
    def _redirect_to_full_async(self, text: str, request_id: str, input_type: str, metadata: Dict) -> Dict[str, Any]:
        """Redirect to full async processing when text is too long."""
        try:
            from rq import Queue
            from redis import Redis
            
            logger.info(f"[EnhancedSyncProcessor {request_id}] Queuing task for async processing (text length: {len(text)})")
            
            redis_url = os.environ.get('REDIS_URL', 'redis://:caseStrainerRedis123@casestrainer-redis-prod:6379/0')
            redis_conn = Redis.from_url(redis_url)
            queue = Queue('casestrainer', connection=redis_conn)
            
            # Queue the task for async processing
            job = queue.enqueue(
                'src.progress_manager.process_citation_task_direct',
                args=(request_id, input_type, {'text': text}),
                job_id=request_id,
                job_timeout=600,  # 10 minutes timeout
                result_ttl=86400,
                failure_ttl=86400
            )
            
            logger.info(f"[EnhancedSyncProcessor {request_id}] Task queued with job_id: {job.id}")
            
            return {
                'success': True,
                'status': 'processing',
                'message': f'Text too long ({len(text)} chars) for enhanced sync processing. Queued for async processing.',
                'task_id': request_id,
                'job_id': job.id,
                'processing_mode': 'async_queued',
                'text_length': len(text),
                'request_id': request_id,
                'input_type': input_type,
                'metadata': metadata
            }
            
        except Exception as e:
            logger.error(f"[EnhancedSyncProcessor {request_id}] Failed to queue async task: {e}")
            return {
                'success': False,
                'status': 'failed',
                'error': f'Failed to queue async processing: {str(e)}',
                'task_id': request_id,
                'request_id': request_id,
                'input_type': input_type,
                'metadata': metadata
            }
    
    def _debug_citation_object(self, citation, prefix="DEBUG"):
        """Debug method to inspect citation objects thoroughly."""
        try:
            logger.info(f"[{prefix}] Citation object type: {type(citation)}")
            logger.info(f"[{prefix}] Citation object: {citation}")
            
            if hasattr(citation, '__dict__'):
                logger.info(f"[{prefix}] Citation object attributes: {citation.__dict__}")
                for attr, value in citation.__dict__.items():
                    logger.info(f"[{prefix}]   {attr}: {value} (type: {type(value)})")
            
            for attr in ['citation', 'extracted_case_name', 'extracted_date', 'extracted_year', 'canonical_name', 'canonical_date']:
                if hasattr(citation, attr):
                    value = getattr(citation, attr)
                    logger.info(f"[{prefix}]   {attr}: {value} (type: {type(value)})")
                else:
                    logger.info(f"[{prefix}]   {attr}: NOT FOUND")
                    
        except Exception as e:
            logger.error(f"[{prefix}] Debug failed: {e}")

    def _convert_citations_to_dicts_simplified(self, citations: List, clusters: List = None) -> List[Dict[str, Any]]:
        """Convert citations to simplified format for frontend."""
        converted = []
        
        true_by_parallel_citations = set()
        
        if clusters:
            for i, cluster in enumerate(clusters):
                cluster_has_verified = cluster.get('cluster_has_verified', False)
                cluster_citations = cluster.get('citations', [])
                
                if cluster_has_verified:
                    for citation_text in cluster_citations:
                        citation_verified = False
                        for citation in citations:
                            if isinstance(citation, dict):
                                if citation.get('citation') == citation_text and citation.get('verified', False):
                                    citation_verified = True
                                    break
                            elif hasattr(citation, 'citation'):
                                if getattr(citation, 'citation') == citation_text and getattr(citation, 'verified', False):
                                    citation_verified = True
                                    break
                        
                        
                        if not citation_verified:
                            true_by_parallel_citations.add(citation_text)
        
        
        for citation in citations:
            if isinstance(citation, dict):
                converted_citation = {
                    'citation': citation.get('citation', ''),
                    'extracted_case_name': citation.get('extracted_case_name'),
                    'extracted_date': citation.get('extracted_date'),
                    'canonical_name': citation.get('canonical_name'),
                    'canonical_date': citation.get('canonical_date'),
                    'canonical_url': citation.get('canonical_url'),
                    'verified': citation.get('verified', False),
                    'confidence_score': citation.get('confidence_score', 0.5),
                    'source': citation.get('source', 'local_extraction'),
                    'start_index': citation.get('start_index'),
                    'end_index': citation.get('end_index'),
                    'extraction_method': citation.get('extraction_method', 'unknown'),
                    'validation_method': citation.get('validation_method', 'none'),
                    'verification_completed': citation.get('verified', False),
                    'verification_confidence': citation.get('verification_confidence', 0.0),
                    'verification_method': 'unknown',
                    'verification_source': citation.get('source', 'CaseMine'),
                    'verification_timestamp': time.time(),
                    'false_positive_filtered': False,
                    'true_by_parallel': citation.get('citation', '') in true_by_parallel_citations
                }
                
                citation_text = citation.get('citation', '')
                true_by_parallel_value = citation_text in true_by_parallel_citations
                
                verification_result = citation.get('verification_result')
                if verification_result:
                    converted_citation.update({
                        'verified': verification_result.get('verified', False),
                        'canonical_name': verification_result.get('canonical_name'),
                        'canonical_date': verification_result.get('canonical_date'),
                        'canonical_url': verification_result.get('canonical_url') or verification_result.get('url'),
                        'source': verification_result.get('source'),
                        'validation_method': verification_result.get('validation_method'),
                        'verification_confidence': verification_result.get('confidence', 0.0)
                    })

                cn = converted_citation.get('canonical_name')
                if not cn or (isinstance(cn, str) and cn.strip().lower() == 'unknown case'):
                    converted_citation['verified'] = False
                    converted_citation['canonical_name'] = None
                    converted_citation['canonical_date'] = None

                cu = converted_citation.get('canonical_url')
                if cu and isinstance(cu, str):
                    # keep as-is if already CL
                    pass
                else:
                    cu = None
                alt_url = citation.get('url') if isinstance(citation, dict) else None
                if alt_url and isinstance(alt_url, str) and 'courtlistener.com' in alt_url:
                    converted_citation['canonical_url'] = alt_url
                elif cu and 'courtlistener.com' in cu:
                    converted_citation['canonical_url'] = cu
                
                converted.append(converted_citation)
                
            elif hasattr(citation, 'citation'):
                try:
                    citation_text = getattr(citation, 'citation', str(citation))
                    case_name = getattr(citation, 'extracted_case_name', None)
                    extracted_date = getattr(citation, 'extracted_date', None) or getattr(citation, 'extracted_year', None)
                    confidence = getattr(citation, 'confidence', 0.7) or getattr(citation, 'confidence_score', 0.7)
                    method = getattr(citation, 'method', 'citation_object') or getattr(citation, 'extraction_method', 'citation_object')
                    verified = getattr(citation, 'verified', False)
                    true_by_parallel = citation_text in true_by_parallel_citations
                    url = getattr(citation, 'url', None) or getattr(citation, 'canonical_url', None)
                    start_index = getattr(citation, 'start_index', None)
                    end_index = getattr(citation, 'end_index', None)
                    
                    source = 'citation_object'
                    validation_method = 'object_extraction'
                    canonical_name = None
                    canonical_date = None
                    canonical_url = url
                    is_verified = verified
                    
                    if hasattr(citation, 'verification_result') and citation.verification_result:
                        verification_result = citation.verification_result
                        if verification_result.get('verified'):
                            is_verified = True
                            source = verification_result.get('source', 'CourtListener')
                            validation_method = verification_result.get('validation_method', 'enhanced_verification')
                            
                            verification_canonical_name = verification_result.get('canonical_name')
                            if verification_canonical_name and case_name:
                                if self._are_case_names_similar(case_name, verification_canonical_name):
                                    canonical_name = verification_canonical_name
                            elif verification_canonical_name:
                                canonical_name = verification_canonical_name
                            
                            if verification_result.get('canonical_date'):
                                canonical_date = verification_result.get('canonical_date')
                            if verification_result.get('canonical_url'):
                                canonical_url = verification_result.get('canonical_url')
                            elif verification_result.get('url'):
                                canonical_url = verification_result.get('url')

                            vr_url = verification_result.get('url')
                            if vr_url and isinstance(vr_url, str) and 'courtlistener.com' in vr_url:
                                canonical_url = vr_url
                    
                    converted_citation = {
                        'citation': citation_text,
                        'extracted_case_name': case_name,
                        'extracted_date': extracted_date,
                        'canonical_name': canonical_name,
                        'canonical_date': canonical_date,
                        'canonical_url': canonical_url,
                        'verified': is_verified,
                        'confidence_score': confidence,
                        'source': source,
                        'start_index': start_index,
                        'end_index': end_index,
                        'extraction_method': method,
                        'validation_method': validation_method,
                        'verification_completed': is_verified,
                        'verification_confidence': confidence,
                        'verification_method': 'unknown',
                        'verification_source': source,
                        'verification_timestamp': time.time(),
                        'false_positive_filtered': False,
                        'true_by_parallel': true_by_parallel
                    }

                    cn2 = converted_citation.get('canonical_name')
                    if not cn2 or (isinstance(cn2, str) and cn2.strip().lower() == 'unknown case'):
                        converted_citation['verified'] = False
                        converted_citation['verification_completed'] = False
                        converted_citation['canonical_name'] = None
                        converted_citation['canonical_date'] = None
                    
                    converted.append(converted_citation)
                    
                except Exception as e:
                    logger.warning(f"Failed to convert citation object: {e}")
                    converted.append({
                        'citation': str(citation),
                        'extracted_case_name': None,
                        'extracted_date': None,
                        'canonical_name': None,
                        'canonical_date': None,
                        'canonical_url': None,
                        'verified': False,
                        'confidence_score': 0.5,
                        'source': 'object_fallback',
                        'extraction_method': 'object_fallback',
                        'validation_method': 'none',
                        'verification_completed': False,
                        'verification_confidence': 0.0,
                        'verification_method': 'unknown',
                        'verification_source': 'CaseMine',
                        'verification_timestamp': time.time(),
                        'false_positive_filtered': False,
                        'true_by_parallel': False
                    })
            else:
                converted.append({
                    'citation': str(citation),
                    'extracted_case_name': None,
                    'extracted_date': None,
                    'canonical_name': None,
                    'canonical_date': None,
                    'canonical_url': None,
                    'verified': False,
                    'confidence_score': 0.5,
                    'source': 'fallback',
                    'extraction_method': 'fallback',
                    'validation_method': 'none',
                    'verification_completed': False,
                    'verification_confidence': 0.0,
                    'verification_method': 'unknown',
                    'verification_source': 'CaseMine',
                    'verification_timestamp': time.time(),
                    'false_positive_filtered': False,
                    'true_by_parallel': False
                })
        
        return converted
    def _transform_citation_for_frontend(self, backend_citation: Dict[str, Any]) -> Dict[str, Any]:
        """Transform backend citation format to frontend-expected format."""
        try:
            metadata = {
                'source': backend_citation.get('source'),
                'year': backend_citation.get('canonical_date'),
                'court': backend_citation.get('court'),
                'reporter': self._extract_reporter_from_citation(backend_citation.get('citation', '')),
                'volume': self._extract_volume_from_citation(backend_citation.get('citation', '')),
                'page': self._extract_page_from_citation(backend_citation.get('citation', '')),
                'url': backend_citation.get('url') or backend_citation.get('canonical_url')
            }
            
            frontend_citation = {
                'text': backend_citation.get('citation'),           # citation -> text
                'name': backend_citation.get('canonical_name'),     # canonical_name -> name
                'valid': backend_citation.get('verified'),          # verified -> valid
                'url': backend_citation.get('url') or backend_citation.get('canonical_url'),
                'metadata': metadata,                               # Wrap in metadata object
                'contexts': [],                                    # Empty contexts array for now
                'extracted_case_name': backend_citation.get('extracted_case_name'),
                'extracted_date': backend_citation.get('extracted_date'),
                'canonical_name': backend_citation.get('canonical_name'),
                'canonical_date': backend_citation.get('canonical_date'),
                'source': backend_citation.get('source'),
                'verified': backend_citation.get('verified')
            }
            
            return frontend_citation
            
        except Exception as e:
            logger.error(f"Failed to transform citation for frontend: {e}")
            return {
                'text': backend_citation.get('citation', 'Unknown'),
                'name': backend_citation.get('canonical_name', 'Unknown'),
                'valid': backend_citation.get('verified', False),
                'url': None,
                'metadata': {'source': 'error'},
                'contexts': []
            }
    
    def _extract_reporter_from_citation(self, citation_text: str) -> Optional[str]:
        """Extract reporter from citation text."""
        import re
        if not citation_text:
            return None
        
        patterns = [
            r'\bWn\.\d*d?\b',      # Wn.2d, Wn.3d
            r'\bP\.\d*d?\b',       # P.2d, P.3d
            r'\bU\.S\.\b',         # U.S.
            r'\bS\.Ct\.\b',        # S.Ct.
            r'\bWn\.\s*App\.\b',   # Wn. App.
            r'\bF\.\d*d?\b',       # F.2d, F.3d
            r'\bF\.Supp\.\b',      # F.Supp.
        ]
        
        for pattern in patterns:
            match = re.search(pattern, citation_text)
            if match:
                return match.group(0)
        
        return None
    
    def _extract_volume_from_citation(self, citation_text: str) -> Optional[str]:
        """Extract volume number from citation text."""
        import re
        if not citation_text:
            return None
        
        match = re.match(r'^(\d+)', citation_text)
        if match:
            return match.group(1)
        
        return None
    
    def _extract_page_from_citation(self, citation_text: str) -> Optional[str]:
        """Extract page number from citation text."""
        import re
        if not citation_text:
            return None
        
        match = re.search(r'(\d+)\s*$', citation_text)
        if match:
            return match.group(1)
        
        return None
    
    def _convert_clusters_to_dicts(self, clusters: List) -> List[Dict[str, Any]]:
        """Convert cluster objects to dictionaries for API response."""
        clusters_list = []
        if clusters:
            for cluster in clusters:
                if isinstance(cluster, dict):
                    cluster_dict = cluster.copy()
                    
                    case_name, canonical_name, canonical_date = self._get_best_cluster_names(cluster_dict)
                    year = cluster_dict.get('year')
                    
                    if 'extracted_case_name' not in cluster_dict:
                        cluster_dict['extracted_case_name'] = case_name
                    if 'extracted_date' not in cluster_dict:
                        cluster_dict['extracted_date'] = year
                    if 'canonical_name' not in cluster_dict:
                        cluster_dict['canonical_name'] = canonical_name  # Use canonical if available
                    if 'canonical_date' not in cluster_dict:
                        cluster_dict['canonical_date'] = canonical_date  # Use canonical if available
                    if 'verified' not in cluster_dict:
                        cluster_dict['verified'] = False
                    if 'source' not in cluster_dict:
                        cluster_dict['source'] = 'local_extraction'
                    if 'validation_method' not in cluster_dict:
                        cluster_dict['validation_method'] = 'local_clustering'
                    
                    if 'citation_objects' in cluster_dict:
                        detailed_citations = []
                        for citation_obj in cluster_dict['citation_objects']:
                            if isinstance(citation_obj, dict):
                                citation_detail = {
                                    'citation': citation_obj.get('citation', str(citation_obj)),
                                    'extracted_case_name': citation_obj.get('extracted_case_name'),
                                    'extracted_date': citation_obj.get('extracted_date'),
                                    'verified': citation_obj.get('verified', False),
                                    'true_by_parallel': citation_obj.get('true_by_parallel', False),
                                    'canonical_name': None,  # Will be populated by verification services
                                    'canonical_date': None,  # Will be populated by verification services
                                    'source': citation_obj.get('source', 'local_extraction'),
                                    'validation_method': citation_obj.get('validation_method', 'object_extraction'),
                                    'confidence_score': citation_obj.get('confidence_score', 0.7)
                                }
                            else:
                                citation_detail = {
                                    'citation': getattr(citation_obj, 'citation', str(citation_obj)),
                                    'extracted_case_name': getattr(citation_obj, 'extracted_case_name', None),
                                    'extracted_date': getattr(citation_obj, 'extracted_date', None),
                                    'verified': getattr(citation_obj, 'verified', False),
                                    'true_by_parallel': getattr(citation_obj, 'true_by_parallel', False),
                                    'canonical_name': None,  # Will be populated by verification services
                                    'canonical_date': None,  # Will be populated by verification services
                                    'source': getattr(citation_obj, 'source', 'local_extraction'),
                                    'validation_method': getattr(citation_obj, 'validation_method', 'object_extraction'),
                                    'confidence_score': getattr(citation_obj, 'confidence_score', 0.7)
                                }
                            detailed_citations.append(citation_detail)
                        
                        cluster_dict['detailed_citations'] = detailed_citations
                        cluster_dict['citation_objects'] = detailed_citations  # Copy to citation_objects for frontend compatibility
                else:
                    case_name = getattr(cluster, 'case_name', None)
                    year = getattr(cluster, 'year', None)
                    
                    canonical_name = None
                    canonical_date = None
                    citations = getattr(cluster, 'citations', [])
                    
                    for citation in citations:
                        if hasattr(citation, 'canonical_name') and citation.canonical_name:
                            canonical_name = citation.canonical_name
                            if hasattr(citation, 'extracted_case_name') and citation.extracted_case_name:
                                case_name = citation.extracted_case_name
                            else:
                                # case_name should only come from extracted_case_name
                                pass
                            if hasattr(citation, 'canonical_date') and citation.canonical_date:
                                canonical_date = citation.canonical_date
                            break
                    
                    cluster_dict = {
                        'cluster_id': getattr(cluster, 'cluster_id', None),
                        'case_name': case_name,
                        'year': year,
                        'citations': [str(c) for c in citations],
                        'reporter': getattr(cluster, 'reporter', None),
                        'cluster_type': getattr(cluster, 'cluster_type', 'local'),
                        'size': len(citations),
                        'extracted_case_name': case_name,
                        'extracted_date': year,
                        'canonical_name': canonical_name,  # Use canonical if available
                        'canonical_date': canonical_date,  # Use canonical if available
                        'verified': bool(canonical_name),  # Consider verified if we have canonical data
                        'source': 'local_extraction',
                        'validation_method': 'local_clustering'
                    }
                clusters_list.append(cluster_dict)
        
        return clusters_list
    
    def _cleanup_cache(self):
        """Clean up old cache entries to prevent memory bloat."""
        current_time = time.time()
        if current_time - self._last_cache_cleanup > self._cache_cleanup_interval:
            old_keys = [
                key for key, value in self.cache.items()
                if current_time - value.get('cache_time', 0) > self.cache_ttl
            ]
            for key in old_keys:
                del self.cache[key]
            
            if old_keys:
                logger.info(f"[EnhancedSyncProcessor] Cleared {len(old_keys)} old cache entries")
            
            self._last_cache_cleanup = current_time
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for monitoring."""
        return {
            'cache': {
                'cache_size': len(self.cache),
                'cache_ttl': self.cache_ttl
            },
            'thresholds': {
                'enhanced_sync_threshold': self.enhanced_sync_threshold,
                'ultra_fast_threshold': self.ultra_fast_threshold,
                'clustering_threshold': self.clustering_threshold,
                'max_citations_for_local_clustering': self.max_citations_for_local_clustering
            },
            'processing_modes': ['enhanced_sync', 'basic_sync', 'full_async_redirect'],
            'features': ['local_extraction', 'local_normalization', 'local_clustering', 'async_verification']
        }
    
    def _are_case_names_similar(self, extracted_name: str, verification_name: str) -> bool:
        """
        Check if two case names are similar enough to trust verification result.
        UPDATED: More lenient to prefer canonical names from CourtListener/CaseMine.
        
        Args:
            extracted_name: Case name extracted from document
            verification_name: Case name from verification result
            
        Returns:
            True if names are similar enough to trust verification
        """
        if not extracted_name or not verification_name:
            return False
        
        extracted_normalized = extracted_name.lower().strip()
        verification_normalized = verification_name.lower().strip()
        
        if extracted_normalized == verification_normalized:
            return True
        
        if extracted_normalized in verification_normalized or verification_normalized in extracted_normalized:
            return True
        
        extracted_words = set(word.lower() for word in extracted_normalized.split() if len(word) > 2)
        verification_words = set(word.lower() for word in verification_normalized.split() if len(word) > 2)
        
        stop_words = {'the', 'and', 'or', 'of', 'in', 'for', 'to', 'a', 'an', 'on', 'at', 'by', 'with', 'from', 'up', 'out', 'about', 'into', 'through', 'during', 'before', 'after', 'above', 'below', 'between', 'among', 'within', 'without', 'against', 'toward', 'towards', 'upon', 'across', 'behind', 'beneath', 'beside', 'beyond', 'inside', 'outside', 'under', 'over', 'inc', 'llc', 'corp', 'ltd', 'co'}
        extracted_words -= stop_words
        verification_words -= stop_words
        
        word_variations = {
            'cnty': 'county', 'dept': 'department', 'dep': 'department', 
            'bros': 'brothers', 'co': 'company', 'corp': 'corporation',
            'inc': 'incorporated', 'llc': 'limited', 'ltd': 'limited'
        }
        
        def normalize_words(words):
            normalized = set()
            for word in words:
                normalized.add(word_variations.get(word, word))
            return normalized
        
        extracted_words = normalize_words(extracted_words)
        verification_words = normalize_words(verification_words)
        
        if extracted_words and verification_words:
            overlap = extracted_words.intersection(verification_words)
            
            if len(verification_name) > len(extracted_name):
                extracted_coverage = len(overlap) / len(extracted_words) if extracted_words else 0
                if extracted_coverage >= 0.5:  # 50% of extracted words found in verification
                    return True
            
            overlap_ratio = len(overlap) / max(len(extracted_words), len(verification_words))
            if overlap_ratio >= 0.2:  # Lowered from 0.3 to 0.2 for more leniency
                return True
        
        extracted_parts = extracted_normalized.split(' v. ')
        verification_parts = verification_normalized.split(' v. ')
        
        if len(extracted_parts) == 2 and len(verification_parts) == 2:
            for i in range(2):
                extracted_party = extracted_parts[i].strip()
                verification_party = verification_parts[i].strip()
                
                if (extracted_party in verification_party or 
                    verification_party in extracted_party or
                    self._are_party_names_similar(extracted_party, verification_party)):
                    return True
        
        return False
    
    def _are_party_names_similar(self, party1: str, party2: str) -> bool:
        """Check if two party names are similar (handles typos, abbreviations)."""
        if not party1 or not party2:
            return False
            
        if len(party1) > 0 and len(party2) > 0:
            chars1 = set(party1.lower())
            chars2 = set(party2.lower())
            overlap = chars1.intersection(chars2)
            
            max_len = max(len(party1), len(party2))
            if max_len > 0 and len(overlap) / max_len >= 0.7:
                return True
        
        return False
    
    def _get_best_cluster_names(self, cluster_dict: Dict[str, Any]) -> tuple[str, str, str]:
        """
        Get the best case name, canonical name, and canonical date for a cluster.
        Prioritizes canonical names from verified citations over extracted names.
        
        Returns:
            tuple: (best_case_name, canonical_name, canonical_date)
        """
        best_case_name = cluster_dict.get('case_name')
        best_canonical_name = None
        best_canonical_date = None
        
        citation_objects = cluster_dict.get('citation_objects', [])
        if citation_objects:
            for citation_obj in citation_objects:
                if isinstance(citation_obj, dict):
                    canonical_name = citation_obj.get('canonical_name')
                    canonical_date = citation_obj.get('canonical_date')
                    is_verified = citation_obj.get('verified', False)
                    
                    if canonical_name and is_verified:
                        best_canonical_name = canonical_name
                        # best_case_name should only come from extracted_case_name
                        # canonical_name and extracted_case_name must remain completely separate
                        if not best_case_name and isinstance(citation_obj, dict) and citation_obj.get('extracted_case_name'):
                            best_case_name = citation_obj.get('extracted_case_name')
                        elif not best_case_name:
                            pass  # No extracted case name available
                        
                        if canonical_date:
                            best_canonical_date = canonical_date
                        break
                else:
                    canonical_name = getattr(citation_obj, 'canonical_name', None)
                    canonical_date = getattr(citation_obj, 'canonical_date', None)
                    is_verified = getattr(citation_obj, 'verified', False)
                    
                    if canonical_name and is_verified:
                        best_canonical_name = canonical_name
                        if not best_case_name and hasattr(citation_obj, 'extracted_case_name'):
                            best_case_name = citation_obj.get('extracted_case_name')
                        elif not best_case_name:
                            pass  # No extracted case name available
                        
                        if canonical_date:
                            best_canonical_date = canonical_date
                        break
            
            if not best_canonical_name:
                for citation_obj in citation_objects:
                    if isinstance(citation_obj, dict):
                        canonical_name = citation_obj.get('canonical_name')
                        canonical_date = citation_obj.get('canonical_date')
                    else:
                        canonical_name = getattr(citation_obj, 'canonical_name', None)
                        canonical_date = getattr(citation_obj, 'canonical_date', None)
                    
                    if canonical_name:
                        best_canonical_name = canonical_name
                        if not best_case_name:
                            if isinstance(citation_obj, dict):
                                extracted_name = citation_obj.get('extracted_case_name')
                            else:
                                extracted_name = getattr(citation_obj, 'extracted_case_name', None)
                            
                            best_case_name = extracted_name if extracted_name else None
                            if not best_case_name:
                                pass  # No extracted case name available
                        
                        if canonical_date:
                            best_canonical_date = canonical_date
                        break
        
        return best_case_name, best_canonical_name, best_canonical_date
    
    def _update_cluster_verification_status(self, clusters: List[Dict[str, Any]], citations: List[Dict[str, Any]]) -> None:
        """Update cluster verification status based on individual citation verification status."""
        try:
            if not clusters or not citations:
                return
            
            # Create lookup for quick citation verification status check
            citation_verification_lookup = {}
            for citation in citations:
                citation_text = citation.get('citation', '')
                if citation_text:
                    citation_verification_lookup[citation_text] = citation.get('verified', False)
            
            logger.info(f"[CLUSTER_VERIFICATION] Updating verification status for {len(clusters)} clusters based on {len(citations)} citations")
            
            # Update each cluster's verification status
            for cluster in clusters:
                if not isinstance(cluster, dict):
                    continue
                
                cluster_citations = cluster.get('citations', [])
                if not cluster_citations:
                    continue
                
                # Count verified citations in this cluster
                verified_count = 0
                total_count = len(cluster_citations)
                
                for citation_text in cluster_citations:
                    if citation_verification_lookup.get(citation_text, False):
                        verified_count += 1
                
                # Update cluster verification status
                cluster_has_verified = verified_count > 0
                cluster['verified'] = cluster_has_verified
                cluster['cluster_has_verified'] = cluster_has_verified
                cluster['verified_citations'] = verified_count
                cluster['total_citations'] = total_count
                
                # Update canonical data from first verified citation if available
                if cluster_has_verified and not cluster.get('canonical_name'):
                    for citation_text in cluster_citations:
                        for citation in citations:
                            if (citation.get('citation') == citation_text and 
                                citation.get('verified', False) and 
                                citation.get('canonical_name')):
                                cluster['canonical_name'] = citation.get('canonical_name')
                                cluster['canonical_date'] = citation.get('canonical_date')
                                cluster['canonical_url'] = citation.get('canonical_url')
                                break
                        if cluster.get('canonical_name'):
                            break
                
                # Update detailed_citations verification status and apply true_by_parallel logic
                if 'detailed_citations' in cluster:
                    for detailed_citation in cluster['detailed_citations']:
                        citation_text = detailed_citation.get('citation', '')
                        if citation_text in citation_verification_lookup:
                            is_verified = citation_verification_lookup[citation_text]
                            detailed_citation['verified'] = is_verified
                            
                            if is_verified:
                                # Find the corresponding full citation data
                                for citation in citations:
                                    if citation.get('citation') == citation_text:
                                        detailed_citation['canonical_name'] = citation.get('canonical_name')
                                        detailed_citation['canonical_date'] = citation.get('canonical_date')
                                        detailed_citation['canonical_url'] = citation.get('canonical_url')
                                        break
                            elif cluster_has_verified:
                                # Mark unverified citations as true_by_parallel if cluster has verified citations
                                detailed_citation['true_by_parallel'] = True
                                logger.info(f"[CLUSTER_VERIFICATION] Citation '{citation_text}' marked as true_by_parallel in verified cluster")
                
                # CRITICAL: Apply true_by_parallel to individual citation objects as well
                if cluster_has_verified:
                    for citation_text in cluster_citations:
                        for citation in citations:
                            if (citation.get('citation') == citation_text and 
                                not citation.get('verified', False)):
                                citation['true_by_parallel'] = True
                                logger.info(f"[CLUSTER_VERIFICATION] Individual citation '{citation_text}' marked as true_by_parallel")
                                break
                
                logger.info(f"[CLUSTER_VERIFICATION] Cluster '{cluster.get('cluster_id', 'unknown')}': {verified_count}/{total_count} citations verified -> cluster verified: {cluster_has_verified}")
            
        except Exception as e:
            logger.error(f"[CLUSTER_VERIFICATION] Error updating cluster verification status: {e}")
    
    def _apply_canonical_names_to_objects(self, citations: List) -> None:
        """
        Apply canonical names to citation objects BEFORE clustering.
        This ensures clustering uses clean canonical names instead of contaminated extracted names.
        """
        for citation in citations:
            try:
                if hasattr(citation, 'extracted_case_name'):
                    current_extracted = citation.extracted_case_name
                else:
                    current_extracted = getattr(citation, 'case_name', None)
                
                if hasattr(citation, 'verification_result') and citation.verification_result:
                    verification_result = citation.verification_result
                    verification_canonical_name = verification_result.get('canonical_name')
                    
                    if verification_canonical_name and current_extracted:
                        if self._are_case_names_similar(current_extracted, verification_canonical_name):
                            if hasattr(citation, 'canonical_name'):
                                citation.canonical_name = verification_canonical_name
                            
                            logger.info(f"🎯 PRE-CLUSTERING: Updated canonical name: '{verification_canonical_name}' (keeping extracted: '{current_extracted}' for clustering)")
                        else:
                            logger.warning(f"⚠️ PRE-CLUSTERING: Verification result differs significantly: extracted='{current_extracted}' vs verification='{verification_canonical_name}' - keeping extracted")
                
            except Exception as e:
                logger.error(f"Error applying canonical name to citation object: {e}")
                continue

    def _update_with_verification_results(self, result: Dict[str, Any], verification_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update the result with verification results from external services.
        """
        try:
            if not verification_results or not result.get('citations'):
                return result
            
            verified_citations = verification_results.get('citations', {})
            
            for citation in result['citations']:
                citation_text = citation.get('citation', str(citation))
                if citation_text in verified_citations:
                    verification_data = verified_citations[citation_text]
                    
                    if verification_data.get('canonical_name'):
                        citation['canonical_name'] = verification_data['canonical_name']
                    if verification_data.get('canonical_date'):
                        citation['canonical_date'] = verification_data['canonical_date']
                    if verification_data.get('canonical_url'):
                        citation['canonical_url'] = verification_data['canonical_url']
                    
                    citation['verified'] = verification_data.get('verified', False)
                    citation['source'] = verification_data.get('source', 'external_verification')
                    citation['validation_method'] = verification_data.get('method', 'external_verification')
            
            if result.get('clusters') and verification_results.get('clusters'):
                verified_clusters = verification_results['clusters']
            
                for cluster in result['clusters']:
                    cluster_key = f"{cluster.get('extracted_case_name', '')}_{cluster.get('extracted_date', '')}"
                    
                    if cluster_key in verified_clusters:
                        cluster_data = verified_clusters[cluster_key]
                        
                        if cluster_data.get('canonical_name'):
                            cluster['canonical_name'] = cluster_data['canonical_name']
                        if cluster_data.get('canonical_date'):
                            cluster['canonical_date'] = cluster_data['canonical_date']
                        
                        cluster['verified'] = True
                        cluster['source'] = cluster_data.get('source', 'external_verification')
                        cluster['validation_method'] = cluster_data.get('method', 'external_verification')
            
            logger.info(f"Updated result with verification data for {len(verified_citations)} citations")
            return result
            
        except Exception as e:
            logger.error(f"Error updating result with verification data: {e}")
            return result
    
    def _perform_courtlistener_sync_verification(self, citations: List[Dict[str, Any]], request_id: str) -> Dict[str, Any]:
        """
        Perform synchronous verification of citations using CourtListener citation-lookup API.
        
        Args:
            citations: List of citations to verify
            request_id: Request identifier for logging
            
        Returns:
            Verification results dictionary
        """
        try:
            logger.info(f"[EnhancedSyncProcessor {request_id}] Starting CourtListener sync verification for {len(citations)} citations")
            
            citation_texts = [c.get('citation', str(c)) for c in citations]
            
            try:
                from verification_services import CourtListenerService
                courtlistener_service = CourtListenerService()
                
                verification_results = courtlistener_service.verify_citations_batch(citation_texts)
                
                if verification_results and verification_results.get('citations'):
                    logger.info(f"[EnhancedSyncProcessor {request_id}] CourtListener sync verification successful")
                    return verification_results
                else:
                    logger.warning(f"[EnhancedSyncProcessor {request_id}] CourtListener sync verification returned no results")
                    
            except Exception as e:
                logger.warning(f"[EnhancedSyncProcessor {request_id}] CourtListener sync verification failed: {e}")
            
            return {
                'citations': {},
                'clusters': {},
                'status': 'failed',
                'method': 'courtlistener_sync_failed'
            }
            
        except Exception as e:
            logger.error(f"[EnhancedSyncProcessor {request_id}] Error in CourtListener sync verification: {e}")
            return {
                'citations': {},
                'clusters': {},
                'status': 'failed',
                'error': str(e),
                'method': 'courtlistener_sync_error'
            }
    
    def _perform_sync_verification(self, citations: List[Dict[str, Any]], request_id: str) -> Dict[str, Any]:
        """
        Perform synchronous verification of citations using CourtListener API.
        
        Args:
            citations: List of citations to verify
            request_id: Request identifier for logging
            
        Returns:
            Verification results dictionary
        """
        try:
            logger.info(f"[EnhancedSyncProcessor {request_id}] Starting synchronous verification for {len(citations)} citations")
            
            citation_texts = [c.get('citation', str(c)) for c in citations]
            
            try:
                from verification_services import CourtListenerService
                courtlistener_service = CourtListenerService()
                
                verification_results = courtlistener_service.verify_citations_batch(citation_texts)
                
                if verification_results and verification_results.get('citations'):
                    logger.info(f"[EnhancedSyncProcessor {request_id}] CourtListener verification successful")
                    return verification_results
                else:
                    logger.warning(f"[EnhancedSyncProcessor {request_id}] CourtListener verification returned no results")
                    
            except Exception as e:
                logger.warning(f"[EnhancedSyncProcessor {request_id}] CourtListener verification failed: {e}")
            
            return {
                'citations': {},
                'clusters': {},
                'status': 'completed',
                'method': 'sync_verification_fallback'
            }
            
        except Exception as e:
            logger.error(f"[EnhancedSyncProcessor {request_id}] Error in synchronous verification: {e}")
            return {
                'citations': {},
                'clusters': {},
                'status': 'failed',
                'error': str(e),
                'method': 'sync_verification_error'
            }
    
    def _wait_and_merge_verification_results(self, result: Dict[str, Any], request_id: str, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Wait for async verification results and merge them back into the result.
        
        Args:
            result: The current result dictionary
            request_id: Request identifier for logging
            job_id: RQ job ID to wait for
            
        Returns:
            Updated result with verification data merged, or None if failed
        """
        try:
            logger.info(f"[EnhancedSyncProcessor {request_id}] Waiting for verification job {job_id} to complete...")
            
            from redis import Redis
            from rq import Queue
            
            redis_url = os.getenv('REDIS_URL', 'redis://:caseStrainerRedis123@casestrainer-redis-prod:6379/0')
            redis_conn = Redis.from_url(redis_url)
            queue = Queue('casestrainer', connection=redis_conn)
            
            max_wait_time = 120  # Wait up to 120 seconds for verification (increased for reliability)
            start_time = time.time()
            
            while time.time() - start_time < max_wait_time:
                job = queue.fetch_job(job_id)
                if not job:
                    logger.warning(f"[EnhancedSyncProcessor {request_id}] Job {job_id} not found")
                    return None
                
                if job.is_finished:
                    logger.info(f"[EnhancedSyncProcessor {request_id}] Verification job {job_id} completed")
                    break
                elif job.is_failed:
                    logger.error(f"[EnhancedSyncProcessor {request_id}] Verification job {job_id} failed: {job.exc_info}")
                    return None
                
                time.sleep(0.5)
            else:
                logger.warning(f"[EnhancedSyncProcessor {request_id}] Verification job {job_id} timed out after {max_wait_time}s")
                return None
            
            verification_results = job.result
            if not verification_results:
                logger.warning(f"[EnhancedSyncProcessor {request_id}] Verification job {job_id} returned no results")
                return None
            
            logger.info(f"[EnhancedSyncProcessor {request_id}] Got verification results: {len(verification_results)} citations")
            
            logger.info(f"[EnhancedSyncProcessor {request_id}] Verification results type: {type(verification_results)}")
            logger.info(f"[EnhancedSyncProcessor {request_id}] Verification results keys: {list(verification_results.keys()) if isinstance(verification_results, dict) else 'Not a dict'}")
            
            if isinstance(verification_results, dict):
                if 'citations' in verification_results:
                    verification_citations = verification_results['citations']
                    logger.info(f"[EnhancedSyncProcessor {request_id}] Found 'citations' key with {len(verification_citations)} items")
                else:
                    verification_citations = [verification_results]
                    logger.info(f"[EnhancedSyncProcessor {request_id}] No 'citations' key, treating whole dict as single result")
            elif isinstance(verification_results, list):
                verification_citations = verification_results
                logger.info(f"[EnhancedSyncProcessor {request_id}] Verification results is already a list")
            else:
                logger.error(f"[EnhancedSyncProcessor {request_id}] Unexpected verification results type: {type(verification_results)}")
                return None
            
            converted_verification_citations = []
            for verif_result in verification_citations:
                if hasattr(verif_result, 'citation'):  # It's a CitationResult object
                    converted_result = {
                        'citation': getattr(verif_result, 'citation', ''),
                        'verified': getattr(verif_result, 'verified', False),
                        'canonical_name': getattr(verif_result, 'canonical_name', None),
                        'canonical_date': getattr(verif_result, 'canonical_date', None),
                        'canonical_url': getattr(verif_result, 'canonical_url', None),
                        'source': getattr(verif_result, 'source', 'unknown'),
                        'confidence': getattr(verif_result, 'confidence', 0.0),
                        'validation_method': getattr(verif_result, 'validation_method', 'enhanced_fallback')
                    }
                    converted_verification_citations.append(converted_result)
                else:
                    converted_verification_citations.append(verif_result)
            
            verification_citations = converted_verification_citations
            
            updated_result = result.copy()
            updated_citations = []
            
            for citation in result.get('citations', []):
                citation_text = citation.get('citation', str(citation))
                
                matching_result = None
                for verif_result in verification_citations:
                    if isinstance(verif_result, dict):
                        if verif_result.get('citation') == citation_text:
                            matching_result = verif_result
                            break
                    elif isinstance(verif_result, str):
                        logger.warning(f"[EnhancedSyncProcessor {request_id}] Verification result is string, not dict: {verif_result}")
                        continue
                    else:
                        logger.warning(f"[EnhancedSyncProcessor {request_id}] Unexpected verification result type: {type(verif_result)}")
                        continue
                
                if isinstance(citation, dict):
                    updated_citation = citation.copy()
                else:
                    updated_citation = {
                        'citation': getattr(citation, 'citation', str(citation)),
                        'extracted_case_name': getattr(citation, 'extracted_case_name', None),
                        'extracted_date': getattr(citation, 'extracted_date', None),
                        'confidence_score': getattr(citation, 'confidence', 0.7),
                        'extraction_method': getattr(citation, 'method', 'unknown'),
                        'false_positive_filtered': False,
                        'verified': False,
                        'true_by_parallel': False,
                        'canonical_name': None,
                        'canonical_date': None,
                        'url': None,
                        'source': 'citation_object',
                        'validation_method': 'object_extraction',
                        'verification_confidence': 0.7
                    }
                
                if matching_result:
                    if isinstance(matching_result, dict):
                        verified = matching_result.get('verified', False)
                        canonical_name = matching_result.get('canonical_name')
                        canonical_date = matching_result.get('canonical_date')
                        canonical_url = matching_result.get('canonical_url')
                        verification_source = matching_result.get('source')
                        verification_confidence = matching_result.get('confidence', 0.0)
                        verification_method = matching_result.get('validation_method', 'enhanced_fallback')
                    else:
                        verified = getattr(matching_result, 'verified', False)
                        canonical_name = getattr(matching_result, 'canonical_name', None)
                        canonical_date = getattr(matching_result, 'canonical_date', None)
                        canonical_url = getattr(matching_result, 'canonical_url', None)
                        verification_source = getattr(matching_result, 'source', None)
                        verification_confidence = getattr(matching_result, 'confidence', 0.0)
                        verification_method = getattr(matching_result, 'validation_method', 'enhanced_fallback')
                    
                    updated_citation.update({
                        'verified': verified,
                        'canonical_name': canonical_name,
                        'canonical_date': canonical_date,
                        'canonical_url': canonical_url,
                        'verification_source': verification_source,
                        'verification_confidence': verification_confidence,
                        'verification_method': verification_method,
                        'verification_completed': True,
                        'verification_timestamp': time.time()
                    })
                else:
                    updated_citation.update({
                        'verified': False,
                        'verification_source': 'verification_failed',
                        'verification_completed': True,
                        'verification_timestamp': time.time()
                    })
                
                updated_citations.append(updated_citation)
            
            updated_result['citations'] = updated_citations
            
            if result.get('clusters'):
                updated_clusters = []
                for cluster in result['clusters']:
                    if isinstance(cluster, dict):
                        updated_cluster = cluster.copy()
                    else:
                        updated_cluster = {
                            'case_name': getattr(cluster, 'case_name', ''),
                            'citations': getattr(cluster, 'citations', []),
                            'citation_objects': getattr(cluster, 'citation_objects', []),
                            'detailed_citations': getattr(cluster, 'detailed_citations', []),
                            'cluster_id': getattr(cluster, 'cluster_id', ''),
                            'cluster_type': getattr(cluster, 'cluster_type', ''),
                            'confidence_score': getattr(cluster, 'confidence_score', 0.0),
                            'size': getattr(cluster, 'size', 0),
                            'verified': getattr(cluster, 'verified', False),
                            'verified_citations': getattr(cluster, 'verified_citations', 0),
                            'total_citations': getattr(cluster, 'total_citations', 0),
                            'year': getattr(cluster, 'year', ''),
                            'extracted_case_name': getattr(cluster, 'extracted_case_name', ''),
                            'extracted_date': getattr(cluster, 'extracted_date', ''),
                            'source': getattr(cluster, 'source', ''),
                            'validation_method': getattr(cluster, 'validation_method', ''),
                            'cluster_has_verified': getattr(cluster, 'cluster_has_verified', False)
                        }
                    
                    cluster_citations = cluster.get('citations', [])
                    verified_citations = []
                    unverified_citations = []
                    
                    for citation_text in cluster_citations:
                        for updated_citation in updated_citations:
                            if updated_citation.get('citation') == citation_text:
                                if updated_citation.get('verified'):
                                    verified_citations.append(updated_citation)
                                else:
                                    unverified_citations.append(updated_citation)
                                break
                    
                    updated_cluster['verified_citations'] = verified_citations
                    updated_cluster['unverified_citations'] = unverified_citations
                    updated_cluster['verification_status'] = 'completed'
                    updated_cluster['verification_timestamp'] = time.time()
                    
                    cluster_has_verified = len(verified_citations) > 0
                    updated_cluster['verified'] = cluster_has_verified
                    updated_cluster['cluster_has_verified'] = cluster_has_verified
                    
                    if cluster_has_verified:
                        for unverified_citation in unverified_citations:
                            for citation in updated_citations:
                                if citation.get('citation') == unverified_citation.get('citation'):
                                    citation['true_by_parallel'] = True
                                    break
                    
                    if cluster.get('citation_objects'):
                        updated_citation_objects = []
                        for citation_obj in cluster['citation_objects']:
                            updated_citation_obj = citation_obj.copy()
                            
                            citation_text = citation_obj.get('citation')
                            for verified_citation in updated_citations:
                                if verified_citation.get('citation') == citation_text:
                                    updated_citation_obj.update({
                                        'verified': verified_citation.get('verified', False),
                                        'canonical_name': verified_citation.get('canonical_name'),
                                        'canonical_date': verified_citation.get('canonical_date'),
                                        'canonical_url': verified_citation.get('canonical_url'),
                                        'verification_source': verified_citation.get('verification_source'),
                                        'verification_confidence': verified_citation.get('verification_confidence', 0.0),
                                        'verification_method': verified_citation.get('verification_method'),
                                        'verification_completed': verified_citation.get('verification_completed', False),
                                        'verification_timestamp': verified_citation.get('verification_timestamp'),
                                        'true_by_parallel': verified_citation.get('true_by_parallel', False)
                                    })
                                    
                                    if 'original_object' in updated_citation_obj:
                                        original_obj = updated_citation_obj['original_object'].copy()
                                        original_obj.update({
                                            'verified': verified_citation.get('verified', False),
                                            'canonical_name': verified_citation.get('canonical_name'),
                                            'canonical_date': verified_citation.get('canonical_date'),
                                            'canonical_url': verified_citation.get('canonical_url')
                                        })
                                        updated_citation_obj['original_object'] = original_obj
                                    
                                    break
                            
                            updated_citation_objects.append(updated_citation_obj)
                        
                        updated_cluster['citation_objects'] = updated_citation_objects
                        
                        if cluster.get('detailed_citations'):
                            updated_detailed_citations = []
                            for detailed_citation in cluster['detailed_citations']:
                                updated_detailed_citation = detailed_citation.copy()
                                
                                citation_text = detailed_citation.get('citation')
                                for verified_citation in updated_citations:
                                    if verified_citation.get('citation') == citation_text:
                                        updated_detailed_citation.update({
                                            'verified': verified_citation.get('verified', False),
                                            'canonical_name': verified_citation.get('canonical_name'),
                                            'canonical_date': verified_citation.get('canonical_date'),
                                            'canonical_url': verified_citation.get('canonical_url'),
                                            'verification_source': verified_citation.get('verification_source'),
                                            'verification_confidence': verified_citation.get('verification_confidence', 0.0),
                                            'verification_method': verified_citation.get('verification_method'),
                                            'verification_completed': verified_citation.get('verification_completed', False),
                                            'verification_timestamp': verified_citation.get('verification_timestamp')
                                        })
                                        break
                                
                                updated_detailed_citations.append(updated_detailed_citation)
                            
                            updated_cluster['detailed_citations'] = updated_detailed_citations
                    
                    updated_clusters.append(updated_cluster)
                
                updated_result['clusters'] = updated_clusters
            
            logger.info(f"[EnhancedSyncProcessor {request_id}] Successfully merged verification results")
            return updated_result
            
        except Exception as e:
            logger.error(f"[EnhancedSyncProcessor {request_id}] Error merging verification results: {e}")
            return None
    
    def _clean_case_name_for_clustering(self, case_name: str) -> Optional[str]:
        """Clean case name for clustering by removing extra context and normalizing."""
        if not case_name:
            return None
        
        context_phrases = [
            r'^We review statutory interpretation de novo\.\s*',
            r'^The goal of statutory interpretation is to give effect to the legislature\'s intentions\.\s*',
            r'^In determining the plain meaning of a statute, we look to the text of the statute, as well as its\s*',
            r'^Only if the plain text is susceptible to more than one interpretation do we turn to\s*',
        ]
        
        cleaned = case_name
        for pattern in context_phrases:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        case_patterns = [
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+[A-Z][a-z]+\.)*)\s+v\.\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+[A-Z][a-z]+\.)*)',  # Standard v. pattern - only capitalized
            r'(In\s+re\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',  # In re pattern - only capitalized
            r'(State\s+v\.\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',  # State v. pattern - only capitalized
        ]
        
        for idx, pattern in enumerate(case_patterns):
            match = re.search(pattern, cleaned)
            if match:
                if len(match.groups()) >= 2 and idx == 0:  # Two-party case
                    return f"{match.group(1).strip()} v. {match.group(2).strip()}"
                else:  # Single-party case
                    return match.group(1).strip()
        
        cleaned = cleaned.strip()
        if len(cleaned) > 100:  # Limit length to avoid very long case names
            return None
        
        return cleaned if cleaned else None

    def _update_clusters_with_verification(self, clusters: List[Dict], verification_results: List[Dict], request_id: str, citations: List = None):
        """Update clusters with verification data from citations."""
        try:
            logger.info(f"[EnhancedSyncProcessor {request_id}] _update_clusters_with_verification called with {len(clusters)} clusters and {len(verification_results)} verification results")
            logger.info(f"[EnhancedSyncProcessor {request_id}] Starting cluster processing loop")
            for cluster in clusters:
                verified_citations = 0
                total_citations = len(cluster.get('citations', []))
                
                if cluster.get('citation_objects'):
                    for citation_obj in cluster['citation_objects']:
                        citation_text = citation_obj.get('citation', '')
                        cleaned_citation = citation_text.replace('\n', ' ').replace('\r', ' ').strip()
                        cleaned_citation = ' '.join(cleaned_citation.split())
                        
                        for verif_result in verification_results:
                            if verif_result.get('citation') == cleaned_citation:
                                canonical_url = verif_result.get('canonical_url') or verif_result.get('url')
                                citation_obj.update({
                                    'verified': verif_result.get('verified', False),
                                    'canonical_name': verif_result.get('canonical_name'),
                                    'canonical_date': verif_result.get('canonical_date'),
                                    'canonical_url': canonical_url,
                                    'url': canonical_url,  # Also set url field
                                    'verification_source': verif_result.get('source'),
                                    'verification_confidence': verif_result.get('confidence', 0.0),
                                    'verification_method': verif_result.get('validation_method'),
                                    'verification_completed': True,
                                    'verification_timestamp': time.time()
                                })
                                
                                if verif_result.get('verified', False):
                                    verified_citations += 1
                                break
                
                if cluster.get('detailed_citations'):
                    for detailed_citation in cluster['detailed_citations']:
                        citation_text = detailed_citation.get('citation', '')
                        cleaned_citation = citation_text.replace('\n', ' ').replace('\r', ' ').strip()
                        cleaned_citation = ' '.join(cleaned_citation.split())
                        
                        for verif_result in verification_results:
                            if verif_result.get('citation') == cleaned_citation:
                                canonical_url = verif_result.get('canonical_url') or verif_result.get('url')
                                detailed_citation.update({
                                    'verified': verif_result.get('verified', False),
                                    'canonical_name': verif_result.get('canonical_name'),
                                    'canonical_date': verif_result.get('canonical_date'),
                                    'canonical_url': canonical_url,
                                    'url': canonical_url,  # Also set url field
                                    'verification_source': verif_result.get('source'),
                                    'verification_confidence': verif_result.get('confidence', 0.0),
                                    'verification_method': verif_result.get('validation_method'),
                                    'verification_completed': True,
                                    'verification_timestamp': time.time()
                                })
                                break
                
                cluster_has_verified = verified_citations > 0
                cluster.update({
                    'verified': cluster_has_verified,
                    'cluster_has_verified': cluster_has_verified,
                    'verified_citations': verified_citations,
                    'total_citations': total_citations
                })
                
                logger.info(f"[EnhancedSyncProcessor {request_id}] Checking cluster '{cluster.get('case_name', 'Unknown')}' - cluster_has_verified: {cluster_has_verified}")
                if cluster_has_verified:
                    logger.info(f"[EnhancedSyncProcessor {request_id}] Applying true_by_parallel logic for cluster '{cluster.get('case_name', 'Unknown')}'")
                    cluster_citations = cluster.get('citations', [])
                    logger.info(f"[EnhancedSyncProcessor {request_id}] Cluster citations: {cluster_citations}")
                    
                    # Check if cluster has any verified citations
                    cluster_has_verified = False
                    for citation_text in cluster_citations:
                        for verif_result in verification_results:
                            if verif_result.get('citation', '').replace('\n', ' ').replace('\r', ' ').strip() == citation_text:
                                if verif_result.get('verified', False):
                                    cluster_has_verified = True
                                    break
                        if cluster_has_verified:
                            break
                    
                    logger.info(f"[EnhancedSyncProcessor {request_id}] Cluster has verified citations: {cluster_has_verified}")
                    
                    for citation_text in cluster_citations:
                        citation_verified = False
                        for verif_result in verification_results:
                            if verif_result.get('citation', '').replace('\n', ' ').replace('\r', ' ').strip() == citation_text:
                                citation_verified = verif_result.get('verified', False)
                                break
                        
                        # Only set true_by_parallel for unverified citations if cluster has verified citations
                        if not citation_verified and cluster_has_verified:
                            logger.info(f"[EnhancedSyncProcessor {request_id}] Setting true_by_parallel=True for unverified citation '{citation_text}' in verified cluster")
                            if citations:
                                for citation in citations:
                                    if isinstance(citation, dict):
                                        if citation.get('citation') == citation_text:
                                            citation['true_by_parallel'] = True
                                            logger.info(f"[EnhancedSyncProcessor {request_id}] Set true_by_parallel=True for citation '{citation_text}'")
                                            break
                                    elif hasattr(citation, 'citation'):
                                        if getattr(citation, 'citation') == citation_text:
                                            setattr(citation, 'true_by_parallel', True)
                                            logger.info(f"[EnhancedSyncProcessor {request_id}] Set true_by_parallel=True for CitationResult '{citation_text}'")
                                            break
                        elif citation_verified:
                            # Verified citations should NOT have true_by_parallel
                            logger.info(f"[EnhancedSyncProcessor {request_id}] Citation '{citation_text}' is verified, setting true_by_parallel=False")
                            if citations:
                                for citation in citations:
                                    if isinstance(citation, dict):
                                        if citation.get('citation') == citation_text:
                                            citation['true_by_parallel'] = False
                                            logger.info(f"[EnhancedSyncProcessor {request_id}] Set true_by_parallel=False for verified citation '{citation_text}'")
                                            break
                                    elif hasattr(citation, 'citation'):
                                        if getattr(citation, 'citation') == citation_text:
                                            setattr(citation, 'true_by_parallel', False)
                                            logger.info(f"[EnhancedSyncProcessor {request_id}] Set true_by_parallel=False for verified CitationResult '{citation_text}'")
                                            break
                
                if cluster_has_verified:
                    for verif_result in verification_results:
                        if verif_result.get('verified', False):
                            citation_text = verif_result.get('citation', '')
                            cleaned_citation = citation_text.replace('\n', ' ').replace('\r', ' ').strip()
                            cleaned_citation = ' '.join(cleaned_citation.split())
                            
                            if cleaned_citation in cluster.get('citations', []):
                                canonical_url = verif_result.get('canonical_url') or verif_result.get('url')
                                cluster.update({
                                    'canonical_name': verif_result.get('canonical_name'),
                                    'canonical_date': verif_result.get('canonical_date'),
                                    'canonical_url': canonical_url
                                })
                                break
                
            
            logger.info(f"[EnhancedSyncProcessor {request_id}] Clusters updated with verification data")
            
        except Exception as e:
            logger.error(f"[EnhancedSyncProcessor {request_id}] Error updating clusters with verification data: {e}")
