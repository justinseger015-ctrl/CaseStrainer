"""
Citation Utilities

This module contains utility functions and helpers used across the citation processing system.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from src.citation_types import CitationMatch, CitationContext, CitationList, CitationDict
from src.models import CitationResult

logger = logging.getLogger(__name__)

def normalize_citation(citation: str) -> str:
    """Normalize citation for consistent lookup."""
    if not citation:
        return ""
    
    # Remove extra whitespace and normalize
    normalized = citation.strip()
    
    # Extract the core citation part (e.g., "999 U.S. 999" from "Fake Case Name v. Another Party, 999 U.S. 999 (1999)")
    # Pattern to match U.S. Supreme Court citations
    us_pattern = r'(\d+\s+U\.S\.\s+\d+)'
    match = re.search(us_pattern, normalized)
    if match:
        return match.group(1)
    
    return normalized

def strip_pincites(cite: str) -> str:
    """Return the citations without page numbers/pincites between them, but preserve all citations."""
    if not cite:
        return cite
    
    # Split by commas and process each part
    parts = [part.strip() for part in cite.split(',')]
    cleaned_parts = []
    
    for part in parts:
        # Check if this part looks like a citation (volume reporter page)
        if re.match(r'^\d+\s+\w+\.\w+\s+\d+', part):
            # It's a citation, keep it
            cleaned_parts.append(part)
        elif re.match(r'^\d+$', part):
            # It's just a page number, skip it
            continue
        else:
            # It might be a citation with extra info, try to extract the main citation
            citation_match = re.match(r'^(\d+\s+\w+\.\w+\s+\d+)', part)
            if citation_match:
                cleaned_parts.append(citation_match.group(1))
            else:
                # Keep it as is if we can't parse it
                cleaned_parts.append(part)
    
    return ', '.join(cleaned_parts)

def extract_citation_components(citation: str) -> Dict[str, str]:
    """Extract volume, reporter, and page from citation string."""
    if not citation:
        return {}
    
    # Pattern to match citation format: volume reporter page
    pattern = r'^(\d+)\s+([A-Za-z\.]+)\s+(\d+)'
    match = re.match(pattern, citation.strip())
    
    if match:
        return {
            'volume': match.group(1),
            'reporter': match.group(2),
            'page': match.group(3)
        }
    
    return {}

def normalize_case_name_for_clustering(case_name: str) -> str:
    """Normalize case name for clustering purposes."""
    if not case_name:
        return ""
    
    # Convert to lowercase and remove extra whitespace
    normalized = case_name.lower().strip()
    
    # Remove common words that don't help with clustering
    stop_words = {'v', 'vs', 'versus', 'and', 'the', 'of', 'in', 'for', 'to', 'a', 'an'}
    words = normalized.split()
    filtered_words = [word for word in words if word not in stop_words]
    
    return ' '.join(filtered_words)

def is_similar_citation(citation1: str, citation2: str) -> bool:
    """Check if two citations are similar (same case, different reporters)."""
    def normalize_citation(citation):
        # Remove spaces and punctuation
        return re.sub(r'[^\w]', '', citation.lower())
    
    norm1 = normalize_citation(citation1)
    norm2 = normalize_citation(citation2)
    
    # Check if they share significant common parts
    return norm1 == norm2 or norm1 in norm2 or norm2 in norm1

def is_similar_date(date1: str, date2: str) -> bool:
    """Check if two dates are similar (within 1 year)."""
    try:
        year1 = int(date1)
        year2 = int(date2)
        return abs(year1 - year2) <= 1
    except (ValueError, TypeError):
        return False

def calculate_similarity(candidate: str, canonical: str) -> float:
    """Calculate similarity between candidate and canonical case names."""
    if not candidate or not canonical:
        return 0.0
    
    # Simple string similarity using set intersection
    candidate_words = set(candidate.lower().split())
    canonical_words = set(canonical.lower().split())
    
    if not candidate_words or not canonical_words:
        return 0.0
    
    intersection = candidate_words & canonical_words
    union = candidate_words | canonical_words
    
    return len(intersection) / len(union) if union else 0.0

def is_valid_case_name(case_name: str) -> bool:
    """Check if a case name has reasonable structure."""
    if not case_name or len(case_name.strip()) < 3:
        return False
    
    # Check for basic case name patterns
    case_patterns = [
        r'.*\sv\.\s.*',  # "Plaintiff v. Defendant"
        r'.*\svs\.\s.*',  # "Plaintiff vs. Defendant"
        r'.*\sversus\s.*',  # "Plaintiff versus Defendant"
        r'.*\s&\s.*',  # "Plaintiff & Defendant"
        r'.*\sand\s.*',  # "Plaintiff and Defendant"
    ]
    
    for pattern in case_patterns:
        if re.search(pattern, case_name, re.IGNORECASE):
            return True
    
    return False

def has_reasonable_case_structure(case_name: str) -> bool:
    """Check if case name has reasonable structure for legal cases."""
    if not case_name:
        return False
    
    # Check for common legal case patterns
    patterns = [
        r'^[A-Z][a-z]+',  # Starts with capitalized word
        r'.*\s(?:v\.|vs\.|versus)\s.*',  # Contains v., vs., or versus
        r'.*\s(?:&|and)\s.*',  # Contains & or and
        r'.*\s(?:Co\.|Corp\.|Inc\.|LLC|Ltd\.)',  # Contains business suffixes
    ]
    
    return any(re.search(pattern, case_name) for pattern in patterns)

def extract_context(text: str, start: int, end: int, window: int = 200) -> str:
    """Extract context around a citation."""
    if not text or start < 0 or end > len(text):
        return ""
    
    context_start = max(0, start - window)
    context_end = min(len(text), end + window)
    
    return text[context_start:context_end]

def deduplicate_citations(citations: CitationList) -> CitationList:
    """Remove duplicate citations based on citation text."""
    seen = set()
    unique_citations = []
    
    for citation in citations:
        citation_text = getattr(citation, 'citation', '')
        if citation_text not in seen:
            seen.add(citation_text)
            unique_citations.append(citation)
    
    return unique_citations

def get_extracted_case_name(citation: 'CitationResult') -> Optional[str]:
    """Utility to safely get extracted case name from a citation."""
    return citation.extracted_case_name if hasattr(citation, 'extracted_case_name') else None

def get_unverified_citations(citations: CitationList) -> CitationList:
    """Utility to filter unverified citations."""
    return [c for c in citations if not getattr(c, 'verified', False)]

def apply_verification_result(citation: 'CitationResult', verify_result: Dict[str, Any], source: str = "CourtListener") -> bool:
    """Centralized method to apply verification results to a citation."""
    if verify_result.get("verified"):
        citation.canonical_name = verify_result.get("canonical_name")
        citation.canonical_date = verify_result.get("canonical_date")
        citation.url = verify_result.get("url")
        citation.verified = True
        citation.source = verify_result.get("source", source)
        citation.metadata = citation.metadata or {}
        citation.metadata[f"{source.lower()}_source"] = verify_result.get("source")
        return True
    else:
        return False 