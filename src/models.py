from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any

@dataclass
class CitationResult:
    citation: str
    extracted_case_name: Optional[str] = None
    extracted_date: Optional[str] = None
    canonical_name: Optional[str] = None
    canonical_date: Optional[str] = None
    canonical_url: Optional[str] = None
    verified: bool = False
    url: Optional[str] = None
    court: Optional[str] = None
    docket_number: Optional[str] = None
    confidence: float = 0.0
    method: str = "unified_processor"
    pattern: str = ""
    context: str = ""
    start_index: Optional[int] = None
    end_index: Optional[int] = None
    is_parallel: bool = False
    is_cluster: bool = False
    parallel_citations: Optional[List[str]] = None
    cluster_members: Optional[List[str]] = None
    pinpoint_pages: Optional[List[str]] = None
    docket_numbers: Optional[List[str]] = None
    case_history: Optional[List[str]] = None
    publication_status: Optional[str] = None
    source: str = "Unknown"
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    cluster_id: Optional[str] = None
    true_by_parallel: bool = False

    def __post_init__(self):
        if self.parallel_citations is None:
            self.parallel_citations = []
        if self.cluster_members is None:
            self.cluster_members = []
        if self.pinpoint_pages is None:
            self.pinpoint_pages = []
        if self.docket_numbers is None:
            self.docket_numbers = []
        if self.case_history is None:
            self.case_history = []
        if self.metadata is None:
            self.metadata = {}
            
    def to_dict(self):
        """Convert the CitationResult to a dictionary for JSON serialization."""
        result = {
            'citation': self.citation,
            'extracted_case_name': self.extracted_case_name,
            'extracted_date': self.extracted_date,
            'canonical_name': self.canonical_name,
            'canonical_date': self.canonical_date,
            'canonical_url': self.canonical_url,
            'verified': self.verified,
            'url': self.url,
            'court': self.court,
            'docket_number': self.docket_number,
            'confidence': self.confidence,
            'method': self.method,
            'pattern': self.pattern,
            'context': self.context,
            'start_index': self.start_index,
            'end_index': self.end_index,
            'is_parallel': self.is_parallel,
            'is_cluster': self.is_cluster,
            'parallel_citations': self.parallel_citations,
            'cluster_members': self.cluster_members,
            'pinpoint_pages': self.pinpoint_pages,
            'docket_numbers': self.docket_numbers,
            'case_history': self.case_history,
            'publication_status': self.publication_status,
            'source': self.source,
            'error': self.error,
            'metadata': self.metadata,
            'cluster_id': self.cluster_id,
            'true_by_parallel': self.true_by_parallel,
            'is_verified': self.verified  # Add is_verified alias for backward compatibility
        }
        return result

@dataclass
class ProcessingConfig:
    use_eyecite: bool = True
    use_regex: bool = True
    extract_case_names: bool = True
    extract_dates: bool = True
    enable_clustering: bool = True
    enable_deduplication: bool = True
    enable_verification: bool = True
    context_window: int = 400
    min_confidence: float = 0.5
    max_citations_per_text: int = 1000
    debug_mode: bool = False 