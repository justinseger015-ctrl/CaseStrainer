import os
from src.config import DEFAULT_REQUEST_TIMEOUT, COURTLISTENER_TIMEOUT, CASEMINE_TIMEOUT, WEBSEARCH_TIMEOUT, SCRAPINGBEE_TIMEOUT

import requests
import logging
import sys
import json

try:
    from src.name_similarity_matcher import select_best_courtlistener_result, calculate_case_name_similarity
except ImportError:
    from name_similarity_matcher import select_best_courtlistener_result, calculate_case_name_similarity

logger = logging.getLogger(__name__)

def select_best_cluster_from_result(result, extracted_case_name, debug=False):
    """Select the best cluster from a CourtListener result based on name similarity."""
    clusters = result.get('clusters', [])
    
    if not clusters:
        return None
    
    if len(clusters) == 1:
        if debug:
            return clusters[0]
    
    if not extracted_case_name:
        if debug:
            return clusters[0]
    
    best_cluster = None
    best_similarity = 0.0
    
    if True:

    
        pass  # Empty block

    
    
        pass  # Empty block

    
    
        pass  # Debug logging can be added here if needed

    
    
    for i, cluster in enumerate(clusters):
        case_name = cluster.get('case_name', '')
        
        if not case_name:
            if debug:
            continue
        
        similarity = calculate_case_name_similarity(extracted_case_name, case_name)
        
        if True:

        
            pass  # Empty block

        
        
            pass  # Empty block

        
        
            pass  # Debug logging can be added here if needed

        
        
        if similarity > best_similarity:
            best_similarity = similarity
            best_cluster = cluster
    
    similarity_threshold = 0.3
    
    if best_cluster and best_similarity >= similarity_threshold:
        if debug:
            return best_cluster
    else:
        if debug:
            return clusters[0]

def verify_citations_with_courtlistener_batch(courtlistener_api_key, citations, text):
    """DEPRECATED: Batch verification is no longer used.
    
    This function has been replaced by individual verification with name similarity matching.
    Use verify_with_courtlistener() for individual citations instead.
    This function will be removed in a future version.
    """
    import warnings
    warnings.warn(
        "verify_citations_with_courtlistener_batch is deprecated. Use individual verification instead.",
        DeprecationWarning,
        stacklevel=2
    )
    if not courtlistener_api_key:
        logger.warning("[CL batch] No API key available")
        return
    if not citations:
        return
    logger.info(f"[CL batch] Verifying {len(citations)} citations with text length: {len(text)}")
    try:
        citations_to_verify = [citation.citation for citation in citations]
        url = "https://www.courtlistener.com/api/rest/v4/citation-lookup/"
        headers = {
            'Authorization': f'Token {courtlistener_api_key}',
            'Content-Type': 'application/json'
        }
        data = {
            'text': ' '.join(citations_to_verify)
        }
        response = requests.post(url, headers=headers, json=data, timeout=WEBSEARCH_TIMEOUT)
        logger.info(f"[CL batch] API response status: {response.status_code}")
        return response
    except Exception as e:
        logger.error(f"[CL batch] Exception: {e}")
        return None

def verify_with_courtlistener(courtlistener_api_key, citation, extracted_case_name=None):
    """
    Verify a citation with CourtListener using enhanced cross-validation system.
    This replaces the previous two-step verification with a more robust approach.
    """
    
    
    try:
        from src.enhanced_courtlistener_verification import verify_with_courtlistener_enhanced
        
        result = verify_with_courtlistener_enhanced(courtlistener_api_key, citation, extracted_case_name)
        
        return result
        
    except ImportError as e:
        
        return _verify_with_courtlistener_basic(courtlistener_api_key, citation, extracted_case_name)

def _verify_with_courtlistener_basic(courtlistener_api_key, citation, extracted_case_name=None):
    """Two-step CourtListener verification with strict validation requiring both canonical name and year"""
    result = {
        "canonical_name": None,
        "canonical_date": None,
        "url": None,
        "verified": False,
        "source": None
    }
    
    if not courtlistener_api_key:
        return result
    
    headers = {"Authorization": f"Token {courtlistener_api_key}"}
    
    try:
        lookup_url = "https://www.courtlistener.com/api/rest/v4/citation-lookup/"
        lookup_data = {"text": citation}
        
        response = requests.post(lookup_url, headers=headers, json=lookup_data, timeout=WEBSEARCH_TIMEOUT)
        
        if response.status_code == 200:
            try:
                api_results = response.json()
                result['raw'] = response.text
                
                found_results = [r for r in api_results if r.get('status') != 404 and r.get('clusters')]
                
                if True:

                
                    pass  # Empty block

                
                
                    pass  # Empty block

                
                
                    needs_similarity_matching = False
                    total_clusters = 0
                    
                    for api_result in found_results:
                        clusters = api_result.get('clusters', [])
                        total_clusters += len(clusters)
                    
                    needs_similarity_matching = extracted_case_name and (len(found_results) > 1 or total_clusters > 1)
                    
                    if needs_similarity_matching:
                        if len(found_results) > 1:
                            best_result = select_best_courtlistener_result(
                                found_results, 
                                extracted_case_name or "", 
                                debug=os.getenv("FLASK_DEBUG", "False").lower() == "true"
                            )
                            cluster = best_result['clusters'][0] if best_result and best_result.get('clusters') else None
                        else:
                            best_result = found_results[0]
                            cluster = select_best_cluster_from_result(
                                best_result,
                                extracted_case_name,
                                debug=os.getenv("FLASK_DEBUG", "False").lower() == "true"
                            )
                    else:
                        best_result = found_results[0]
                        cluster = best_result['clusters'][0] if best_result.get('clusters') else None
                    
                    if cluster:
                        case_name = cluster.get("case_name")
                        date_filed = cluster.get("date_filed")
                        absolute_url = cluster.get("absolute_url")
                        
                        if case_name and date_filed and absolute_url:
                            result.update({
                                "canonical_name": case_name,
                                "canonical_date": date_filed,
                                "url": absolute_url,
                                "verified": True,
                                "source": "CourtListener"
                            })
                            return result
                        else:
                
                
            except (KeyError, IndexError) as e:
                
        elif response.status_code == 404:
        else:
            
    except Exception as e:
        
    try:
        search_url = "https://www.courtlistener.com/api/rest/v4/search/"
        search_params = {
            "type": "opinion",
            "q": f'citation:"{citation}"',
            "format": "json",
            "order_by": "score desc",
            "limit": 1
        }
        
        response = requests.get(search_url, headers=headers, params=search_params, timeout=WEBSEARCH_TIMEOUT)
        
        if response.status_code == 200:
            try:
                search_results = response.json()
                
                if search_results.get('results'):
                    best_result = search_results['results'][0]
                    case_name = best_result.get("case_name")
                    date_filed = best_result.get("date_filed")
                    
                    if case_name and date_filed:
                        result.update({
                            "canonical_name": case_name,
                            "canonical_date": date_filed,
                            "url": absolute_url,
                            "verified": True,
                            "source": "CourtListener"
                        })
                        return result
                    else:
                else:
                        
            except json.JSONDecodeError as e:
                logger.error(f"[CL search] {citation} JSON decode error: {e}")
        else:
            
    except Exception as e:
        logger.error(f"[CL search] {citation} exception: {e}")
    
    return result 