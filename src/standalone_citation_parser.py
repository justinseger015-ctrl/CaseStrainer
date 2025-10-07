"""
Standalone Citation Parser
A simple citation parser that doesn't depend on other modules to avoid circular imports.
"""

import re
from src.config import DEFAULT_REQUEST_TIMEOUT, COURTLISTENER_TIMEOUT, CASEMINE_TIMEOUT, WEBSEARCH_TIMEOUT, SCRAPINGBEE_TIMEOUT

import logging
from typing import Dict, Optional, Any
import warnings

logger = logging.getLogger(__name__)

class CitationParser:
    """
    Simple citation parser for extracting case names and dates from text.
    """
    
    def __init__(self):
        # Enhanced patterns with better boundary detection and sentence-start handling
        self.case_name_patterns = [
            # Sentence-start patterns (highest priority) - captures cases at beginning of sentences
            r"(?:^|[.!?]\s+)([A-Z][A-Za-z&\s,\.\'\-]{1,120}?\s+v\.?\s+[A-Z][A-Za-z&\s,\.\'\-]{1,120}?)(?=\s*[,;:.]|\s*\d+\s+[A-Z]|\s*\(|\s*$)",
            r"(?:^|[.!?]\s+)([A-Z][A-Za-z&\s,\.\'\-]{1,120}?\s+vs\.?\s+[A-Z][A-Za-z&\s,\.\'\-]{1,120}?)(?=\s*[,;:.]|\s*\d+\s+[A-Z]|\s*\(|\s*$)",
            
            # Standard patterns with improved boundaries
            r"([A-Z][A-Za-z&\s,\.\'\-]{1,120}?\s+v\.?\s+[A-Z][A-Za-z&\s,\.\'\-]{1,120}?)(?=\s*[,;:.]|\s*\d+\s+[A-Z]|\s*\(|\s*$)",
            r"([A-Z][A-Za-z&\s,\.\'\-]{1,120}?\s+vs\.?\s+[A-Z][A-Za-z&\s,\.\'\-]{1,120}?)(?=\s*[,;:.]|\s*\d+\s+[A-Z]|\s*\(|\s*$)",
            r"([A-Z][A-Za-z&\s,\.\'\-]{1,120}?\s+versus\s+[A-Z][A-Za-z&\s,\.\'\-]{1,120}?)(?=\s*[,;:.]|\s*\d+\s+[A-Z]|\s*\(|\s*$)",
            
            # Special case patterns (government, estate, etc.)
            r"(Dep't\s+of\s+[A-Za-z&\s,\.\'\-]{1,120}?\s+v\.?\s+[A-Za-z&\s,\.\'\-]{1,120}?)(?=\s*[,;:.]|\s*\d+\s+[A-Z]|\s*\(|\s*$)",
            r"(Department\s+of\s+[A-Za-z&\s,\.\'\-]{1,120}?\s+v\.?\s+[A-Za-z&\s,\.\'\-]{1,120}?)(?=\s*[,;:.]|\s*\d+\s+[A-Z]|\s*\(|\s*$)",
            r"(In\s+re\s+(?:Marriage\s+of\s+)?[A-Za-z&\s,\.\'\-]{1,120}?)(?=\s*[,;:.]|\s*\d+\s+[A-Z]|\s*\(|\s*$)",
            r"(Estate\s+of\s+[A-Za-z&\s,\.\'\-]{1,120}?)(?=\s*[,;:.]|\s*\d+\s+[A-Z]|\s*\(|\s*$)",
            r"(Matter\s+of\s+[A-Za-z&\s,\.\'\-]{1,120}?)(?=\s*[,;:.]|\s*\d+\s+[A-Z]|\s*\(|\s*$)",
            
            # Criminal/government patterns
            r"(State\s+(?:of\s+)?[A-Z][a-z]+\s+v\.?\s+[A-Za-z&\s,\.\'\-]{1,120}?)(?=\s*[,;:.]|\s*\d+\s+[A-Z]|\s*\(|\s*$)",
            r"(People\s+(?:of\s+(?:the\s+)?State\s+of\s+)?[A-Z][a-z]+\s+v\.?\s+[A-Za-z&\s,\.\'\-]{1,120}?)(?=\s*[,;:.]|\s*\d+\s+[A-Z]|\s*\(|\s*$)",
            r"(United\s+States\s+v\.?\s+[A-Za-z&\s,\.\'\-]{1,120}?)(?=\s*[,;:.]|\s*\d+\s+[A-Z]|\s*\(|\s*$)",
            r"(Commonwealth\s+(?:of\s+)?[A-Z][a-z]+\s+v\.?\s+[A-Za-z&\s,\.\'\-]{1,120}?)(?=\s*[,;:.]|\s*\d+\s+[A-Z]|\s*\(|\s*$)",
            
            # Ex rel pattern
            r"([A-Z][A-Za-z&\s,\.\'\-]+?\s+ex\s+rel\.?\s+[A-Za-z&\s,\.\'\-]+?)(?=\s*[,;:.]|\s*\d+\s+[A-Z]|\s*\(|\s*$)",
            
            # Fallback patterns (lower priority)
            r"([A-Z][A-Za-z&\s,\.\'\-]{1,120}?\s+v\.?\s+[A-Z][A-Za-z&\s,\.\'\-]{1,120}?)(?=\s*[,;:.])",
        ]
        
        self.date_patterns = [
            r'\((\d{4})\)',  # (2020) - most common format
            r'\((\d{4})\s*\)',  # (2020 ) - with trailing space
            r'\(\s*(\d{4})\s*\)',  # ( 2020 ) - with spaces
            r'\b(\d{4})\b',  # 2020 - standalone year
            r'(?:decided|filed|issued|released|argued|submitted)\s+(?:in\s+)?(\d{4})\b',
            r'\b(19|20)\d{2}\b',  # Simple year pattern
        ]
    
    def extract_from_text(self, text: str, citation: str) -> Dict[str, Any]:
        """
        Extract case name and date from text using citation as context.
        Now more robust: captures all text from the start of the case name up to the volume number of the citation.
        """
        import logging
        logger = logging.getLogger("case_name_extraction")
        try:
            result = {
                'case_name': None,
                'year': None,
                'full_citation_found': False,
                'extraction_method': 'standalone_parser'
            }

            citation_index = text.find(citation)
            matched_citation = citation
            if citation_index == -1:
                citation_escaped = re.escape(citation)
                citation_no_year = re.sub(r'\s*\(?\d{4}\)?$', '', citation)
                citation_no_year_escaped = re.escape(citation_no_year.strip())
                pattern = rf'({citation_no_year_escaped})(?:\s*[\(,]\s*(\d{{4}})[\)]?)?'
                match = re.search(pattern, text)
                logger.info(f"[DEBUG] Regex citation search pattern: {pattern}")
                if match:
                    citation_index = match.start(1)
                    matched_citation = match.group(0)
                    if match.lastindex and match.lastindex >= 2 and match.group(2):
                        result['year'] = match.group(2)
                        logger.info(f"[DEBUG] Year found in regex match: {match.group(2)}")
                else:
                    logger.warning(f"[DEBUG] Citation not found by regex in text: '{citation}'")

            if citation_index == -1:
                logger.warning(f"[DEBUG] Citation not found in text: '{citation}'")
                return result

            result['full_citation_found'] = True
            result['matched_citation'] = matched_citation

            # Enhanced context extraction with better sentence boundary detection
            context_start = max(0, citation_index - 800)  # Expanded from 500 to 800 for better coverage
            context_before = text[context_start:citation_index]
            
            # More comprehensive citation patterns to avoid contamination
            citation_patterns = [
                r'\b\d+\s+[A-Za-z.]+(?:\s+\d+)?\s*(?:\(?\d{4}\)?)?',  # Full citation with optional year
                r'\b\d+\s+(?:Wash\.|Wn\.|P\.|A\.|S\.|N\.|F\.|U\.S\.|Cal\.|N\.Y\.)\s*\d+[a-z]*',  # Reporter with page
                r'\b\d+\s+(?:Wash\.|Wn\.|P\.|A\.|S\.|N\.|F\.|U\.S\.)\b',  # Common reporters
            ]
            
            # Find the last citation before our target citation to establish clean boundary
            last_citation_pos = 0
            for pattern in citation_patterns:
                matches = list(re.finditer(pattern, context_before))
                for match in matches:
                    if match.end() < (citation_index - context_start):
                        last_citation_pos = max(last_citation_pos, match.end())
            
            # If we found a previous citation, find the next sentence boundary after it
            if last_citation_pos > 0:
                # If the previous citation is close (within 150 chars), find sentence boundary
                if (citation_index - context_start) - last_citation_pos < 150:
                    # Enhanced sentence boundary detection (period, exclamation, question mark followed by capital)
                    sentence_pattern = re.compile(r'[.!?]\s+(?=[A-Z])')
                    sentence_matches = list(sentence_pattern.finditer(context_before, last_citation_pos))
                    if sentence_matches:
                        # Start from first sentence after previous citation
                        adjusted_start = context_start + sentence_matches[0].end()
                        context_start = max(context_start, adjusted_start)
                        logger.info(f"[DEBUG] Adjusted context start to sentence boundary after previous citation")
                    else:
                        # No sentence boundary found, use position after citation with buffer
                        context_start = max(context_start, context_start + last_citation_pos + 2)
                        logger.info(f"[DEBUG] No sentence boundary after previous citation, using position after citation")
            
            context_before = text[context_start:citation_index]

            logger.info(f"[DEBUG] Citation: '{citation}'")
            logger.info(f"[DEBUG] Context before citation (len={len(context_before)}): ...{context_before[-200:]}\n")

            last_case_name = None
            last_match_end = None
            
            for pattern in self.case_name_patterns:
                matches = list(re.finditer(pattern, context_before, re.IGNORECASE))
                logger.info(f"[DEBUG] Trying case name pattern: {pattern}")
                if matches:
                    logger.info(f"[DEBUG] {len(matches)} matches found for pattern: {pattern}")
                    for m in matches:
                        logger.info(f"[DEBUG]   Match: '{m.group(1)}'")
                    match = matches[-1]
                    candidate = match.group(1).strip()
                    candidate = re.sub(r',[\s]*$', '', candidate)
                    if self._is_valid_case_name(candidate):
                        last_case_name = candidate
                        last_match_end = match.end(1)
                        logger.info(f"[DEBUG] Valid case name candidate: '{candidate}'")
                        break  # Found a valid case name, stop searching
                    else:
                        logger.info(f"[DEBUG] Invalid case name candidate: '{candidate}'")
                else:
                    logger.info(f"[DEBUG] No matches for pattern: {pattern}")
            
            if not last_case_name:
                logger.info(f"[DEBUG] No valid case name found with patterns, trying to find actual case name start")
                comma_pos = context_before.rfind(',')
                if comma_pos != -1:
                    # until we find a non-stopword that starts with a lowercase letter
                    STOPWORDS = {"of", "and", "the", "in", "for", "on", "at", "by", "with", "to", "from", "as", "but", "or", "nor", "so", "yet", "a", "an", "re", "see", "held", "accord", "cf", "eg", "ie", "questions", "law", "review", "statute", "meaning", "certified", "also", "federal", "court", "may", "ask", "this", "necessary", "resolve", "case", "before", "washington", "when", "resolution"}
                    
                    LEGAL_ABBREVIATIONS = {"v", "vs", "versus", "ex", "rel", "in", "re", "estate", "matter"}
                    
                    case_start = comma_pos
                    for i in range(comma_pos - 1, max(0, comma_pos - 300), -1):
                        if i > 0 and context_before[i] in ' \t\n':
                            if i + 1 < len(context_before):
                                word_end = i + 1
                                while word_end < len(context_before) and context_before[word_end] not in ' \t\n,;':
                                    word_end += 1
                                word = context_before[i+1:word_end].strip()
                                
                                if (word and word[0].islower() and 
                                    word.lower() not in STOPWORDS and 
                                    word.lower() not in LEGAL_ABBREVIATIONS and
                                    len(word) > 2):  # Exclude very short words like "v."
                                    case_start = word_end
                                    logger.info(f"[DEBUG] Found case name boundary at word: '{word}', case starts at position {case_start}")
                                    break
                    
                    case_name = context_before[case_start:comma_pos].strip()
                    case_name = re.sub(r'[,\s]+$', '', case_name)
                    
                    if case_name and self._is_valid_case_name(case_name):
                        last_case_name = case_name
                        last_match_end = comma_pos
                        logger.info(f"[DEBUG] Found case name by backwards search: '{case_name}'")
                    else:
                        logger.info(f"[DEBUG] Backwards search found invalid case name: '{case_name}'")
                        logger.info(f"[DEBUG] Trying alternative approach: looking for 'word v. word' pattern")
                        v_pattern = r'([A-Z][A-Za-z&\s,\.\'\-]*?\s+v\.\s+[A-Z][A-Za-z&\s,\.\'\-]*?)(?=\s*,)'
                        v_matches = list(re.finditer(v_pattern, context_before))
                        if v_matches:
                            last_v_match = v_matches[-1]
                            potential_case_name = last_v_match.group(1).strip()
                            if self._is_valid_case_name(potential_case_name):
                                last_case_name = potential_case_name
                                last_match_end = comma_pos
                                logger.info(f"[DEBUG] Found case name by v. pattern: '{potential_case_name}'")
                        else:
                            logger.info(f"[DEBUG] Final fallback: looking for any 'v.' pattern")
                            sentences = re.split(r'[.!?]', context_before)
                            for sentence in reversed(sentences):
                                if 'v.' in sentence:
                                    v_matches = list(re.finditer(r'([A-Z][A-Za-z&\s,\.\'\-]*?\s+v\.\s+[A-Z][A-Za-z&\s,\.\'\-]*?)', sentence))
                                    if v_matches:
                                        potential_case_name = v_matches[-1].group(1).strip()
                                        if self._is_valid_case_name(potential_case_name):
                                            last_case_name = potential_case_name
                                            last_match_end = comma_pos
                                            logger.info(f"[DEBUG] Found case name by sentence fallback: '{potential_case_name}'")
                                            break
            if last_case_name and last_match_end is not None:
                suffixes = [
                    ', LLC', ', L.L.C.', ', LLP', ', L.L.P.', ', Inc.', ', Incorporated', ', Ltd.', ', Co.', ', Corp.', ', Corporation', ', P.C.', ', P.A.', ', S.C.', ', N.A.', ', PLC', ', PC', ', LP', ', LLLP', ', PLLC', ', P.L.L.C.'
                ]
                trailing = context_before[last_match_end:]
                suffix_pattern = r'(,\s*(?:LLC|L\.L\.C\.|LLP|L\.L\.P\.|Inc\.|Incorporated|Ltd\.|Co\.|Corp\.|Corporation|P\.C\.|P\.A\.|S\.C\.|N\.A\.|PLC|PC|LP|LLLP|PLLC|P\.L\.L\.C\.))'
                matches = list(re.finditer(suffix_pattern, trailing, re.IGNORECASE))
                if matches:
                    logger.info(f"[DEBUG] Appending business suffixes to case name: {last_case_name}")
                    for m in matches:
                        logger.info(f"[DEBUG]   Suffix found: '{m.group(1)}'")
                        last_case_name += m.group(1)
            if last_case_name:
                result['case_name'] = last_case_name
                logger.info(f"[DEBUG] Final extracted case name: '{last_case_name}'")
            else:
                logger.warning(f"[DEBUG] No valid case name found before citation: '{citation}'")

            if not result['year']:
                context_after_start = citation_index + len(matched_citation)
                context_after = text[context_after_start:context_after_start + 100]
                year = self._extract_year_from_context(context_before, matched_citation, context_after)
                if year:
                    result['year'] = year
                    logger.info(f"[DEBUG] Year extracted from context: {year}")
                else:
                    logger.warning(f"[DEBUG] No year found in context for citation: '{citation}'")

            if not result['case_name']:
                full_citation = self.find_full_citation_in_text(text, citation)
                if full_citation:
                    fallback_case_name = self.find_case_name_before_citation(text, full_citation)
                    if fallback_case_name and self._is_valid_case_name(fallback_case_name):
                        result['case_name'] = fallback_case_name
                        result['extraction_method'] = 'fallback_case_name_before_citation'
                        logger.info(f"[DEBUG] Fallback case name extraction succeeded: '{fallback_case_name}'")
                    else:
                        logger.warning(f"[DEBUG] Fallback case name extraction failed for citation: '{citation}'")
                else:
                    logger.warning(f"[DEBUG] Full citation not found for fallback extraction: '{citation}'")

            return result

        except Exception as e:
            logger.error(f"Error in extract_from_text: {e}")
            return {
                'case_name': None,
                'year': None,
                'full_citation_found': False,
                'extraction_method': f'error: {str(e)}'
            }
    
    def _extract_case_name_from_context(self, context: str) -> Optional[str]:
        """Extract case name from context."""
        try:
            recent_context = context[-150:] if len(context) > 150 else context

            for pattern in self.case_name_patterns:
                matches = list(re.finditer(pattern, recent_context, re.IGNORECASE))
                if matches:
                    match = matches[-1]
                    case_name = self._clean_case_name(match.group(1))
                    case_name = self._extract_just_case_name(case_name)
                    if self._is_valid_case_name(case_name):
                        return case_name
            return None
        except Exception as e:
            logger.warning(f"Error extracting case name from context: {e}")
            return None
    
    def _extract_just_case_name(self, text: str) -> str:
        """Extract just the case name from potentially longer text."""
        case_patterns = [
            r'([A-Za-z\s,\.\'-]+?\s+v\.\s+[A-Za-z\s,\.\'-]+?)(?=\s*[,;]|\s*\d+\s+[A-Z]|\s*\(|\s*$)',
            r'([A-Za-z\s,\.\'-]+?\s+v\.\s+[A-Za-z\s,\.\'-]+?)(?=\s*[,;])',
            r'([A-Za-z\s,\.\'-]+?\s+v\.\s+[A-Za-z\s,\.\'-]+?)',
            r'(Dep\'t\s+of\s+[A-Za-z\s,\.\'-]+?\s+v\.\s+[A-Za-z\s,\.\'-]+?)(?=\s*[,;]|\s*\d+\s+[A-Z]|\s*\(|\s*$)',
            r'(Dep\'t\s+of\s+[A-Za-z\s,\.\'-]+?\s+v\.\s+[A-Za-z\s,\.\'-]+?)',
        ]
        
        for pattern in case_patterns:
            matches = list(re.finditer(pattern, text, re.IGNORECASE))
            if matches:
                match = matches[-1]
                return self._clean_case_name(match.group(1))
        
        return text
    
    def _extract_year_from_context(self, context_before: str, citation: str, context_after: Optional[str] = None) -> Optional[str]:
        """Extract year from context before citation, after citation, or citation itself (DEPRECATED: use isolation-aware logic instead)."""
        warnings.warn(
            "_extract_year_from_context is deprecated. Use isolation-aware extraction instead.",
            DeprecationWarning,
            stacklevel=2
        )
        try:
            for pattern in self.date_patterns:
                matches = re.findall(pattern, citation)
                if matches:
                    year = matches[0]
                    if year and self._is_valid_year(year):
                        return year
            
            if context_after:
                for pattern in self.date_patterns:
                    matches = re.findall(pattern, context_after)
                    if matches:
                        year = matches[0]
                        if year and self._is_valid_year(year):
                            return year
            
            for pattern in self.date_patterns:
                matches = re.findall(pattern, context_before)
                if matches:
                    year = matches[-1]
                    if year and self._is_valid_year(year):
                        return year
            
            return None
            
        except Exception as e:
            logger.warning(f"Error extracting year from context: {e}")
            return None
    
    def _clean_case_name(self, case_name: str) -> str:
        """Clean and normalize case name while preserving full names."""
        if not case_name:
            return ""
        
        case_name = case_name.strip()
        
        leading_patterns = [
            r'^.*?\b(held|in|that|the|principle|applies)\s+',
            r'^.*?\b(court|held|in)\s+',
            r'^.*?\b(federal|court|may|ask|this)\s+',
        ]
        
        for pattern in leading_patterns:
            case_name = re.sub(pattern, '', case_name, flags=re.IGNORECASE)
        
        case_name = re.sub(r'[,\s]*$', '', case_name)
        case_name = re.sub(r'[.;:]$', '', case_name)
        
        case_name = re.sub(r'\s+', ' ', case_name)
        
        if case_name.endswith(', LLC') or case_name.endswith(', Inc.') or case_name.endswith(', Corp.'):
            pass
        else:
            case_name = re.sub(r',\s*$', '', case_name)
            case_name = re.sub(r'\.\s*$', '', case_name)
        
        return case_name.strip()
    
    def _is_valid_case_name(self, case_name: str) -> bool:
        """
        Enhanced validation to filter out false positives.
        Returns True if the case name appears legitimate.
        """
        if not case_name or len(case_name.strip()) < 5:
            logger.debug(f"[VALIDATION] Rejected: too short - '{case_name}'")
            return False
        
        case_name = case_name.strip()
        
        # Must contain v. or vs. or versus or "In re" or similar legal indicators
        legal_indicators = [
            r'\bv\.?\s+',
            r'\bvs\.?\s+',
            r'\bversus\s+',
            r'^In\s+re\s+',
            r'^Matter\s+of\s+',
            r'^Estate\s+of\s+'
        ]
        has_indicator = any(re.search(pattern, case_name, re.IGNORECASE) for pattern in legal_indicators)
        if not has_indicator:
            logger.debug(f"[VALIDATION] Rejected: no legal indicator - '{case_name}'")
            return False
        
        # Must start with capital letter or "In"
        if not (case_name[0].isupper() or case_name.startswith('In ')):
            logger.debug(f"[VALIDATION] Rejected: doesn't start with capital - '{case_name}'")
            return False
        
        # Reasonable length check (most case names are 10-150 chars)
        if len(case_name) > 150:
            logger.debug(f"[VALIDATION] Rejected: too long ({len(case_name)} chars) - '{case_name[:50]}...'")
            return False
        
        # Enhanced invalid patterns - common false positives
        invalid_patterns = [
            # Procedural/descriptive terms at start
            r'^(questions?|law|review|de\s+novo|statute|meaning)\b',
            r'^(certified|we\s+also|review|meaning)\b',
            r'^(federal\s+court|may\s+ask|this\s+court)\b',
            r'^(necessary|resolve|case|before|federal)\b',
            r'^(Washington|law|when|resolution)\b',
            r'^(held|holding|ruled|ruled\s+that|noted)\b',
            r'^(the\s+court|this\s+court|such\s+court)\b',
            
            # Common legal phrases that aren't case names
            r'^(see|see\s+also|cf\.|compare|accord|but\s+see)\b',
            r'^(citing|quoting|relying\s+on|following)\b',
            
            # Too generic or problematic content
            r'\b(id\.|supra|infra|ibid)\b',  # Citations to previous material
            r'^\d',  # Starts with a number
            r'^[^A-Za-z]',  # Starts with non-letter
        ]
        
        for pattern in invalid_patterns:
            if re.search(pattern, case_name, re.IGNORECASE):
                logger.debug(f"[VALIDATION] Rejected: matches invalid pattern '{pattern}' - '{case_name}'")
                return False
        
        # For "v." cases, ensure both parties have substance (at least 2 chars each)
        if ' v. ' in case_name.lower():
            parties = re.split(r'\s+v\.?\s+', case_name, flags=re.IGNORECASE)
            if len(parties) >= 2:
                party1 = parties[0].strip()
                party2 = parties[1].strip()
                if len(party1) < 2 or len(party2) < 2:
                    logger.debug(f"[VALIDATION] Rejected: parties too short - '{case_name}'")
                    return False
                
                # Check that parties contain actual letters (not just punctuation)
                if not re.search(r'[A-Za-z]{2,}', party1) or not re.search(r'[A-Za-z]{2,}', party2):
                    logger.debug(f"[VALIDATION] Rejected: parties lack substance - '{case_name}'")
                    return False
        
        logger.debug(f"[VALIDATION] Accepted: '{case_name}'")
        return True
    
    def _is_valid_year(self, year: str) -> bool:
        """Validate if extracted text is a valid year."""
        try:
            year_int = int(year)
            return 1800 <= year_int <= 2030
        except (ValueError, TypeError):
            return False 

    def parse_json_citation(self, json_citation: str) -> Dict[str, Optional[str]]:
        """
        Parse citation string into volume, reporter, page, and parallel citation components.
        """
        parts = json_citation.split()
        result: Dict[str, Optional[str]] = {
            'primary_volume': None,
            'primary_reporter': None,
            'primary_page': None,
            'parallel_volume': None,
            'parallel_reporter': None,
            'parallel_page': None
        }
        if len(parts) < 3:
            return result
        i = 0
        if i < len(parts) and parts[i].isdigit():
            result['primary_volume'] = parts[i]
            i += 1
        reporter_parts = []
        while i < len(parts) and not parts[i].isdigit():
            reporter_parts.append(parts[i])
            i += 1
            if len(reporter_parts) >= 3:
                break
            if i < len(parts) and parts[i].isdigit():
                break
        if reporter_parts:
            result['primary_reporter'] = ' '.join(reporter_parts)
        if i < len(parts) and parts[i].isdigit():
            result['primary_page'] = parts[i]
            i += 1
        if i < len(parts):
            if i < len(parts) and parts[i].isdigit():
                result['parallel_volume'] = parts[i]
                i += 1
            parallel_reporter_parts = []
            while i < len(parts) and not parts[i].isdigit():
                parallel_reporter_parts.append(parts[i])
                i += 1
                if len(parallel_reporter_parts) >= 3:
                    break
                if i < len(parts) and parts[i].isdigit():
                    break
            if parallel_reporter_parts:
                result['parallel_reporter'] = ' '.join(parallel_reporter_parts)
            if i < len(parts) and parts[i].isdigit():
                result['parallel_page'] = parts[i]
                i += 1
        return result

    def normalize_reporter(self, reporter: str) -> list:
        """
        Generate all possible variations of a reporter name for matching.
        """
        if not reporter:
            return []
        variations = [reporter]
        if 'Wash' in reporter:
            variations.append(reporter.replace('Wash.', 'Wn.').replace('Wash', 'Wn'))
            variations.append(reporter.replace('Wash.', 'Wn.').replace('Wash', 'Wn.'))
        elif 'Wn' in reporter:
            variations.append(reporter.replace('Wn.', 'Wash.').replace('Wn', 'Wash'))
            variations.append(reporter.replace('Wn', 'Washington'))
        original = reporter
        variations.append(re.sub(r'\s+', '', original))
        variations.append(re.sub(r'\.', '. ', original))
        variations.append(re.sub(r'\s+', ' ', original))
        seen = set()
        unique_variations = []
        for var in variations:
            if var not in seen:
                seen.add(var)
                unique_variations.append(var)
        return unique_variations

    def find_full_citation_in_text(self, text: str, json_citation: str) -> Optional[str]:
        """
        Try to find the full citation in the text using flexible reporter patterns.
        """
        parsed = self.parse_json_citation(json_citation)
        if not parsed['primary_volume'] or not parsed['primary_page']:
            return None
        volume = parsed['primary_volume']
        page = parsed['primary_page']
        reporter_variations = []
        if parsed['primary_reporter']:
            reporter_variations = self.normalize_reporter(parsed['primary_reporter'])
        for reporter in reporter_variations:
            escaped_reporter = re.escape(reporter)
            flexible_reporter = escaped_reporter.replace(r"\ ", r"\\s*")
            patterns = [
                rf'{volume}\\s+{escaped_reporter}\\s+{page}(?:,\\s*\\d+(?:-\\d+)?)*(?:,\\s*\\d{{1,3}}\\s+[A-Za-z\\. ]+\\d+(?:,\\s*\\d+(?:-\\d+)?)*)*\\s*\\(\\d{{4}}\\)',
                rf'{volume}\\s+{escaped_reporter}\\s+{page}(?:,\\s*\\d+(?:-\\d+)?)*\\s*\\(\\d{{4}}\\)',
                rf'{volume}\\s+{escaped_reporter}\\s+{page}\\s*\\(\\d{{4}}\\)',
                rf'{volume}\\s+{flexible_reporter}\\s+{page}[^()]*\\(\\d{{4}}\\)'
            ]
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    return match.group(0)
        return None

    def find_case_name_before_citation(self, text: str, full_citation: str) -> Optional[str]:
        """
        Find the case name immediately before the citation in the text.
        """
        idx = text.find(full_citation)
        if idx == -1:
            return None
        context = text[max(0, idx-500):idx]
        pattern = r'([A-Z][A-Za-z\s,\.\'-]{1,80}?\s+v\.\s+[A-Z][A-Za-z\s,\.\'-]{1,80}?)\s*[,;:.]?$'
        match = re.search(pattern, context, re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip()
        return None 

    def is_case_name_associated_with_citation(self, context: str, case_name: str, citation: str) -> bool:
        """
        Check if a case name is actually associated with the specific citation we're looking for.
        This prevents picking up case names from other citations in the same context.
        """
        pattern = rf'{re.escape(case_name)}\s*,\s*{re.escape(citation)}'
        if re.search(pattern, context, re.IGNORECASE):
            return True
        
        case_name_index = context.find(case_name)
        citation_index = context.find(citation)
        
        if case_name_index != -1 and citation_index != -1:
            if case_name_index < citation_index:
                distance = citation_index - case_name_index
                if distance <= 50:  # Within 50 characters
                    return True
        
        return False

    def starts_with_signal_word(self, text: str) -> bool:
        """
        Check if text starts with common signal words that indicate it's not a case name.
        """
        signal_words = [
            'the', 'this', 'that', 'these', 'those', 'a', 'an',
            'held', 'in', 'principle', 'applies', 'court', 'federal',
            'may', 'ask', 'necessary', 'resolve', 'case', 'before',
            'when', 'resolution', 'question', 'law', 'review', 'de',
            'novo', 'statute', 'meaning', 'certified', 'we', 'also'
        ]
        
        words = text.lower().split()
        if words and words[0] in signal_words:
            return True
        return False

    def clean_case_name_enhanced(self, case_name: str) -> str:
        """
        Enhanced case name cleaning with better handling of edge cases.
        """
        if not case_name:
            return ""
        
        case_name = re.sub(r'\s+', ' ', case_name).strip()
        
        case_name = re.sub(r'[,\s]+$', '', case_name)
        case_name = case_name.rstrip('.,;:')
        
        case_name = re.sub(r'\s+v\.\s+', ' v. ', case_name)
        case_name = re.sub(r'\s+vs\.\s+', ' v. ', case_name)
        case_name = re.sub(r'\s+versus\s+', ' v. ', case_name)
        
        case_name = re.sub(r'\s+In\s+re\s+', ' In re ', case_name)
        
        leading_patterns = [
            r'^.*?\b(held|in|that|the|principle|applies)\s+',
            r'^.*?\b(court|held|in)\s+',
            r'^.*?\b(federal|court|may|ask|this)\s+',
        ]
        
        for pattern in leading_patterns:
            case_name = re.sub(pattern, '', case_name, flags=re.IGNORECASE)
        
        if case_name.endswith(', LLC') or case_name.endswith(', Inc.') or case_name.endswith(', Corp.'):
            pass
        else:
            case_name = re.sub(r',\s*$', '', case_name)
            case_name = re.sub(r'\.\s*$', '', case_name)
        
        return case_name.strip() 

class DateExtractor:
    """Date extraction utilities - enhanced with patterns from EnhancedDateExtractor."""
    
    def __init__(self):
        self.date_patterns = [
            r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b',
            
            r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b',
            
            r'\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})\b',
            
            r'\((\d{4})\)',
            
            r'(?:decided|filed|issued|released|argued|submitted)\s+(?:in\s+)?(\d{4})\b',
            
            r'\b(19|20)\d{2}\b',
            
            r'\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b',
            
            r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b',
        ]
        
        self.month_map = {
            'january': '01', 'jan': '01',
            'february': '02', 'feb': '02',
            'march': '03', 'mar': '03',
            'april': '04', 'apr': '04',
            'may': '05',
            'june': '06', 'jun': '06',
            'july': '07', 'jul': '07',
            'august': '08', 'aug': '08',
            'september': '09', 'sep': '09',
            'october': '10', 'oct': '10',
            'november': '11', 'nov': '11',
            'december': '12', 'dec': '12'
        }
    
    def extract_date(self, text: str, citation: Optional[str] = None) -> Optional[str]:
        """
        Extract date from text, optionally using citation as context.
        Prioritizes a year in parentheses immediately after the citation if present.
        Args:
            text: The text to search for dates
            citation: Optional citation to use for context positioning
        Returns:
            Extracted date in ISO format (YYYY-MM-DD) or None if not found
        """
        try:
            if not text:
                return None

            if citation:
                citation_index = text.find(citation)
                if citation_index != -1:
                    after_citation = text[citation_index + len(citation): citation_index + len(citation) + 20]
                    match = re.search(r'\(\s*(\d{4})\s*\)', after_citation)
                    if match:
                        year = match.group(1)
                        if 1900 <= int(year) <= 2100:
                            return f"{year}-01-01"
                return self._extract_with_citation_context(text, citation)

            return self._extract_from_full_text(text)

        except Exception as e:
            logger.warning(f"Error extracting date: {e}")
            return None
    
    def extract_year(self, text: str, citation: Optional[str] = None) -> Optional[str]:
        """
        Extract just the year from text.
        
        Args:
            text: The text to search for years
            citation: Optional citation to use for context positioning
            
        Returns:
            Extracted year as string or None if not found
        """
        try:
            date = self.extract_date(text, citation)
            if date:
                return date.split('-')[0]
            return None
            
        except Exception as e:
            logger.warning(f"Error extracting year: {e}")
            return None
    
    def _extract_with_citation_context(self, text: str, citation: str) -> Optional[str]:
        """Extract date using citation as context anchor."""
        try:
            citation_index = text.find(citation)
            if citation_index == -1:
                return self._extract_from_full_text(text)
            
            context_start = max(0, citation_index - 300)  # Increased from 200
            context_end = min(len(text), citation_index + len(citation) + 100)
            
            context_text = text[context_start:context_end]
            
            citation_patterns = [
                r'\b\d+\s+[A-Za-z.]+(?:\s+\d+)?\b',  # Basic citation pattern
                r'\b\d+\s+(?:Wash\.|Wn\.|P\.|A\.|S\.|N\.|F\.|U\.S\.)\b',  # Common reporters
            ]
            
            last_citation_pos = 0
            for pattern in citation_patterns:
                matches = list(re.finditer(pattern, context_text))
                for match in matches:
                    if match.end() < (citation_index - context_start):
                        last_citation_pos = max(last_citation_pos, match.end())
            
            if last_citation_pos > 0:
                sentence_pattern = re.compile(r'\.\s+[A-Z]')
                sentence_matches = list(sentence_pattern.finditer(context_text, last_citation_pos))
                if sentence_matches:
                    adjusted_start = context_start + sentence_matches[0].start() + 1
                    context_start = max(context_start, adjusted_start)
                else:
                    context_start = max(context_start, context_start + last_citation_pos)
            
            context = text[context_start:context_end]
            
            return self._parse_date_patterns(context)
            
        except Exception as e:
            logger.warning(f"Error extracting date with citation context: {e}")
            return None
    
    def _extract_from_full_text(self, text: str) -> Optional[str]:
        """Extract date from full text without citation context."""
        try:
            return self._parse_date_patterns(text)
            
        except Exception as e:
            logger.warning(f"Error extracting date from full text: {e}")
            return None
    
    def _parse_date_patterns(self, text: str) -> Optional[str]:
        """Parse date patterns and return the best match."""
        try:
            best_date = None
            best_confidence = 0
            
            for pattern in self.date_patterns:
                matches = list(re.finditer(pattern, text, re.IGNORECASE))
                for match in matches:
                    groups = match.groups()
                    date_str = self._parse_date_groups(groups, pattern)
                    
                    if date_str:
                        confidence = self._calculate_date_confidence(pattern, groups)
                        
                        if confidence > best_confidence:
                            best_date = date_str
                            best_confidence = confidence
            
            return best_date
            
        except Exception as e:
            logger.warning(f"Error parsing date patterns: {e}")
            return None
    
    def _parse_date_groups(self, groups: tuple, pattern: str) -> Optional[str]:
        """Parse date groups and return ISO format date string."""
        try:
            if len(groups) == 3:
                if 'January|February' in pattern:
                    month_name, day, year = groups
                    month = self.month_map.get(month_name.lower(), '01')
                elif pattern == r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b':
                    year, month, day = groups
                else:
                    month, day, year = groups
                
                try:
                    year_int = int(year)
                    month_int = int(month)
                    day_int = int(day)
                    
                    if 1900 <= year_int <= 2100 and 1 <= month_int <= 12 and 1 <= day_int <= 31:
                        return f"{year_int:04d}-{month_int:02d}-{day_int:02d}"
                except (ValueError, TypeError):
                    pass
                    
            elif len(groups) == 1:
                year = groups[0]
                try:
                    year_int = int(year)
                    if 1900 <= year_int <= 2100:
                        return f"{year_int:04d}-01-01"  # Default to January 1st
                except (ValueError, TypeError):
                    pass
            
            return None
            
        except Exception as e:
            logger.warning(f"Error parsing date groups: {e}")
            return None
    
    def _calculate_date_confidence(self, pattern: str, groups: tuple) -> float:
        """Calculate confidence score for a date match."""
        try:
            confidence = 0.5  # Base confidence
            
            if 'January|February' in pattern:
                confidence += 0.3  # Full month names are more reliable
            elif pattern == r'\((\d{4})\)':
                confidence += 0.2  # Parenthesized years are common in citations
            elif pattern == r'\b(19|20)\d{2}\b':
                confidence += 0.1  # Simple year patterns
            
            if len(groups) >= 1:
                try:
                    year = int(groups[0])
                    if 1900 <= year <= 2100:
                        confidence += 0.2
                    else:
                        confidence -= 0.3
                except (ValueError, TypeError):
                    confidence -= 0.3
            
            return max(0.0, min(1.0, confidence))
            
        except Exception:
            return 0.0
    
    def extract_date_multi_pattern(self, text: str, citation_start: int, citation_end: int) -> Optional[str]:
        """
        Use multiple detection strategies for date extraction.
        """
        context = self._get_adaptive_context(text, citation_start, citation_end)
        citation_text = text[citation_start:citation_end]
        
        def extract_immediate_parentheses():
            after_citation = text[citation_end:citation_end+20]
            match = re.search(r'\(\s*(\d{4})\s*\)', after_citation)
            if match:
                year = match.group(1)
                if 1900 <= int(year) <= 2100:
                    return f"{year}-01-01"
            return None
        
        def extract_from_sentence():
            sentence = context
            match = re.search(r'(19|20)\d{2}', sentence)
            if match:
                year = match.group(0)
                if 1900 <= int(year) <= 2100:
                    return f"{year}-01-01"
            return None
        
        def extract_from_paragraph():
            para = context
            match = re.search(r'(19|20)\d{2}', para)
            if match:
                year = match.group(0)
                if 1900 <= int(year) <= 2100:
                    return f"{year}-01-01"
            return None
        
        def extract_from_citation_text():
            match = re.search(r'(19|20)\d{2}', citation_text)
            if match:
                year = match.group(0)
                if 1900 <= int(year) <= 2100:
                    return f"{year}-01-01"
            return None
        
        strategies = [
            extract_immediate_parentheses,
            extract_from_sentence,
            extract_from_paragraph,
            extract_from_citation_text
        ]
        for strategy in strategies:
            try:
                result = strategy()
                if result:
                    return result
            except Exception:
                continue
        return None
    
    def _get_adaptive_context(self, text: str, citation_start: int, citation_end: int) -> str:
        """
        Adaptive context window based on sentence and paragraph boundaries.
        """
        sentence_start = text.rfind('.', 0, citation_start) + 1
        sentence_end = text.find('.', citation_end)
        if sentence_end == -1:
            sentence_end = len(text)
        
        para_start = text.rfind('\n\n', 0, citation_start) + 2
        para_end = text.find('\n\n', citation_end)
        if para_end == -1:
            para_end = len(text)
        
        context_start = max(sentence_start, para_start, citation_start - 500)
        context_end = min(sentence_end, para_end, citation_end + 200)
        
        return text[context_start:context_end]

    @staticmethod
    def extract_date_from_context_precise(text: str, citation_start: int, citation_end: int) -> Optional[str]:
        """Extract date with precise context to avoid wrong years."""
        
        immediate_after = text[citation_end:citation_end + 50]  # Increased window
        year_match = re.search(r'\((\d{4})\)', immediate_after)
        if year_match:
            year = year_match.group(1)
            if 1800 <= int(year) <= 2030:
                return f"{year}-01-01"
        
        sentence_start = max(0, text.rfind('.', 0, citation_start) + 1)
        sentence_end = text.find('.', citation_end)
        if sentence_end == -1:
            sentence_end = len(text)
        
        sentence = text[sentence_start:sentence_end]
        
        year_matches = re.findall(r'\((\d{4})\)', sentence)
        for year in year_matches:
            if 1800 <= int(year) <= 2030:
                return f"{year}-01-01"
        
        context_start = max(0, citation_start - 200)  # Increased from 100
        context_end = min(len(text), citation_end + 100)
        
        context_text = text[context_start:context_end]
        
        citation_patterns = [
            r'\b\d+\s+[A-Za-z.]+(?:\s+\d+)?\b',  # Basic citation pattern
            r'\b\d+\s+(?:Wash\.|Wn\.|P\.|A\.|S\.|N\.|F\.|U\.S\.)\b',  # Common reporters
        ]
        
        last_citation_pos = 0
        for pattern in citation_patterns:
            matches = list(re.finditer(pattern, context_text))
            for match in matches:
                if match.end() < (citation_start - context_start):
                    last_citation_pos = max(last_citation_pos, match.end())
        
        if last_citation_pos > 0:
            sentence_pattern = re.compile(r'\.\s+[A-Z]')
            sentence_matches = list(sentence_pattern.finditer(context_text, last_citation_pos))
            if sentence_matches:
                adjusted_start = context_start + sentence_matches[0].start() + 1
                context_start = max(context_start, adjusted_start)
            else:
                context_start = max(context_start, context_start + last_citation_pos)
        
        context = text[context_start:context_end]
        
        year_matches = re.findall(r'\((\d{4})\)', context)
        for year in year_matches:
            if 1800 <= int(year) <= 2030:
                return f"{year}-01-01"
        
        return None

    @staticmethod
    def extract_date_from_context(text: str, citation_start: int, citation_end: int, context_window: int = 300) -> Optional[str]:
        """
        DEPRECATED: Use isolation-aware date extraction logic instead.
        Extract date from context around a citation. Now with expanded patterns and larger window.
        Enhanced: If no date is found by regex, scan the 50 characters after the citation for a 4-digit year in parentheses or after a comma/semicolon.
        """
        warnings.warn(
            "extract_date_from_context is deprecated. Use isolation-aware extraction instead.",
            DeprecationWarning,
            stacklevel=2
        )
        try:
            context_start = max(0, citation_start - context_window)
            context_end = min(len(text), citation_end + context_window)
            context_before = text[context_start:citation_start]
            context_after = text[citation_end:context_end]
            full_context = context_before + context_after

            date_patterns = [
                r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b',  # ISO
                r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b',  # US
                r'\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})\b',
                r'\((\d{4})\)',  # (2024)
                r'(?:decided|filed|issued|released|argued|submitted|entered|adjudged|rendered|delivered|opinion\s+filed)\s+(?:on\s+)?(?:the\s+)?(?:day\s+of\s+)?([A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{4})',
                r'\b(19|20)\d{2}\b',  # year
                r'\b(\d{4})\s+Wash\.\s+App\.',  # e.g. 1989 Wash. App.
                r'\b(\d{4})\s+LEXIS\b',  # e.g. 1989 LEXIS
                r'\b(\d{4})\s+WL\b',  # e.g. 1989 WL
            ]
            month_map = {
                'january': '01', 'jan': '01',
                'february': '02', 'feb': '02',
                'march': '03', 'mar': '03',
                'april': '04', 'apr': '04',
                'may': '05',
                'june': '06', 'jun': '06',
                'july': '07', 'jul': '07',
                'august': '08', 'aug': '08',
                'september': '09', 'sep': '09',
                'october': '10', 'oct': '10',
                'november': '11', 'nov': '11',
                'december': '12', 'dec': '12'
            }
            for pattern in date_patterns:
                matches = re.finditer(pattern, full_context, re.IGNORECASE)
                for match in matches:
                    groups = match.groups()
                    if len(groups) == 3:
                        if pattern == r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b':
                            year, month, day = groups
                        elif pattern == r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b':
                            month, day, year = groups
                        elif 'January|February' in pattern:
                            month_name, day, year = groups
                            month = month_map.get(month_name.lower(), '01')
                        else:
                            continue
                        try:
                            year = int(year)
                            month = int(month)
                            day = int(day)
                            if 1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
                                return f"{year:04d}-{month:02d}-{day:02d}"
                        except (ValueError, TypeError):
                            continue
                    elif len(groups) == 1:
                        year = groups[0]
                        try:
                            year_int = int(year)
                            if 1900 <= year_int <= 2100:
                                return f"{year_int:04d}-01-01"
                        except (ValueError, TypeError):
                            continue
            after = text[citation_end:citation_end+50]
            m = re.search(r'\((19|20)\d{2}\)', after)
            if m:
                return f"{m.group(1)}-01-01"
            m = re.search(r'[;,]\s*(19|20)\d{2}', after)
            if m:
                return f"{m.group(1)}-01-01"
            m = re.search(r'(19|20)\d{2}', after)
            if m:
                return f"{m.group(1)}-01-01"
            return None
        except Exception as e:
            logger.warning(f"Error extracting date from context: {e}")
            return None


def safe_set_extracted_date(citation, new_date, source="unknown"):
    """
    Safely set extracted_date on a citation, preventing overwriting better dates with worse ones.
    
    Args:
        citation: Citation object with extracted_date attribute
        new_date: New date to potentially set
        source: Source of the date assignment for debugging
        
    Returns:
        bool: True if date was set/changed, False if skipped
    """
    try:
        if not new_date or new_date.strip() == "":
            return False
        
        if new_date.strip().upper() in ["N/A", "NONE", "NULL", "UNKNOWN"]:
            return False
        
        current_date = getattr(citation, 'extracted_date', None)
        
        if not current_date or current_date.strip() == "" or current_date.strip().upper() in ["N/A", "NONE", "NULL", "UNKNOWN"]:
            citation.extracted_date = new_date
            return True
        
        if len(current_date) > len(new_date):
            return False
        
        if len(current_date) == len(new_date):
            return False
        
        citation.extracted_date = new_date
        return True
        
    except Exception as e:
        logger.warning(f"Error in safe_set_extracted_date: {e}")
        return False


def validate_citation_dates(citation):
    """
    Validate that a citation has a valid extracted_date.
    
    Args:
        citation: Citation object with extracted_date attribute
        
    Returns:
        bool: True if date is valid, False otherwise
    """
    try:
        date = getattr(citation, 'extracted_date', None)
        
        if not date or date.strip() == "":
            return False
        
        if date.strip().upper() in ["N/A", "NONE", "NULL", "UNKNOWN"]:
            return False
        
        if not re.match(r'^\d{4}(-\d{2}-\d{2})?$', date):
            return False
        
        year = int(date.split('-')[0])
        if not (1800 <= year <= 2030):
            return False
        
        return True
        
    except Exception as e:
        logger.warning(f"Error validating citation date: {e}")
        return False


def extract_date_enhanced(text: str, citation: Optional[str] = None) -> Optional[str]:
    """Enhanced date extraction function - compatibility wrapper."""
    extractor = DateExtractor()
    return extractor.extract_date(text, citation)


def extract_year_enhanced(text: str, citation: Optional[str] = None) -> Optional[str]:
    """Enhanced year extraction function - compatibility wrapper."""
    extractor = DateExtractor()
    return extractor.extract_year(text, citation) 