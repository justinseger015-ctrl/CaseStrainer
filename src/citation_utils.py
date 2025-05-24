import os
import traceback
import time
import logging

from config import ALLOWED_EXTENSIONS

# Robust import for extract_text_from_file
try:
    from file_utils import extract_text_from_file
except ImportError:

    def extract_text_from_file(file_path):
        raise NotImplementedError(
            "extract_text_from_file is not available in this environment"
        )


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# Setup logger (modules importing this should configure logging)
logger = logging.getLogger(__name__)

from config import COURTLISTENER_API_KEY


def verify_citation(
    citation,
    context=None,
    logger=logger,
    DEFAULT_API_KEY=COURTLISTENER_API_KEY,
    thread_local=None,
):
    """Verify a citation using the robust CitationVerifier logic with improved error handling, including retry, throttling, timeout, and caching."""
    try:
        # Import CitationVerifier with better error handling
        try:
            from src.citation_verification import CitationVerifier

            logger.info(
                f"Successfully imported CitationVerifier from src.citation_verification"
            )
        except ImportError as import_err:
            try:
                from citation_verification import CitationVerifier

                logger.info(
                    f"Successfully imported CitationVerifier from citation_verification (relative import)"
                )
            except ImportError:
                logger.error(f"Failed to import CitationVerifier: {str(import_err)}")
                raise

        # Import our citation verification logging function
        try:
            from citation_api import log_citation_verification

            logger.info("Successfully imported log_citation_verification function")
        except ImportError as import_err:
            logger.warning(
                f"Could not import log_citation_verification function: {str(import_err)}"
            )

            def log_citation_verification(
                citation, verification_result, api_response=None
            ):
                logger.info(f"Citation: {citation}, Result: {verification_result}")

        api_key = (
            getattr(thread_local, "api_key", DEFAULT_API_KEY)
            if thread_local
            else DEFAULT_API_KEY
        )
        if api_key:
            logger.info(
                f"Using API key for verification: {api_key[:5]}... (length: {len(api_key)})"
            )
        else:
            logger.warning("No API key available for citation verification")
            print("WARNING: No API key available for citation verification")

        # --- Begin: Caching and Throttling ---
        import threading
        import time
        import random

        # Simple in-memory cache for previously verified citations
        if not hasattr(verify_citation, "_cache"):
            verify_citation._cache = {}
            verify_citation._cache_lock = threading.Lock()
        cache = verify_citation._cache
        cache_lock = verify_citation._cache_lock
        cache_key = (citation, context)
        with cache_lock:
            if cache_key in cache:
                logger.info("Cache hit for citation: %s", citation)
                return cache[cache_key]
        # --- End: Caching ---

        # --- Begin: Throttling ---
        if not hasattr(verify_citation, "_last_call_time"):
            verify_citation._last_call_time = 0
        min_interval = 0.5  # seconds between API calls
        now = time.time()
        elapsed = now - verify_citation._last_call_time
        if elapsed < min_interval:
            sleep_time = min_interval - elapsed
            logger.info(f"Throttling: sleeping {sleep_time:.2f}s before API call")
            time.sleep(sleep_time)
        verify_citation._last_call_time = time.time()
        # --- End: Throttling ---

        verifier = CitationVerifier(api_key=api_key)
        logger.info(f"Verifying citation: {citation}")
        start_time = time.time()
        # --- Begin: Retry Logic with Exponential Backoff ---
        max_retries = 3
        base_timeout = 45  # seconds (increased from 30)
        for attempt in range(1, max_retries + 1):
            try:
                if context:
                    logger.info(f"Context provided, length: {len(context)}")
                    result = verifier.verify_citation(citation, context=context)
                else:
                    result = verifier.verify_citation(citation)
                verification_time = time.time() - start_time
                logger.info(
                    f"Verification completed in {verification_time:.2f} seconds (attempt {attempt})"
                )
                logger.info(f"Verification result: {result}")
                log_citation_verification(citation, result)
                # Save to cache
                with cache_lock:
                    cache[cache_key] = result
                return result
            except Exception as e:
                logger.warning(f"Attempt {attempt} failed: {e}")
                if attempt == max_retries:
                    logger.error(
                        f"All {max_retries} attempts failed for citation: {citation}"
                    )
                    traceback.print_exc()
                    break
                backoff = 2 ** (attempt - 1) + random.uniform(0, 1)
                logger.info(f"Retrying after {backoff:.2f}s...")
                time.sleep(backoff)
        # --- End: Retry Logic ---
        return {
            "found": False,
            "source": None,
            "explanation": f"Error during verification after {max_retries} attempts.",
            "error": True,
            "error_message": f"Failed after {max_retries} attempts.",
        }
    except Exception as e:
        logger.error(f"Error verifying citation: {e}")
        traceback.print_exc()
        return {
            "found": False,
            "source": None,
            "explanation": f"Error during verification: {str(e)}",
            "error": True,
            "error_message": str(e),
        }


def extract_citations_from_file(filepath, logger=logger):
    """Extract citations from a file and return full metadata."""
    try:
        logger.info(f"[DEBUG] Starting extract_citations_from_file for: {filepath}")
        file_size = os.path.getsize(filepath)
        file_extension = os.path.splitext(filepath)[1].lower()
        logger.info(
            f"[DEBUG] File details - Size: {file_size} bytes, Extension: {file_extension}"
        )
        start_time = time.time()
        text = ""
        if filepath.endswith(".pdf"):
            logger.info("Detected PDF file, using PyPDF2 for extraction")
            import PyPDF2

            with open(filepath, "rb") as file:
                try:
                    reader = PyPDF2.PdfReader(file)
                    logger.info(f"PDF has {len(reader.pages)} pages")
                    text = ""
                    for i, page in enumerate(reader.pages):
                        logger.info(
                            f"Extracting text from page {i+1}/{len(reader.pages)}"
                        )
                        page_text = page.extract_text()
                        text += page_text
                        logger.info(
                            f"Page {i+1} extracted: {len(page_text)} characters"
                        )
                except Exception as pdf_error:
                    logger.error(f"Error reading PDF: {str(pdf_error)}")
                    raise
        elif filepath.endswith((".doc", ".docx")):
            logger.info("Detected Word document, using python-docx for extraction")
            import docx

            try:
                doc = docx.Document(filepath)
                logger.info(f"Word document has {len(doc.paragraphs)} paragraphs")
                paragraphs = [paragraph.text for paragraph in doc.paragraphs]
                text = "\n".join(paragraphs)
                logger.info(
                    f"Extracted {len(paragraphs)} paragraphs with total {len(text)} characters"
                )
            except Exception as docx_error:
                logger.error(f"Error reading Word document: {str(docx_error)}")
                raise
        else:
            logger.info(f"Using standard text file reading for {file_extension} file")
            try:
                with open(filepath, "r", encoding="utf-8") as file:
                    text = file.read()
                    logger.info(f"Read {len(text)} characters from text file")
            except UnicodeDecodeError:
                logger.warning("UTF-8 decoding failed, trying with latin-1 encoding")
                with open(filepath, "r", encoding="latin-1") as file:
                    text = file.read()
                    logger.info(
                        f"Read {len(text)} characters from text file using latin-1 encoding"
                    )
        extraction_time = time.time() - start_time
        logger.info(
            f"File content extraction completed in {extraction_time:.2f} seconds"
        )
        logger.info(f"Extracted text sample (first 200 chars): {text[:200]}...")
        logger.info("Calling extract_citations_from_text with the extracted content")
        return extract_citations_from_text(text, logger=logger)
    except Exception as e:
        logger.error(f"Error extracting citations from file: {str(e)}")
        logger.error(traceback.format_exc())
        return []


def extract_citations_from_text(text, logger=logger):
    """Extract citations from text using eyecite and return full metadata."""
    try:
        logger.info(
            f"[DEBUG] Starting extract_citations_from_text with text of length {len(text)}"
        )
        # Ensure text is a string before slicing
        if not isinstance(text, str):
            logger.warning(
                f"[DEBUG] Text is not a string (type: {type(text)}); attempting to convert to string for logging."
            )
            logger.warning(f"[DEBUG] Text value: {repr(text)}")
            try:
                text = str(text)
            except Exception as conversion_error:
                logger.error(
                    f"[DEBUG] Failed to convert text to string: {conversion_error}"
                )
                text = ""
        logger.info(f"[DEBUG] Text sample: {text[:300]}...")
        start_time = time.time()
        from eyecite import get_citations
        from eyecite.tokenizers import AhocorasickTokenizer

        logger.info("Successfully imported eyecite libraries")
        tokenizer = None
        try:
            logger.info("Attempting to initialize AhocorasickTokenizer")
            tokenizer_start = time.time()
            tokenizer = AhocorasickTokenizer()
            logger.info(
                f"AhocorasickTokenizer initialized in {time.time() - tokenizer_start:.2f} seconds"
            )
        except Exception as tokenizer_error:
            logger.warning(
                f"Failed to initialize AhocorasickTokenizer: {str(tokenizer_error)}"
            )
            logger.warning("Will fall back to default tokenizer")
            tokenizer = None
        logger.info("Starting citation extraction with eyecite")
        extraction_start = time.time()
        if tokenizer:
            logger.info("Using AhocorasickTokenizer for extraction")
            citations = get_citations(text, tokenizer=tokenizer)
        else:
            logger.info("Using default tokenizer for extraction")
            citations = get_citations(text)
        extraction_time = time.time() - extraction_start
        logger.info(f"Citation extraction completed in {extraction_time:.2f} seconds")
        logger.info(f"Found {len(citations)} citations in the text")
        logger.info("Processing citation objects to extract metadata")
        metadata_start = time.time()
        citation_dicts = []
        unique_citations = {}
        for i, citation in enumerate(citations):
            citation_text = citation.matched_text()
            logger.info(f"Processing citation {i+1}/{len(citations)}: {citation_text}")
            case_name = None
            try:
                if (
                    hasattr(citation, "metadata")
                    and citation.metadata
                    and hasattr(citation.metadata, "case_name")
                ):
                    case_name = citation.metadata.case_name
                    logger.info(f"Found case name: {case_name}")
                else:
                    logger.info("No case name found in metadata")
            except Exception as name_error:
                logger.warning(f"Error extracting case name: {str(name_error)}")
                pass
            reporter = getattr(citation, "reporter", None)
            volume = getattr(citation, "volume", None)
            page = getattr(citation, "page", None)
            year = getattr(citation, "year", None)
            court = getattr(citation, "court", None)
            logger.info(
                f"Citation metadata - Reporter: {reporter}, Volume: {volume}, Page: {page}, Year: {year}, Court: {court}"
            )
            try:
                citation_pos = text.find(citation_text)
                if citation_pos != -1:
                    start_pos = max(0, citation_pos - 100)
                    end_pos = min(len(text), citation_pos + len(citation_text) + 100)
                    context = text[start_pos:end_pos]
                    logger.info(
                        f"Extracted context of length {len(context)} for citation"
                    )
                else:
                    context = ""
                    logger.warning(
                        f"Could not find citation '{citation_text}' in text for context extraction"
                    )
            except Exception as context_error:
                logger.warning(f"Error extracting context: {str(context_error)}")
                context = ""
            citation_key = (
                f"{volume or ''}|{reporter or ''}|{page or ''}|{citation_text}"
            )
            if citation_key in unique_citations:
                unique_citations[citation_key]["contexts"].append(
                    {"text": context, "citation_text": citation_text}
                )
                logger.info(f"Added context to existing citation: {citation_key}")
            else:
                # Fallback to context-based extraction if Eyecite did not provide a case name
                if not case_name or case_name.strip() == "":
                    # Try to extract from the context before the citation
                    context_before = (
                        context[: context.find(citation_text)]
                        if citation_text in context
                        else context
                    )
                    try:
                        from extract_case_name import extract_case_name_from_context

                        context_case_name = extract_case_name_from_context(
                            context_before
                        )
                    except Exception as e:
                        logger.warning(
                            f"Could not import or run extract_case_name_from_context: {e}"
                        )
                        context_case_name = ""
                    final_case_name = (
                        context_case_name if context_case_name else "Unknown Case"
                    )
                else:
                    final_case_name = case_name
                citation_dict = {
                    "text": citation_text,
                    "name": final_case_name,
                    "valid": None,
                    "contexts": [{"text": context, "citation_text": citation_text}],
                    "metadata": {
                        "reporter": reporter,
                        "volume": volume,
                        "page": page,
                        "year": year,
                        "court": court,
                    },
                    "extraction_method": "eyecite",
                    "eyecite_processed": True,
                }
                unique_citations[citation_key] = citation_dict
                logger.info(f"Added new citation: {citation_key}")
        citation_dicts = list(unique_citations.values())
        logger.info(
            f"After deduplication, {len(citation_dicts)} unique citations remain"
        )
        metadata_time = time.time() - metadata_start
        logger.info(f"Metadata extraction completed in {metadata_time:.2f} seconds")
        total_time = time.time() - start_time
        logger.info(
            f"Total citation extraction process completed in {total_time:.2f} seconds"
        )
        logger.info(f"Returning {len(citation_dicts)} citation dictionaries")
        return citation_dicts
    except Exception as e:
        logger.error(f"Error extracting citations from text: {str(e)}")
        logger.error(traceback.format_exc())
        logger.error(f"Error occurred after processing text of length {len(text)}")
        # Defensive: ensure text is a string before slicing for error logging
        if not isinstance(text, str):
            logger.error(
                f"Text is not a string (type: {type(text)}); attempting to convert to string for error logging."
            )
            logger.error(f"Text value: {repr(text)}")
            try:
                text = str(text)
            except Exception as conversion_error:
                logger.error(f"Failed to convert text to string: {conversion_error}")
                text = ""
        if len(text) > 0:
            sample_size = min(500, len(text))
            logger.error(
                f"Text sample that caused the error (first {sample_size} chars): {text[:sample_size]}"
            )
        else:
            logger.error("Text is empty or could not be converted to string.")
        return []


def extract_all_citations(text, logger=logger):
    """Extract citations from text using both eyecite and regex, deduplicate, and return full metadata."""
    try:
        logger.info(
            f"[DEBUG] Starting extract_all_citations with text of length {len(text)}"
        )
        # Ensure text is a string before slicing
        if not isinstance(text, str):
            logger.warning(
                f"[DEBUG] Text is not a string (type: {type(text)}); attempting to convert to string for logging."
            )
            logger.warning(f"[DEBUG] Text value: {repr(text)}")
            try:
                text = str(text)
            except Exception as conversion_error:
                logger.error(
                    f"[DEBUG] Failed to convert text to string: {conversion_error}"
                )
                text = ""
        logger.info(f"[DEBUG] Text sample: {text[:300]}...")
        start_time = time.time()
        from eyecite import get_citations
        from eyecite.tokenizers import AhocorasickTokenizer

        logger.info("Successfully imported eyecite libraries")
        tokenizer = None
        try:
            logger.info("Attempting to initialize AhocorasickTokenizer")
            tokenizer_start = time.time()
            tokenizer = AhocorasickTokenizer()
            logger.info(
                f"AhocorasickTokenizer initialized in {time.time() - tokenizer_start:.2f} seconds"
            )
        except Exception as tokenizer_error:
            logger.warning(
                f"Failed to initialize AhocorasickTokenizer: {str(tokenizer_error)}"
            )
            logger.warning("Will fall back to default tokenizer")
            tokenizer = None
        logger.info("Starting citation extraction with eyecite")
        extraction_start = time.time()
        if tokenizer:
            logger.info("Using AhocorasickTokenizer for extraction")
            eyecite_citations = get_citations(text, tokenizer=tokenizer)
        else:
            logger.info("Using default tokenizer for extraction")
            eyecite_citations = get_citations(text)
        extraction_time = time.time() - extraction_start
        logger.info(f"Citation extraction completed in {extraction_time:.2f} seconds")
        logger.info(f"Found {len(eyecite_citations)} citations in the text (eyecite)")

        # --- REGEX Citation Extraction ---
        import re

        regex_pattern = (
            r"\b\d+\s+[A-Za-z\.]+\s+\d+\b"  # Simple baseline, can be improved
        )
        regex_citations = [m.group(0) for m in re.finditer(regex_pattern, text)]
        logger.info(f"Found {len(regex_citations)} citations in the text (regex)")

        # --- Normalization and Deduplication ---
        def normalize_citation(citation_text):
            normalized = re.sub(r"[^\w\d]", "", citation_text)
            normalized = re.sub(r"(\w)\.(\w)", r"\1\2", normalized)
            return normalized.lower()

        # Build sets for deduplication
        normalized_eyecite = set()
        eyecite_dicts = []
        for citation in eyecite_citations:
            citation_text = citation.matched_text()
            norm = normalize_citation(citation_text)
            normalized_eyecite.add(norm)
            # Build metadata as before
            case_name = None
            try:
                if (
                    hasattr(citation, "metadata")
                    and citation.metadata
                    and hasattr(citation.metadata, "case_name")
                ):
                    case_name = citation.metadata.case_name
                else:
                    case_name = None
            except Exception:
                case_name = None
            reporter = getattr(citation, "reporter", None)
            volume = getattr(citation, "volume", None)
            page = getattr(citation, "page", None)
            year = getattr(citation, "year", None)
            court = getattr(citation, "court", None)
            # Context extraction
            citation_pos = text.find(citation_text)
            if citation_pos != -1:
                start_pos = max(0, citation_pos - 100)
                end_pos = min(len(text), citation_pos + len(citation_text) + 100)
                context = text[start_pos:end_pos]
            else:
                context = ""
            citation_dict = {
                "text": citation_text,
                "name": case_name or "Unknown Case",
                "valid": None,
                "contexts": [{"text": context, "citation_text": citation_text}],
                "metadata": {
                    "reporter": reporter,
                    "volume": volume,
                    "page": page,
                    "year": year,
                    "court": court,
                },
                "extraction_method": "eyecite",
                "eyecite_processed": True,
            }
            eyecite_dicts.append(citation_dict)

        # Now add regex citations that are not in eyecite set
        merged_citations = eyecite_dicts.copy()
        for regex_cite in regex_citations:
            norm = normalize_citation(regex_cite)
            if norm not in normalized_eyecite:
                # Build a minimal citation dict for regex
                citation_pos = text.find(regex_cite)
                if citation_pos != -1:
                    start_pos = max(0, citation_pos - 100)
                    end_pos = min(len(text), citation_pos + len(regex_cite) + 100)
                    context = text[start_pos:end_pos]
                else:
                    context = ""
                citation_dict = {
                    "text": regex_cite,
                    "name": "Unknown Case",
                    "valid": None,
                    "contexts": [{"text": context, "citation_text": regex_cite}],
                    "metadata": {},
                    "extraction_method": "regex",
                    "eyecite_processed": False,
                }
                merged_citations.append(citation_dict)

        logger.info(
            f"After deduplication, {len(merged_citations)} unique citations remain"
        )
        total_time = time.time() - start_time
        logger.info(
            f"Total citation extraction process completed in {total_time:.2f} seconds"
        )
        return merged_citations
    except Exception as e:
        logger.error(f"Error extracting citations from text: {str(e)}")
        logger.error(traceback.format_exc())
        logger.error(f"Error occurred after processing text of length {len(text)}")
        if not isinstance(text, str):
            logger.error(
                f"Text is not a string (type: {type(text)}); attempting to convert to string for error logging."
            )
            logger.error(f"Text value: {repr(text)}")
            try:
                text = str(text)
            except Exception as conversion_error:
                logger.error(f"Failed to convert text to string: {conversion_error}")
                text = ""
        if len(text) > 0:
            sample_size = min(500, len(text))
            logger.error(
                f"Text sample that caused the error (first {sample_size} chars): {text[:sample_size]}"
            )
        else:
            logger.error("Text is empty or could not be converted to string.")
        return []
