"""
Eyecite Citation Extractor

This script downloads sample briefs, uses eyecite to extract citations,
verifies them using the fixed_multi_source_verifier, and saves
unverified citations along with the source brief URL.
"""

import os
import sys
import json
import requests
import traceback
import time
import random
import warnings

# Import eyecite for citation extraction
try:
    from eyecite import get_citations
    from eyecite.tokenizers import AhocorasickTokenizer

    print("Successfully imported eyecite")
except ImportError:
    print("Error: eyecite not installed. Please install it with 'pip install eyecite'")
    sys.exit(1)

# Import the unified citation processor for verification
try:
    from src.unified_citation_processor_v2 import UnifiedCitationProcessorV2, ProcessingConfig

    print("Successfully imported UnifiedCitationProcessorV2")
except ImportError:
    print("Error: unified_citation_processor_v2 not found")
    sys.exit(1)

# Constants
OUTPUT_FILE = "unverified_citations_with_sources.json"
SAMPLE_BRIEFS_DIR = "sample_briefs"
PROCESSED_BRIEFS_CACHE = "processed_briefs.json"

# Create directories if they don't exist
if not os.path.exists(SAMPLE_BRIEFS_DIR):
    os.makedirs(SAMPLE_BRIEFS_DIR)

# Sample brief URLs - these are example URLs, replace with actual brief URLs
SAMPLE_BRIEF_URLS = [
    "https://www.courts.wa.gov/content/Briefs/A01/789301%20Appellant%20Thurston%20County.pdf",
    "https://www.courts.wa.gov/content/Briefs/A01/789301%20Respondent%20Black%20Hills.pdf",
    "https://www.courts.wa.gov/content/Briefs/A01/789301%20Respondent%20Confederated%20Tribes.pdf",
    "https://www.courts.wa.gov/content/Briefs/A01/789301%20Respondent%20Squaxin.pdf",
    "https://www.courts.wa.gov/content/Briefs/A01/789301%20Respondent.pdf",
]


def load_processed_briefs():
    """Load the list of already processed briefs."""
    if os.path.exists(PROCESSED_BRIEFS_CACHE):
        try:
            with open(PROCESSED_BRIEFS_CACHE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading processed briefs cache: {e}")
    return []


def save_processed_briefs(processed_briefs):
    """Save the list of processed briefs."""
    try:
        with open(PROCESSED_BRIEFS_CACHE, "w") as f:
            json.dump(processed_briefs, f)
    except Exception as e:
        print(f"Error saving processed briefs cache: {e}")


def download_brief(brief_url):
    """Download a brief from a URL."""
    print(f"Downloading brief: {brief_url}")

    try:
        # Set up user agent to avoid being blocked
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        # Make the request
        response = requests.get(brief_url, headers=headers)

        if response.status_code != 200:
            print(f"Error downloading brief: {response.status_code}")
            return None

        # Save the brief
        filename = os.path.join(SAMPLE_BRIEFS_DIR, os.path.basename(brief_url))
        with open(filename, "wb") as f:
            f.write(response.content)

        return filename

    except Exception as e:
        print(f"Error downloading brief: {e}")
        traceback.print_exc()
        return None


def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF file using pdfminer.six first, with PyPDF2 as fallback."""
    print(f"Extracting text from PDF: {pdf_path}")
    try:
        from pdfminer.high_level import extract_text as pdfminer_extract_text
        text = pdfminer_extract_text(pdf_path)
        if text and text.strip():
            print("pdfminer.six succeeded.")
            return text
        else:
            print("pdfminer.six extracted no text, trying PyPDF2...")
    except Exception as e:
        print(f"pdfminer.six failed: {e}")
    # Only use PyPDF2 if pdfminer fails
    try:
        import PyPDF2
        with open(pdf_path, "rb") as file:
            reader = PyPDF2.PdfReader(file)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        if text and text.strip():
            print("PyPDF2 succeeded.")
            return text
        else:
            print("PyPDF2 also extracted no text.")
            return None
    except Exception as e:
        print(f"PyPDF2 failed: {e}")
    return None


def extract_citations_with_eyecite(text):
    """
    Extract citations using the unified citation extractor (eyecite and regex).
    Args:
        text (str): The text to extract citations from
    Returns:
        list: List of extracted citation dicts
    """
    from src.unified_citation_extractor import extract_all_citations
    return extract_all_citations(text)


def process_brief(brief_url, processed_briefs, unified_processor):
    """Process a brief to extract and verify citations."""
    print(f"Processing brief: {brief_url}")

    # Check if brief has already been processed
    if brief_url in processed_briefs:
        print(f"Brief already processed: {brief_url}")
        return []

    try:
        # Download the brief
        brief_path = download_brief(brief_url)
        if not brief_path:
            return []

        # Extract text from the brief
        brief_text = extract_text_from_pdf(brief_path)
        if not brief_text:
            return []

        # Extract citations from the text using eyecite
        citations = extract_citations_with_eyecite(brief_text)
        if not citations:
            print(f"No citations found in brief: {brief_url}")
            return []

        print(f"Found {len(citations)} citations in brief: {brief_url}")

        # Verify each citation
        unverified_citations = []
        for citation in citations:
            citation_text = citation.get("citation_text")
            if not citation_text:
                continue

            # Verify the citation
            result = unified_processor.verify_citation_unified_workflow(citation_text)

            # If citation is not verified, add it to the list
            if not result.get("found", False):
                unverified_citations.append(
                    {
                        "citation_text": citation_text,
                        "source_brief": brief_url,
                        "citation_metadata": citation.get("metadata", {}),
                        "verification_result": result,
                    }
                )
                print(f"Unverified citation: {citation_text}")

            # Add a small delay to avoid overwhelming the API
            time.sleep(random.uniform(0.5, 1.5))

        # Mark brief as processed
        processed_briefs.append(brief_url)
        save_processed_briefs(processed_briefs)

        return unverified_citations

    except Exception as e:
        print(f"Error processing brief: {e}")
        traceback.print_exc()
        return []


def save_unverified_citations(unverified_citations):
    """Save unverified citations to a JSON file."""
    print(f"Saving {len(unverified_citations)} unverified citations to {OUTPUT_FILE}")

    try:
        # Load existing unverified citations if the file exists
        existing_citations = []
        if os.path.exists(OUTPUT_FILE):
            with open(OUTPUT_FILE, "r") as f:
                existing_citations = json.load(f)

        # Combine existing and new citations
        all_citations = existing_citations + unverified_citations

        # Remove duplicates based on citation_text and source_brief
        unique_citations = []
        seen = set()
        for citation in all_citations:
            key = (citation["citation_text"], citation["source_brief"])
            if key not in seen:
                seen.add(key)
                unique_citations.append(citation)

        # Save to file
        with open(OUTPUT_FILE, "w") as f:
            json.dump(unique_citations, f, indent=2)

        print(
            f"Saved {len(unique_citations)} unique unverified citations to {OUTPUT_FILE}"
        )

    except Exception as e:
        print(f"Error saving unverified citations: {e}")
        traceback.print_exc()


def main():
    """Main function to process briefs and extract unverified citations."""
    print(
        "Starting extraction of unverified citations from sample briefs using eyecite"
    )

    # Initialize the unified citation processor
    config_obj = ProcessingConfig(
        use_eyecite=True,
        use_regex=True,
        extract_case_names=True,
        extract_dates=True,
        enable_clustering=True,
        enable_deduplication=True,
        enable_verification=True,
        debug_mode=True
    )
    unified_processor = UnifiedCitationProcessorV2(config_obj)

    # Load processed briefs
    processed_briefs = load_processed_briefs()
    print(f"Loaded {len(processed_briefs)} previously processed briefs")

    # Filter out already processed briefs
    new_briefs = [brief for brief in SAMPLE_BRIEF_URLS if brief not in processed_briefs]
    print(f"Found {len(new_briefs)} new briefs to process")

    # Process each brief
    all_unverified_citations = []
    for i, brief_url in enumerate(new_briefs):
        print(f"Processing brief {i+1}/{len(new_briefs)}: {brief_url}")
        unverified_citations = process_brief(
            brief_url, processed_briefs, unified_processor
        )
        all_unverified_citations.extend(unverified_citations)

        # Save progress periodically
        if (i + 1) % 5 == 0 or i == len(new_briefs) - 1:
            save_unverified_citations(all_unverified_citations)

        # Add a small delay to avoid overwhelming the server
        time.sleep(random.uniform(1.0, 3.0))

    # Save final results
    save_unverified_citations(all_unverified_citations)

    print("Finished extracting unverified citations from briefs")
    print(
        f"Found {len(all_unverified_citations)} unverified citations in {len(new_briefs)} briefs"
    )


if __name__ == "__main__":
    main()
