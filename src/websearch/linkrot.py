"""
Linkrot Detection Module
Advanced linkrot detection with recovery strategies.
"""

import logging
import re
import aiohttp
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, quote
from aiohttp import ClientTimeout

from .cache import CacheManager

logger = logging.getLogger(__name__)


class EnhancedLinkrotDetector:
    """Advanced linkrot detection with recovery strategies."""
    
    def __init__(self, cache_manager: CacheManager):
        self.cache = cache_manager
        self.recovery_strategies = [
            self._try_wayback_machine,
            self._try_alternative_domains,
            self._try_similar_urls,
        ]
    
    async def check_url_status(self, url: str) -> Dict[str, Any]:
        """Check URL accessibility with caching."""
        if not url:
            return {'status': 'invalid', 'accessible': False}
        
        # Check cache first
        cached_status = self.cache.get_url_status(url)
        if cached_status:
            return {
                'status': cached_status['status'],
                'accessible': cached_status['status'] == 'accessible',
                'status_code': cached_status['status_code'],
                'last_checked': cached_status['last_checked']
            }
        
        # Check URL accessibility
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
            
            async with aiohttp.ClientSession() as session:
                timeout = ClientTimeout(total=10)
                async with session.head(url, headers=headers, timeout=timeout, allow_redirects=True) as response:
                    if response.status < 400:
                        status = 'accessible'
                        accessible = True
                    elif response.status == 403:
                        status = 'paywall'
                        accessible = False
                    else:
                        status = 'linkrot'
                        accessible = False
                    
                    self.cache.set_url_status(url, status, response.status)
                    
                    return {
                        'status': status,
                        'accessible': accessible,
                        'status_code': response.status,
                        'last_checked': datetime.now()
                    }
        
        except Exception as e:
            status = 'linkrot'
            self.cache.set_url_status(url, status, None)
            
            return {
                'status': status,
                'accessible': False,
                'error': str(e),
                'last_checked': datetime.now()
            }
    
    async def recover_dead_link(self, url: str, metadata: Optional[Dict[str, Any]] = None) -> List[str]:
        """Attempt to recover a dead link using various strategies."""
        recovery_urls = []
        
        for strategy in self.recovery_strategies:
            try:
                recovered = await strategy(url, metadata)
                recovery_urls.extend(recovered)
            except Exception as e:
                logger.debug(f"Recovery strategy failed: {e}")
        
        return recovery_urls
    
    async def _try_wayback_machine(self, url: str, metadata: Optional[Dict[str, Any]] = None) -> List[str]:
        """Try to find the URL in Wayback Machine."""
        wayback_urls = []
        
        try:
            # Query Wayback Machine API
            api_url = f"http://archive.org/wayback/available?url={quote(url)}"
            
            async with aiohttp.ClientSession() as session:
                timeout = ClientTimeout(total=10)
                async with session.get(api_url, timeout=timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('archived_snapshots', {}).get('closest', {}).get('available'):
                            wayback_url = data['archived_snapshots']['closest']['url']
                            wayback_urls.append(wayback_url)
        
        except Exception as e:
            logger.debug(f"Wayback Machine lookup failed: {e}")
        
        return wayback_urls
    
    async def _try_alternative_domains(self, url: str, metadata: Optional[Dict[str, Any]] = None) -> List[str]:
        """Try alternative domains for the same content."""
        alternative_urls = []
        
        try:
            parsed = urlparse(url)
            path = parsed.path
            
            # Common domain alternatives
            domain_alternatives = {
                'caselaw.findlaw.com': ['findlaw.com', 'laws.findlaw.com'],
                'law.justia.com': ['justia.com', 'supreme.justia.com'],
                'www.leagle.com': ['leagle.com'],
                'casetext.com': ['www.casetext.com'],
            }
            
            original_domain = parsed.netloc
            if original_domain in domain_alternatives:
                for alt_domain in domain_alternatives[original_domain]:
                    alt_url = f"{parsed.scheme}://{alt_domain}{path}"
                    alternative_urls.append(alt_url)
        
        except Exception as e:
            logger.debug(f"Alternative domain generation failed: {e}")
        
        return alternative_urls
    
    async def _try_similar_urls(self, url: str, metadata: Optional[Dict[str, Any]] = None) -> List[str]:
        """Try to construct similar URLs based on metadata."""
        similar_urls = []
        
        if not metadata:
            return similar_urls
        
        try:
            # If we have case name and citation, try to construct URLs
            case_name = metadata.get('case_name', '')
            citation = metadata.get('citation', '')
            
            if case_name and citation:
                # Try different URL patterns
                case_slug = re.sub(r'[^a-z0-9]+', '-', case_name.lower()).strip('-')
                citation_slug = re.sub(r'[^a-z0-9]+', '-', citation.lower()).strip('-')
                
                url_patterns = [
                    f"https://law.justia.com/cases/{case_slug}",
                    f"https://caselaw.findlaw.com/case/{case_slug}",
                    f"https://www.leagle.com/decision/{citation_slug}",
                    f"https://casetext.com/case/{case_slug}",
                ]
                
                similar_urls.extend(url_patterns)
        
        except Exception as e:
            logger.debug(f"Similar URL generation failed: {e}")
        
        return similar_urls 