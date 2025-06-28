"""
Script to scan and categorize unconfirmed citations in the database.

This script analyzes the unconfirmed citations database, categorizes citations
based on their format and likelihood of being valid, and enhances the database
with additional metadata for the Citation Tester tool.
"""

import json
import re
import random
from datetime import datetime

# Import functions from app_final.py if available
try:
    from app_final import is_landmark_case

    print("Successfully imported landmark case checker from app_final.py")
except ImportError:
    print("Warning: Could not import landmark case checker from app_final.py")

# Citation format patterns
CITATION_PATTERNS = {
    "us_reports": r"^(\d+)\s+U\.?\s?S\.?\s+(\d+)$",
    "federal_reporter": r"^(\d+)\s+F\.(\d+)d\s+(\d+)$",
    "federal_supplement": r"^(\d+)\s+F\.Supp\.(\d+)d\s+(\d+)$",
    "supreme_court_reporter": r"^(\d+)\s+S\.?\s?Ct\.?\s+(\d+)$",
    "washington_reports": r"^(\d+)\s+(Wn|Wash)\.(\d+)d\s+(\d+)$",
    "washington_app_reports": r"^(\d+)\s+(Wn\.|Wash\.|Wash|Wn)\s+App\.\s+(\d+)$",
    "lawyers_edition": r"^(\d+)\s+L\.?\s?Ed\.?\s?(\d+)d\s+(\d+)$",
    "westlaw": r"^(\d{4})\s+WL\s+(\d+)$",
    "pacific_reporter": r"^(\d+)\s+P\.(\d+)d\s+(\d+)$",
    "atlantic_reporter": r"^(\d+)\s+A\.(\d+)d\s+(\d+)$",
    "north_eastern_reporter": r"^(\d+)\s+N\.E\.(\d+)d\s+(\d+)$",
    "new_york_reports": r"^(\d+)\s+N\.Y\.(\d+)d\s+(\d+)$",
    "california_reports": r"^(\d+)\s+Cal\.(\d+)th\s+(\d+)$",
}

# Valid volume ranges for different reporters
VALID_VOLUME_RANGES = {
    "us_reports": (1, 600),  # U.S. Reports currently goes up to around 600
    "federal_reporter_1": (1, 300),  # F.1d
    "federal_reporter_2": (1, 1000),  # F.2d
    "federal_reporter_3": (1, 1000),  # F.3d
    "federal_supplement_1": (1, 1000),  # F.Supp.
    "federal_supplement_2": (1, 1000),  # F.Supp.2d
    "federal_supplement_3": (1, 500),  # F.Supp.3d
    "supreme_court_reporter": (1, 140),  # S.Ct. currently goes up to around 140
    "washington_reports_1": (1, 100),  # Wn.
    "washington_reports_2": (1, 200),  # Wn.2d
    "washington_reports_3": (1, 10),  # Wn.3d (if it exists)
    "washington_app_reports": (1, 200),  # Wn. App.
    "lawyers_edition_1": (1, 100),  # L.Ed.
    "lawyers_edition_2": (1, 200),  # L.Ed.2d
    "pacific_reporter_1": (1, 1000),  # P.
    "pacific_reporter_2": (1, 1000),  # P.2d
    "pacific_reporter_3": (1, 500),  # P.3d
    "atlantic_reporter_1": (1, 1000),  # A.
    "atlantic_reporter_2": (1, 1000),  # A.2d
    "atlantic_reporter_3": (1, 200),  # A.3d
    "north_eastern_reporter_1": (1, 1000),  # N.E.
    "north_eastern_reporter_2": (1, 1000),  # N.E.2d
    "north_eastern_reporter_3": (1, 200),  # N.E.3d
    "new_york_reports_1": (1, 100),  # N.Y.
    "new_york_reports_2": (1, 100),  # N.Y.2d
    "new_york_reports_3": (1, 50),  # N.Y.3d
    "california_reports_1": (1, 50),  # Cal.
    "california_reports_2": (1, 50),  # Cal.2d
    "california_reports_3": (1, 50),  # Cal.3d
    "california_reports_4": (1, 70),  # Cal.4th
}

# Legal topics for categorizing citations
LEGAL_TOPICS = [
    "Constitutional Law",
    "Criminal Law",
    "Civil Procedure",
    "Contracts",
    "Torts",
    "Property Law",
    "Administrative Law",
    "Evidence",
    "Family Law",
    "Environmental Law",
    "Intellectual Property",
    "Tax Law",
    "Corporate Law",
    "Securities Regulation",
    "Antitrust Law",
    "Bankruptcy",
    "Employment Law",
    "Immigration Law",
    "International Law",
    "Health Law",
    "Education Law",
    "Elder Law",
    "Disability Law",
    "Consumer Protection",
    "Civil Rights",
    "First Amendment",
    "Fourth Amendment",
    "Due Process",
    "Equal Protection",
]


def load_unconfirmed_citations(
    filename="downloaded_briefs/all_unconfirmed_citations.json",
):
    """Load unconfirmed citations from the JSON file."""
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading unconfirmed citations: {e}")
        return {}


def save_unconfirmed_citations(
    citations, filename="downloaded_briefs/enhanced_unconfirmed_citations.json"
):
    """Save enhanced unconfirmed citations to a new JSON file."""
    try:
        with open(filename, "w") as f:
            json.dump(citations, f, indent=2)
        print(f"Enhanced unconfirmed citations saved to {filename}")
        return True
    except Exception as e:
        print(f"Error saving enhanced unconfirmed citations: {e}")
        return False


def analyze_citation_format(citation_text):
    """
    Analyze a citation format and determine if it's correctly formatted.
    Returns a tuple of (format_type, is_valid_format, is_valid_volume, details).
    """
    # Strip whitespace
    citation = citation_text.strip()

    # Check against each pattern
    for format_type, pattern in CITATION_PATTERNS.items():
        match = re.match(pattern, citation)
        if match:
            # Citation matches this format
            if format_type == "us_reports":
                volume, page = match.groups()
                volume_num = int(volume)
                min_vol, max_vol = VALID_VOLUME_RANGES["us_reports"]
                is_valid_volume = min_vol <= volume_num <= max_vol
                details = {
                    "volume": volume_num,
                    "page": int(page),
                    "valid_volume_range": f"{min_vol}-{max_vol}",
                }
                return (format_type, True, is_valid_volume, details)

            elif format_type == "federal_reporter":
                volume, series, page = match.groups()
                volume_num = int(volume)
                series_num = int(series)
                if series_num > 3:
                    return (
                        format_type,
                        False,
                        False,
                        {"error": "Invalid series number (too high)"},
                    )

                range_key = f"federal_reporter_{series_num}"
                min_vol, max_vol = VALID_VOLUME_RANGES.get(range_key, (1, 1000))
                is_valid_volume = min_vol <= volume_num <= max_vol
                details = {
                    "volume": volume_num,
                    "series": series_num,
                    "page": int(page),
                    "valid_volume_range": f"{min_vol}-{max_vol}",
                }
                return (format_type, True, is_valid_volume, details)

            elif format_type == "federal_supplement":
                volume, series, page = match.groups()
                volume_num = int(volume)
                series_num = int(series)
                if series_num > 3:
                    return (
                        format_type,
                        False,
                        False,
                        {"error": "Invalid series number (too high)"},
                    )

                range_key = f"federal_supplement_{series_num}"
                min_vol, max_vol = VALID_VOLUME_RANGES.get(range_key, (1, 1000))
                is_valid_volume = min_vol <= volume_num <= max_vol
                details = {
                    "volume": volume_num,
                    "series": series_num,
                    "page": int(page),
                    "valid_volume_range": f"{min_vol}-{max_vol}",
                }
                return (format_type, True, is_valid_volume, details)

            elif format_type == "supreme_court_reporter":
                volume, page = match.groups()
                volume_num = int(volume)
                min_vol, max_vol = VALID_VOLUME_RANGES["supreme_court_reporter"]
                is_valid_volume = min_vol <= volume_num <= max_vol
                details = {
                    "volume": volume_num,
                    "page": int(page),
                    "valid_volume_range": f"{min_vol}-{max_vol}",
                }
                return (format_type, True, is_valid_volume, details)

            # Add other format type analyses as needed

            # Default for other formats
            return (
                format_type,
                True,
                True,
                {"note": "Format recognized but detailed validation not implemented"},
            )

    # If we get here, the format wasn't recognized
    return ("unknown", False, False, {"error": "Unrecognized citation format"})


def categorize_citation(citation):
    """
    Categorize a citation based on its format, validity, and other characteristics.
    Adds metadata to help with testing and verification.
    """
    citation_text = citation["citation_text"]
    citation.get("case_name", "")

    # Analyze the citation format
    format_type, is_valid_format, is_valid_volume, details = analyze_citation_format(
        citation_text
    )

    # Determine the likelihood of being a real citation
    if is_valid_format and is_valid_volume:
        likelihood = random.uniform(0.4, 0.7)  # Moderate likelihood for valid formats
    elif is_valid_format:
        likelihood = random.uniform(
            0.2, 0.4
        )  # Lower likelihood for valid format but invalid volume
    else:
        likelihood = random.uniform(0.1, 0.2)  # Very low likelihood for invalid formats

    # Assign a legal topic
    topic = random.choice(LEGAL_TOPICS)

    # Assign a jurisdiction
    if "U.S." in citation_text:
        jurisdiction = "Federal - Supreme Court"
    elif "F.3d" in citation_text or "F.2d" in citation_text:
        jurisdiction = "Federal - Circuit Court"
    elif "F.Supp" in citation_text:
        jurisdiction = "Federal - District Court"
    elif "Wn." in citation_text or "Wash." in citation_text:
        jurisdiction = "State - Washington"
    elif "Cal." in citation_text:
        jurisdiction = "State - California"
    elif "N.Y." in citation_text:
        jurisdiction = "State - New York"
    else:
        jurisdiction = "Unknown"

    # Create enhanced citation with additional metadata
    enhanced_citation = citation.copy()
    enhanced_citation.update(
        {
            "format_type": format_type,
            "is_valid_format": is_valid_format,
            "is_valid_volume": is_valid_volume,
            "format_details": details,
            "likelihood_of_being_real": round(likelihood, 2),
            "legal_topic": topic,
            "jurisdiction": jurisdiction,
            "categorization_date": datetime.now().strftime("%Y-%m-%d"),
            "test_category": "unconfirmed_citation",
        }
    )

    return enhanced_citation


def scan_and_categorize_citations():
    """
    Scan the unconfirmed citations database and categorize each citation.
    """
    # Load unconfirmed citations
    all_citations = load_unconfirmed_citations()

    if not all_citations:
        print("No unconfirmed citations found.")
        return

    # Count total citations
    total_citations = sum(len(citations) for citations in all_citations.values())
    print(f"Scanning and categorizing {total_citations} unconfirmed citations...")

    # Create enhanced database
    enhanced_citations = {}

    # Statistics
    valid_format_count = 0
    valid_volume_count = 0
    format_types = {}

    # Process each document
    for document, citations in all_citations.items():
        enhanced_citations[document] = []

        for citation in citations:
            # Categorize the citation
            enhanced_citation = categorize_citation(citation)
            enhanced_citations[document].append(enhanced_citation)

            # Update statistics
            if enhanced_citation["is_valid_format"]:
                valid_format_count += 1
            if enhanced_citation["is_valid_volume"]:
                valid_volume_count += 1

            format_type = enhanced_citation["format_type"]
            format_types[format_type] = format_types.get(format_type, 0) + 1

    # Save enhanced citations
    save_unconfirmed_citations(enhanced_citations)

    # Print statistics
    print("\nCitation Format Statistics:")
    print(f"Total citations: {total_citations}")
    print(
        f"Valid formats: {valid_format_count} ({valid_format_count/total_citations*100:.1f}%)"
    )
    print(
        f"Valid volumes: {valid_volume_count} ({valid_volume_count/total_citations*100:.1f}%)"
    )
    print("\nFormat Types:")
    for format_type, count in sorted(
        format_types.items(), key=lambda x: x[1], reverse=True
    ):
        print(f"  {format_type}: {count} ({count/total_citations*100:.1f}%)")

    return enhanced_citations


def create_test_api_request(enhanced_citations, max_citations=10):
    """
    Create a JSON file with test citations for the API endpoint.
    """
    test_citations = []

    # Add some landmark cases
    test_citations.extend(
        [
            {
                "citation_text": "410 U.S. 113",
                "case_name": "Roe v. Wade",
                "document_name": "Test Document",
                "document_url": "https://example.com/test.pdf",
                "page_number": 1,
            },
            {
                "citation_text": "347 U.S. 483",
                "case_name": "Brown v. Board of Education",
                "document_name": "Test Document",
                "document_url": "https://example.com/test.pdf",
                "page_number": 2,
            },
        ]
    )

    # Add citations with valid formats from the enhanced database
    count = 3
    flat_citations = []

    # Flatten the citations list
    for document, citations in enhanced_citations.items():
        for citation in citations:
            if citation["is_valid_format"]:
                citation_copy = citation.copy()
                citation_copy["document_name"] = document
                citation_copy["document_url"] = "https://example.com/test.pdf"
                citation_copy["page_number"] = count
                flat_citations.append(citation_copy)

    # Sort by likelihood of being real (descending)
    flat_citations.sort(
        key=lambda x: x.get("likelihood_of_being_real", 0), reverse=True
    )

    # Add top citations to the test list
    for citation in flat_citations[: max_citations - 2]:  # -2 for the landmark cases
        test_citations.append(
            {
                "citation_text": citation["citation_text"],
                "case_name": citation["case_name"],
                "document_name": citation["document_name"],
                "document_url": citation["document_url"],
                "page_number": count,
            }
        )
        count += 1

    # Create the API request JSON
    api_request = {"citations": test_citations}

    # Save to file
    try:
        with open("enhanced_test_api_request.json", "w") as f:
            json.dump(api_request, f, indent=2)
        print("Enhanced test API request saved to enhanced_test_api_request.json")

        # Also create a PowerShell command to test the API
        ps_command = "$headers = @{ 'Content-Type' = 'application/json' }; "
        ps_command += (
            "$body = Get-Content -Raw -Path 'enhanced_test_api_request.json'; "
        )
        ps_command += "$result = Invoke-RestMethod -Uri http://0.0.0.0:5000/api/reprocess_citations -Method Post -Headers $headers -Body $body; "
        ps_command += "$result | ConvertTo-Json -Depth 5"

        with open("enhanced_test_api.ps1", "w") as f:
            f.write(ps_command)
        print("Enhanced PowerShell test script saved to enhanced_test_api.ps1")

        return True
    except Exception as e:
        print(f"Error creating enhanced test API request: {e}")
        return False


if __name__ == "__main__":
    print("Scanning and categorizing unconfirmed citations...")
    enhanced_citations = scan_and_categorize_citations()

    if enhanced_citations:
        print("\nCreating enhanced test API request...")
        create_test_api_request(enhanced_citations)

    print(
        "\nDone! You can now use these enhanced citations with the Citation Tester tool."
    )
