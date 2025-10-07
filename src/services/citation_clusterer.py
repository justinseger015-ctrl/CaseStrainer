"""
Citation Clusterer Service

This service handles citation clustering and parallel citation detection.
It implements the improved clustering logic that prevents cross-contamination.
"""

import logging
from src.config import DEFAULT_REQUEST_TIMEOUT, COURTLISTENER_TIMEOUT, CASEMINE_TIMEOUT, WEBSEARCH_TIMEOUT, SCRAPINGBEE_TIMEOUT

from typing import List, Dict, Any, Optional, Set, Tuple
from collections import defaultdict
import re

from .interfaces import ICitationClusterer
from src.models import CitationResult, ProcessingConfig

logger = logging.getLogger(__name__)


class CitationClusterer(ICitationClusterer):
    """
    Citation clustering service for grouping related citations.
    
    This service is responsible for:
    - Detecting parallel citations that refer to the same case
    - Grouping citations into clusters based on case relationships
    - Preventing cross-contamination between different cases
    - Propagating canonical data within clusters
    """
    
    def __init__(self, config: Optional[ProcessingConfig] = None):
        """Initialize the citation clusterer with configuration."""
        self.config = config or ProcessingConfig()
        
        if self.config.debug_mode:
            logger.info("CitationClusterer initialized")
    
    def detect_parallel_citations(self, citations: List[CitationResult], text: str) -> List[CitationResult]:
        """
        Detect and group parallel citations that refer to the same case.
        
        This method identifies parallel citations (different reporters citing the same case)
        and ensures consistent metadata (case names, dates) across them.
        
        Args:
            citations: List of citations to analyze
            text: Original text for context
            
        Returns:
            Updated citations with parallel citation relationships and consistent metadata
        """
        if len(citations) < 2:
            return citations
        
        citations = sorted(citations, key=lambda c: c.start_index if c.start_index is not None else 0)
        
        citation_groups = self._group_citations_by_proximity(citations, text)
        
        for group in citation_groups:
            if len(group) > 1:
                group = sorted(group, key=lambda c: c.start_index if c.start_index is not None else 0)
                self._detect_parallels_in_group(group)
        
        self._propagate_metadata_across_groups(citations)
        
        if self.config.debug_mode:
            parallel_count = sum(1 for c in citations if hasattr(c, 'parallel_citations') and c.parallel_citations)
            logger.info(f"CitationClusterer detected {parallel_count} citations with parallels")
        
        return citations
    
    def cluster_citations(self, citations: List[CitationResult]) -> List[Dict[str, Any]]:
        """
        DEPRECATED: Use cluster_citations_unified_master() instead.
        
        This function now delegates to the new unified master implementation
        that consolidates all 45+ duplicate clustering functions.
        
        MIGRATION: Replace calls with:
        from src.unified_clustering_master import cluster_citations_unified_master
        """
        import warnings
        warnings.warn(
            "CitationClusterer.cluster_citations() is deprecated. Use cluster_citations_unified_master() instead.",
            DeprecationWarning,
            stacklevel=2
        )
        
        # Delegate to the new master implementation
        from src.unified_clustering_master import cluster_citations_unified_master
        return cluster_citations_unified_master(
            citations=citations,
            config=self.config
        )
    
    def _group_citations_by_proximity(self, citations: List[CitationResult], text: str) -> List[List[CitationResult]]:
        """
        Group citations that are close together in the text.
        
        This method groups citations that appear within a certain distance of each other,
        which helps in identifying parallel citations that might refer to the same case.
        """
        if not citations:
            return []
            
        sorted_citations = sorted(citations, key=lambda c: c.start_index or 0)
        
        groups = []
        current_group = [sorted_citations[0]]
        
        for i in range(1, len(sorted_citations)):
            current_citation = sorted_citations[i]
            previous_citation = sorted_citations[i-1]
            
            distance = (current_citation.start_index or 0) - (previous_citation.end_index or 0)
            
            between_text = text[previous_citation.end_index:current_citation.start_index].strip()
            
            # words that typically separate different citations (like 'but', 'however', etc.)
            separator_words = ['but', 'however', 'but see', 'cf.', 'e.g.', 'i.e.', ';', 'also', 'furthermore', 'moreover']
            is_separator_present = any(sep in between_text.lower() for sep in separator_words)
            
            if distance <= 150 and not is_separator_present:
                current_group.append(current_citation)
            else:
                if current_group:
                    groups.append(current_group)
                current_group = [current_citation]
        
        if current_group:
            groups.append(current_group)
        
        return groups
    
    def _detect_parallels_in_group(self, group: List[CitationResult]) -> None:
        """Detect parallel citations within a group and propagate metadata."""
        for i, citation1 in enumerate(group):
            for j, citation2 in enumerate(group):
                if i != j and self._are_citations_parallel(citation1, citation2):
                    if not hasattr(citation1, 'parallel_citations') or citation1.parallel_citations is None:
                        citation1.parallel_citations = []
                    if not hasattr(citation2, 'parallel_citations') or citation2.parallel_citations is None:
                        citation2.parallel_citations = []
                    
                    if citation2.citation not in citation1.parallel_citations:
                        citation1.parallel_citations.append(citation2.citation)
                    if citation1.citation not in citation2.parallel_citations:
                        citation2.parallel_citations.append(citation1.citation)
        
        self._propagate_metadata_within_parallels(group)
    
    def _are_citations_parallel(self, citation1: CitationResult, citation2: CitationResult) -> bool:
        """Check if two citations are parallel (refer to the same case)."""
        if (citation1.canonical_name and citation2.canonical_name and
            citation1.canonical_date and citation2.canonical_date):
            return (citation1.canonical_name.lower() == citation2.canonical_name.lower() and
                    citation1.canonical_date == citation2.canonical_date)
        
        if (citation1.extracted_case_name and citation2.extracted_case_name and
            citation1.extracted_date and citation2.extracted_date):
            return (self._normalize_case_name(citation1.extracted_case_name) == 
                    self._normalize_case_name(citation2.extracted_case_name) and
                    citation1.extracted_date == citation2.extracted_date)
        
        return self._citations_refer_to_same_case(citation1.citation, citation2.citation)
    
    def _create_canonical_clusters(self, citations: List[CitationResult]) -> Dict[str, List[CitationResult]]:
        """Create clusters based on canonical name and date for verified citations."""
        clusters = {}
        
        for citation in citations:
            if (citation.verified and 
                citation.canonical_name and 
                citation.canonical_date):
                
                cluster_key = f"canonical_{self._normalize_case_name(citation.canonical_name)}_{citation.canonical_date}"
                
                if cluster_key not in clusters:
                    clusters[cluster_key] = []
                
                clusters[cluster_key].append(citation)
                
                citation.metadata = citation.metadata or {}
                citation.metadata['cluster_id'] = cluster_key
                citation.metadata['is_in_cluster'] = True
        
        return clusters
    
    def _merge_unverified_with_canonical(self, citations: List[CitationResult], 
                                       canonical_clusters: Dict[str, List[CitationResult]]) -> None:
        """Merge unverified citations with existing canonical clusters when they match."""
        for citation in citations:
            if citation.metadata and citation.metadata.get('is_in_cluster'):
                continue
            
            if (not citation.verified and 
                citation.extracted_case_name and 
                citation.extracted_date):
                
                normalized_extracted = self._normalize_case_name(citation.extracted_case_name)
                
                for cluster_key, cluster_members in canonical_clusters.items():
                    for cluster_member in cluster_members:
                        if (cluster_member.canonical_name and 
                            cluster_member.canonical_date):
                            
                            normalized_canonical = self._normalize_case_name(cluster_member.canonical_name)
                            
                            if (normalized_extracted == normalized_canonical and
                                citation.extracted_date == cluster_member.canonical_date):
                                
                                canonical_clusters[cluster_key].append(citation)
                                
                                citation.metadata = citation.metadata or {}
                                citation.metadata['cluster_id'] = cluster_key
                                citation.metadata['is_in_cluster'] = True
                                break
                    
                    if citation.metadata and citation.metadata.get('is_in_cluster'):
                        break
    
    def _create_extracted_clusters(self, citations: List[CitationResult], 
                                 existing_clusters: Dict[str, List[CitationResult]]) -> Dict[str, List[CitationResult]]:
        """Create clusters for remaining unverified citations based on extracted data."""
        extracted_clusters = {}
        
        extracted_groups = defaultdict(list)
        
        for citation in citations:
            if citation.metadata and citation.metadata.get('is_in_cluster'):
                continue
            
            if (citation.extracted_case_name and 
                citation.extracted_date):
                
                key = (self._normalize_case_name(citation.extracted_case_name), 
                       citation.extracted_date)
                extracted_groups[key].append(citation)
        
        for (case_name, date), members in extracted_groups.items():
            if len(members) > 1:
                cluster_key = f"extracted_{case_name.replace(' ', '_')}_{date}"
                extracted_clusters[cluster_key] = members
                
                for citation in members:
                    citation.metadata = citation.metadata or {}
                    citation.metadata['cluster_id'] = cluster_key
                    citation.metadata['is_in_cluster'] = True
        
        return extracted_clusters
    
    def _propagate_canonical_data(self, clusters: Dict[str, List[CitationResult]]) -> None:
        """Propagate canonical data within clusters from verified citations to unverified ones."""
        for cluster_key, cluster_members in clusters.items():
            if len(cluster_members) <= 1:
                continue
            
            canonical_source = None
            
            sorted_members = sorted(cluster_members, key=lambda c: c.start_index or 0)
            
            for citation in reversed(sorted_members):
                if citation.canonical_name and citation.canonical_date:
                    canonical_source = citation
                    break
            
            if not canonical_source:
                for citation in sorted_members:
                    if citation.canonical_name and citation.canonical_date:
                        canonical_source = citation
                        break
            
            if canonical_source:
                for citation in cluster_members:
                    if not citation.canonical_name:
                        citation.canonical_name = canonical_source.canonical_name
                    if not citation.canonical_date:
                        citation.canonical_date = canonical_source.canonical_date
                    
                    citation.metadata = citation.metadata or {}
                    if citation != canonical_source:
                        citation.metadata['canonical_data_source'] = canonical_source.citation
    
    def _format_clusters(self, clusters: Dict[str, List[CitationResult]]) -> List[Dict[str, Any]]:
        """Format clusters for output with proper merging and canonical name extraction."""
        formatted_clusters = []
        
        for cluster_key, cluster_members in clusters.items():
            if not cluster_members:
                continue
            
            case_name = self._get_best_case_name_for_cluster(cluster_members)
            
            cluster = {
                'id': cluster_key,
                'case_name': case_name,
                'size': len(cluster_members),
                'citations': [self._citation_to_dict(c) for c in cluster_members],
                'verified_count': sum(1 for c in cluster_members if c.verified),
                'unverified_count': sum(1 for c in cluster_members if not c.verified)
            }
            
            formatted_clusters.append(cluster)
        
        return formatted_clusters
    
    def _get_best_case_name_for_cluster(self, cluster_members: List[CitationResult]) -> str:
        """Get the best case name for a cluster, prioritizing canonical over extracted."""
        for citation in cluster_members:
            if citation.canonical_name:
                return citation.canonical_name
        
        for citation in cluster_members:
            if citation.extracted_case_name:
                return citation.extracted_case_name
        
        return "Unknown Case"
    
    def _citation_to_dict(self, citation: CitationResult) -> Dict[str, Any]:
        """Convert a CitationResult to a dictionary for output."""
        return {
            'citation': citation.citation,
            'verified': citation.verified,
            'canonical_name': citation.canonical_name,
            'canonical_date': citation.canonical_date,
            'extracted_case_name': citation.extracted_case_name,
            'extracted_date': citation.extracted_date,
            'start_index': citation.start_index,
            'end_index': citation.end_index,
            'confidence': citation.confidence,
            'method': citation.method,
            'metadata': citation.metadata
        }
    
    def _normalize_case_name(self, case_name: str) -> str:
        """Normalize case name for consistent clustering."""
        if not case_name:
            return ""
        
        normalized = re.sub(r'\s+', ' ', case_name.strip().lower())
        
        suffixes_to_remove = [', inc.', ', corp.', ', ltd.', ', llc.']
        for suffix in suffixes_to_remove:
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)]
        
        return normalized
    
    def _citations_refer_to_same_case(self, citation1: str, citation2: str) -> bool:
        """Check if two citation strings refer to the same case."""
        parts1 = self._extract_citation_components(citation1)
        parts2 = self._extract_citation_components(citation2)
        
        if not parts1 or not parts2:
            return False
        
        return (parts1['volume'] == parts2['volume'] and
                parts1['page'] == parts2['page'] and
                self._reporters_compatible(parts1['reporter'], parts2['reporter']))
    
    def _extract_citation_components(self, citation: str) -> Optional[Dict[str, str]]:
        """Extract volume, reporter, and page from citation."""
        pattern = r'(\d+)\s+([A-Za-z\.\s]+?)\s+(\d+)'
        match = re.search(pattern, citation)
        
        if match:
            return {
                'volume': match.group(1),
                'reporter': match.group(2).strip(),
                'page': match.group(3)
            }
        
        return None
    
    def _propagate_metadata_within_parallels(self, group: List[CitationResult]) -> None:
        """
        Propagate metadata (case names, dates) within parallel citation groups.
        
        This ensures that all parallel citations share the same case name and date metadata
        when one member of the group has this information.
        """
        parallel_groups = []
        processed = set()
        
        for citation in group:
            if citation.citation in processed:
                continue
                
            parallel_group = set()
            queue = [citation]
            
            while queue:
                current = queue.pop(0)
                if current.citation in processed:
                    continue
                    
                processed.add(current.citation)
                parallel_group.add(current)
                
                if hasattr(current, 'parallel_citations') and current.parallel_citations:
                    for parallel_cite in current.parallel_citations:
                        for c in group:
                            if c.citation == parallel_cite and c not in parallel_group:
                                queue.append(c)
                                break
            
            if len(parallel_group) > 1:
                parallel_groups.append(list(parallel_group))
        
        for parallel_group in parallel_groups:
            self._propagate_metadata_in_group(parallel_group)
    
    def _propagate_metadata_in_group(self, group: List[CitationResult]) -> None:
        """Propagate metadata within a group of parallel citations."""
        if not group:
            return
        
        best_source = None
        
        for citation in group:
            if citation.verified and citation.canonical_name and citation.canonical_date:
                best_source = citation
                break
        
        if not best_source:
            for citation in group:
                if citation.extracted_case_name and citation.extracted_date:
                    best_source = citation
                    break
        
        if not best_source:
            return
        
        for citation in group:
            if citation == best_source:
                continue
                
            if best_source.canonical_name and best_source.canonical_date:
                citation.canonical_name = best_source.canonical_name
                citation.canonical_date = best_source.canonical_date
                
                if citation.verified:
                    if citation.metadata is None:
                        citation.metadata = {}
                    citation.metadata['canonical_data_updated'] = True
            
            if best_source.extracted_case_name and best_source.extracted_date:
                if not citation.extracted_case_name:
                    citation.extracted_case_name = best_source.extracted_case_name
                if not citation.extracted_date:
                    citation.extracted_date = best_source.extracted_date
    
    def _propagate_metadata_across_groups(self, citations: List[CitationResult]) -> None:
        """
        Propagate metadata across citation groups to handle cases where parallel citations
        might be in different proximity groups.
        """
        parallel_map = {}
        
        for citation in citations:
            if hasattr(citation, 'parallel_citations') and citation.parallel_citations:
                parallel_map[citation.citation] = citation.parallel_citations
        
        processed = set()
        
        for citation in citations:
            if citation.citation in processed:
                continue
                
            connected = set()
            queue = [citation.citation]
            
            while queue:
                current = queue.pop(0)
                if current in processed:
                    continue
                    
                processed.add(current)
                connected.add(current)
                
                for parallel in parallel_map.get(current, []):
                    if parallel not in connected:
                        queue.append(parallel)
            
            if len(connected) > 1:
                group = [c for c in citations if c.citation in connected]
                self._propagate_metadata_in_group(group)
    
    def _reporters_compatible(self, reporter1: str, reporter2: str) -> bool:
        """Check if two reporters are compatible."""
        r1 = re.sub(r'[^\w]', '', reporter1.lower())
        r2 = re.sub(r'[^\w]', '', reporter2.lower())
        
        if r1 == r2:
            return True
        
        compatible_sets = [
            {'wn', 'wash', 'wn2d', 'wash2d'},
            {'us', 'unitedstates'},
            {'sct', 'supremecourt'},
            {'led', 'led2d', 'lawyersedition'},
            {'f', 'f2d', 'f3d', 'federal'},
            {'fsupp', 'fsupp2d', 'fsupp3d'},
            {'p', 'p2d', 'p3d', 'pacific'},  # Add Pacific Reporter variations
            {'was', 'washapp'}  # Washington Appellate Reports
        ]
        
        for compatible_set in compatible_sets:
            if r1 in compatible_set and r2 in compatible_set:
                return True
        
        return False
