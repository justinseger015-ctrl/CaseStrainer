#!/usr/bin/env python3
"""
Enhanced Fallback Citation Verification System

This module integrates the best components from:
1. FallbackVerifier's verification logic
2. EnhancedLegalSearchEngine's query strategies
3. ComprehensiveWebSearchEngine's search capabilities

It provides robust fallback verification for citations not found in CourtListener,
ensuring canonical name, year, and URL are extracted from approved sites.
"""

import asyncio
import logging
import re
import time
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urljoin, quote, urlparse
import requests
import json
from src.url_decoder import URLDecoder
import os

logger = logging.getLogger(__name__)

class EnhancedFallbackVerifier:
    """
    Enhanced fallback verification system that integrates multiple approaches
    to provide reliable citation verification with canonical data extraction.
    """
    
    def __init__(self, enable_experimental_engines=True):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'CaseStrainer Citation Verifier (Educational Research)'
        })
        
        # Rate limiting
        self.last_request_time = {}
        self.min_delay = 0.2  # Reduced from 1.0 to 0.2 seconds for faster processing
        
        # Legal-specific domains with priority scores
        self.legal_domains = {
            'justia.com': 95,
            'caselaw.findlaw.com': 90, 
            'findlaw.com': 85,
            'courtlistener.com': 100,
            'leagle.com': 85,
            'casetext.com': 80,
            'law.cornell.edu': 80,
            'google.com/scholar': 75,
            'casemine.com': 80,
            'vlex.com': 85,
            'openjurist.org': 70
        }
        
        # State-specific citation patterns (extensible for all 50 states)
        self.state_patterns = {
            'WA': [  # Washington
                r'(\d+)\s+Wn\.?\s*2d\s+(\d+)',
                r'(\d+)\s+Wn\.?\s*3d\s+(\d+)', 
                r'(\d+)\s+Wn\.?\s*App\.?\s*2d\s+(\d+)',
                r'(\d+)\s+Wash\.?\s*2d\s+(\d+)',
                r'(\d+)\s+Washington\s+2d\s+(\d+)'
            ],
            'CA': [  # California
                r'(\d+)\s+Cal\.?\s*2d\s+(\d+)',
                r'(\d+)\s+Cal\.?\s*3d\s+(\d+)',
                r'(\d+)\s+Cal\.?\s*App\.?\s*2d\s+(\d+)',
                r'(\d+)\s+Cal\.?\s*App\.?\s*3d\s+(\d+)'
            ],
            'NY': [  # New York
                r'(\d+)\s+N\.?Y\.?\s*2d\s+(\d+)',
                r'(\d+)\s+N\.?Y\.?\s*3d\s+(\d+)',
                r'(\d+)\s+N\.?Y\.?\s*Supp\.?\s*2d\s+(\d+)'
            ],
            'TX': [  # Texas
                r'(\d+)\s+S\.?W\.?\s*2d\s+(\d+)',
                r'(\d+)\s+S\.?W\.?\s*3d\s+(\d+)',
                r'(\d+)\s+Tex\.?\s*App\.?\s*(\d+)'
            ],
            'FL': [  # Florida
                r'(\d+)\s+So\.?\s*2d\s+(\d+)',
                r'(\d+)\s+So\.?\s*3d\s+(\d+)',
                r'(\d+)\s+Fla\.?\s*App\.?\s*(\d+)'
            ]
        }
        
        # Regional reporter patterns (cover all states)
        self.regional_reporters = {
            'P.': [  # Pacific (Western states)
                r'(\d+)\s+P\.\s*3d\s+(\d+)',
                r'(\d+)\s+P\.\s*2d\s+(\d+)'
            ],
            'S.E.': [  # Southeast (GA, NC, SC, VA, WV)
                r'(\d+)\s+S\.?E\.?\s*2d\s+(\d+)',
                r'(\d+)\s+S\.?E\.?\s*3d\s+(\d+)'
            ],
            'S.W.': [  # Southwest (TX, AR, KY, TN)
                r'(\d+)\s+S\.?W\.?\s*2d\s+(\d+)',
                r'(\d+)\s+S\.?W\.?\s*3d\s+(\d+)'
            ],
            'N.E.': [  # Northeast (NY, MA, OH, IL, IN)
                r'(\d+)\s+N\.?E\.?\s*2d\s+(\d+)',
                r'(\d+)\s+N\.?E\.?\s*3d\s+(\d+)'
            ],
            'N.W.': [  # Northwest (MN, IA, NE, ND, SD)
                r'(\d+)\s+N\.?W\.?\s*2d\s+(\d+)',
                r'(\d+)\s+N\.?W\.?\s*3d\s+(\d+)'
            ],
            'A.': [  # Atlantic (PA, NJ, DE, MD)
                r'(\d+)\s+A\.\s*2d\s+(\d+)',
                r'(\d+)\s+A\.\s*3d\s+(\d+)'
            ]
        }
        
        # Enable experimental engines for broader coverage
        self.enable_experimental_engines = enable_experimental_engines
        
    def _rate_limit(self, domain: str):
        """Apply rate limiting for requests to the same domain."""
        now = time.time()
        if domain in self.last_request_time:
            time_since_last = now - self.last_request_time[domain]
            if time_since_last < self.min_delay:
                sleep_time = self.min_delay - time_since_last
                time.sleep(sleep_time)
        self.last_request_time[domain] = now
    
    def normalize_citation(self, citation: str) -> str:
        """Normalize citation format (e.g., WN. -> Wash.)."""
        if not citation:
            return citation
        
        # Washington reporter normalization
        normalized = re.sub(r'\bWN\.?\b', 'Wash.', citation, flags=re.IGNORECASE)
        normalized = re.sub(r'\bWn\.?\b', 'Wash.', normalized, flags=re.IGNORECASE)
        
        # Clean up extra spaces
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized
    
    def detect_state_from_citation(self, citation: str) -> Optional[str]:
        """Detect which state a citation is from based on citation patterns."""
        for state_code, patterns in self.state_patterns.items():
            for pattern in patterns:
                if re.search(pattern, citation, re.IGNORECASE):
                    return state_code
        
        # Check regional reporters
        for reporter_code, patterns in self.regional_reporters.items():
            for pattern in patterns:
                if re.search(pattern, citation, re.IGNORECASE):
                    # Map regional reporters to likely states
                    if reporter_code == 'P.':  # Pacific
                        return 'WA'  # Default to Washington for Pacific reporter
                    elif reporter_code == 'S.E.':  # Southeast
                        return 'GA'  # Default to Georgia for Southeast reporter
                    elif reporter_code == 'S.W.':  # Southwest
                        return 'TX'  # Default to Texas for Southwest reporter
                    elif reporter_code == 'N.E.':  # Northeast
                        return 'NY'  # Default to New York for Northeast reporter
                    elif reporter_code == 'N.W.':  # Northwest
                        return 'MN'  # Default to Minnesota for Northwest reporter
                    elif reporter_code == 'A.':  # Atlantic
                        return 'PA'  # Default to Pennsylvania for Atlantic reporter
        
        return None
    
    def is_washington_citation(self, citation: str) -> bool:
        """Check if citation is from Washington state (maintained for backward compatibility)."""
        return self.detect_state_from_citation(citation) == 'WA'
    
    def generate_citation_variants(self, citation: str) -> List[str]:
        """Generate citation variants for any state."""
        variants = []
        state = self.detect_state_from_citation(citation)
        
        if state == 'WA':  # Washington
            # Replace Wn. with Wash.
            if 'Wn.' in citation:
                variants.append(citation.replace('Wn.', 'Wash.'))
            
            # Replace Wash. with Wn.
            if 'Wash.' in citation:
                variants.append(citation.replace('Wash.', 'Wn.'))
            
            # Replace Washington with Wn.
            if 'Washington' in citation:
                variants.append(citation.replace('Washington', 'Wn.'))
            
            # Handle Wn. App. → Wash. App.
            if 'Wn. App.' in citation:
                variants.append(citation.replace('Wn. App.', 'Wash. App.'))
            
            # Handle Wash. App. → Wn. App.
            if 'Wash. App.' in citation:
                variants.append(citation.replace('Wash. App.', 'Wn. App.'))
            
            # Handle Wn.2d → Wash.2d
            if 'Wn.2d' in citation:
                variants.append(citation.replace('Wn.2d', 'Wash.2d'))
            
            # Handle Wash.2d → Wn.2d
            if 'Wash.2d' in citation:
                variants.append(citation.replace('Wash.2d', 'Wn.2d'))
        
        elif state == 'CA':  # California
            # Replace Cal. with California
            if 'Cal.' in citation:
                variants.append(citation.replace('Cal.', 'California'))
            
            # Replace California with Cal.
            if 'California' in citation:
                variants.append(citation.replace('California', 'Cal.'))
        
        elif state == 'NY':  # New York
            # Replace N.Y. with New York
            if 'N.Y.' in citation:
                variants.append(citation.replace('N.Y.', 'New York'))
            
            # Replace New York with N.Y.
            if 'New York' in citation:
                variants.append(citation.replace('New York', 'N.Y.'))
        
        elif state == 'TX':  # Texas
            # Replace Tex. with Texas
            if 'Tex.' in citation:
                variants.append(citation.replace('Tex.', 'Texas'))
            
            # Replace Texas with Tex.
            if 'Texas' in citation:
                variants.append(citation.replace('Texas', 'Tex.'))
        
        return variants
    
    def generate_washington_variants(self, citation: str) -> List[str]:
        """Generate Washington citation variants (maintained for backward compatibility)."""
        return self.generate_citation_variants(citation)
    
    def _get_state_name(self, state_code: str) -> str:
        """Get full state name from state code."""
        state_names = {
            'WA': 'Washington',
            'CA': 'California',
            'NY': 'New York',
            'TX': 'Texas',
            'FL': 'Florida',
            'GA': 'Georgia',
            'PA': 'Pennsylvania',
            'MN': 'Minnesota'
        }
        return state_names.get(state_code, state_code)
    
    def _get_state_legal_sites(self, state_code: str) -> List[str]:
        """Get state-specific legal database sites."""
        state_sites = {
            'WA': [  # Washington
                'site:caselaw.findlaw.com/court/wa-supreme-court',
                'site:caselaw.findlaw.com/court/wa-court-of-appeals',
                'site:justia.com/courts/wa',
                'site:leagle.com/courts/wa',
                'site:law.justia.com/courts/wa',
                'site:supreme.findlaw.com/court/wa',
                'site:courts.wa.gov',
                'site:leg.wa.gov',
                'site:app.leg.wa.gov'
            ],
            'CA': [  # California
                'site:caselaw.findlaw.com/court/ca-supreme-court',
                'site:caselaw.findlaw.com/court/ca-court-of-appeal',
                'site:justia.com/courts/ca',
                'site:leagle.com/courts/ca',
                'site:law.justia.com/courts/ca',
                'site:courts.ca.gov'
            ],
            'NY': [  # New York
                'site:caselaw.findlaw.com/court/ny-court-of-appeals',
                'site:caselaw.findlaw.com/court/ny-supreme-court',
                'site:justia.com/courts/ny',
                'site:leagle.com/courts/ny',
                'site:law.justia.com/courts/ny',
                'site:courts.ny.gov'
            ],
            'TX': [  # Texas
                'site:caselaw.findlaw.com/court/tx-supreme-court',
                'site:caselaw.findlaw.com/court/tx-court-of-appeals',
                'site:justia.com/courts/tx',
                'site:leagle.com/courts/tx',
                'site:law.justia.com/courts/tx',
                'site:courts.texas.gov'
            ]
        }
        return state_sites.get(state_code, [])
    
    def _get_court_type(self, citation_text: str, state_code: str) -> str:
        """Determine court type from citation."""
        if 'App.' in citation_text:
            return 'appellate court'
        elif '2d' in citation_text and 'App.' not in citation_text:
            return 'supreme court'
        else:
            return 'court'
    
    def generate_enhanced_legal_queries(self, citation_text: str, case_name: Optional[str] = None) -> List[Dict]:
        """
        Generate optimized search queries for enhanced fallback verification.
        Prioritizes simple, effective queries that work well with Google/Bing.
        """
        queries = []
        
        # Clean and normalize citation
        citation_text = citation_text.strip()
        
        # Strategy 1: Simple citation search (most likely to succeed)
        queries.append({
            'query': f'"{citation_text}"',
            'priority': 1,
            'type': 'simple_citation',
            'citation': citation_text
        })
        
        # Strategy 1b: Citation variants (for any state)
        state = self.detect_state_from_citation(citation_text)
        if state:
            citation_variants = self.generate_citation_variants(citation_text)
            for variant in citation_variants:
                queries.append({
                    'query': f'"{variant}"',
                    'priority': 1,  # Same priority as original
                    'type': 'citation_variant',
                    'citation': variant,
                    'original': citation_text
                })
        
        # Strategy 2: Citation + "court decision" (very effective for Google/Bing)
        queries.append({
            'query': f'"{citation_text}" court decision',
            'priority': 2,
            'type': 'citation_court',
            'citation': citation_text
        })
        
        # Strategy 3: Citation + state name (if state is detected)
        state = self.detect_state_from_citation(citation_text)
        if state:
            state_name = self._get_state_name(state)
            queries.append({
                'query': f'"{citation_text}" {state_name}',
                'priority': 2,  # Increased priority for state-specific cases
                'type': f'citation_{state.lower()}',
                'citation': citation_text
            })
            
            # Strategy 3b: State-specific legal database searches
            state_legal_sites = self._get_state_legal_sites(state)
            for site in state_legal_sites:
                queries.append({
                    'query': f'{site} "{citation_text}"',
                    'priority': 2,  # High priority for state-specific searches
                    'type': f'{state.lower()}_site_specific',
                    'citation': citation_text,
                    'site': site
                })
            
            # Strategy 3c: State case name + citation (if case name available)
            if case_name:
                court_type = self._get_court_type(citation_text, state)
                queries.append({
                    'query': f'"{case_name}" "{citation_text}" {state_name} {court_type}',
                    'priority': 1,  # Highest priority for state cases with names
                    'type': f'{state.lower()}_case_citation',
                    'citation': citation_text,
                    'case_name': case_name
                })
        
        # Strategy 4: Case name + citation (if case name available)
        if case_name:
            queries.append({
                'query': f'"{case_name}" "{citation_text}"',
                'priority': 4,
                'type': 'case_and_citation',
                'citation': citation_text,
                'case_name': case_name
            })
            
            # Also try with "v." instead of "vs." for case names
            if ' vs. ' in case_name:
                alt_case_name = case_name.replace(' vs. ', ' v. ')
                queries.append({
                    'query': f'"{alt_case_name}" "{citation_text}"',
                    'priority': 4,
                    'type': 'case_and_citation_alt',
                    'citation': citation_text,
                    'case_name': alt_case_name
                })
        
        # Strategy 5: Legal database specific searches (HIGH priority - these are most effective!)
        legal_sites = [
            'site:caselaw.findlaw.com',  # FindLaw - very reliable for legal cases
            'site:justia.com',           # Justia - excellent legal database
            'site:courtlistener.com',    # CourtListener - official court data
            'site:case-law.vlex.com',    # Vlex - international legal database
            'site:leagle.com',           # Leagle - legal case database
            'site:supreme.findlaw.com',  # FindLaw Supreme Court cases
            'site:law.justia.com',      # Justia law database
            'site:scholar.google.com',   # Google Scholar (legal cases)
        ]
        for site in legal_sites:
            queries.append({
                'query': f'{site} "{citation_text}"',
                'priority': 2,  # Increased from 5 to 2 - these are very effective!
                'type': 'site_specific',
                'citation': citation_text,
                'site': site
            })
        
        # Strategy 6: Enhanced state-specific queries (if state is detected)
        state = self.detect_state_from_citation(citation_text)
        if state:
            # Add state-specific search strategies
            state_queries = self._generate_state_specific_queries(citation_text, case_name, state)
            queries.extend(state_queries)
        
        # Strategy 7: Parallel citation searches (if we know about parallel citations)
        if state:
            parallel_queries = self._generate_parallel_citation_queries(citation_text, case_name)
            queries.extend(parallel_queries)
        
        return queries
    
    def _generate_state_specific_queries(self, citation_text: str, case_name: Optional[str] = None, state_code: str = 'WA') -> List[Dict]:
        """Generate state-specific search queries for better case discovery."""
        state_queries = []
        state_name = self._get_state_name(state_code)
        
        # Court of Appeals specific searches
        if 'App.' in citation_text:
            state_queries.append({
                'query': f'"{citation_text}" "{state_name} Court of Appeals"',
                'priority': 1,  # Highest priority
                'type': f'{state_code.lower()}_appeals_specific',
                'citation': citation_text
            })
            
            # Try with case name if available
            if case_name:
                state_queries.append({
                    'query': f'"{case_name}" "{citation_text}" "{state_name} Court of Appeals"',
                    'priority': 1,  # Highest priority
                    'type': f'{state_code.lower()}_appeals_case',
                    'citation': citation_text,
                    'case_name': case_name
                })
        
        # Supreme Court specific searches
        if '2d' in citation_text and 'App.' not in citation_text:
            state_queries.append({
                'query': f'"{citation_text}" "{state_name} Supreme Court"',
                'priority': 1,  # Highest priority
                'type': f'{state_code.lower()}_supreme_specific',
                'citation': citation_text
            })
            
            # Try with case name if available
            if case_name:
                state_queries.append({
                    'query': f'"{case_name}" "{citation_text}" "{state_name} Supreme Court"',
                    'priority': 1,  # Highest priority
                    'type': f'{state_code.lower()}_supreme_case',
                    'citation': citation_text,
                    'case_name': case_name
                })
        
        # Regional reporter parallel citation searches
        if 'P.3d' in citation_text or 'P.2d' in citation_text:
            state_queries.append({
                'query': f'"{citation_text}" "{state_name}" "Pacific Reporter"',
                'priority': 2,  # High priority
                'type': f'{state_code.lower()}_pacific_parallel',
                'citation': citation_text
            })
        elif 'S.E.' in citation_text:
            state_queries.append({
                'query': f'"{citation_text}" "{state_name}" "Southeast Reporter"',
                'priority': 2,  # High priority
                'type': f'{state_code.lower()}_southeast_parallel',
                'citation': citation_text
            })
        elif 'S.W.' in citation_text:
            state_queries.append({
                'query': f'"{citation_text}" "{state_name}" "Southwest Reporter"',
                'priority': 2,  # High priority
                'type': f'{state_code.lower()}_southwest_parallel',
                'citation': citation_text
            })
        elif 'N.E.' in citation_text:
            state_queries.append({
                'query': f'"{citation_text}" "{state_name}" "Northeast Reporter"',
                'priority': 2,  # High priority
                'type': f'{state_code.lower()}_northeast_parallel',
                'citation': citation_text
            })
        elif 'N.W.' in citation_text:
            state_queries.append({
                'query': f'"{citation_text}" "{state_name}" "Northwest Reporter"',
                'priority': 2,  # High priority
                'type': f'{state_code.lower()}_northwest_parallel',
                'citation': citation_text
            })
        elif 'A.' in citation_text:
            state_queries.append({
                'query': f'"{citation_text}" "{state_name}" "Atlantic Reporter"',
                'priority': 2,  # High priority
                'type': f'{state_code.lower()}_atlantic_parallel',
                'citation': citation_text
            })
        
        return state_queries
    
    def _generate_parallel_citation_queries(self, citation_text: str, case_name: Optional[str] = None) -> List[Dict]:
        """Generate queries for parallel citations to improve case discovery."""
        parallel_queries = []
        
        # If this is a Washington Reporter citation, also search for Pacific Reporter
        if 'Wn.' in citation_text or 'Wash.' in citation_text:
            # Extract volume and page numbers
            volume_page_match = re.search(r'(\d+)\s+(?:Wn\.|Wash\.)\s*(?:App\.|2d|3d)\s+(\d+)', citation_text)
            if volume_page_match:
                volume, page = volume_page_match.groups()
                
                # Generate Pacific Reporter parallel citation queries
                if 'App.' in citation_text:
                    # Court of Appeals - try P.3d
                    parallel_queries.append({
                        'query': f'"{volume} P.3d {page}" Washington',
                        'priority': 1,  # High priority
                        'type': 'parallel_pacific_appeals',
                        'citation': citation_text
                    })
                elif '2d' in citation_text:
                    # Supreme Court - try P.2d
                    parallel_queries.append({
                        'query': f'"{volume} P.2d {page}" Washington',
                        'priority': 1,  # High priority
                        'type': 'parallel_pacific_supreme',
                        'citation': citation_text
                    })
        
        # If this is a Pacific Reporter citation, also search for Washington Reporter
        elif 'P.3d' in citation_text or 'P.2d' in citation_text:
            # Extract volume and page numbers
            volume_page_match = re.search(r'(\d+)\s+P\.(?:3d|2d)\s+(\d+)', citation_text)
            if volume_page_match:
                volume, page = volume_page_match.groups()
                
                # Generate Washington Reporter parallel citation queries
                if 'P.3d' in citation_text:
                    # Try Washington App. (Court of Appeals)
                    parallel_queries.append({
                        'query': f'"{volume} Wn. App. {page}" Washington',
                        'priority': 1,  # High priority
                        'type': 'parallel_washington_appeals',
                        'citation': citation_text
                    })
                    parallel_queries.append({
                        'query': f'"{volume} Wash. App. {page}" Washington',
                        'priority': 1,  # High priority
                        'type': 'parallel_washington_appeals_full',
                        'citation': citation_text
                    })
                elif 'P.2d' in citation_text:
                    # Try Washington 2d (Supreme Court)
                    parallel_queries.append({
                        'query': f'"{volume} Wn.2d {page}" Washington',
                        'priority': 1,  # High priority
                        'type': 'parallel_washington_supreme',
                        'citation': citation_text
                    })
                    parallel_queries.append({
                        'query': f'"{volume} Wash.2d {page}" Washington',
                        'priority': 1,  # High priority
                        'type': 'parallel_washington_supreme_full',
                        'citation': citation_text
                    })
        
        return parallel_queries
    
    def _parse_citation(self, citation_text: str) -> Dict:
        """Parse citation to extract volume, reporter, page, and court type."""
        citation_info = {
            'volume': None,
            'reporter': None,
            'page': None,
            'year': None,
            'court_type': 'unknown'
        }
        
        # Washington-specific patterns
        washington_patterns = [
            r'(\d+)\s+Wn\.\s*2d\s+(\d+)',  # 188 Wn.2d 114
            r'(\d+)\s+Wn\.\s*App\.\s+(\d+)',  # 178 Wn. App. 929
            r'(\d+)\s+Wash\.\s*2d\s+(\d+)',  # 188 Wash. 2d 114
            r'(\d+)\s+Wash\.\s*App\.\s+(\d+)',  # 178 Wash. App. 929
        ]
        
        for pattern in washington_patterns:
            match = re.search(pattern, citation_text, re.IGNORECASE)
            if match:
                citation_info['volume'] = match.group(1)
                citation_info['page'] = match.group(2)
                citation_info['court_type'] = 'washington'
                citation_info['reporter'] = 'Wn.' if 'Wn.' in citation_text else 'Wash.'
                break
        
        # Pacific Reporter patterns
        pacific_patterns = [
            r'(\d+)\s+P\.\s*3d\s+(\d+)',  # 392 P.3d 1041
            r'(\d+)\s+P\.\s*2d\s+(\d+)',  # 317 P.2d 1068
        ]
        
        for pattern in pacific_patterns:
            match = re.search(pattern, citation_text, re.IGNORECASE)
            if match:
                citation_info['volume'] = match.group(1)
                citation_info['page'] = match.group(2)
                citation_info['court_type'] = 'pacific'
                citation_info['reporter'] = 'P.3d' if '3d' in citation_text else 'P.2d'
                break
        
        # Extract year if present in citation
        year_match = re.search(r'\((\d{4})\)', citation_text)
        if year_match:
            citation_info['year'] = year_match.group(1)
        
        return citation_info
    
    async def verify_citation(self, citation_text: str, extracted_case_name: Optional[str] = None, extracted_date: Optional[str] = None, has_courtlistener_data: bool = False) -> Dict[str, Any]:
        """
        Verify a citation using hybrid verification: CourtListener first, then enhanced fallback with 10 sources.
        
        Args:
            citation_text: The citation text to verify
            extracted_case_name: Optional extracted case name
            extracted_date: Optional extracted date
            has_courtlistener_data: If True, skip fallback verification (already verified)
            
        Returns:
            Dictionary with verification results
        """
        logger.info(f"🚀 HYBRID VERIFICATION CALLED for {citation_text}")
        
        # Skip fallback verification if citation already has CourtListener data
        if has_courtlistener_data:
            logger.info(f"Skipping fallback verification for {citation_text} - already has CourtListener data")
            return self._create_fallback_result(citation_text, "already_verified", extracted_case_name)
        
        start_time = time.time()
        max_total_time = 15.0  # Increased to 15 seconds total per citation for better reliability
        
        try:
            # STEP 1: Try CourtListener first (fast, reliable, official)
            courtlistener_result = await self._try_courtlistener_first(citation_text, extracted_case_name)
            if courtlistener_result and courtlistener_result.get('verified', False):
                elapsed = time.time() - start_time
                logger.info(f"✅ CourtListener verified: {citation_text} -> {courtlistener_result.get('canonical_name', 'N/A')} in {elapsed:.1f}s")
                return courtlistener_result
            
            logger.info(f"CourtListener failed for {citation_text}, proceeding with enhanced fallback verification")
            
            # Parse citation to determine type and court
            citation_info = self._parse_citation(citation_text)
            
            # Generate optimized search queries
            queries = self.generate_enhanced_legal_queries(citation_text, extracted_case_name)
            
            # Debug logging for state citations
            state = self.detect_state_from_citation(citation_text)
            if state:
                logger.info(f"Generated {len(queries)} queries for {state} citation {citation_text}")
                for i, q in enumerate(queries[:6]):  # Show first 6 queries
                    logger.debug(f"  Query {i+1}: '{q['query']}' (type: {q['type']}, priority: {q['priority']})")
            
            # Define sources with their verification functions
            # Prioritize legal databases first (more tolerant of automated access)
            # Then general search engines last (more likely to be rate-limited)
            sources = [
                ('scrapingbee', self._verify_with_scrapingbee),  # Premium: handles JS, anti-bot bypass
                ('descrybe', self._verify_with_descrybe),        # Legal database, 3.6M U.S. cases - NEW!
                ('casemine', self._verify_with_casemine),        # Legal database, international - HAS WASHINGTON CASES!
                ('findlaw', self._verify_with_findlaw),          # Legal database, good coverage
                ('leagle', self._verify_with_leagle),            # Legal database, comprehensive
                ('vlex', self._verify_with_vlex),                # Legal database, extensive
                ('justia', self._verify_with_justia),            # Legal-specific but reliable
                ('google', self._verify_with_google_scholar),    # Fast, reliable, broad coverage (rate-limited)
                ('bing', self._verify_with_bing),                # Fast, reliable, good legal indexing (rate-limited)
                ('duckduckgo', self._verify_with_duckduckgo),    # Fast, no rate limiting (rate-limited)
            ]
            
            logger.info(f"Configured {len(sources)} verification sources: {[s[0] for s in sources]}")
            
            # Create tasks for all sources to run concurrently
            tasks = []
            logger.info(f"🔍 Processing {len(sources)} verification sources: {[s[0] for s in sources]}")
            
            for source_name, verify_func in sources:
                # For state citations, use more queries to ensure coverage
                state = self.detect_state_from_citation(citation_text)
                max_queries = 4 if state else 2
                logger.info(f"📋 Processing source {source_name} with max_queries={max_queries}")
                
                # Ensure ALL sources are called with appropriate queries
                for query_info in queries[:max_queries]:
                    query = query_info['query']
                    query_type = query_info.get('type', '')
                    
                    # Create task for ALL sources - no filtering out
                    task = self._create_verification_task(
                        source_name, verify_func, citation_text, citation_info, extracted_case_name, extracted_date, query
                    )
                    tasks.append(task)
                    logger.info(f"✅ Created task for {source_name} with query: {query[:50]}...")
            
            # Run all tasks concurrently with strict timeout
            logger.info(f"Created {len(tasks)} verification tasks for {len(sources)} sources")
            results = []
            try:
                # Use asyncio.wait_for to enforce the timeout
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=max_total_time
                )
            except asyncio.TimeoutError:
                logger.warning(f"Enhanced fallback verification timed out after {max_total_time}s for {citation_text}")
                # Return early with partial results if we have any
                return self._create_fallback_result(citation_text, "timeout", extracted_case_name)
            
            # Process results and find the best match
            best_result = None
            best_score = 0
            
            for result in results:
                if isinstance(result, Exception):
                    continue
                    
                if isinstance(result, dict) and result.get('verified'):
                    # Use expected extracted name/year to guide scoring
                    expected_name = extracted_case_name
                    expected_year = extracted_date or (citation_info.get('year') if citation_info else None)
                    score = self._calculate_verification_score(result, expected_name, expected_year)
                    if score > best_score:
                        best_score = score
                        best_result = result
            
            if best_result and best_score >= 1.5:  # Require minimum score for verification
                # Update source to be user-friendly based on URL
                source_url = best_result.get('canonical_url') or best_result.get('url')
                if source_url:
                    best_result['source'] = self._extract_source_from_url(source_url)
                
                # Ensure canonical_url is set for UI linking
                if not best_result.get('canonical_url') and best_result.get('url'):
                    best_result['canonical_url'] = best_result['url']
                
                elapsed = time.time() - start_time
                logger.info(f"✅ Enhanced fallback verified: {citation_text} -> {best_result.get('canonical_name', 'N/A')} (via {best_result.get('source', 'unknown')}) in {elapsed:.1f}s")
                return best_result
            elif best_result:
                # Score too low - log and return failure
                elapsed = time.time() - start_time
                logger.warning(f"❌ Verification score too low ({best_score:.2f}) for {citation_text} -> {best_result.get('canonical_name', 'N/A')} in {elapsed:.1f}s")
                return self._create_fallback_result(citation_text, "low_confidence", extracted_case_name)
            
            # No verification found
            elapsed = time.time() - start_time
            logger.debug(f"Enhanced fallback verification failed for {citation_text} after {elapsed:.1f}s")
            return self._create_fallback_result(citation_text, "not_found", extracted_case_name)
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Enhanced fallback verification error for {citation_text} after {elapsed:.1f}s: {str(e)}")
            return self._create_fallback_result(citation_text, "error", extracted_case_name)
    
    async def _try_courtlistener_first(self, citation_text: str, extracted_case_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Try CourtListener verification first for fast, reliable results.
        
        Args:
            citation_text: The citation to verify
            extracted_case_name: Optional extracted case name
            
        Returns:
            CourtListener verification result or None if failed
        """
        try:
            # Check if CourtListener API key is available
            courtlistener_api_key = os.getenv('COURTLISTENER_API_KEY')
            if not courtlistener_api_key:
                logger.debug("CourtListener API key not available - skipping CourtListener verification")
                return None
            
            # Import CourtListener verifier
            try:
                from src.enhanced_courtlistener_verification import EnhancedCourtListenerVerifier
            except ImportError:
                logger.debug("CourtListener verifier not available - skipping CourtListener verification")
                return None
            
            # Create CourtListener verifier
            courtlistener_verifier = EnhancedCourtListenerVerifier(courtlistener_api_key)
            
            # Try CourtListener verification
            logger.debug(f"Attempting CourtListener verification for: {citation_text}")
            result = courtlistener_verifier.verify_citation_enhanced(citation_text, extracted_case_name)
            
            if result and result.get('verified', False):
                logger.info(f"✓ CourtListener verification successful for: {citation_text}")
                
                # Ensure URLs are absolute
                url = result.get('url', '')
                canonical_url = result.get('canonical_url') or result.get('url', '')
                
                # Convert relative URLs to absolute
                if url and url.startswith('/'):
                    url = f"https://www.courtlistener.com{url}"
                if canonical_url and canonical_url.startswith('/'):
                    canonical_url = f"https://www.courtlistener.com{canonical_url}"
                
                return {
                    'verified': True,
                    'canonical_name': result.get('canonical_name'),
                    'canonical_date': result.get('canonical_date'),
                    'url': url,
                    'canonical_url': canonical_url,
                    'source': 'CourtListener',
                    'validation_method': result.get('validation_method', 'enhanced_cross_validation'),
                    'confidence': result.get('confidence', 0.0),
                    'verification_strategy': 'courtlistener_only'
                }
            else:
                logger.debug(f"CourtListener verification failed for: {citation_text}")
                return None
                
        except Exception as e:
            logger.warning(f"CourtListener verification error for {citation_text}: {str(e)}")
            return None
    
    def _extract_source_from_url(self, url: Optional[str]) -> str:
        """Extract a user-friendly source name from a URL."""
        if not url:
            return "unknown"
        
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # Map domains to user-friendly names
            source_map = {
                'courtlistener.com': 'CourtListener',
                'caselaw.findlaw.com': 'FindLaw',
                'findlaw.com': 'FindLaw',
                'justia.com': 'Justia',
                'leagle.com': 'Leagle',
                'casetext.com': 'Casetext',
                'law.cornell.edu': 'Cornell Law',
                'scholar.google.com': 'Google Scholar',
                'casemine.com': 'CaseMine',
                'vlex.com': 'vLex',
                'openjurist.org': 'OpenJurist',
                'descrybe.ai': 'Descrybe.ai',
                'scrapingbee.com': 'Web Search'
            }
            
            # Check for exact domain match
            for domain_pattern, source_name in source_map.items():
                if domain_pattern in domain:
                    return source_name
            
            # Check for partial domain match
            for domain_pattern, source_name in source_map.items():
                if domain_pattern.split('.')[0] in domain:
                    return source_name
            
            # Return domain if no match found
            return domain.replace('www.', '')
            
        except Exception:
            return "unknown"

    def _create_fallback_result(self, citation_text: str, status: str, case_name: Optional[str] = None) -> Dict[str, Any]:
        """Create a standardized fallback result."""
        return {
            'verified': False,
            'source': f"fallback_{status}",
            'canonical_name': None,
            'canonical_date': None,
            'url': None,
            'canonical_url': None,
            'confidence': 0.0,
            'error': f"Verification {status}"
        }
    
    def _normalize_case_name(self, name: Optional[str]) -> str:
        """Normalize a case name for fuzzy comparison."""
        if not name:
            return ""
        name_norm = name.lower()
        # Common punctuation/variants
        name_norm = name_norm.replace('.', ' ').replace(',', ' ').replace('\n', ' ').replace('\r', ' ')
        name_norm = name_norm.replace(' v ', ' v. ').replace(' vs ', ' v. ').replace(' vs. ', ' v. ')
        name_norm = name_norm.replace('in re', 'in re').replace('ex parte', 'ex parte')
        # Collapse spaces
        name_norm = re.sub(r'\s+', ' ', name_norm).strip()
        return name_norm

    def _token_jaccard(self, a: str, b: str) -> float:
        """Simple token Jaccard similarity for fuzzy matching."""
        if not a or not b:
            return 0.0
        ta = set(a.split())
        tb = set(b.split())
        if not ta or not tb:
            return 0.0
        inter = ta.intersection(tb)
        union = ta.union(tb)
        return len(inter) / len(union) if union else 0.0

    def _year_from_any(self, value: Optional[str]) -> Optional[str]:
        """Extract a 4-digit year from various date formats."""
        if not value:
            return None
        m = re.search(r'(19|20)\d{2}', str(value))
        return m.group(0) if m else None

    def _calculate_verification_score(self, result: Dict[str, Any], expected_name: Optional[str] = None, expected_year: Optional[str] = None) -> float:
        """Calculate a score for verification result quality with fuzzy name/year alignment."""
        score = 0.0
        
        # Base score for verification
        if result.get('verified'):
            score += 1.0
        
        # Bonus for having canonical name
        canonical_name = result.get('canonical_name')
        if canonical_name:
            score += 0.5
        
        # Bonus for having canonical date
        canonical_date = result.get('canonical_date')
        if canonical_date:
            score += 0.3
        
        # Bonus for having URL
        if result.get('url'):
            score += 0.2
        
        # Bonus for high confidence
        if result.get('confidence'):
            score += min(result['confidence'], 1.0)
        
        # Fuzzy name similarity (expected vs canonical) - ADJUSTED FOR WASHINGTON CASES
        if expected_name and canonical_name:
            sim = self._token_jaccard(self._normalize_case_name(expected_name), self._normalize_case_name(canonical_name))
            
            # Special handling for "In re Marriage of" cases - be more lenient
            if 'marriage' in expected_name.lower() and 'marriage' in canonical_name.lower():
                if sim >= 0.4:  # Lower threshold for marriage cases
                    score += sim * 1.5  # Bonus for marriage case similarity
                elif sim < 0.3:  # Still require some similarity
                    score -= 1.5  # Reduced penalty for marriage cases
                else:
                    score += sim * 0.5  # Partial credit
            else:
                # Standard similarity threshold for other cases
                if sim < 0.6:  # Require 60% similarity minimum
                    score -= 2.0  # Heavy penalty for low similarity
                else:
                    score += sim  # Bonus for high similarity
        else:
            # No expected name - penalize
            score -= 1.0
        
        # Year alignment bonus/penalty - MORE LENIENT FOR WASHINGTON CASES
        exp_year = self._year_from_any(expected_year)
        can_year = self._year_from_any(canonical_date)
        if exp_year and can_year:
            try:
                exp_year_int = int(exp_year) if isinstance(exp_year, (int, str)) else None
                can_year_int = int(can_year) if isinstance(can_year, (int, str)) else None
                
                if exp_year_int and can_year_int:
                    year_diff = abs(exp_year_int - can_year_int)
                    if year_diff == 0:
                        score += 1.5  # Strong bonus for exact year match
                    elif year_diff <= 2:  # Allow 2 year difference for Washington cases
                        score += 0.5  # Small bonus for close years
                    elif year_diff <= 5:  # Allow 5 year difference with penalty
                        score -= 0.5  # Small penalty for moderate year difference
                    else:
                        score -= 1.5  # Heavy penalty for large year difference
            except (ValueError, TypeError):
                # If year conversion fails, use standard penalty
                score -= 1.0
        
        return score
    
    def _create_verification_task(self, source_name: str, verify_func, citation_text: str, 
                                 citation_info: Dict, extracted_case_name: Optional[str], 
                                 extracted_date: Optional[str], query: str):
        """Create a verification task with proper error handling."""
        async def task_wrapper():
            try:
                logger.debug(f"Starting {source_name} verification for {citation_text}")
                result = await verify_func(citation_text, citation_info, extracted_case_name, extracted_date, query)
                if result and result.get('verified', False):
                    logger.debug(f"{source_name} verification successful for {citation_text}")
                return result
            except Exception as e:
                logger.debug(f"{source_name} verification failed for {citation_text}: {e}")
                return None
        
        return task_wrapper()
    
    def verify_citation_sync(self, citation_text: str, extracted_case_name: Optional[str] = None, extracted_date: Optional[str] = None) -> Dict:
        """
        Synchronous version of verify_citation for use in non-async contexts.
        
        Args:
            citation_text: The citation to verify (e.g., "188 Wn.2d 114")
            extracted_case_name: Optional case name (e.g., "In re Marriage of Black")
            extracted_date: Optional date (e.g., "2017")
            
        Returns:
            Dict with verification results including canonical_name, canonical_date, and url
        """
        try:
            # Create a new event loop for this thread
            import asyncio
            import threading
            
            # Check if we're already in an event loop
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're in an event loop, can't run sync version
                    logger.warning(f"Sync verification called from within event loop for {citation_text}")
                    return {
                        'verified': False,
                        'source': 'sync_limitation',
                        'canonical_name': None,
                        'canonical_date': None,
                        'url': None,
                        'confidence': 0.0,
                        'error': 'Cannot run sync verification from within event loop'
                    }
            except RuntimeError:
                # No event loop, we can create one
                pass
            
            # Create a new event loop and run the async verification
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # Run the async verification
                result = loop.run_until_complete(
                    self.verify_citation(citation_text, extracted_case_name)
                )
                return result
            finally:
                loop.close()
                asyncio.set_event_loop(None)
            
        except Exception as e:
            logger.error(f"Error in sync verification: {e}")
            return {
                'verified': False,
                'source': None,
                'canonical_name': None,
                'canonical_date': None,
                'url': None,
                'confidence': 0.0,
                'error': str(e)
            }
    
    async def _verify_with_justia(self, citation_text: str, citation_info: Dict, 
                                 extracted_case_name: Optional[str] = None, extracted_date: Optional[str] = None,
                                 search_query: Optional[str] = None) -> Optional[Dict]:
        """Verify citation with Justia legal database."""
        try:
            # Use provided search query or generate one
            if not search_query:
                search_query = citation_text
                if extracted_case_name:
                    search_query += f" {extracted_case_name}"
            
            # Justia search URL
            search_url = f"https://law.justia.com/search?query={quote(search_query)}"
            
            self._rate_limit('justia.com')
            response = self.session.get(search_url, timeout=5)  # Reduced from 15 to 5 seconds
            
            if response.status_code == 200:
                content = response.text
                
                # Look for case links that contain our citation
                case_link_pattern = r'<a[^>]*href="([^"]*cases[^"]+)"[^>]*>([^<]*)</a>'
                matches = re.findall(case_link_pattern, content, re.IGNORECASE)
                
                for link_url, link_text in matches:
                    # Check if this link contains our citation
                    if citation_text.replace(' ', '').lower() in link_text.replace(' ', '').lower():
                        # Found a matching case link
                        full_url = link_url if link_url.startswith('http') else f"https://law.justia.com{link_url}"
                        
                        # Extract case name from link text
                        case_name = self._extract_case_name_from_link(link_text)
                        if not case_name and extracted_case_name:
                            case_name = extracted_case_name
                        
                        # Extract year
                        year = extracted_date or (citation_info.get('year') if citation_info else None)
                        if not year:
                            year_match = re.search(r'(\d{4})', link_text)
                            if year_match:
                                year = year_match.group(1)
                        
                        if case_name:
                            return {
                                'verified': True,
                                'source': 'justia',
                                'canonical_name': case_name,
                                'canonical_date': year,
                                'url': full_url,
                                'confidence': 0.85
                            }
            
            return None
            
        except Exception as e:
            logger.warning(f"Justia verification failed for {citation_text}: {e}")
            return None
    
    async def _verify_with_findlaw(self, citation_text: str, citation_info: Dict,
                                  extracted_case_name: Optional[str] = None, extracted_date: Optional[str] = None,
                                  search_query: Optional[str] = None) -> Optional[Dict]:
        """Verify citation with FindLaw legal database."""
        try:
            # Use provided search query or generate one
            if not search_query:
                search_query = citation_text
                if extracted_case_name:
                    search_query += f" {extracted_case_name}"
            
            # FindLaw search URL
            search_url = f"https://caselaw.findlaw.com/search?query={quote(search_query)}"
            
            self._rate_limit('findlaw.com')
            response = self.session.get(search_url, timeout=5)  # Reduced from 15 to 5 seconds
            
            if response.status_code == 200:
                content = response.text
                
                # Look for case links that contain our citation
                case_link_pattern = r'<a[^>]*href="([^"]*)"[^>]*>([^<]*)</a>'
                matches = re.findall(case_link_pattern, content, re.IGNORECASE)
                
                for link_url, link_text in matches:
                    # Check if this link contains our citation
                    if citation_text.replace(' ', '').lower() in link_text.replace(' ', '').lower():
                        # Found a matching case link
                        full_url = link_url if link_url.startswith('http') else f"https://caselaw.findlaw.com{link_url}"
                        
                        # Extract case name from link text
                        case_name = self._extract_case_name_from_link(link_text)
                        if not case_name and extracted_case_name:
                            case_name = extracted_case_name
                        
                        # Extract year
                        year = extracted_date or (citation_info.get('year') if citation_info else None)
                        if not year:
                            year_match = re.search(r'(\d{4})', link_text)
                            if year_match:
                                year = year_match.group(1)
                        
                        if case_name:
                            return {
                                'verified': True,
                                'source': 'findlaw',
                                'canonical_name': case_name,
                                'canonical_date': year,
                                'url': full_url,
                                'confidence': 0.8
                            }
            
            return None
            
        except Exception as e:
            logger.warning(f"FindLaw verification failed for {citation_text}: {e}")
            return None
    
    async def _verify_with_leagle(self, citation_text: str, citation_info: Dict,
                                 extracted_case_name: Optional[str] = None, extracted_date: Optional[str] = None,
                                 search_query: Optional[str] = None) -> Optional[Dict]:
        """Verify citation with Leagle legal database."""
        try:
            # Use provided search query or generate one
            if not search_query:
                search_query = citation_text
                if extracted_case_name:
                    search_query += f" {extracted_case_name}"
            
            # Leagle search URL
            search_url = f"https://www.leagle.com/search?query={quote(search_query)}"
            
            self._rate_limit('leagle.com')
            response = self.session.get(search_url, timeout=5)  # Reduced from 15 to 5 seconds
            
            if response.status_code == 200:
                content = response.text
                
                # Look for case links that contain our citation
                case_link_pattern = r'<a[^>]*href="([^"]*)"[^>]*>([^<]*)</a>'
                matches = re.findall(case_link_pattern, content, re.IGNORECASE)
                
                for link_url, link_text in matches:
                    # Check if this link contains our citation
                    if citation_text.replace(' ', '').lower() in link_text.replace(' ', '').lower():
                        # Found a matching case link
                        full_url = link_url if link_url.startswith('http') else f"https://www.leagle.com{link_url}"
                        
                        # Extract case name from link text
                        case_name = self._extract_case_name_from_link(link_text)
                        if not case_name and extracted_case_name:
                            case_name = extracted_case_name
                        
                        # Extract year
                        year = extracted_date or (citation_info.get('year') if citation_info else None)
                        if not year:
                            year_match = re.search(r'(\d{4})', link_text)
                            if year_match:
                                year = year_match.group(1)
                        
                        if case_name:
                            return {
                                'verified': True,
                                'source': 'leagle',
                                'canonical_name': case_name,
                                'canonical_date': year,
                                'url': full_url,
                                'confidence': 0.8
                            }
            
            return None
            
        except Exception as e:
            logger.warning(f"Leagle verification failed for {citation_text}: {e}")
            return None
    
    async def _verify_with_casemine(self, citation_text: str, citation_info: Dict,
                                   extracted_case_name: Optional[str] = None, extracted_date: Optional[str] = None,
                                   search_query: Optional[str] = None) -> Optional[Dict]:
        """Verify citation with CaseMine legal database."""
        try:
            # Use provided search query or generate one
            if not search_query:
                search_query = citation_text
                if extracted_case_name:
                    search_query += f" {extracted_case_name}"
            
            # CaseMine US search URL - target US courts specifically
            search_url = f"https://www.casemine.com/search/us?q={quote(search_query)}"
            
            self._rate_limit('casemine.com')
            response = self.session.get(search_url, timeout=5)  # Reduced from 15 to 5 seconds
            
            if response.status_code == 200:
                content = response.text
                logger.debug(f"CaseMine search response received, content length: {len(content)}")
                
                # Debug: Look for key indicators in the content
                if 'judgement' in content.lower():
                    logger.debug("Found 'judgement' in CaseMine response")
                if 'case-card' in content.lower():
                    logger.debug("Found 'case-card' in CaseMine response")
                if 'search-result' in content.lower():
                    logger.debug("Found 'search-result' in CaseMine response")
                
                # Look for CaseMine US case results - they have a specific structure
                # CaseMine search results typically show case cards with titles and citations
                
                # Pattern 1: Look for case title links in search results
                case_title_patterns = [
                    r'<a[^>]*href="([^"]*judgement/us/[^"]*)"[^>]*>([^<]*In re[^<]*)</a>',  # In re case links
                    r'<a[^>]*href="([^"]*judgement/us/[^"]*)"[^>]*>([^<]*v\.[^<]*)</a>',  # v. case links
                    r'<a[^>]*href="([^"]*judgement/us/[^"]*)"[^>]*>([^<]*[A-Z][a-z]+[^<]*)</a>',  # General case links
                ]
                
                # Pattern 2: Look for case cards/sections that contain our citation
                case_card_patterns = [
                    r'<div[^>]*class="[^"]*case-card[^"]*"[^>]*>.*?<a[^>]*href="([^"]*judgement/us/[^"]*)"[^>]*>([^<]*)</a>.*?</div>',
                    r'<div[^>]*class="[^"]*search-result[^"]*"[^>]*>.*?<a[^>]*href="([^"]*judgement/us/[^"]*)"[^>]*>([^<]*)</a>.*?</div>',
                ]
                
                matches = []
                
                # Try case title patterns first
                for pattern in case_title_patterns:
                    pattern_matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
                    if pattern_matches:
                        matches.extend(pattern_matches)
                
                # Try case card patterns if no title matches
                if not matches:
                    for pattern in case_card_patterns:
                        pattern_matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
                        if pattern_matches:
                            matches.extend(pattern_matches)
                
                # If still no matches, try to find any judgement links
                if not matches:
                    judgement_pattern = r'<a[^>]*href="([^"]*judgement/us/[^"]*)"[^>]*>([^<]*)</a>'
                    judgement_matches = re.findall(judgement_pattern, content, re.IGNORECASE)
                    matches.extend(judgement_matches)
                
                for link_url, link_text in matches:
                    # Check if this link contains our citation or case name
                    if (citation_text.replace(' ', '').lower() in link_text.replace(' ', '').lower() or
                        (extracted_case_name and extracted_case_name.lower() in link_text.lower())):
                        
                        # Found a matching case! Now get the full case details
                        full_url = link_url if link_url.startswith('http') else f"https://www.casemine.com{link_url}"
                        
                        # Extract case name from link text
                        case_name = self._extract_case_name_from_link(link_text)
                        if not case_name and extracted_case_name:
                            case_name = extracted_case_name
                        
                        # Extract year
                        year = extracted_date or (citation_info.get('year') if citation_info else None)
                        if not year:
                            year_match = re.search(r'(\d{4})', link_text)
                            if year_match:
                                year = year_match.group(1)
                        
                        if case_name:
                            logger.info(f"Found CaseMine case: {case_name} at {full_url}")
                            return {
                                'verified': True,
                                'source': 'casemine',
                                'canonical_name': case_name,
                                'canonical_date': year,
                                'url': full_url,
                                'confidence': 0.85
                            }
            
            return None
            
        except Exception as e:
            logger.warning(f"CaseMine verification failed for {citation_text}: {e}")
            return None
    
    async def _verify_with_google_scholar(self, citation_text: str, citation_info: Dict, 
                                         extracted_case_name: Optional[str] = None, extracted_date: Optional[str] = None,
                                         search_query: Optional[str] = None) -> Optional[Dict]:
        """Verify citation with Google Scholar using the courts endpoint for better legal results."""
        try:
            # Use provided search query or generate one
            if not search_query:
                search_query = citation_text
                if extracted_case_name:
                    search_query += f" {extracted_case_name}"
            
            # Google Scholar courts endpoint - much more reliable for legal research
            search_url = f"https://scholar.google.com/scholar_courts?hl=en&as_sdt=0,33&q={quote(search_query)}"
            
            self._rate_limit('scholar.google.com')
            response = self.session.get(search_url, timeout=5)  # Reduced from 15 to 5 seconds
            
            if response.status_code == 200:
                content = response.text
                
                # Look for case links and snippets that contain our citation
                case_link_pattern = r'<a[^>]*href="([^"]*)"[^>]*>([^<]*)</a>'
                matches = re.findall(case_link_pattern, content, re.IGNORECASE)
                
                # Also look for case name patterns in the content
                case_name_patterns = [
                    r'<h3[^>]*class="gs_rt"[^>]*>([^<]*)</h3>',  # Google Scholar result titles
                    r'<div[^>]*class="gs_a"[^>]*>([^<]*)</div>',  # Google Scholar author/date info
                    r'<span[^>]*class="gs_ct"[^>]*>([^<]*)</span>',  # Google Scholar citation info
                ]
                
                # Extract potential case names from various patterns
                potential_case_names = []
                for pattern in case_name_patterns:
                    name_matches = re.findall(pattern, content, re.IGNORECASE)
                    potential_case_names.extend(name_matches)
                
                # First, look for citations in the search result content (snippets, titles)
                # This is more reliable than just checking link text
                citation_patterns = [
                    r'(\d+\s+Wn\.?\s*2d\s+\d+)',  # Washington citations
                    r'(\d+\s+Wn\.?\s*3d\s+\d+)',  # Washington citations
                    r'(\d+\s+Wn\.?\s*App\.?\s*\d+)',  # Washington App citations
                    r'(\d+\s+P\.\s*3d\s+\d+)',  # Pacific Reporter citations
                    r'(\d+\s+P\.\s*2d\s+\d+)',  # Pacific Reporter citations
                ]
                
                # Look for our citation in the content
                for pattern in citation_patterns:
                    citation_matches = re.findall(pattern, content, re.IGNORECASE)
                    for match in citation_matches:
                        # Check if this citation matches our search citation
                        if citation_text.replace(' ', '').lower() in match.replace(' ', '').lower():
                            # Found our citation! Now extract case name and URL
                            logger.info(f"Found citation {match} in Google Scholar results for {citation_text}")
                            
                            # Look for case name in the same result section
                            # Find the result that contains this citation
                            for link_url, link_text in matches:
                                # Check if this link is near our citation in the content
                                if link_text and len(link_text.strip()) > 10:  # Valid link text
                                    # Extract case name from link text
                                    case_name = self._extract_case_name_from_link(link_text)
                                    if not case_name and extracted_case_name:
                                        case_name = extracted_case_name
                                    
                                    # Extract year
                                    year = extracted_date or (citation_info.get('year') if citation_info else None)
                                    if not year:
                                        year_match = re.search(r'(\d{4})', match)
                                        if year_match:
                                            year = year_match.group(1)
                                    
                                    # Try to extract the underlying URL from Google redirect
                                    underlying_url = URLDecoder.decode_google_redirect_url(link_url)
                                    if underlying_url:
                                        full_url = underlying_url
                                        logger.info(f"Extracted underlying URL from Google Scholar: {underlying_url}")
                                    else:
                                        full_url = link_url if link_url.startswith('http') else f"https://scholar.google.com{link_url}"
                                    
                                    if case_name:
                                        return {
                                            'verified': True,
                                            'source': 'google_scholar',
                                            'canonical_name': case_name,
                                            'canonical_date': year,
                                            'url': full_url,
                                            'confidence': 0.8
                                        }
                
                # Look for case links that contain our citation
                for link_url, link_text in matches:
                    # Check if this link contains our citation
                    if citation_text.replace(' ', '').lower() in link_text.replace(' ', '').lower():
                        # Found a matching case link
                        # Try to extract the underlying URL from Google redirect
                        underlying_url = URLDecoder.decode_google_redirect_url(link_url)
                        if underlying_url:
                            full_url = underlying_url
                            logger.info(f"Extracted underlying URL from Google Scholar: {underlying_url}")
                        else:
                            full_url = link_url if link_url.startswith('http') else f"https://scholar.google.com{link_url}"
                        
                        # Extract case name from link text
                        case_name = self._extract_case_name_from_link(link_text)
                        if not case_name and extracted_case_name:
                            case_name = extracted_case_name
                        
                        # Extract year
                        year = extracted_date or (citation_info.get('year') if citation_info else None)
                        if not year:
                            year_match = re.search(r'(\d{4})', link_text)
                            if year_match:
                                year = year_match.group(1)
                        
                        if case_name:
                            return {
                                'verified': True,
                                'source': 'google_scholar',
                                'canonical_name': case_name,
                                'canonical_date': year,
                                'url': full_url,
                                'confidence': 0.75
                            }
                
                # If no direct citation match found, look for case names in the content
                # that might be related to our citation
                if extracted_case_name and potential_case_names:
                    for potential_name in potential_case_names:
                        # Check if this potential case name is similar to our extracted name
                        if self._are_case_names_similar(potential_name, extracted_case_name):
                            # Found a similar case name, check if we can extract more info
                            year = extracted_date or (citation_info.get('year') if citation_info else None)
                            
                            # Look for a URL that might contain this case
                            for link_url, link_text in matches:
                                if potential_name.lower() in link_url.lower():
                                    # Try to extract the underlying URL from Google redirect
                                    underlying_url = URLDecoder.decode_google_redirect_url(link_url)
                                    if underlying_url:
                                        full_url = underlying_url
                                        logger.info(f"Extracted underlying URL from Google Scholar (fallback): {underlying_url}")
                                    else:
                                        full_url = link_url if link_url.startswith('http') else f"https://scholar.google.com{link_url}"
                                    return {
                                        'verified': True,
                                        'source': 'google_scholar',
                                        'canonical_name': potential_name,
                                        'canonical_date': year,
                                        'url': full_url,
                                        'confidence': 0.7
                                    }
            
            return None
            
        except Exception as e:
            logger.warning(f"Google Scholar verification failed for {citation_text}: {e}")
            return None
    
    def _verify_with_bing(self, search_query, citation_text, extracted_case_name, extracted_date, citation_info):
        """Verify citation using Bing search"""
        try:
            # Bing search URL
            search_url = f"https://www.bing.com/search?q={quote(search_query)}"
            logger.debug(f"Searching Bing with URL: {search_url}")
            
            self._rate_limit('bing.com')
            response = self.session.get(search_url, timeout=5)  # Reduced from 15 to 5 seconds
            
            if response.status_code == 200:
                content = response.text
                logger.debug(f"Bing response received, content length: {len(content)}")
                
                # Look for case links and snippets that contain our citation
                matches = []
                
                # Parse Bing search results structure
                # Look for b_algo elements which contain search results
                import re
                
                # Extract search result items (b_algo class)
                result_pattern = r'<li[^>]*class="[^"]*b_algo[^"]*"[^>]*>(.*?)</li>'
                results = re.findall(result_pattern, content, re.DOTALL | re.IGNORECASE)
                
                logger.debug(f"Found {len(results)} Bing search results")
                
                for i, result in enumerate(results[:5]):  # Check first 5 results
                    logger.debug(f"Processing Bing result {i+1}")
                    
                    # Extract title/link (h2 with a tag)
                    title_match = re.search(r'<h2[^>]*>(.*?)</h2>', result, re.DOTALL | re.IGNORECASE)
                    if title_match:
                        title_content = title_match.group(1)
                        # Extract link URL
                        link_match = re.search(r'href="([^"]+)"', title_content)
                        if link_match:
                            link_url = link_match.group(1)
                            # Extract link text
                            link_text_match = re.search(r'<a[^>]*>(.*?)</a>', title_content, re.DOTALL | re.IGNORECASE)
                            if link_text_match:
                                link_text = re.sub(r'<[^>]+>', '', link_text_match.group(1)).strip()
                                matches.append((link_url, link_text))
                                logger.debug(f"Found Bing result: {link_text} -> {link_url}")
                    
                    # Extract caption/snippet (b_caption class)
                    caption_match = re.search(r'<div[^>]*class="[^"]*b_caption[^"]*"[^>]*>(.*?)</div>', result, re.DOTALL | re.IGNORECASE)
                    if caption_match:
                        caption_content = caption_match.group(1)
                        # Clean HTML tags
                        caption_text = re.sub(r'<[^>]+>', '', caption_content).strip()
                        logger.debug(f"Bing caption: {caption_text}")
                        
                        # Check if caption contains our citation
                        if citation_text.replace(' ', '').lower() in caption_text.replace(' ', '').lower():
                            logger.info(f"Found citation {citation_text} in Bing caption: {caption_text}")
                            
                            # Try to extract case name from caption
                            case_name = self._extract_case_name_from_text(caption_text)
                            if not case_name and extracted_case_name:
                                case_name = extracted_case_name
                            
                            # Extract year from caption
                            year = extracted_date or (citation_info.get('year') if citation_info else None)
                            if not year:
                                year_match = re.search(r'(\d{4})', caption_text)
                                if year_match:
                                    year = year_match.group(1)
                            
                            # Get the URL from the first match
                            if matches:
                                full_url = matches[0][0]
                                # Try to extract underlying URL from Bing redirect
                                underlying_url = URLDecoder.decode_bing_url(full_url)
                                if underlying_url:
                                    full_url = underlying_url
                                    logger.info(f"Extracted underlying URL from Bing: {underlying_url}")
                                
                                if case_name:
                                    return {
                                        'verified': True,
                                        'source': 'bing',
                                        'canonical_name': case_name,
                                        'canonical_date': year,
                                        'url': full_url,
                                        'confidence': 0.75
                                    }
                
                # If no citation found in captions, check link text
                logger.debug(f"Checking {len(matches)} Bing result links for citation")
                for link_url, link_text in matches:
                    # Check if this link contains our citation
                    if citation_text.replace(' ', '').lower() in link_text.replace(' ', '').lower():
                        # Found a matching case link
                        # Try to extract the underlying URL from Bing redirect
                        underlying_url = URLDecoder.decode_bing_url(link_url)
                        if underlying_url:
                            full_url = underlying_url
                            logger.info(f"Extracted underlying URL from Bing: {underlying_url}")
                        else:
                            full_url = link_url if link_url.startswith('http') else f"https://www.bing.com{link_url}"
                        
                        # Extract case name from link text
                        case_name = self._extract_case_name_from_link(link_text)
                        if not case_name and extracted_case_name:
                            case_name = extracted_case_name
                        
                        # Extract year
                        year = extracted_date or (citation_info.get('year') if citation_info else None)
                        if not year:
                            year_match = re.search(r'(\d{4})', link_text)
                            if year_match:
                                year = year_match.group(1)
                        
                        if case_name:
                            return {
                                'verified': True,
                                'source': 'bing',
                                'canonical_name': case_name,
                                'canonical_date': year,
                                'url': full_url,
                                'confidence': 0.75
                            }
                
                logger.debug("No matching citations found in Bing results")
                return None
            else:
                logger.warning(f"Bing search failed with status code: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error during Bing verification: {str(e)}")
            return None
    
    async def _verify_with_duckduckgo(self, citation_text: str, citation_info: Dict,
                                     extracted_case_name: Optional[str] = None, extracted_date: Optional[str] = None,
                                     search_query: Optional[str] = None) -> Optional[Dict]:
        """Verify citation with DuckDuckGo search."""
        try:
            # Use provided search query or generate one
            if not search_query:
                search_query = citation_text
                if extracted_case_name:
                    search_query += f" {extracted_case_name}"
            
            # DuckDuckGo search URL
            search_url = f"https://duckduckgo.com/html/?q={quote(search_query)}"
            
            self._rate_limit('duckduckgo.com')
            response = self.session.get(search_url, timeout=5)  # Reduced from 15 to 5 seconds
            
            if response.status_code == 200:
                content = response.text
                
                # Look for case links and snippets that contain our citation
                case_link_pattern = r'<a[^>]*href="([^"]*)"[^>]*>([^<]*)</a>'
                matches = re.findall(case_link_pattern, content, re.IGNORECASE)
                
                # Also look for case name patterns in DuckDuckGo search results
                case_name_patterns = [
                    r'<h2[^>]*>([^<]*)</h2>',  # DuckDuckGo result titles
                    r'<a[^>]*class="result__title"[^>]*>([^<]*)</a>',  # DuckDuckGo result titles
                    r'<a[^>]*class="result__snippet"[^>]*>([^<]*)</a>',  # DuckDuckGo result snippets
                ]
                
                # Extract potential case names from various patterns
                potential_case_names = []
                for pattern in case_name_patterns:
                    name_matches = re.findall(pattern, content, re.IGNORECASE)
                    potential_case_names.extend(name_matches)
                
                # First, look for citations in the search result content (snippets, titles)
                # This is more reliable than just checking link text
                citation_patterns = [
                    r'(\d+\s+Wn\.?\s*2d\s+\d+)',  # Washington citations
                    r'(\d+\s+Wn\.?\s*3d\s+\d+)',  # Washington citations
                    r'(\d+\s+Wn\.?\s*App\.?\s*\d+)',  # Washington App citations
                    r'(\d+\s+P\.\s*3d\s+\d+)',  # Pacific Reporter citations
                    r'(\d+\s+P\.\s*2d\s+\d+)',  # Pacific Reporter citations
                ]
                
                # Look for our citation in the content
                for pattern in citation_patterns:
                    citation_matches = re.findall(pattern, content, re.IGNORECASE)
                    for match in citation_matches:
                        # Check if this citation matches our search citation
                        if citation_text.replace(' ', '').lower() in match.replace(' ', '').lower():
                            # Found our citation! Now extract case name and URL
                            logger.info(f"Found citation {match} in DuckDuckGo results for {citation_text}")
                            
                            # Look for case name in the same result section
                            # Find the result that contains this citation
                            for link_url, link_text in matches:
                                # Check if this link is near our citation in the content
                                if link_text and len(link_text.strip()) > 10:  # Valid link text
                                    # Extract case name from link text
                                    case_name = self._extract_case_name_from_link(link_text)
                                    if not case_name and extracted_case_name:
                                        case_name = extracted_case_name
                                    
                                    # Extract year
                                    year = extracted_date or (citation_info.get('year') if citation_info else None)
                                    if not year:
                                        year_match = re.search(r'(\d{4})', match)
                                        if year_match:
                                            year = year_match.group(1)
                                    
                                    # Try to extract the underlying URL from DuckDuckGo redirect
                                    underlying_url = URLDecoder.decode_duckduckgo_url(link_url)
                                    if underlying_url:
                                        full_url = underlying_url
                                        logger.info(f"Extracted underlying URL from DuckDuckGo: {underlying_url}")
                                    else:
                                        full_url = link_url if link_url.startswith('http') else f"https://duckduckgo.com{link_url}"
                                    
                                    if case_name:
                                        return {
                                            'verified': True,
                                            'source': 'duckduckgo',
                                            'canonical_name': case_name,
                                            'canonical_date': year,
                                            'url': full_url,
                                            'confidence': 0.8
                                        }
                
                # Look for case links that contain our citation
                for link_url, link_text in matches:
                    # Check if this link contains our citation
                    if citation_text.replace(' ', '').lower() in link_text.replace(' ', '').lower():
                        # Found a matching case link
                        # Try to extract the underlying URL from DuckDuckGo redirect
                        underlying_url = URLDecoder.decode_duckduckgo_url(link_url)
                        if underlying_url:
                            full_url = underlying_url
                            logger.info(f"Extracted underlying URL from DuckDuckGo: {underlying_url}")
                        else:
                            full_url = link_url if link_url.startswith('http') else f"https://duckduckgo.com{link_url}"
                        
                        # Extract case name from link text
                        case_name = self._extract_case_name_from_link(link_text)
                        if not case_name and extracted_case_name:
                            case_name = extracted_case_name
                        
                        # Extract year
                        year = extracted_date or (citation_info.get('year') if citation_info else None)
                        if not year:
                            year_match = re.search(r'(\d{4})', link_text)
                            if year_match:
                                year = year_match.group(1)
                        
                        if case_name:
                            return {
                                'verified': True,
                                'source': 'duckduckgo',
                                'canonical_name': case_name,
                                'canonical_date': year,
                                'url': full_url,
                                'confidence': 0.75
                            }
                
                # If no direct citation match found, look for case names in the content
                # that might be related to our citation
                if extracted_case_name and potential_case_names:
                    for potential_name in potential_case_names:
                        # Check if this potential case name is similar to our extracted name
                        if self._are_case_names_similar(potential_name, extracted_case_name):
                            # Found a similar case name, check if we can extract more info
                            year = extracted_date or (citation_info.get('year') if citation_info else None)
                            
                            # Look for a URL that might contain this case
                            for link_url, link_text in matches:
                                if potential_name.lower() in link_text.lower():
                                    # Try to extract the underlying URL from DuckDuckGo redirect
                                    underlying_url = URLDecoder.decode_duckduckgo_url(link_url)
                                    if underlying_url:
                                        full_url = underlying_url
                                        logger.info(f"Extracted underlying URL from DuckDuckGo (fallback): {underlying_url}")
                                    else:
                                        full_url = link_url if link_url.startswith('http') else f"https://duckduckgo.com{link_url}"
                                    return {
                                        'verified': True,
                                        'source': 'duckduckgo',
                                        'canonical_name': potential_name,
                                        'canonical_date': year,
                                        'url': full_url,
                                        'confidence': 0.7
                                    }
            
            return None
            
        except Exception as e:
            logger.warning(f"DuckDuckGo verification failed for {citation_text}: {e}")
            return None

    async def _verify_with_vlex(self, citation_text: str, citation_info: Dict,
                               extracted_case_name: Optional[str] = None, extracted_date: Optional[str] = None,
                               search_query: Optional[str] = None) -> Optional[Dict]:
        """Verify citation with vLex legal database."""
        try:
            # Use provided search query or generate one
            if not search_query:
                search_query = citation_text
                if extracted_case_name:
                    search_query += f" {extracted_case_name}"
            
            # vLex search URL - try multiple search endpoints
            search_urls = [
                f"https://vlex.com/search?q={quote(search_query)}",
                f"https://vlex.com/search?query={quote(search_query)}",
                f"https://vlex.com/search?search={quote(search_query)}"
            ]
            
            for search_url in search_urls:
                try:
                    self._rate_limit('vlex.com')
                    response = self.session.get(search_url, timeout=5)  # Reduced from 15 to 5 seconds
                    
                    if response.status_code == 200:
                        content = response.text
                        
                        # Look for case links that contain our citation
                        case_link_pattern = r'<a[^>]*href="([^"]*)"[^>]*>([^<]*)</a>'
                        matches = re.findall(case_link_pattern, content, re.IGNORECASE)
                        
                        for link_url, link_text in matches:
                            # Check if this link contains our citation
                            if citation_text.replace(' ', '').lower() in link_text.replace(' ', '').lower():
                                # Found a matching case link
                                full_url = link_url if link_url.startswith('http') else f"https://vlex.com{link_url}"
                                
                                # Extract case name from link text
                                case_name = self._extract_case_name_from_link(link_text)
                                if not case_name and extracted_case_name:
                                    case_name = extracted_case_name
                                
                                # Extract year
                                year = extracted_date or (citation_info.get('year') if citation_info else None)
                                if not year:
                                    year_match = re.search(r'(\d{4})', link_text)
                                    if year_match:
                                        year = year_match.group(1)
                                
                                if case_name:
                                    return {
                                        'verified': True,
                                        'source': 'vlex',
                                        'canonical_name': case_name,
                                        'canonical_date': year,
                                        'url': full_url,
                                        'confidence': 0.8
                                    }
                        
                        # If we get here, no matches found in this URL
                        continue
                        
                except Exception as e:
                    logger.debug(f"vLex search URL {search_url} failed: {e}")
                    continue
            
            return None
            
        except Exception as e:
            logger.warning(f"vLex verification failed for {citation_text}: {e}")
            return None
    
    def _extract_case_name_from_link(self, link_text: str) -> Optional[str]:
        """Extract case name from link text."""
        # Remove HTML tags and clean up
        clean_text = re.sub(r'<[^>]+>', '', link_text).strip()
        
        # Look for case name patterns
        case_patterns = [
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+v\.\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',  # Smith v. Jones
            r'(In\s+re\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',  # In re Smith
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+Petition\s+for\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',  # Smith Petition for Jones
        ]
        
        for pattern in case_patterns:
            match = re.search(pattern, clean_text)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _extract_case_name_from_text(self, text: str) -> Optional[str]:
        """Extract case name from text content."""
        if not text:
            return None
        
        # Remove HTML tags and clean up
        clean_text = re.sub(r'<[^>]+>', '', text).strip()
        
        # Look for case name patterns
        case_patterns = [
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+v\.\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',  # Smith v. Jones
            r'(In\s+re\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',  # In re Smith
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+Petition\s+for\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',  # Smith Petition for Jones
        ]
        
        for pattern in case_patterns:
            match = re.search(pattern, clean_text)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _are_case_names_similar(self, name1: str, name2: str) -> bool:
        """Check if two case names are similar."""
        if not name1 or not name2:
            return False
        
        # Clean and normalize names
        clean1 = re.sub(r'[^\w\s]', '', name1.lower()).strip()
        clean2 = re.sub(r'[^\w\s]', '', name2.lower()).strip()
        
        # Check exact match
        if clean1 == clean2:
            return True
        
        # Check if one name is contained in the other
        if clean1 in clean2 or clean2 in clean1:
            return True
        
        # Check word overlap (at least 2 words in common)
        words1 = set(clean1.split())
        words2 = set(clean2.split())
        common_words = words1.intersection(words2)
        
        # Filter out common words that don't indicate similarity
        common_words = {w for w in common_words if len(w) > 2 and w not in {'the', 'and', 'for', 'petition', 'in', 're'}}
        
        return len(common_words) >= 2

    async def _verify_with_descrybe(self, citation_text: str, citation_info: Dict[str, Any], 
                                   extracted_case_name: Optional[str], extracted_date: Optional[str], 
                                   search_query: str) -> Optional[Dict[str, Any]]:
        """Verify citation using Descrybe.ai legal database."""
        try:
            # Descrybe.ai search URL
            search_url = "https://descrybe.ai/search"
            
            # Prepare search parameters
            params = {
                'q': search_query,
                'type': 'cases'  # Focus on case law
            }
            
            # Make request to Descrybe.ai
            response = self.session.get(search_url, params=params, timeout=10)
            
            if response.status_code == 200:
                content = response.text
                logger.debug(f"Descrybe.ai search response received, content length: {len(content)}")
                
                # Look for case results in Descrybe.ai response
                # Descrybe.ai typically shows case cards with titles and citations
                case_patterns = [
                    r'<a[^>]*href="([^"]*)"[^>]*>([^<]*In re[^<]*)</a>',  # In re case links
                    r'<a[^>]*href="([^"]*)"[^>]*>([^<]*v\.[^<]*)</a>',  # v. case links
                    r'<a[^>]*href="([^"]*)"[^>]*>([^<]*[A-Z][a-z]+[^<]*)</a>',  # General case links
                ]
                
                matches = []
                for pattern in case_patterns:
                    pattern_matches = re.findall(pattern, content, re.IGNORECASE)
                    if pattern_matches:
                        matches.extend(pattern_matches)
                
                for link_url, link_text in matches:
                    # Check if this link contains our citation or case name
                    if (citation_text.replace(' ', '').lower() in link_text.replace(' ', '').lower() or
                        (extracted_case_name and extracted_case_name.lower() in link_text.lower())):
                        
                        # Found a matching case!
                        full_url = link_url if link_url.startswith('http') else f"https://descrybe.ai{link_url}"
                        
                        # Extract case name from link text
                        case_name = self._extract_case_name_from_link(link_text)
                        if not case_name and extracted_case_name:
                            case_name = extracted_case_name
                        
                        # Extract year
                        year = extracted_date or (citation_info.get('year') if citation_info else None)
                        if not year:
                            year_match = re.search(r'(\d{4})', link_text)
                            if year_match:
                                year = year_match.group(1)
                        
                        if case_name:
                            logger.info(f"Found Descrybe.ai case: {case_name} at {full_url}")
                            return {
                                'verified': True,
                                'source': 'descrybe',
                                'canonical_name': case_name,
                                'canonical_date': year,
                                'url': full_url,
                                'confidence': 0.85
                            }
            
            logger.debug(f"Descrybe.ai verification failed for {citation_text}")
            return None
            
        except Exception as e:
            logger.error(f"Descrybe.ai verification error for {citation_text}: {str(e)}")
            return None

    async def _verify_with_scrapingbee(self, citation_text: str, citation_info: Dict,
                                      extracted_case_name: Optional[str] = None, extracted_date: Optional[str] = None,
                                      search_query: Optional[str] = None) -> Optional[Dict]:
        """Verify citation using ScrapingBee API for reliable web scraping."""
        try:
            # Use provided search query or generate one
            if not search_query:
                search_query = citation_text
                if extracted_case_name:
                    search_query += f" {extracted_case_name}"
            
            # ScrapingBee API configuration
            api_key = os.getenv('SCRAPINGBEE_API_KEY')
            
            if not api_key:
                logger.warning("ScrapingBee API key not configured. Set SCRAPINGBEE_API_KEY in config/scrapingbee_config.py or environment variable")
                return None
            
            # Try multiple search engines through ScrapingBee
            search_urls = [
                f"https://www.google.com/search?q={quote(search_query)}",
                f"https://www.bing.com/search?q={quote(search_query)}",
                f"https://duckduckgo.com/?q={quote(search_query)}",
                f"https://law.justia.com/search?query={quote(search_query)}",
                f"https://caselaw.findlaw.com/search?query={quote(search_query)}",
                f"https://www.casemine.com/search/us?q={quote(search_query)}"
            ]
            
            for search_url in search_urls:
                try:
                    # ScrapingBee API call
                    scrapingbee_url = "https://app.scrapingbee.com/api/v1/"
                    params = {
                        'api_key': api_key,
                        'url': search_url,
                        'render_js': 'true',
                        'premium_proxy': 'true',
                        'country_code': 'us',
                        'wait': '3000'  # Wait 3 seconds for JavaScript to load
                    }
                    
                    self._rate_limit('scrapingbee.com')
                    response = self.session.get(scrapingbee_url, params=params, timeout=15)
                    
                    if response.status_code == 200:
                        content = response.text
                        
                        # Look for citations in the content
                        citation_patterns = [
                            r'(\d+\s+Wn\.?\s*2d\s+\d+)',  # Washington citations
                            r'(\d+\s+Wn\.?\s*3d\s+\d+)',  # Washington citations
                            r'(\d+\s+Wn\.?\s*App\.?\s*\d+)',  # Washington App citations
                            r'(\d+\s+P\.\s*3d\s+\d+)',  # Pacific Reporter citations
                            r'(\d+\s+P\.\s*2d\s+\d+)',  # Pacific Reporter citations
                        ]
                        
                        # Look for our citation in the content
                        for pattern in citation_patterns:
                            citation_matches = re.findall(pattern, content, re.IGNORECASE)
                            for match in citation_matches:
                                # Check if this citation matches our search citation
                                if citation_text.replace(' ', '').lower() in match.replace(' ', '').lower():
                                    # Found our citation! Now extract case name and URL
                                    logger.info(f"Found citation {match} in ScrapingBee results for {citation_text}")
                                    
                                    # Extract case name from various patterns
                                    case_name_patterns = [
                                        r'<h[1-6][^>]*>([^<]*In re[^<]*)</h[1-6]>',  # In re case titles
                                        r'<h[1-6][^>]*>([^<]*v\.[^<]*)</h[1-6]>',  # v. case titles
                                        r'<a[^>]*href="[^"]*"[^>]*>([^<]*In re[^<]*)</a>',  # In re case links
                                        r'<a[^>]*href="[^"]*"[^>]*>([^<]*v\.[^<]*)</a>',  # v. case links
                                    ]
                                    
                                    case_name = None
                                    for case_pattern in case_name_patterns:
                                        case_matches = re.findall(case_pattern, content, re.IGNORECASE)
                                        if case_matches:
                                            case_name = case_matches[0].strip()
                                            break
                                    
                                    if not case_name and extracted_case_name:
                                        case_name = extracted_case_name
                                    
                                    # Extract year
                                    year = extracted_date or (citation_info.get('year') if citation_info else None)
                                    if not year:
                                        year_match = re.search(r'(\d{4})', content)
                                        if year_match:
                                            year = year_match.group(1)
                                    
                                    # Determine source from URL
                                    source = 'scrapingbee'
                                    if 'google.com' in search_url:
                                        source = 'google'
                                    elif 'bing.com' in search_url:
                                        source = 'bing'
                                    elif 'duckduckgo.com' in search_url:
                                        source = 'duckduckgo'
                                    elif 'justia.com' in search_url:
                                        source = 'justia'
                                    elif 'findlaw.com' in search_url:
                                        source = 'findlaw'
                                    elif 'casemine.com' in search_url:
                                        source = 'casemine'
                                    
                                    return {
                                        'verified': True,
                                        'source': source,
                                        'canonical_name': case_name,
                                        'canonical_date': year,
                                        'url': search_url,
                                        'confidence': 0.85
                                    }
                    
                    # Add delay between requests
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.debug(f"ScrapingBee request failed for {search_url}: {e}")
                    continue
            
            return None
            
        except Exception as e:
            logger.warning(f"ScrapingBee verification failed for {citation_text}: {e}")
            return None

# Convenience function for easy integration
async def verify_citation_with_enhanced_fallback(citation_text: str, extracted_case_name: Optional[str] = None, extracted_date: Optional[str] = None) -> Dict:
    """
    Convenience function to verify a citation using the enhanced fallback verifier.
    
    Args:
        citation_text: The citation to verify
        extracted_case_name: Optional extracted case name
        extracted_date: Optional extracted date
        
    Returns:
        Dict with verification results
    """
    verifier = EnhancedFallbackVerifier()
    return await verifier.verify_citation(citation_text, extracted_case_name)

# Convenience function specifically for vlex verification
async def verify_citation_with_vlex(citation_text: str, extracted_case_name: Optional[str] = None, extracted_date: Optional[str] = None) -> Optional[Dict]:
    """
    Convenience function to verify a citation specifically using vLex.
    
    Args:
        citation_text: The citation to verify
        extracted_case_name: Optional extracted case name
        extracted_date: Optional extracted date
        
    Returns:
        Dict with verification results
    """
    verifier = EnhancedFallbackVerifier()
    return await verifier._verify_with_vlex(citation_text, {}, extracted_case_name, extracted_date, None)
