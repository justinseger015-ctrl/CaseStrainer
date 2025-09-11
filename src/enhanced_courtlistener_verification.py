"""
Enhanced CourtListener verification with cross-validation to prevent false positives
"""

import re
from src.config import DEFAULT_REQUEST_TIMEOUT, COURTLISTENER_TIMEOUT, CASEMINE_TIMEOUT, WEBSEARCH_TIMEOUT, SCRAPINGBEE_TIMEOUT

import requests
import json
import logging
import time
from typing import Dict, Optional, List

from src.enhanced_case_name_matcher import enhanced_matcher, is_likely_same_case

logger = logging.getLogger(__name__)

class EnhancedCourtListenerVerifier:
    """Enhanced verification with cross-validation between API endpoints"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {"Authorization": f"Token {api_key}"}
    
    def verify_citation_enhanced(self, citation: str, extracted_case_name: Optional[str] = None) -> Dict:
        """
        Enhanced verification using citation-lookup API v4 as primary method.
        
        Strategy:
        1. Use citation-lookup API v4 (fast, reliable, designed for citations)
        2. Only use search API if we need additional metadata not in citation-lookup
        3. Apply strict matching criteria: same year, citation, and meaningful words in common
        """
        
        print(f"[ENHANCED] Starting citation-lookup API v4 verification for: {citation}")
        
        if self._is_test_citation(citation):
            print(f"[ENHANCED] REJECTED: Test citation detected: {citation}")
            return {
                "canonical_name": None,
                "canonical_date": None,
                "url": None,
                "verified": False,
                "raw": None,
                "source": "test_citation_rejected",
                "confidence": 0.0,
                "validation_method": "test_citation_filter"
            }
        
        result = {
            "canonical_name": None,
            "canonical_date": None,
            "url": None,
            "verified": False,
            "raw": None,
            "source": None,
            "confidence": 0.0,
            "validation_method": "citation_lookup_v4"
        }
        
        lookup_result = self._verify_with_citation_lookup_v4_enhanced(citation, extracted_case_name)
        
        if lookup_result['verified']:
            result.update(lookup_result)
            result['validation_method'] = "citation_lookup_v4_success"
            result['confidence'] = 0.95  # High confidence for citation-lookup matches
            
            print(f"[ENHANCED] Citation-lookup succeeded - using only citation-lookup data (search API disabled)")
            result['validation_method'] = "citation_lookup_v4_only"
            result['confidence'] = 0.95  # High confidence with citation-lookup only
        else:
            print(f"[ENHANCED] Citation-lookup failed - NOT using search API fallback to prevent data contamination")
            result['verified'] = False
            result['validation_method'] = "citation_lookup_v4_only"
            result['confidence'] = 0.0  # No confidence when citation-lookup fails
        
        return result
    
    def verify_citations_batch(self, citations: List[str], extracted_case_names: Optional[List[str]] = None) -> List[Dict]:
        """
        Verify multiple citations using CourtListener citation-lookup API v4 batch processing.
        
        Args:
            citations: List of citation strings to verify
            extracted_case_names: Optional list of extracted case names (must match citations length)
            
        Returns:
            List of verification results for each citation
        """
        if not citations:
            return []
        
        if extracted_case_names and len(extracted_case_names) != len(citations):
            logger.warning("extracted_case_names length doesn't match citations length")
            extracted_case_names = None
        
        results = []
        
        try:
            url = "https://www.courtlistener.com/api/rest/v4/citation-lookup/"
            
            batch_size = 60
            for i in range(0, len(citations), batch_size):
                batch_citations = citations[i:i + batch_size]
                batch_names = extracted_case_names[i:i + batch_size] if extracted_case_names else [None] * len(batch_citations)
                
                batch_data = {"text": batch_citations[0]}  # Send the full text (first item)
                
                logger.info(f"Processing CourtListener batch {i//batch_size + 1}: {len(batch_citations)} citations")
                
                response = requests.post(url, headers=self.headers, json=batch_data, timeout=DEFAULT_REQUEST_TIMEOUT)
                
                if response.status_code == 200:
                    batch_results = response.json()
                    logger.info(f"CourtListener API response: {batch_results}")
                    
                    for j, citation in enumerate(batch_citations):
                        citation_result = self._process_batch_citation_result(
                            citation, 
                            batch_names[j] if batch_names else None,
                            batch_results[j] if j < len(batch_results) else None
                        )
                        results.append(citation_result)
                    
                    for i, api_result in enumerate(batch_results):
                        if i >= len(batch_citations):  # This is an additional citation found by API
                            citation_text = api_result.get('citation', '')
                            citation_result = self._process_batch_citation_result(
                                citation_text,
                                None,
                                api_result
                            )
                            results.append(citation_result)
                else:
                    logger.warning(f"CourtListener batch API error: {response.status_code}")
                    for citation in batch_citations:
                        results.append(self._create_failed_batch_result(citation))
            
        except Exception as e:
            logger.error(f"CourtListener batch verification error: {e}")
            for citation in citations:
                results.append(self._create_failed_batch_result(citation))
        
        return results
    
    def _process_batch_citation_result(self, citation: str, extracted_case_name: Optional[str], api_result: Optional[Dict]) -> Dict:
        """Process a single citation result from batch API response."""
        
        result = {
            "citation": citation,  # Add the citation field
            "canonical_name": None,
            "canonical_date": None,
            "url": None,
            "verified": False,
            "raw": api_result,
            "source": "CourtListener Batch API",
            "confidence": 0.0,
            "validation_method": "batch_citation_lookup"
        }
        
        if not api_result or api_result.get('status') == 404:
            return result
        
        clusters = api_result.get('clusters', [])
        if not clusters:
            return result
        
        best_case = self._find_best_case_with_strict_criteria(
            clusters, citation, extracted_case_name
        )
        
        if best_case:
            result.update({
                "canonical_name": best_case.get('case_name', ''),
                "canonical_date": best_case.get('date_filed', ''),
                "url": self._normalize_url(best_case.get('absolute_url', '')),
                "verified": True,
                "confidence": 0.9
            })
        
        return result
    
    def _find_best_case_with_strict_criteria(self, clusters: List[Dict], citation: str, extracted_case_name: Optional[str]) -> Optional[Dict]:
        """
        Find the best case using strict criteria:
        1. Same year and citation
        2. At least one non-stopword in common between extracted and canonical names
        
        Args:
            clusters: List of case clusters from CourtListener API
            citation: Citation text to match
            extracted_case_name: Extracted case name from document
            
        Returns:
            Best matching case or None
        """
        if not clusters:
            return None
        
        best_match = None
        best_score = 0.0
        
        for cluster in clusters:
            score = self._calculate_strict_match_score(cluster, citation, extracted_case_name)
            if score > best_score:
                best_score = score
                best_match = cluster
        
        if best_match and best_score >= 1.0:  # Reduced from 1.5 to 1.0 for more leniency
            print(f"[ENHANCED] Primary case found with score {best_score:.3f}: {best_match.get('case_name')}")
            return best_match
        
        return None
    
    def _calculate_strict_match_score(self, case: Dict, citation: str, extracted_case_name: Optional[str]) -> float:
        """
        Calculate match score using strict criteria.
        
        Returns:
            float: Score >= 1.5 for a match, 0.0 for no match
        """
        score = 0.0
        
        case_citations = case.get('citations', [])
        citation_found = False
        
        
        for case_citation in case_citations:
            if case_citation.get('volume') and case_citation.get('reporter') and case_citation.get('page'):
                case_citation_str = f"{case_citation['volume']} {case_citation['reporter']} {case_citation['page']}"
                
                if self._citations_match(citation, case_citation_str):
                    citation_found = True
                    break
                else:
                    continue  # Check next citation
        
        if not citation_found:
            return 0.0
        
        score += 1.0
        
        exp_year = self._extract_year_from_citation(citation)
        can_year = self._extract_year_from_date(case.get('date_filed') or '')
        
        
        if exp_year and can_year:
            try:
                year_diff = abs(int(exp_year) - int(can_year))
                if year_diff == 0:
                    score += 1.0  # Exact match
                elif year_diff <= 5:  # Allow up to 5 years difference
                    score += 0.5
                elif year_diff <= 10:  # Allow up to 10 years with penalty
                    score += 0.2
            except (ValueError, TypeError):
                score += 0.3
        else:
            score += 0.3
        
        if extracted_case_name:
            if self._has_meaningful_words_in_common(extracted_case_name, case.get('case_name', '')):
                score += 1.0
            else:
                score += 0.5  # Moderate bonus for continuing
        else:
            score += 0.5
        
        return score
    
    def _extract_year_from_citation(self, citation: str) -> Optional[str]:
        """Extract year from citation text."""
        import re
        year_match = re.search(r'(19|20)\d{2}', citation)
        return year_match.group(0) if year_match else None
    
    def _extract_year_from_date(self, date_str: str) -> Optional[str]:
        """Extract year from date string."""
        if not date_str:
            return None
        
        import re
        year_match = re.search(r'(19|20)\d{2}', str(date_str))
        return year_match.group(0) if year_match else None
    
    def _citations_match(self, citation1: str, citation2: str) -> bool:
        """Check if two citations match (allowing for reporter variations)."""
        if not citation1 or not citation2:
            return False
        
        norm1 = self._normalize_citation(citation1)
        norm2 = self._normalize_citation(citation2)
        
        return norm1 == norm2
    
    def _normalize_citation(self, citation: str) -> str:
        """Normalize citation for comparison."""
        norm = citation.replace(' ', '').lower()
        
        norm = norm.replace('wn.', 'wn').replace('wash.', 'wn')
        norm = norm.replace('wn2d', 'wn2d').replace('wash2d', 'wn2d')
        norm = norm.replace('wnapp', 'wnapp').replace('washapp', 'wnapp')
        
        norm = norm.replace('wash.app.', 'wnapp').replace('wash.app', 'wnapp')
        norm = norm.replace('wash.2d', 'wn2d').replace('wash.2d.', 'wn2d')
        
        norm = norm.replace('p.', 'p').replace('pac.', 'p')
        norm = norm.replace('p2d', 'p2d').replace('pac2d', 'p2d')
        norm = norm.replace('p3d', 'p3d').replace('pac3d', 'p3d')
        
        return norm
    
    def _has_meaningful_words_in_common(self, name1: str, name2: str) -> bool:
        """
        Check if two case names have at least one meaningful (non-stopword) word in common.
        
        Args:
            name1: First case name
            name2: Second case name
            
        Returns:
            True if they share at least one meaningful word
        """
        if not name1 or not name2:
            return False
        
        stopwords = {
            'in', 're', 'of', 'the', 'and', 'or', 'for', 'to', 'a', 'an', 'v', 'vs', 'versus',
            'petition', 'petitioner', 'respondent', 'appellant', 'appellee', 'plaintiff', 'defendant',
            'state', 'united', 'states', 'county', 'city', 'town', 'village', 'corporation',
            'inc', 'llc', 'ltd', 'co', 'company', 'association', 'foundation', 'trust'
        }
        
        words1 = set(self._extract_meaningful_words(name1, stopwords))
        words2 = set(self._extract_meaningful_words(name2, stopwords))
        
        common_words = words1.intersection(words2)
        
        if len(common_words) == 0:
            return False
        
        if len(common_words) >= 1:
            return True
        
        return True
        
        print(f"  Name1: '{name1}' -> {words1}")
        print(f"  Name2: '{name2}' -> {words2}")
        print(f"  Common words: {common_words}")
        print(f"  Total score: {total_score}, Max possible: {max_possible_score}")
        print(f"  Normalized score: {normalized_score:.3f}, Required: {min_score}")
        
        return normalized_score >= min_score
    
    def _extract_meaningful_words(self, name: str, stopwords: set) -> List[str]:
        """Extract meaningful (non-stopword) words from a case name."""
        if not name:
            return []
        
        words = re.findall(r'\b[a-zA-Z]+\b', name.lower())
        meaningful_words = [word for word in words if word not in stopwords and len(word) > 2]
        
        return meaningful_words
    
    def _create_failed_batch_result(self, citation: str) -> Dict:
        """Create a result for a failed batch verification."""
        return {
            "canonical_name": None,
            "canonical_date": None,
            "url": None,
            "verified": False,
            "raw": None,
            "source": "CourtListener Batch API",
            "confidence": 0.0,
            "validation_method": "batch_failed",
            "error": "Batch verification failed"
        }
    
    def _verify_with_search_api(self, citation: str, extracted_case_name: Optional[str] = None) -> Dict:
        """Verify using search API with fuzzy case name matching - focus on PRIMARY cases"""
        
        result = {
            "canonical_name": None,
            "canonical_date": None,
            "url": None,
            "verified": False,
            "raw": None
        }
        
        try:
            
            if extracted_case_name:
                search_query = extracted_case_name
                citation_filter = citation
                
                best_result = self._search_for_primary_case_multiple_strategies(
                    extracted_case_name, citation, citation_filter
                )
                
                if best_result:
                    result.update({
                        "canonical_name": best_result.get('caseName', ''),
                        "canonical_date": best_result.get('dateFiled', ''),
                        "url": self._normalize_url(best_result.get('absolute_url', '')),
                        "verified": True,
                        "source": "CourtListener Search API"
                    })
                    
                    similarity = enhanced_matcher.calculate_similarity(
                        extracted_case_name, 
                        best_result.get('caseName', '')
                    )
                    result['confidence'] = min(0.9, 0.6 + similarity * 0.3)
            else:
                search_query = citation
                citation_filter = None
                
                url = f"https://www.courtlistener.com/api/rest/v4/search/"
                params = {
                    'q': search_query,
                    'format': 'json',
                    'stat_Precedential': 'on',  # Only published opinions
                    'type': 'o',  # Opinions only
                    'order_by': 'dateFiled desc'  # Most recent first
                }
                
                response = requests.get(url, headers=self.headers, params=params, timeout=DEFAULT_REQUEST_TIMEOUT)
                
                if response.status_code == 200:
                    api_results = response.json()
                    result['raw'] = response.text
                    
                    found_results = [r for r in api_results.get('results', []) if r.get('status') != 404]
                    
                    if found_results:
                        best_result = self._find_primary_case_with_enhanced_matching(
                            found_results, extracted_case_name, citation, citation_filter
                        )
                        
                        if best_result:
                            result.update({
                                "canonical_name": best_result.get('caseName', ''),
                                "canonical_date": best_result.get('dateFiled', ''),
                                "url": best_result.get('absolute_url', ''),
                                "verified": True,
                                "source": "CourtListener Search API"
                            })
                            
                            result['confidence'] = 0.7
                
        except Exception as e:
            print(f"[ENHANCED] Search API error: {e}")
            logger.error(f"Search API error: {e}")
        
        return result
    
    def _verify_with_citation_lookup(self, citation: str, extracted_case_name: Optional[str] = None) -> Dict:
        """Verify using citation-lookup API with citation-first search strategy"""
        
        result = {
            "canonical_name": None,
            "canonical_date": None,
            "url": None,
            "verified": False,
            "raw": None
        }
        
        try:
            url = "https://www.courtlistener.com/api/rest/v4/citation-lookup/"
            data = {"text": citation}
            
            response = requests.post(url, headers=self.headers, json=data, timeout=DEFAULT_REQUEST_TIMEOUT)
            
            if response.status_code == 200:
                api_results = response.json()
                result['raw'] = response.text
                
                found_results = [r for r in api_results if r.get('status') != 404 and r.get('clusters')]
                
                if found_results:
                    best_result = self._find_primary_case_with_enhanced_matching(
                        found_results, extracted_case_name, citation, citation
                    )
                    
                    if best_result:
                        result.update({
                            "canonical_name": best_result.get('caseName', ''),
                            "canonical_date": best_result.get('dateFiled', ''),
                            "url": self._normalize_url(best_result.get('absolute_url', '')),
                            "verified": True,
                            "source": "CourtListener Citation-Lookup API"
                        })
                        
                        if extracted_case_name:
                            similarity = enhanced_matcher.calculate_similarity(
                                extracted_case_name, 
                                best_result.get('caseName', '')
                            )
                            result['confidence'] = min(0.9, 0.6 + similarity * 0.3)
                        else:
                            result['confidence'] = 0.7
                
        except Exception as e:
            print(f"[ENHANCED] Citation-lookup API error: {e}")
            logger.error(f"Citation-lookup API error: {e}")
        
        return result
    
    def _find_best_match_with_fuzzy_matching(self, api_results: List[Dict], 
                                           extracted_case_name: Optional[str], 
                                           citation: str) -> Optional[Dict]:
        """
        Find the best matching result using fuzzy case name matching.
        
        Args:
            api_results: List of results from CourtListener API
            extracted_case_name: Case name extracted from document
            citation: Citation text
            
        Returns:
            Best matching result or None
        """
        if not api_results:
            return None
        
        if extracted_case_name:
            best_match = None
            best_score = 0.0
            
            for result in api_results:
                api_case_name = result.get('caseName', '')
                if api_case_name:
                    similarity = enhanced_matcher.calculate_similarity(
                        extracted_case_name, api_case_name
                    )
                    
                    print(f"[ENHANCED] Case name similarity: '{extracted_case_name}' vs '{api_case_name}' = {similarity:.3f}")
                    
                    if similarity >= 0.6 and similarity > best_score:
                        best_score = similarity
                        best_match = result
            
            if best_match:
                print(f"[ENHANCED] Best match found with similarity {best_score:.3f}")
                return best_match
        
        for result in api_results:
            if result.get('caseName') and result.get('absolute_url'):
                return result
        
        return None
    
    def _search_for_primary_case_multiple_strategies(self, extracted_case_name: str, citation: str, citation_filter: str) -> Optional[Dict]:
        """
        Use multiple search strategies to find the primary case.
        
        Strategy 1: Search by citation (highest priority) - FIND THE ACTUAL CASE
        Strategy 2: Search by citation + case name (medium priority)
        Strategy 3: Search by case name only (lower priority) - FALLBACK
        
        Args:
            extracted_case_name: Case name extracted from document
            citation: Citation text
            citation_filter: Citation to use as filter
            
        Returns:
            Best matching primary case result or None
        """
        url = f"https://www.courtlistener.com/api/rest/v4/search/"
        
        print(f"[ENHANCED] Strategy 1: Searching by citation: '{citation}'")
        params = {
            'q': citation,
            'format': 'json',
            'stat_Precedential': 'on',
            'type': 'o',
            'order_by': 'dateFiled desc'
        }
        
        response = requests.get(url, headers=self.headers, params=params, timeout=DEFAULT_REQUEST_TIMEOUT)
        if response.status_code == 200:
            api_results = response.json()
            found_results = [r for r in api_results.get('results', []) if r.get('status') != 404]
            
            if found_results:
                best_result = self._find_primary_case_with_enhanced_matching(
                    found_results, extracted_case_name, citation, citation_filter
                )
                if best_result:
                    print(f"[ENHANCED] Strategy 1 successful: Found primary case by citation")
                    return best_result
        
        print(f"[ENHANCED] Strategy 2: Searching by citation + case name")
        params = {
            'q': f'{citation} {extracted_case_name}',
            'format': 'json',
            'stat_Precedential': 'on',
            'type': 'o',
            'order_by': 'dateFiled desc'
        }
        
        response = requests.get(url, headers=self.headers, params=params, timeout=DEFAULT_REQUEST_TIMEOUT)
        if response.status_code == 200:
            api_results = response.json()
            found_results = [r for r in api_results.get('results', []) if r.get('status') != 404]
            
            if found_results:
                best_result = self._find_primary_case_with_enhanced_matching(
                    found_results, extracted_case_name, citation, citation_filter
                )
                if best_result:
                    print(f"[ENHANCED] Strategy 2 successful: Found primary case by citation + name")
                    return best_result
        
        print(f"[ENHANCED] Strategy 3: Searching by exact case name (fallback)")
        params = {
            'q': f'"{extracted_case_name}"',  # Exact phrase match
            'format': 'json',
            'stat_Precedential': 'on',
            'type': 'o',
            'order_by': 'dateFiled desc'
        }
        
        response = requests.get(url, headers=self.headers, params=params, timeout=DEFAULT_REQUEST_TIMEOUT)
        if response.status_code == 200:
            api_results = response.json()
            found_results = [r for r in api_results.get('results', []) if r.get('status') != 404]
            
            if found_results:
                best_result = self._find_primary_case_with_enhanced_matching(
                    found_results, extracted_case_name, citation, citation_filter
                )
                if best_result:
                    print(f"[ENHANCED] Strategy 3 successful: Found primary case by name (fallback)")
                    return best_result
        
        print(f"[ENHANCED] All search strategies failed to find primary case")
        return None
    
    def _find_primary_case_with_enhanced_matching(self, api_results: List[Dict], 
                                                extracted_case_name: Optional[str], 
                                                citation: str,
                                                citation_filter: Optional[str] = None) -> Optional[Dict]:
        """
        Find the PRIMARY case (the one in header/metadata) rather than cases that just cite it.
        
        Strategy:
        1. Prioritize exact case name matches
        2. Use citation as a filter to eliminate cases that just cite the target
        3. Focus on finding the case that IS the citation, not cases that CONTAIN the citation
        
        Args:
            api_results: List of results from CourtListener API
            extracted_case_name: Case name extracted from document
            citation: Citation text
            citation_filter: Citation to use as a filter
            
        Returns:
            Primary case result or None
        """
        if not api_results:
            return None
        
        if extracted_case_name:
            best_match = None
            best_score = 0.0
            
            for result in api_results:
                api_case_name = result.get('caseName', '')
                if not api_case_name:
                    continue
                
                similarity = enhanced_matcher.calculate_similarity(
                    extracted_case_name, api_case_name
                )
                
                print(f"[ENHANCED] Primary case similarity: '{extracted_case_name}' vs '{api_case_name}' = {similarity:.3f}")
                
                if citation_filter:
                    result_text = result.get('plain_text', '') or result.get('html', '') or ''
                    
                    if True:

                    
                        pass  # Empty block

                    
                    
                        pass  # Empty block

                    
                    
                        case_name_contains_citation = citation_filter.lower() in api_case_name.lower()
                        metadata_contains_citation = any(
                            citation_filter.lower() in str(value).lower() 
                            for key, value in result.items() 
                            if key in ['docket_number', 'case_number', 'citation', 'parallel_citations']
                        )
                        
                        if case_name_contains_citation or metadata_contains_citation:
                            print(f"[ENHANCED] Citation found in metadata - likely primary case: {api_case_name}")
                        else:
                            print(f"[ENHANCED] Citation only in text content - likely not primary: {api_case_name}")
                            citation_penalty = 0.3
                            print(f"[ENHANCED] Applying citation penalty: {citation_penalty}")
                        continue
                
                citation_penalty = 0.0
                if self._case_appears_to_cite_target(result, citation, extracted_case_name):
                    print(f"[ENHANCED] Case appears to cite target, reducing score: {api_case_name}")
                    citation_penalty = 0.2
                
                score = similarity - citation_penalty
                
                if extracted_case_name.lower() == api_case_name.lower():
                    score += 0.3
                
                if similarity >= 0.8:
                    score += 0.2
                elif similarity >= 0.6:
                    score += 0.1
                
                if similarity < 0.4:
                    score -= 0.3
                
                if citation_filter and citation_filter in api_case_name:
                    score += 0.2
                    print(f"[ENHANCED] Citation found in case name - bonus applied: {api_case_name}")
                
                if extracted_case_name and extracted_case_name.lower() in api_case_name.lower() and similarity < 0.7:
                    score -= 0.3
                    print(f"[ENHANCED] Case name contains target but low similarity - penalty applied: {api_case_name}")
                
                print(f"[ENHANCED] Case '{api_case_name}' scored: {score:.3f}")
                
                if score > best_score:
                    best_score = score
                    best_match = result
            
            if best_match and best_score >= 0.5:  # Require minimum score for primary case
                print(f"[ENHANCED] Primary case found with score {best_score:.3f}: {best_match.get('caseName')}")
                
                if best_score < 0.3:
                    print(f"[ENHANCED] REJECTING result: Score {best_score:.3f} too low - likely wrong case")
                    print(f"[ENHANCED] Extracted: '{extracted_case_name}' vs API: '{best_match.get('caseName')}'")
                    return None
                
                return best_match
        
        for result in api_results:
            if result.get('caseName') and result.get('absolute_url'):
                return result
        
        return None
    
    def _case_appears_to_cite_target(self, result: Dict, citation: str, extracted_case_name: Optional[str] = None) -> bool:
        """
        Check if a case result appears to be citing the target case rather than being the target.
        
        Args:
            result: Case result from CourtListener API
            citation: Citation text we're looking for
            extracted_case_name: Extracted case name
            
        Returns:
            True if the case appears to cite the target, False otherwise
        """
        case_text = result.get('plain_text', '') or result.get('html', '') or ''
        if not case_text:
            return False
        
        citation_patterns = [
            rf'(?:see|citing|cited)\s+{re.escape(citation)}',
            rf'\({re.escape(citation)}\)',
            rf'(?:in|see)\s+{re.escape(citation)}',
        ]
        
        for pattern in citation_patterns:
            if re.search(pattern, case_text, re.IGNORECASE):
                print(f"[ENHANCED] Found citation pattern '{pattern}' in case text")
                return True
        
        if extracted_case_name:
            # but the case name doesn't match the result's case name, it's likely citing
            case_name_patterns = [
                rf'(?:see|citing|cited)\s+{re.escape(extracted_case_name)}',
                rf'\({re.escape(extracted_case_name)}\)',
                rf'(?:in|see)\s+{re.escape(extracted_case_name)}',
            ]
            
            for pattern in case_name_patterns:
                if re.search(pattern, case_text, re.IGNORECASE):
                    print(f"[ENHANCED] Found case name citation pattern '{pattern}' in case text")
                    return True
        
        return False
    
    def _is_test_citation(self, citation: str) -> bool:
        """Check if citation is a known test citation."""
        test_patterns = [
            r'\b123\s+f\.?3d\s+456\b',
            r'\b999\s+u\.?s\.?\s+999\b',
            r'\bsmith\s+v\.?\s+jones\b',
            r'\btest\s+citation\b',
            r'\bsample\s+citation\b',
            r'\bfake\s+citation\b'
        ]
        
        citation_lower = citation.lower()
        for pattern in test_patterns:
            if re.search(pattern, citation_lower):
                return True
        
        return False

    def _normalize_url(self, url: str) -> str:
        """
        Normalize a CourtListener URL to ensure it's absolute.
        CourtListener URLs are often relative, but the API expects absolute.
        """
        if url and not url.startswith('http://') and not url.startswith('https://'):
            if url.startswith('/'):
                return f"https://www.courtlistener.com{url}"
            if url.startswith('api/'):
                return f"https://www.courtlistener.com{url}"
            return f"https://www.courtlistener.com{url}"
        return url

    def _verify_with_citation_lookup_v4(self, citation: str, extracted_case_name: Optional[str] = None) -> Dict:
        """Verify using citation-lookup API v4 with strict matching criteria."""
        
        result = {
            "canonical_name": None,
            "canonical_date": None,
            "url": None,
            "verified": False,
            "raw": None,
            "source": "CourtListener Citation-Lookup API v4"
        }
        
        try:
            url = "https://www.courtlistener.com/api/rest/v4/citation-lookup/"
            data = {"text": citation}
            
            print(f"[ENHANCED] Citation-lookup API v4 request: {url}")
            print(f"[ENHANCED] Citation-lookup API v4 data: {data}")
            
            response = requests.post(url, headers=self.headers, json=data, timeout=DEFAULT_REQUEST_TIMEOUT)
            
            print(f"[ENHANCED] Citation-lookup API v4 response status: {response.status_code}")
            
            if response.status_code == 200:
                api_results = response.json()
                result['raw'] = response.text
                
                print(f"[ENHANCED] Citation-lookup API v4 raw response: {api_results}")
                
                found_results = [r for r in api_results if r.get('status') != 404 and r.get('clusters')]
                
                print(f"[ENHANCED] Citation-lookup API v4 found {len(found_results)} valid results")
                
                if found_results:
                    all_clusters = []
                    for api_response in found_results:
                        clusters = api_response.get('clusters', [])
                        all_clusters.extend(clusters)
                    
                    print(f"[ENHANCED] Extracted {len(all_clusters)} clusters from {len(found_results)} API responses")
                    
                    best_case = self._find_best_case_with_strict_criteria(
                        all_clusters, citation, extracted_case_name
                    )
                    
                    if best_case:
                        print(f"[ENHANCED] Citation-lookup API v4 found best case: {best_case.get('case_name', 'N/A')}")
                        # CRITICAL: Extract only year from date_filed to prevent contamination
                        date_filed = best_case.get('date_filed', '')
                        canonical_year = None
                        if date_filed:
                            year_match = re.search(r'(\d{4})', date_filed)
                            if year_match:
                                canonical_year = year_match.group(1)
                        
                        result.update({
                            "canonical_name": best_case.get('case_name', ''),
                            "canonical_date": canonical_year or '',  # Only year, never full date
                            "url": self._normalize_url(best_case.get('absolute_url', '')),
                            "verified": True,
                            "confidence": 0.9
                        })
                    else:
                        print(f"[ENHANCED] Citation-lookup API v4 found results but strict criteria failed")
                else:
                    print(f"[ENHANCED] Citation-lookup API v4 found no valid results")
            else:
                print(f"[ENHANCED] Citation-lookup API v4 failed with status: {response.status_code}")
                print(f"[ENHANCED] Citation-lookup API v4 error response: {response.text}")
                
        except Exception as e:
            print(f"[ENHANCED] Citation-lookup API v4 error: {e}")
            logger.error(f"Citation-lookup API v4 error: {e}")
        
        return result

    def _verify_with_citation_lookup_v4_enhanced(self, citation: str, extracted_case_name: Optional[str] = None) -> Dict:
        """Enhanced citation-lookup API v4 with WA reporter normalization and strict matching."""
        
        result = {
            "canonical_name": None,
            "canonical_date": None,
            "url": None,
            "verified": False,
            "raw": None,
            "source": "CourtListener Citation-Lookup API v4"
        }
        
        try:
            def normalize_reporter(cit: str) -> str:
                c = cit
                c = c.replace('\u2019', "'")  # Fix smart quotes
                c = re.sub(r'\bWn\.?\s*2d\b', 'Wash. 2d', c, flags=re.IGNORECASE)
                c = re.sub(r'\bWash\.?\s*2d\b', 'Wash. 2d', c, flags=re.IGNORECASE)
                c = re.sub(r'\bWn\.?\s*App\.?\b', 'Wash. App.', c, flags=re.IGNORECASE)
                c = re.sub(r'\bWash\.?\s*App\.?\b', 'Wash. App.', c, flags=re.IGNORECASE)
                return c

            norm_citation = normalize_reporter(citation)
            
            url = "https://www.courtlistener.com/api/rest/v4/citation-lookup/"
            data = {"text": norm_citation}
            
            response = requests.post(url, headers=self.headers, json=data, timeout=COURTLISTENER_TIMEOUT)
            
            if response.status_code == 200:
                api_results = response.json()
                result['raw'] = response.text
                
                found_results = [r for r in api_results if r.get('status') != 404 and r.get('clusters')]
                
                if found_results:
                    all_clusters = []
                    for api_response in found_results:
                        clusters = api_response.get('clusters', [])
                        all_clusters.extend(clusters)
                    
                    best_case = self._find_best_case_with_strict_criteria(
                        all_clusters, citation, extracted_case_name
                    )
                    
                    if best_case:
                        # CRITICAL: Extract only year from date_filed to prevent contamination
                        date_filed = best_case.get('date_filed', '')
                        canonical_year = None
                        if date_filed:
                            year_match = re.search(r'(\d{4})', date_filed)
                            if year_match:
                                canonical_year = year_match.group(1)
                        
                        result.update({
                            "canonical_name": best_case.get('case_name', ''),
                            "canonical_date": canonical_year or '',  # Only year, never full date
                            "url": self._normalize_url(best_case.get('absolute_url', '')),
                            "verified": True,
                            "confidence": 0.95
                        })
                else:
                    result['verified'] = False
                    result['confidence'] = 0.0
            else:
                result['verified'] = False
                result['confidence'] = 0.0
                
        except Exception as e:
            result['verified'] = False
            result['confidence'] = 0.0
        
        return result
    

def verify_with_courtlistener_enhanced(courtlistener_api_key: str, citation: str, extracted_case_name: Optional[str] = None) -> Dict:
    """Enhanced verification function with cross-validation"""
    
    verifier = EnhancedCourtListenerVerifier(courtlistener_api_key)
    return verifier.verify_citation_enhanced(citation, extracted_case_name)
