"""
Enhanced Multi-Source Verifier

This module provides an enhanced citation verification system that uses multiple sources
and advanced techniques to validate legal citations.
"""

import os
import json
import logging
import requests
import re
import time
import sqlite3
import datetime
import importlib.util
import concurrent.futures
from typing import Dict, Any, Optional, List
from src.citation_format_utils import apply_washington_spacing_rules
from urllib.parse import quote
from bs4 import BeautifulSoup
import redis
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging
logger = logging.getLogger(__name__)


class EnhancedMultiSourceVerifier:
    """
    An enhanced citation verifier that uses multiple sources and techniques
    to validate legal citations with higher accuracy.
    """

    def __init__(self):
        """Initialize the enhanced multi-source verifier."""
        self.logger = logging.getLogger(__name__)
        self.config = self._load_config()
        self.db_path = self.config.get("database_path", "data/citations.db")
        self.courtlistener_api_key = self.config.get("courtlistener_api_key")
        self.cache_manager = get_cache_manager()
        
        # Initialize database connection pool
        self._init_database()
        
        # Initialize connection pool for HTTP requests
        self.session = self._create_session()
        
        # Request cache for API calls
        self.request_cache = {}
        self.cache_ttl = 3600  # 1 hour cache
        
        # Performance tracking
        self.stats = {
            'api_calls': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'total_time': 0
        }

    def _load_config(self):
        """Load configuration from config.json."""
        config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "config.json"
        )
        try:
            with open(config_path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {}

    def _init_database(self):
        """Initialize SQLite database with proper schema."""
        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Check if citations table exists
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='citations'")
                table_exists = cursor.fetchone() is not None
                
                if not table_exists:
                    # Create citations table with the existing schema
                    cursor.execute('''
                        CREATE TABLE citations (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            citation_text TEXT UNIQUE NOT NULL,
                            case_name TEXT,
                            year INTEGER,
                            parallel_citations TEXT,
                            verification_result TEXT,
                            found BOOLEAN DEFAULT FALSE,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')
                else:
                    # Table exists, check if we need to add new columns
                    cursor.execute("PRAGMA table_info(citations)")
                    existing_columns = [col[1] for col in cursor.fetchall()]
                    
                    # Add missing columns if they don't exist
                    try:
                        if 'parallel_citations' not in existing_columns:
                            cursor.execute('ALTER TABLE citations ADD COLUMN parallel_citations TEXT')
                    except:
                        pass  # Column might already exist
                        
                    try:
                        if 'verification_result' not in existing_columns:
                            cursor.execute('ALTER TABLE citations ADD COLUMN verification_result TEXT')
                    except:
                        pass  # Column might already exist
                        
                    try:
                        if 'found' not in existing_columns:
                            cursor.execute('ALTER TABLE citations ADD COLUMN found BOOLEAN DEFAULT FALSE')
                    except:
                        pass  # Column might already exist
                        
                    try:
                        if 'updated_at' not in existing_columns:
                            cursor.execute('ALTER TABLE citations ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
                    except:
                        pass  # Column might already exist
                
                conn.commit()
                logger.info("SQLite database initialized")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")

    def _normalize_citation(self, citation):
        """Normalize citation format for better matching.

        This method normalizes citations by:
        1. Removing extra whitespace
        2. Applying Washington citation spacing rules
        3. Standardizing Washington citations (Wn. -> Wash.)
        4. Preserving reporter series (e.g., P.3d, F.4th)
        5. Handling international citations
        6. Standardizing regional reporters
        7. Handling edge cases and variations

        Args:
            citation (str): The citation to normalize

        Returns:
            str: The normalized citation
        """
        if not citation or not isinstance(citation, str):
            return ""

        # Replace multiple spaces with a single space and trim
        normalized = re.sub(r"\s+", " ", citation.strip())

        # Apply Washington citation spacing rules
        normalized = apply_washington_spacing_rules(normalized)

        # Normalize Washington citations (Wn. -> Wash.)
        normalized = re.sub(r"Wn\.\s*App\.", "Wash. App.", normalized)
        normalized = re.sub(r"Wn\.", "Wash.", normalized)

        # Standardize regional reporters
        normalized = re.sub(r"Cal\.\s*App\.", "Cal. App.", normalized)
        normalized = re.sub(r"Cal\.\s*Rptr\.", "Cal. Rptr.", normalized)
        normalized = re.sub(r"N\.Y\.\s*App\.", "N.Y. App.", normalized)
        normalized = re.sub(r"Tex\.\s*App\.", "Tex. App.", normalized)
        normalized = re.sub(r"Fla\.\s*App\.", "Fla. App.", normalized)
        normalized = re.sub(r"Ill\.\s*App\.", "Ill. App.", normalized)
        normalized = re.sub(r"Ohio\s*App\.", "Ohio App.", normalized)
        normalized = re.sub(r"Mich\.\s*App\.", "Mich. App.", normalized)
        normalized = re.sub(r"Pa\.\s*Super\.", "Pa. Super.", normalized)
        normalized = re.sub(r"Mass\.\s*App\.", "Mass. App.", normalized)

        # Handle international citations
        normalized = re.sub(r"UKSC", "UKSC", normalized)  # UK Supreme Court
        normalized = re.sub(r"EWCA\s+Civ", "EWCA Civ", normalized)  # England and Wales Court of Appeal
        normalized = re.sub(r"EWHC", "EWHC", normalized)  # England and Wales High Court
        normalized = re.sub(r"SCC", "SCC", normalized)  # Supreme Court of Canada
        normalized = re.sub(r"FCA", "FCA", normalized)  # Federal Court of Appeal (Canada)
        normalized = re.sub(r"FC", "FC", normalized)  # Federal Court (Canada)
        normalized = re.sub(r"HCA", "HCA", normalized)  # High Court of Australia
        normalized = re.sub(r"FCA", "FCA", normalized)  # Federal Court of Australia

        # Handle special characters and edge cases
        normalized = re.sub(r"[\u2013\u2014]", "-", normalized)  # Replace em/en dashes with hyphens
        normalized = re.sub(r"[\u2018\u2019]", "'", normalized)  # Replace smart quotes
        normalized = re.sub(r"[\u201C\u201D]", '"', normalized)  # Replace smart quotes
        normalized = re.sub(r"[\u00A0]", " ", normalized)  # Replace non-breaking spaces

        # Clean up common formatting issues
        normalized = re.sub(r"\s*,\s*", ", ", normalized)  # Standardize commas
        normalized = re.sub(r"\s+v\.?\s+", " v. ", normalized)  # Standardize v.
        normalized = re.sub(r"\s+&\.?\s+", " & ", normalized)  # Standardize &
        normalized = re.sub(r"\s+vs\.?\s+", " v. ", normalized)  # Standardize vs.
        normalized = re.sub(r"\s+versus\s+", " v. ", normalized)  # Standardize versus

        # Handle parentheses and brackets
        normalized = re.sub(r"\(\s*", "(", normalized)  # Remove space after opening parenthesis
        normalized = re.sub(r"\s*\)", ")", normalized)  # Remove space before closing parenthesis
        normalized = re.sub(r"\[\s*", "[", normalized)  # Remove space after opening bracket
        normalized = re.sub(r"\s*\]", "]", normalized)  # Remove space before closing bracket

        # Handle periods and abbreviations
        normalized = re.sub(r"\.\s*\.", "..", normalized)  # Fix double periods
        normalized = re.sub(r"\.\s*\.\s*\.", "...", normalized)  # Fix triple periods

        return normalized

    def _extract_citation_components(self, citation):
        """Extract components from a citation for flexible matching.

        Handles various citation formats including:
        - Standard: 123 Wn.2d 456
        - Pinpoint: 123 Wn.2d 456, 459
        - Parallel: 123 Wn.2d 456, 789 P.2d 123
        - Short form: Id. at 459
        - International: [2020] UKSC 1, [2019] SCC 1
        - Regional: 123 Cal. App. 4th 456, 123 N.Y. App. Div. 456
        - Federal: 123 F.3d 456, 123 F.Supp.2d 456
        - State: 123 P.3d 456, 123 A.3d 456

        Args:
            citation (str): The citation to parse

        Returns:
            dict: Dictionary containing citation components
        """
        if not citation or not isinstance(citation, str):
            return {"volume": "", "reporter": "", "page": "", "court": "", "year": ""}

        components = {
            "volume": "",
            "reporter": "",
            "page": "",
            "court": "",
            "year": "",
            "pinpoint": "",
            "parallel_citations": [],
        }

        try:
            # Handle short form citations (e.g., "Id. at 459")
            if citation.lower().startswith(("id.", "idem")):
                components["short_form"] = True
                # Extract pinpoint reference if present
                pinpoint_match = re.search(r"(?:at\s+)(\d+)", citation, re.IGNORECASE)
                if pinpoint_match:
                    components["pinpoint"] = pinpoint_match.group(1)
                return components

            # Handle international citations with brackets [2020] UKSC 1
            international_match = re.search(r"\[(\d{4})\]\s+([A-Z]{2,4})\s+(\d+)", citation)
            if international_match:
                components["year"] = international_match.group(1)
                components["reporter"] = international_match.group(2)
                components["page"] = international_match.group(3)
                # Determine court based on international reporter
                reporter = components["reporter"].upper()
                if reporter == "UKSC":
                    components["court"] = "UK Supreme Court"
                elif reporter == "EWCA":
                    components["court"] = "England and Wales Court of Appeal"
                elif reporter == "EWHC":
                    components["court"] = "England and Wales High Court"
                elif reporter == "SCC":
                    components["court"] = "Supreme Court of Canada"
                elif reporter == "FCA":
                    components["court"] = "Federal Court of Appeal (Canada)"
                elif reporter == "FC":
                    components["court"] = "Federal Court (Canada)"
                elif reporter == "HCA":
                    components["court"] = "High Court of Australia"
                return components

            # Handle parallel citations (e.g., "123 Wn.2d 456, 789 P.2d 123")
            if "," in citation:
                parts = [p.strip() for p in citation.split(",")]
                if len(parts) > 1 and any(p[0].isdigit() for p in parts[1:]):
                    components["parallel_citations"] = [
                        p.strip() for p in parts[1:] if p.strip()
                    ]
                    citation = parts[0]  # Process the first citation normally

            # Enhanced volume, reporter, and page extraction
            # Handle various formats including regional reporters
            patterns = [
                # Standard format: 123 Wn.2d 456
                r"(\d+)\s+([A-Za-z\.\s]+?)(?:\s+(\d+))?(?:\s*,\s*(\d+))?",
                # Federal format: 123 F.3d 456
                r"(\d+)\s+(F\.\d+[a-z]?)\s+(\d+)",
                # Regional format: 123 Cal. App. 4th 456
                r"(\d+)\s+([A-Za-z\.\s]+?)\s+(\d+[a-z]+)\s+(\d+)",
                # State format: 123 P.3d 456
                r"(\d+)\s+([A-Z]\.\d+[a-z]?)\s+(\d+)",
            ]

            for pattern in patterns:
                volume_reporter_page = re.search(pattern, citation)
                if volume_reporter_page:
                    components["volume"] = volume_reporter_page.group(1)
                    components["reporter"] = volume_reporter_page.group(2).strip()

                    # Handle both main page and pinpoint (e.g., "123 Wn.2d 456, 459")
                    if len(volume_reporter_page.groups()) >= 4 and volume_reporter_page.group(4):  # Has pinpoint
                        components["page"] = volume_reporter_page.group(3)
                        components["pinpoint"] = volume_reporter_page.group(4)
                    elif len(volume_reporter_page.groups()) >= 3 and volume_reporter_page.group(3):  # Just page number
                        components["page"] = volume_reporter_page.group(3)
                    break

            # Extract year if present (e.g., "(1999)" or ", 1999")
            year_match = re.search(r"\((\d{4})\)|,\s*(\d{4})\b", citation)
            if year_match:
                components["year"] = year_match.group(1) or year_match.group(2)

            # Enhanced court determination based on reporter
            reporter = components["reporter"].lower()
            
            # Washington courts
            if "wn. app" in reporter or "wash. app" in reporter:
                components["court"] = "Washington Court of Appeals"
            elif "wn." in reporter or "wash." in reporter:
                components["court"] = "Washington Supreme Court"
            
            # Federal courts
            elif "u.s." in reporter:
                components["court"] = "United States Supreme Court"
            elif "f.supp" in reporter:
                components["court"] = "United States District Court"
            elif "f." in reporter:
                components["court"] = "United States Court of Appeals"
            
            # Regional courts
            elif "cal. app" in reporter:
                components["court"] = "California Court of Appeal"
            elif "cal. rptr" in reporter:
                components["court"] = "California Reporter"
            elif "n.y. app" in reporter:
                components["court"] = "New York Appellate Division"
            elif "tex. app" in reporter:
                components["court"] = "Texas Court of Appeals"
            elif "fla. app" in reporter:
                components["court"] = "Florida Court of Appeal"
            elif "ill. app" in reporter:
                components["court"] = "Illinois Appellate Court"
            elif "ohio app" in reporter:
                components["court"] = "Ohio Court of Appeals"
            elif "mich. app" in reporter:
                components["court"] = "Michigan Court of Appeals"
            elif "pa. super" in reporter:
                components["court"] = "Pennsylvania Superior Court"
            elif "mass. app" in reporter:
                components["court"] = "Massachusetts Appeals Court"
            
            # State courts by reporter
            elif "p." in reporter and "d" in reporter:
                components["court"] = "Pacific Reporter"
            elif "a." in reporter and "d" in reporter:
                components["court"] = "Atlantic Reporter"
            elif "s." in reporter and "e" in reporter:
                components["court"] = "Southeast Reporter"
            elif "s." in reporter and "w" in reporter:
                components["court"] = "Southwest Reporter"
            elif "n." in reporter and "e" in reporter:
                components["court"] = "Northeast Reporter"
            elif "n." in reporter and "w" in reporter:
                components["court"] = "Northwest Reporter"

            # Clean up reporter abbreviation
            components["reporter"] = (
                components["reporter"].replace(" ", "").replace("..", ".")
            )

        except Exception as e:
            logger.warning(
                f"Error extracting citation components from '{citation}': {e}"
            )

        return components

    def _check_cache(self, citation):
        """Check if the citation is in the cache."""
        cache_file = os.path.join(
            self.cache_dir,
            f"{self._normalize_citation(citation).replace(' ', '_')}.json",
        )
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading cache for citation '{citation}': {e}")
        return None

    def _save_to_cache(self, citation, result):
        """Save the verification result to the cache."""
        cache_file = os.path.join(
            self.cache_dir,
            f"{self._normalize_citation(citation).replace(' ', '_')}.json",
        )
        try:
            with open(cache_file, "w") as f:
                json.dump(result, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving cache for citation '{citation}': {e}")

    def _save_to_database(self, citation, result):
        """
        Save the verification result to the database, including parallel citations and year metadata.

        Args:
            citation (str): The original citation
            result (dict): Verification result with optional parallel_citations list and metadata
        """
        if not citation or not isinstance(citation, str):
            logger.error("Invalid citation provided to _save_to_database")
            return False

        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Create tables if they don't exist with the correct schema
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS citations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    citation_text TEXT NOT NULL UNIQUE,
                    case_name TEXT,
                    confidence REAL,
                    found BOOLEAN,
                    explanation TEXT,
                    source TEXT,
                    source_document TEXT,
                    url TEXT,
                    context TEXT,
                    year TEXT,
                    date_filed TEXT,
                    court TEXT,
                    docket_number TEXT,
                    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Create parallel_citations table if it doesn't exist
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS parallel_citations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    citation_id INTEGER NOT NULL,
                    citation TEXT NOT NULL,
                    reporter TEXT,
                    category TEXT,
                    year TEXT,
                    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (citation_id) REFERENCES citations(id) ON DELETE CASCADE,
                    UNIQUE(citation_id, citation)
                )
            """
            )

            # Get current schema to handle any missing columns
            cursor.execute("PRAGMA table_info(citations)")
            columns = {column[1].lower(): column[1] for column in cursor.fetchall()}

            # Add any missing columns with proper error handling
            columns_to_add = [
                ("case_name", "TEXT"),
                ("found", "BOOLEAN"),
                ("explanation", "TEXT"),
                ("source", "TEXT"),
                ("source_document", "TEXT"),
                ("url", "TEXT"),
                ("context", "TEXT"),
                ("year", "TEXT"),
                ("date_filed", "TEXT"),
                ("court", "TEXT"),
                ("docket_number", "TEXT"),
            ]

            for col_name, col_type in columns_to_add:
                if col_name not in columns:
                    try:
                        cursor.execute(
                            f"ALTER TABLE citations ADD COLUMN {col_name} {col_type}"
                        )
                        logger.info(
                            f"Added missing column {col_name} to citations table"
                        )
                    except sqlite3.Error as e:
                        logger.warning(f"Error adding column {col_name}: {e}")

            # Extract year from various sources
            year = ""
            date_filed = result.get("date_filed", "")
            
            # Try to extract year from date_filed first
            if date_filed:
                try:
                    # Handle various date formats
                    if isinstance(date_filed, str):
                        # Try to extract year from ISO format (YYYY-MM-DD)
                        year_match = re.search(r'(\d{4})', date_filed)
                        if year_match:
                            year = year_match.group(1)
                except Exception as e:
                    logger.warning(f"Error extracting year from date_filed '{date_filed}': {e}")
            
            # If no year from date_filed, try metadata
            if not year:
                metadata = result.get("metadata", {})
                if metadata.get("year"):
                    year = str(metadata["year"])
                elif metadata.get("date_filed"):
                    try:
                        year_match = re.search(r'(\d{4})', str(metadata["date_filed"]))
                        if year_match:
                            year = year_match.group(1)
                    except Exception as e:
                        logger.warning(f"Error extracting year from metadata: {e}")

            # Prepare the data for insertion/update
            case_name = result.get("case_name", "")
            found = bool(result.get("verified", False))
            explanation = f"Verified via {result.get('source', 'unknown')} on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            source = result.get("source", "")
            url = result.get("absolute_url", result.get("url", ""))
            source_doc = result.get("source_document", "")
            court = result.get("court", "")
            docket_number = result.get("docket_number", "")
            parallel_cites = result.get("parallel_citations", [])

            try:
                # First, insert or update the main citation
                cursor.execute(
                    """
                    INSERT INTO citations (
                        citation_text, case_name, found, explanation, 
                        source, url, source_document, context, year, date_filed, court, docket_number
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(citation_text) DO UPDATE SET
                        case_name = excluded.case_name,
                        found = excluded.found,
                        explanation = excluded.explanation,
                        source = excluded.source,
                        url = excluded.url,
                        source_document = excluded.source_document,
                        context = excluded.context,
                        year = excluded.year,
                        date_filed = excluded.date_filed,
                        court = excluded.court,
                        docket_number = excluded.docket_number
                    RETURNING id
                """,
                    (
                        citation,
                        case_name,
                        found,
                        explanation,
                        source,
                        url,
                        source_doc,
                        result.get("context", ""),
                        year,
                        date_filed,
                        court,
                        docket_number,
                    ),
                )

                # Get the citation ID
                row = cursor.fetchone()
                if not row:
                    raise Exception("Failed to get citation ID after insert/update")

                citation_id = row[0]

                # Handle parallel citations if they exist
                if parallel_cites and isinstance(parallel_cites, list):
                    # First, get existing parallel citations to determine what needs to be updated/inserted/deleted
                    cursor.execute(
                        """
                        SELECT citation FROM parallel_citations 
                        WHERE citation_id = ?
                    """,
                        (citation_id,),
                    )
                    existing_parallels = {row[0] for row in cursor.fetchall()}

                    # Process each parallel citation
                    for parallel in parallel_cites:
                        if not isinstance(parallel, dict):
                            continue

                        cite = parallel.get("citation", "").strip()
                        if not cite:
                            continue

                        # Extract year from parallel citation if available
                        parallel_year = ""
                        if parallel.get("year"):
                            parallel_year = str(parallel["year"])
                        elif parallel.get("date_filed"):
                            try:
                                year_match = re.search(r'(\d{4})', str(parallel["date_filed"]))
                                if year_match:
                                    parallel_year = year_match.group(1)
                            except Exception as e:
                                logger.warning(f"Error extracting year from parallel citation: {e}")

                        # Remove from existing_parallels set to track what needs to be deleted
                        if cite in existing_parallels:
                            existing_parallels.remove(cite)

                        # Insert or update the parallel citation
                        cursor.execute(
                            """
                            INSERT INTO parallel_citations (
                                citation_id, citation, reporter, category, year
                            ) VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(citation_id, citation) DO UPDATE SET
                                reporter = excluded.reporter,
                                category = excluded.category,
                                year = excluded.year
                        """,
                            (
                                citation_id,
                                cite,
                                parallel.get("reporter", ""),
                                parallel.get("category", ""),
                                parallel_year,
                            ),
                        )

                    # Delete any remaining parallel citations that weren't in the new list
                    if existing_parallels:
                        placeholders = ",".join(["?"] * len(existing_parallels))
                        cursor.execute(
                            f"""
                            DELETE FROM parallel_citations 
                            WHERE citation_id = ? 
                            AND citation IN ({placeholders})
                            """,
                            [citation_id] + list(existing_parallels),
                        )

                # Commit the transaction
                conn.commit()
                logger.debug(
                    f"Successfully saved verification result for citation '{citation}' to database with year '{year}' and {len(parallel_cites)} parallel citations"
                )
                return True

            except sqlite3.Error as e:
                conn.rollback()
                logger.error(f"Database error saving citation '{citation}': {e}")
                return False
            except Exception as e:
                conn.rollback()
                logger.error(f"Unexpected error saving citation '{citation}': {e}")
                return False

        except sqlite3.Error as e:
            logger.error(f"Database error saving citation '{citation}': {e}")
            if conn:
                conn.rollback()
            return False
        except Exception as e:
            logger.error(
                f"Error saving verification result for citation '{citation}': {e}"
            )
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    def _get_parallel_citations(self, case_data):
        """Extract parallel citations from case data.

        Handles CourtListener API v4 response format where citations might be in different fields.
        """
        parallel_cites = []
        if not case_data:
            return parallel_cites

        try:
            # Try to get citations from the case data
            citations = case_data.get("citations", [])

            # If no citations array, try to get from the opinion_cites field
            if not citations and "opinion_cites" in case_data:
                citations = [
                    cite
                    for cite in case_data["opinion_cites"]
                    if isinstance(cite, dict) and "cite" in cite
                ]

            # Process all found citations
            for cite in citations:
                # Skip if it's not a dictionary
                if not isinstance(cite, dict):
                    continue

                # Get the citation text from either 'cite' or 'citation' field
                citation_text = cite.get("cite") or cite.get("citation")
                if not citation_text:
                    continue

                # Add to parallel citations with available metadata
                parallel_cites.append(
                    {
                        "citation": citation_text,
                        # Try to get reporter from various possible fields
                        "reporter": cite.get("reporter")
                        or cite.get("reporter_name", ""),
                        # Try to get category or type
                        "category": cite.get("category") or cite.get("type", ""),
                        # Include any additional metadata that might be useful
                        "url": cite.get("resource_uri") or cite.get("url", ""),
                    }
                )

        except Exception as e:
            logger.error(f"Error extracting parallel citations: {e}")

        return parallel_cites

    def _clean_citation_for_lookup(self, citation: str) -> str:
        """
        Clean and standardize a citation for the lookup API.

        Args:
            citation (str): The citation to clean

        Returns:
            str: Cleaned citation string
        """
        if not citation:
            return ""

        # Remove any surrounding quotes and extra whitespace
        clean = citation.strip("\"'").strip()

        # Handle common citation formats
        # 1. Standard format: 123 F.4th 456
        # 2. With comma: 123 F.4th 456, 789
        # 3. With 'at': 123 F.4th 456, at 789
        parts = []
        for part in clean.split():
            # Remove any non-alphanumeric characters except periods and hyphens
            part = "".join(c for c in part if c.isalnum() or c in ".-")
            if part and part.lower() not in [
                "at",
                "p.",
            ]:  # Skip common connecting words
                parts.append(part)

        # Rejoin with single spaces
        return " ".join(parts)

    def _lookup_citation(self, citation: str) -> dict:
        """
        Look up a citation using the CourtListener Citation Lookup API.

        Args:
            citation (str): The citation to look up

        Returns:
            dict: Result with case information if found, or None if not found

        The API endpoint expects a POST request to /api/rest/v4/citation-lookup/
        with the citation in the request body as form data with key 'text'.

        Authentication is done via the Authorization header with a token.
        """
        if not citation:
            logger.debug("No citation provided for lookup")
            return None

        try:
            # Clean and prepare the citation for the API
            clean_citation = self._clean_citation_for_lookup(citation)
            if not clean_citation:
                logger.warning(f"Could not clean citation for lookup: {citation}")
                return None

            # Set up headers with authentication
            headers = {
                "Authorization": (
                    f"Token {self.courtlistener_api_key}"
                    if self.courtlistener_api_key
                    else ""
                ),
                "Content-Type": "application/json",
            }

            # Remove empty headers
            headers = {k: v for k, v in headers.items() if v}

            # Ensure we have an API key
            if not self.courtlistener_api_key:
                error_msg = "No CourtListener API key provided. Please set COURTLISTENER_API_KEY in your environment."
                logger.error(error_msg)
                return {
                    "verified": False,
                    "citation": clean_citation,
                    "error": error_msg,
                    "source": "CourtListener API",
                }

            # Build the API URL
            base_url = "https://www.courtlistener.com/api/rest/v4"
            endpoint = f"{base_url}/citation-lookup/"

            logger.info(f"Looking up citation with CourtListener API: {clean_citation}")

            try:
                # Make the API request to the citation lookup endpoint using POST with JSON data
                response = requests.post(
                    endpoint,
                    json={"citation": clean_citation},  # Send as JSON
                    headers=headers,
                    timeout=15,  # 15 second timeout
                )

                # Log the response status and headers for debugging
                logger.debug(f"Lookup status: {response.status_code}")

                # Handle rate limiting (429 Too Many Requests)
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 5))
                    logger.warning(f"Rate limited. Waiting {retry_after} seconds...")
                    time.sleep(retry_after + 1)
                    return self._lookup_citation(citation)  # Retry once

                # Handle other error status codes
                response.raise_for_status()

                # Parse the JSON response
                try:
                    data = response.json()
                    # Log the response data structure for debugging
                    logger.debug(
                        f"API Response: {json.dumps(data, indent=2)[:1000]}..."
                    )
                except json.JSONDecodeError as e:
                    error_msg = f"Failed to parse JSON response: {str(e)}"
                    # Safely log the response text to avoid Unicode encoding errors
                    try:
                        logger.error(f"{error_msg}. Response text: {response.text[:500]}")
                    except UnicodeEncodeError:
                        # If Unicode fails, log a safe version
                        safe_text = response.text[:500].encode('cp1252', errors='replace').decode('cp1252')
                        logger.error(f"{error_msg}. Response text (safe): {safe_text}")
                    return {
                        "verified": False,
                        "citation": clean_citation,
                        "error": error_msg,
                        "source": "CourtListener API",
                    }

                # Process the response based on the API version and structure
                if not data or not isinstance(data, dict):
                    error_msg = "Empty or invalid response from API"
                    logger.warning(f"{error_msg} for citation: {clean_citation}")
                    return {
                        "verified": False,
                        "citation": clean_citation,
                        "error": error_msg,
                        "source": "CourtListener API",
                    }

                # Process the response based on the structure
                result = self._process_courtlistener_result(clean_citation, data)

                if result and result.get("verified", False):
                    logger.info(
                        f"Successfully verified citation via lookup: {clean_citation}"
                    )
                    return result
                else:
                    error_msg = result.get(
                        "error", "Citation not found in CourtListener"
                    )
                    logger.info(
                        f"Citation not found via lookup: {clean_citation} - {error_msg}"
                    )
                    return {
                        "verified": False,
                        "citation": clean_citation,
                        "error": error_msg,
                        "source": "CourtListener API",
                    }

            except requests.exceptions.HTTPError as e:
                status_code = (
                    int(e.response.status_code)
                    if hasattr(e, "response") and e.response
                    else 0
                )
                error_msg = f"HTTP {status_code} error during citation lookup"

                if status_code == 400:
                    logger.warning(f"Bad request: {clean_citation} - {str(e)}")
                    error_msg = "Invalid citation format"
                elif status_code == 401:
                    error_msg = "Authentication failed. Please check your API key."
                    logger.error(error_msg)
                elif status_code == 403:
                    error_msg = "Access forbidden. Your API key may not have the required permissions."
                    logger.error(error_msg)
                elif status_code == 404:
                    error_msg = f"Citation not found: {clean_citation}"
                    logger.debug(error_msg)
                elif status_code >= 500:
                    error_msg = f"Server error during citation lookup: {status_code}"
                    logger.error(error_msg)
                else:
                    error_msg = f"HTTP {status_code} error: {str(e)}"

                # Log response details if available
                if hasattr(e, "response") and e.response is not None:
                    try:
                        error_body = e.response.json()
                        logger.debug(
                            f"Error response: {json.dumps(error_body, indent=2)}"
                        )
                        error_msg = error_body.get("detail", error_msg)
                    except:
                        error_text = e.response.text[:500]
                        # Safely log the error text to avoid Unicode encoding errors
                        try:
                            logger.debug(f"Error response (non-JSON): {error_text}")
                        except UnicodeEncodeError:
                            # If Unicode fails, log a safe version
                            safe_text = error_text.encode('cp1252', errors='replace').decode('cp1252')
                            logger.debug(f"Error response (non-JSON, safe): {safe_text}")
                        error_msg = f"{error_msg}: {error_text}"

                return {
                    "verified": False,
                    "citation": clean_citation,
                    "error": error_msg,
                    "source": "CourtListener API",
                }

        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {str(e)}")

        except Exception as e:
            logger.error(
                f"Unexpected error in citation lookup: {str(e)}", exc_info=True
            )

        return None

    def _verify_with_courtlistener(self, citation: str) -> dict:
        """
        Verify a citation using the CourtListener API v4.
        First tries the Citation Lookup API, then falls back to search.

        Args:
            citation (str): The citation to verify

        Returns:
            dict: Verification result with parallel citations if found.
                 Always contains 'verified' (bool), 'citation' (str), and 'source' (str) keys.
        """
        # First try the Citation Lookup API
        lookup_result = self._lookup_citation(citation)
        if lookup_result:
            processed = self._process_courtlistener_result(citation, lookup_result)
            if isinstance(processed, dict) and processed.get("verified", False):
                return processed

        # If lookup failed, try exact match search
        result = self._search_courtlistener_exact(citation)

        # If exact match failed, try flexible search
        if not result.get("verified", False):
            flexible_result = self._search_courtlistener_flexible(citation)
            if flexible_result.get("verified", False):
                return flexible_result

        return result

    def _search_courtlistener_exact(self, citation: str) -> dict:
        """Search for an exact citation match in CourtListener.

        Returns:
            dict: A dictionary with verification results, always containing 'verified' and 'citation' keys
        """
        result = {
            "verified": False,
            "citation": citation,
            "source": "CourtListener",
            "parallel_citations": [],
        }

        try:
            # Set up headers if not already set
            if not hasattr(self, "headers"):
                self.headers = {
                    "Authorization": (
                        f"Token {self.courtlistener_api_key}"
                        if self.courtlistener_api_key
                        else ""
                    ),
                    "Content-Type": "application/json",
                }

            # Set base URL if not already set
            if not hasattr(self, "courtlistener_base_url"):
                self.courtlistener_base_url = (
                    "https://www.courtlistener.com/api/rest/v4"
                )

            # Clean and prepare the citation for exact matching
            clean_citation = citation.strip("\"'").strip()

            # For v4 API, try an exact match with the full citation
            # First clean the citation - remove spaces and standardize format
            clean_citation = clean_citation.replace(" ", "").upper()

            # Build query parameters for exact match
            params = {
                "q": f"citation:({clean_citation})",  # No quotes around the citation
                "type": "o",  # Opinions only
                "order_by": "score desc",  # Best match first
                "filed_after": "1750-01-01",  # Include older cases
                "page_size": 1,  # We only need one match for exact search
            }

            # Make the API request to the search endpoint
            response = requests.get(
                f"{self.courtlistener_base_url}/search/",
                headers={
                    k: v for k, v in self.headers.items() if v
                },  # Remove empty headers
                params=params,
                timeout=15,
            )
            response.raise_for_status()

            data = response.json()
            if (
                isinstance(data, dict)
                and data.get("count", 0) > 0
                and isinstance(data.get("results"), list)
                and data["results"]
            ):
                processed_result = self._process_courtlistener_result(
                    citation, data["results"][0]
                )
                if isinstance(processed_result, dict):
                    return processed_result
                else:
                    result["error"] = "Invalid response format from CourtListener"
                    logger.error(
                        f"Unexpected response format from _process_courtlistener_result: {type(processed_result)}"
                    )
            else:
                result["warning"] = "No exact match found in CourtListener"

        except requests.exceptions.RequestException as e:
            error_msg = f"Request to CourtListener failed: {str(e)}"
            logger.error(error_msg)
            result["error"] = error_msg
        except Exception as e:
            error_msg = f"Unexpected error in exact search: {str(e)}"
            logger.error(error_msg, exc_info=True)
            result["error"] = error_msg

        return result

    def _search_courtlistener_flexible(self, citation: str) -> dict:
        """
        Perform a more flexible search using citation components.

        Returns:
            dict: A dictionary with verification results, always containing 'verified' and 'citation' keys
        """
        result = {
            "verified": False,
            "citation": citation,
            "source": "CourtListener",
            "parallel_citations": [],
        }

        try:
            components = self._extract_citation_components(citation)
            if not components:
                result["error"] = "Could not extract citation components"
                return result

            # For v4 API, build a structured query using the components
            search_terms = []

            # Clean and prepare components
            if "volume" in components and components["volume"]:
                search_terms.append(f'citation.volume:{components["volume"]}')

            if "reporter" in components and components["reporter"]:
                # Clean reporter - remove periods and spaces, convert to uppercase
                reporter = (
                    components["reporter"].replace(".", "").replace(" ", "").upper()
                )
                if reporter:  # Only add if not empty after cleaning
                    search_terms.append(f"citation.reporter:{reporter}")

            if "page" in components and components["page"]:
                search_terms.append(f'citation.page:{components["page"]}')

            if not search_terms:
                result["error"] = "No valid search terms could be generated"
                return result

            # Join terms with space for OR logic (more flexible matching)
            search_query = " ".join(search_terms)

            # Set up parameters for v4 API
            params = {
                "q": search_query,
                "type": "o",  # Opinions only
                "order_by": "score desc",  # Best match first
                "filed_after": "1750-01-01",
                "page_size": 5,  # Get more results to find the best match
            }

            # Make the API request to the v4 search endpoint
            response = requests.get(
                f"{self.courtlistener_base_url}/search/",
                headers={
                    k: v for k, v in self.headers.items() if v
                },  # Remove empty headers
                params=params,
                timeout=15,
            )
            response.raise_for_status()

            data = response.json()
            if data.get("count", 0) > 0 and isinstance(data.get("results"), list):
                # Try to find the best match among results
                for result_item in data["results"]:
                    if self._is_best_match(citation, result_item, components):
                        processed = self._process_courtlistener_result(
                            citation, result_item
                        )
                        if isinstance(processed, dict):
                            return processed

                result["warning"] = (
                    "Matching results found but none matched all criteria"
                )
            else:
                result["warning"] = "No matching results found"

        except requests.exceptions.RequestException as e:
            error_msg = f"Request error in flexible search: {str(e)}"
            logger.error(error_msg)
            result["error"] = error_msg
        except Exception as e:
            error_msg = f"Unexpected error in flexible search: {str(e)}"
            logger.error(error_msg)
            result["error"] = error_msg

        return result

    def _is_best_match(self, citation: str, result: dict, components: dict) -> bool:
        """Determine if a search result is the best match for the citation."""
        # Check if any of the citation fields match exactly
        if (
            "citation" in result
            and result["citation"]
            and citation.lower() in [c.lower() for c in result["citation"].split("; ")]
        ):
            return True

        # Check if the components match
        result_components = self._extract_citation_components(
            result.get("citation", "")
        )
        if not result_components:
            return False

        # Compare key components - ensure both values are strings before comparison
        for key in ["volume", "reporter", "page"]:
            if components.get(key) and result_components.get(key):
                # Convert both values to strings to avoid type comparison errors
                comp_val = str(components[key]).lower()
                result_val = str(result_components[key]).lower()
                if comp_val != result_val:
                    return False

        return True

    def _process_courtlistener_result(
        self, original_citation: str, result: dict
    ) -> dict:
        """
        Process a successful CourtListener API result.

        Args:
            original_citation (str): The original citation that was searched for
            result (dict): The API response from CourtListener

        Returns:
            dict: Processed result with citation details and verification status
        """
        if not result or not isinstance(result, dict):
            return {
                "verified": False,
                "citation": original_citation,
                "error": "Invalid API response format",
                "source": "CourtListener API",
            }

        try:
            # Handle different response formats
            # 1. Direct citation lookup response
            if (
                "citations" in result
                and isinstance(result["citations"], list)
                and result["citations"]
            ):
                # Process the first citation in the list
                return self._process_citation_data(
                    original_citation, result["citations"][0]
                )

            # 2. Search result with 'results' array
            elif (
                "results" in result
                and isinstance(result["results"], list)
                and result["results"]
            ):
                # Process the first result
                return self._process_citation_data(
                    original_citation, result["results"][0]
                )

            # 3. Direct case data (from citation lookup v4)
            elif any(key in result for key in ["citation", "caseName", "resource_uri"]):
                return self._process_citation_data(original_citation, result)

            # If we get here, we couldn't process the response
            logger.warning(
                f"Unrecognized CourtListener API response format for {original_citation}"
            )
            return {
                "verified": False,
                "citation": original_citation,
                "error": "Unrecognized API response format",
                "source": "CourtListener API",
            }

        except Exception as e:
            error_msg = f"Error processing CourtListener result: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                "verified": False,
                "citation": original_citation,
                "error": error_msg,
                "source": "CourtListener API",
            }

    def _process_citation_data(
        self, original_citation: str, citation_data: dict
    ) -> dict:
        """
        Process citation data from CourtListener API into a standardized format.

        Args:
            original_citation (str): The original citation that was searched for
            citation_data (dict): The citation data from the API

        Returns:
            dict: Standardized citation result
        """
        try:
            # Extract case information with fallbacks for different API versions
            case_name = (
                citation_data.get("caseName")
                or citation_data.get("name")
                or "Unknown Case"
            )
            docket_number = citation_data.get("docketNumber") or citation_data.get(
                "docket_number", ""
            )

            # Handle court information which might be a string or object
            court = ""
            court_data = citation_data.get("court") or {}
            if isinstance(court_data, dict):
                court = court_data.get("name") or court_data.get("full_name") or ""
            elif isinstance(court_data, str):
                court = court_data

            # Get the main citation, falling back to the original if not found
            citation = citation_data.get("citation") or original_citation

            # Extract parallel citations if available
            parallel_citations = []
            if "parallel_citations" in citation_data and isinstance(
                citation_data["parallel_citations"], list
            ):
                parallel_citations = citation_data["parallel_citations"]
            elif "citations" in citation_data and isinstance(
                citation_data["citations"], list
            ):
                parallel_citations = citation_data["citations"]

            # Get the URL, falling back to resource_uri or absolute_url
            url = citation_data.get("absolute_url") or citation_data.get(
                "resource_uri", ""
            )
            if url and not url.startswith(("http://", "https://")):
                url = f"https://www.courtlistener.com{url}"

            # Get the date, trying multiple possible fields
            date_filed = ""
            for date_field in [
                "date_filed",
                "decision_date",
                "date_modified",
                "date_created",
            ]:
                if date_field in citation_data and citation_data[date_field]:
                    date_filed = citation_data[date_field]
                    break

            # Extract year from date_filed
            year = ""
            if date_filed:
                try:
                    if isinstance(date_filed, str):
                        year_match = re.search(r'(\d{4})', date_filed)
                        if year_match:
                            year = year_match.group(1)
                except Exception as e:
                    logger.warning(f"Error extracting year from date_filed '{date_filed}': {e}")

            # Format the result with all available metadata
            processed = {
                "verified": True,
                "citation": citation,
                "original_citation": original_citation,
                "case_name": case_name,
                "docket_number": docket_number,
                "court": court,
                "source": "CourtListener API",
                "url": url,
                "date_filed": date_filed,
                "parallel_citations": parallel_citations,
                "metadata": {
                    "api_version": "v4",
                    "result_type": citation_data.get("resource_type", "case"),
                    "id": str(citation_data.get("id", "")),
                    "timestamp": datetime.datetime.utcnow().isoformat(),
                    "jurisdiction": citation_data.get("jurisdiction", ""),
                    "reporter": citation_data.get("reporter", ""),
                    "volume": citation_data.get("volume", ""),
                    "page": citation_data.get("page", ""),
                },
            }

            # Add year to both top-level and metadata if available
            if year:
                processed["year"] = year
                processed["metadata"]["year"] = year

            # Add any additional fields that might be useful
            for field in [
                "precedential_status",
                "citation_count",
                "cite_count",
                "needs_case_date",
            ]:
                if field in citation_data:
                    processed["metadata"][field] = citation_data[field]

            logger.info(
                f"Successfully processed CourtListener result for {original_citation} with year '{year}'"
            )
            return processed

        except Exception as e:
            logger.error(
                f"Error processing citation data for {original_citation}: {str(e)}",
                exc_info=True,
            )
            return {
                "verified": False,
                "citation": original_citation,
                "error": f"Error processing citation data: {str(e)}",
                "source": "CourtListener API",
            }

    def _verify_with_langsearch(self, citation):
        """Verify a citation using the LangSearch API."""
        if not self.langsearch_api_key:
            return {
                "verified": False,
                "source": "LangSearch",
                "error": "No API key provided",
            }

        try:
            # Extract components for flexible search
            components = self._extract_citation_components(citation)

            # Build the search query
            query = f"legal citation {components['volume']} {components['reporter']} {components['page']}"
            if components["year"]:
                query += f" {components['year']}"
            if components["court"]:
                query += f" {components['court']}"

            # Make the API request
            headers = {
                "Authorization": f"Bearer {self.langsearch_api_key}",
                "Content-Type": "application/json",
            }
            data = {"query": query, "max_results": 3}
            response = requests.post(
                "https://api.langsearch.ai/v1/search", headers=headers, json=data
            )

            if response.status_code != 200:
                return {
                    "verified": False,
                    "source": "LangSearch",
                    "error": f"API error: {response.status_code}",
                }

            results = response.json()

            # Check if any results match the citation
            if results.get("results", []):
                for result in results.get("results", []):
                    content = result.get("content", "")
                    # Check if the content contains the citation components
                    if (
                        components["volume"] in content
                        and components["reporter"] in content
                        and components["page"] in content
                    ):
                        return {
                            "verified": True,
                            "source": "LangSearch",
                            "content": content,
                            "url": result.get("url", ""),
                            "score": result.get("score", 0),
                        }

            return {
                "verified": False,
                "source": "LangSearch",
                "error": "Citation not found",
            }

        except Exception as e:
            logger.error(f"Error verifying citation '{citation}' with LangSearch: {e}")
            return {"verified": False, "source": "LangSearch", "error": str(e)}

    def verify_citation(
        self,
        citation,
        extracted_case_name=None,  # Add parameter for extracted case name
        use_cache=True,
        use_database=False,  # Changed default to False - database only for archiving
        use_api=True,
        force_refresh=False,
    ):
        """
        Verify a citation using external APIs and cache only.
        Database is used only for archiving results, not for verification.
        Triggers fallback sources (Google Scholar, Justia, Leagle, web search) if CourtListener is incomplete/unverified.
        """
        if not citation or not isinstance(citation, str):
            return {
                "verified": False,
                "source": "None",
                "error": "No valid citation provided",
                "citation": "",
                "timestamp": datetime.datetime.utcnow().isoformat(),
            }

        try:
            citation = citation.strip()
            if not citation:
                raise ValueError("Citation is empty after stripping whitespace")
            normalized = self._normalize_citation(citation)
            if not normalized:
                raise ValueError("Failed to normalize citation")
            verification_steps = []
            cache_key = f"citation:{normalized}" if self.cache else None

            # 1. Check cache first if enabled and not forcing refresh
            if use_cache and self.cache and not force_refresh:
                try:
                    cached = self.cache.get(cache_key)
                    if cached is not None:
                        verification_steps.append({"step": "cache", "status": "hit"})
                        if not isinstance(cached, dict):
                            raise ValueError("Cached result is not a dictionary")
                        return {
                            **cached,
                            "cached": True,
                            "verification_steps": verification_steps,
                            "timestamp": datetime.datetime.utcnow().isoformat(),
                        }
                    verification_steps.append({"step": "cache", "status": "miss"})
                except Exception as e:
                    logger.warning(f"Cache lookup failed: {str(e)}")
                    verification_steps.append({"step": "cache", "status": "error", "error": str(e)})

            # 2. Try CourtListener API if enabled
            api_result = None
            if use_api:
                try:
                    api_result = self._verify_with_api(normalized)
                    verified_case_name = api_result.get("case_name", "")
                    found_url = api_result.get("url", "")
                    case_name_similarity = None
                    case_name_mismatch = False
                    note = None
                    if found_url:
                        api_result["url"] = found_url
                    if extracted_case_name and verified_case_name:
                        case_name_similarity = self._calculate_case_name_similarity(
                            extracted_case_name, verified_case_name
                        )
                        threshold = 0.7
                        case_name_mismatch = case_name_similarity < threshold
                        if case_name_mismatch:
                            api_result["verified"] = False
                            note = f"Case name differs: extracted='{extracted_case_name}', source='{verified_case_name}' (similarity: {case_name_similarity:.2f})"
                        else:
                            api_result["verified"] = True
                    elif verified_case_name:
                        api_result["verified"] = True
                    elif found_url:
                        api_result["verified"] = True
                    else:
                        api_result["verified"] = False
                    api_result["case_name_similarity"] = case_name_similarity
                    api_result["case_name_mismatch"] = case_name_mismatch
                    api_result["extracted_case_name"] = extracted_case_name
                    if note:
                        api_result["note"] = note
                    verification_steps.append({"step": "courtlistener", "status": "success" if api_result["verified"] else "incomplete", "result": api_result})

                    # Fallback: If not verified, case name is missing/unknown, or similarity is too low, try other sources
                    fallback_needed = (
                        not api_result.get("verified")
                        or not verified_case_name
                        or verified_case_name.strip().lower() == "unknown case"
                        or (case_name_similarity is not None and case_name_similarity < 0.7)
                    )
                    if fallback_needed:
                        # Try Google Scholar
                        scholar_result = self._try_google_scholar(normalized)
                        verification_steps.append({"step": "google_scholar", "status": "success" if scholar_result.get("verified") else "fail", "result": scholar_result})
                        if scholar_result.get("verified"):
                            api_result = scholar_result
                        else:
                            # Try Justia
                            justia_result = self._try_justia(normalized)
                            verification_steps.append({"step": "justia", "status": "success" if justia_result.get("verified") else "fail", "result": justia_result})
                            if justia_result.get("verified"):
                                api_result = justia_result
                            else:
                                # Try Leagle
                                leagle_result = self._try_leagle(normalized)
                                verification_steps.append({"step": "leagle", "status": "success" if leagle_result.get("verified") else "fail", "result": leagle_result})
                                if leagle_result.get("verified"):
                                    api_result = leagle_result
                                else:
                                    # Try web search
                                    web_result = self._verify_with_web_search(normalized)
                                    verification_steps.append({"step": "web_search", "status": "success" if web_result.get("verified") else "fail", "result": web_result})
                                    if web_result.get("verified"):
                                        api_result = web_result
                    # Save to database for archiving (not verification)
                    if use_database:
                        try:
                            self._save_to_database(normalized, api_result)
                            verification_steps.append({"step": "database_archive", "status": "success"})
                        except Exception as e:
                            logger.error(f"Failed to save to database: {str(e)}", exc_info=True)
                            verification_steps.append({"step": "database_archive", "status": "error", "error": str(e)})
                    # Update cache with API result
                    result_to_cache = {
                        **api_result,
                        "verification_steps": verification_steps,
                        "cached": False,
                    }
                    if self.cache:
                        self.cache.set(cache_key, json.dumps(result_to_cache), ex=86400)
                    return result_to_cache
                except Exception as e:
                    logger.error(f"API verification failed: {str(e)}", exc_info=True)
                    verification_steps.append({"step": "api", "status": "error", "error": str(e)})

            # 3. If we get here, no verification method succeeded
            result = {
                "verified": False,
                "source": "None",
                "error": "Citation could not be verified by any available source",
                "citation": citation,
                "normalized_citation": normalized,
                "verification_steps": verification_steps,
                "timestamp": datetime.datetime.utcnow().isoformat(),
            }
            if self.cache:
                try:
                    self.cache.set(cache_key, json.dumps({**result, "cached": False}), ex=3600)
                except Exception as e:
                    logger.warning(f"Failed to cache negative result: {str(e)}")
            return result

        except Exception as e:
            logger.error(f"Error in verify_citation for '{citation}': {str(e)}", exc_info=True)
            return {
                "verified": False,
                "source": "None",
                "error": f"Error verifying citation: {str(e)}",
                "citation": citation,
                "timestamp": datetime.datetime.utcnow().isoformat(),
            }

    def _check_database(self, citation):
        """
        Check if the citation exists in the database using optimized multi-strategy lookup.

        Args:
            citation (str): The citation to look up

        Returns:
            dict: A dictionary containing the verification result and any matching data
        """
        if not citation or not isinstance(citation, str):
            return {
                "verified": False,
                "source": "Database",
                "error": "No valid citation provided",
                "citation": "",
            }

        conn = None
        try:
            # Clean and normalize the citation
            normalized_citation = self._normalize_citation(citation)
            components = self._extract_citation_components(normalized_citation)

            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # Enable column access by name
            cursor = conn.cursor()

            # Optimized single query with multiple strategies
            query = """
                SELECT * FROM citations 
                WHERE citation_text = ? 
                   OR citation_text = ?
                   OR (citation_text LIKE ? AND citation_text LIKE ? AND citation_text LIKE ?)
                ORDER BY 
                    CASE 
                        WHEN citation_text = ? THEN 1
                        WHEN citation_text = ? THEN 2
                        ELSE 3
                    END
                LIMIT 1
            """
            
            # Prepare parameters for the optimized query
            volume_like = f"%{components.get('volume', '')}%" if components.get('volume') else "%"
            reporter_like = f"%{components.get('reporter', '')}%" if components.get('reporter') else "%"
            page_like = f"%{components.get('page', '')}%" if components.get('page') else "%"
            
            params = (
                citation,  # Exact match original
                normalized_citation,  # Exact match normalized
                volume_like, reporter_like, page_like,  # Component match
                citation,  # For ordering
                normalized_citation  # For ordering
            )

            cursor.execute(query, params)
            match = cursor.fetchone()

            if match:
                # Determine match type based on the result
                if match['citation_text'] == citation:
                    match_type = "exact"
                elif match['citation_text'] == normalized_citation:
                    match_type = "normalized"
                else:
                    match_type = "components"
                
                result = self._format_database_match(match, match_type, citation)
                if result.get("verified", False):
                    return result

            return {
                "verified": False,
                "source": "Database",
                "error": "Citation not found in database",
                "citation": citation,
            }

        except Exception as e:
            logger.error(f"Database lookup error for citation '{citation}': {e}")
            return {
                "verified": False,
                "source": "Database",
                "error": f"Database error: {str(e)}",
                "citation": citation,
            }
        finally:
            if conn:
                conn.close()

    def _format_database_match(
        self,
        match,
        match_type,
        original_citation,
        matched_column=None,
        matched_value=None,
    ):
        """
        Format a database match into a standardized result dictionary.

        Args:
            match: The database row (as a dict-like object or dictionary)
            match_type: Type of match (e.g., 'exact', 'normalized', 'components')
            original_citation: The original citation that was searched for
            matched_column: The column or criteria that produced the match
            matched_value: The value that was matched against

        Returns:
            dict: A standardized result dictionary with the match details
        """
        try:
            # Convert SQLite Row to dictionary if needed
            if hasattr(match, "keys"):
                match_dict = dict(match)
            else:
                match_dict = match or {}

            # Safely get the citation value
            citation_value = match_dict.get("citation_text", "")

            # Build the result dictionary
            result = {
                "verified": True,
                "source": "Database",
                "match_type": match_type,
                "citation": citation_value,
                "original_citation": original_citation,
                "timestamp": datetime.datetime.utcnow().isoformat(),
            }

            # Add match details if provided
            if matched_column is not None:
                result["matched_column"] = matched_column
            if matched_value is not None:
                result["matched_value"] = matched_value

            # Add all columns from the database to the result
            if hasattr(match, "keys"):
                for key in match.keys():
                    if (
                        key != "id" and key not in result
                    ):  # Skip id and any already set fields
                        result[key] = match[key]
            elif isinstance(match_dict, dict):
                for key, value in match_dict.items():
                    if (
                        key != "id" and key not in result
                    ):  # Skip id and any already set fields
                        result[key] = value

            # Extract year from various sources
            year = ""
            if match_dict.get("year"):
                year = str(match_dict["year"])
            elif match_dict.get("date_filed"):
                try:
                    year_match = re.search(r'(\d{4})', str(match_dict["date_filed"]))
                    if year_match:
                        year = year_match.group(1)
                except Exception as e:
                    logger.warning(f"Error extracting year from date_filed: {e}")

            # Add year to result and metadata
            if year:
                result["year"] = year
                if "metadata" not in result:
                    result["metadata"] = {}
                result["metadata"]["year"] = year

            # Add parallel citations if available
            if "id" in match_dict:
                try:
                    # Create a new connection for parallel citations query
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT citation, reporter, category, year 
                        FROM parallel_citations 
                        WHERE citation_id = ?
                    """,
                        (match_dict["id"],),
                    )

                    parallel_cites = []
                    for row in cursor.fetchall():
                        parallel_cite = {
                            "citation": row[0], 
                            "reporter": row[1], 
                            "category": row[2]
                        }
                        # Add year if available
                        if row[3]:
                            parallel_cite["year"] = str(row[3])
                        parallel_cites.append(parallel_cite)

                    if parallel_cites:
                        result["parallel_citations"] = parallel_cites
                        logger.debug(f"Found {len(parallel_cites)} parallel citations for citation ID {match_dict['id']}")
                    
                    conn.close()
                except Exception as e:
                    logger.warning(f"Error fetching parallel citations: {e}")

            logger.info(
                f"Database match found (type: {match_type}) for citation: {original_citation} -> "
                f"{citation_value} (matched on: {matched_column or 'N/A'}) with year '{year}'"
            )
            return result

        except Exception as e:
            logger.error(f"Error formatting database match: {e}")
            return {
                "verified": False,
                "source": "Database",
                "error": f"Error processing database match: {str(e)}",
                "original_citation": original_citation,
                "match_type": match_type,
            }

    def _verify_with_database(self, citation):
        """
        Try to verify the citation using the database with multiple strategies.

        Args:
            citation (str): The citation to verify

        Returns:
            dict: Verification result with source 'Database' if found, None otherwise
        """
        if not citation or not isinstance(citation, str):
            logger.debug("Invalid citation provided to _verify_with_database")
            return {
                "verified": False,
                "source": "Database",
                "error": "Invalid citation format",
                "citation": citation,
            }

        try:
            # First try with the exact citation
            result = self._check_database(citation)

            # If we have a verified result, return it
            if result and result.get("verified", False):
                return result

            # If we have an error (not just not found), log it
            if (
                "error" in result
                and "not found" not in str(result.get("error", "")).lower()
            ):
                logger.warning(
                    f"Database lookup error for citation '{citation}': {result.get('error')}"
                )

            # If we got here, no match was found
            return {
                "verified": False,
                "source": "Database",
                "error": "Citation not found in database",
                "citation": citation,
                "timestamp": datetime.datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(
                f"Error in _verify_with_database for citation '{citation}': {str(e)}",
                exc_info=True,
            )
            return {
                "verified": False,
                "source": "Database",
                "error": f"Error verifying citation: {str(e)}",
                "citation": citation,
                "timestamp": datetime.datetime.utcnow().isoformat(),
            }

    # Landmark cases functionality has been removed as it's no longer maintained

    def _verify_with_fuzzy_matching(self, citation):
        """Verify citation using fuzzy matching against database."""
        try:
            # This is a placeholder for fuzzy matching implementation
            # Could be implemented with fuzzy string matching against known citations
            return {"verified": False, "error": "Fuzzy matching not implemented"}
        except Exception as e:
            logger.error(f"Error in fuzzy matching: {e}")
            return {"verified": False, "error": str(e)}

    def _verify_with_web_search(self, citation: str) -> dict:
        """
        Verify citation using web search (Google search).
        
        This method searches for the citation on the web to find case information
        from various legal databases and websites.
        
        Args:
            citation (str): The citation to verify
            
        Returns:
            dict: Verification result with case information
        """
        try:
            logger.info(f"Attempting web search verification for: {citation}")
            
            # Normalize the citation for search
            search_query = f'"{citation}" case law'
            
            # Use Google search to find case information
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            # Search for the citation on legal websites
            legal_sites = [
                f'https://law.justia.com/cases/search?query={citation}',
                f'https://www.casemine.com/search?q={citation}',
                f'https://www.findlaw.com/search?query={citation}',
                f'https://www.leagle.com/search?query={citation}',
                f'https://vlex.com/search?searchText={citation}',  # Add vLex as a source
                f'https://casetext.com/search?q={citation}'  # Add Casetext as a source
            ]
            
            results = []
            for site_url in legal_sites:
                try:
                    response = requests.get(site_url, headers=headers, timeout=10)
                    if response.status_code == 200:
                        # Extract case name from the page content
                        case_name = self._extract_case_name_from_page(response.text, citation)
                        if case_name:
                            results.append({
                                'source': site_url,
                                'case_name': case_name,
                                'url': site_url
                            })
                except Exception as e:
                    logger.warning(f"Error searching {site_url}: {e}")
                    continue
            
            if results:
                # Return the first successful result
                best_result = results[0]
                return {
                    "verified": True,
                    "case_name": best_result['case_name'],
                    "citation": citation,
                    "source": "web_search",
                    "url": best_result['url'],
                    "confidence": "medium",
                    "verification_method": "web_search"
                }
            else:
                return {
                    "verified": False,
                    "error": "No web search results found",
                    "citation": citation,
                    "verification_method": "web_search"
                }
                
        except Exception as e:
            logger.error(f"Error in web search verification: {e}")
            return {
                "verified": False,
                "error": str(e),
                "citation": citation,
                "verification_method": "web_search"
            }

    def _extract_case_name_from_page(self, html_content: str, citation: str, source_url: str = "") -> str:
        """
        Extract case name from HTML page content using site-specific patterns.
        
        Args:
            html_content (str): The HTML content of the page
            citation (str): The citation being searched for
            source_url (str): The URL of the page for site-specific extraction
            
        Returns:
            str: Extracted case name or empty string
        """
        try:
            # Determine the site type from URL
            site_type = self._identify_site_type(source_url)
            
            # Use site-specific extraction patterns
            case_name = self._extract_case_name_by_site(html_content, citation, site_type)
            
            if case_name:
                return case_name
            
            # Fallback to generic patterns if site-specific extraction fails
            return self._extract_case_name_generic(html_content, citation)
            
        except Exception as e:
            logger.warning(f"Error extracting case name from page: {e}")
            return ""

    def _verify_with_api(self, citation):
        """
        Verify a citation using multiple external APIs and sources in parallel.
        Returns a standardized result dictionary, including up to two verifying sources and their case names.
        Always includes a URL if a citation is found, even if case name similarity is low.
        """
        # Prioritize sources by reliability and speed
        sources = [
            ("CourtListener", self._try_courtlistener),  # Most reliable, fastest
            ("Google Scholar", self._try_google_scholar),  # Good coverage
            ("Justia", self._try_justia),  # Reliable
            ("Leagle", self._try_leagle),  # Good for state cases
            ("FindLaw", self._try_findlaw),  # Backup
            ("CaseText", self._try_casetext),  # Backup
            ("OpenLegal", self._try_openlegal),  # Backup
            ("Supreme Court", self._try_supreme_court),  # Specialized
            ("Federal Courts", self._try_federal_courts),  # Specialized
            ("State Courts", self._try_state_courts),  # Specialized
            ("OpenJurist", self._try_openjurist),  # Backup
        ]
        
        results = []
        verifying_sources = []
        case_names = []
        urls = []
        found_url = None
        found_case_name = None
        found_source = None
        courtlistener_verified = False
        
        # Run all sources in parallel with timeout
        import concurrent.futures
        import time
        
        start_time = time.time()
        timeout = 15  # 15 second timeout for all API calls
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            # Submit all tasks
            future_to_source = {
                executor.submit(self._call_api_with_timeout, method, citation, 8): (name, method) 
                for name, method in sources
            }
            
            # Process results as they complete
            for future in concurrent.futures.as_completed(future_to_source, timeout=timeout):
                name, method = future_to_source[future]
                try:
                    result = future.result()
                    results.append((name, result))
                    
                    if result.get("verified", False):
                        # Track CourtListener verification separately
                        if name == "CourtListener":
                            courtlistener_verified = True
                        
                        verifying_sources.append(name)
                        case_name = result.get("case_name", "")
                        url = result.get("url", "")
                        if case_name and case_name != "Unknown Case" and not case_name.startswith("Found in"):
                            case_names.append(case_name)
                            if url:
                                urls.append(url)
                        else:
                            case_names.append("")
                        
                        # Early termination: if we have CourtListener + one other source, we're done
                        if courtlistener_verified and len(verifying_sources) >= 2:
                            break
                        # Or if we have 3 sources total
                        elif len(verifying_sources) >= 3:
                            break
                    
                    # Always record the first found URL, even if not verified
                    if not found_url and result.get("url"):
                        found_url = result.get("url")
                        found_case_name = result.get("case_name", "")
                        found_source = name
                        
                except concurrent.futures.TimeoutError:
                    logger.warning(f"API call to {name} timed out")
                    results.append((name, {"verified": False, "error": "timeout"}))
                except Exception as e:
                    logger.warning(f"API call to {name} failed: {e}")
                    results.append((name, {"verified": False, "error": str(e)}))
        
        # Fallback logic for case name
        final_case_name = ""
        final_url = ""
        for name in verifying_sources:
            for n, result in results:
                if n == name:
                    case_name = result.get("case_name", "")
                    url = result.get("url", "")
                    if case_name and case_name != "Unknown Case" and not case_name.startswith("Found in"):
                        final_case_name = case_name
                        final_url = url
                        break
            if final_case_name:
                break
        if not final_case_name:
            # Try to use any non-empty case name from any result
            for n, result in results:
                case_name = result.get("case_name", "")
                url = result.get("url", "")
                if case_name and case_name != "Unknown Case" and not case_name.startswith("Found in"):
                    final_case_name = case_name
                    final_url = url
                    break
        
        # If we have a URL but no case name, try to extract case name from the URL
        if (final_url or found_url) and not (final_case_name or found_case_name):
            url_to_extract = final_url or found_url
            extracted_case_name = self._extract_case_name_from_url_content(url_to_extract, citation)
            if extracted_case_name:
                if not final_case_name:
                    final_case_name = extracted_case_name
                if not found_case_name:
                    found_case_name = extracted_case_name
        
        # Always include the first found URL and case name if available
        return {
            "verified": False,  # Verification status will be set in verify_citation
            "sources": verifying_sources,
            "case_names": case_names,
            "case_name": final_case_name or found_case_name or "",
            "url": final_url or found_url or "",
            "results": results,
            "citation": citation,
            "verification_reason": "",
            "courtlistener_verified": courtlistener_verified,
            "found_source": found_source,
        }

    def _call_api_with_timeout(self, method, citation, timeout):
        """Call an API method with a timeout."""
        import concurrent.futures
        import time
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(method, citation)
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                return {"verified": False, "error": "timeout"}
            except Exception as e:
                return {"verified": False, "error": str(e)}

    def _try_courtlistener(self, citation):
        """Try to verify citation using CourtListener API."""
        api_key = self.courtlistener_api_key
        if not api_key:
            return {
                "verified": False,
                "source": "CourtListener",
                "error": "No CourtListener API key provided",
                "citation": citation,
            }
        
        try:
            encoded_citation = quote(citation)
            url = f"https://www.courtlistener.com/api/rest/v4/opinions/?cite={encoded_citation}"
            headers = {
                "Authorization": f"Token {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                # Handle cases where count might not be a number
                try:
                    count = int(data.get("count", 0)) if data.get("count") is not None else 0
                except (ValueError, TypeError):
                    # If count is not a number, check if results exist
                    count = len(data.get("results", []))
                
                if count > 0:
                    result = data["results"][0]
                    case_name = result.get("case_name", "")
                    case_url = f"https://www.courtlistener.com{result.get('absolute_url', '')}"
                    
                    # If case name is missing or unknown, try to extract from the URL
                    if not case_name or case_name == "Unknown Case" or case_name.strip() == "":
                        if case_url and case_url != "https://www.courtlistener.com":
                            extracted_case_name = self._extract_case_name_from_url_content(case_url, citation)
                            if extracted_case_name:
                                case_name = extracted_case_name
                    
                    # Be more strict about accepting results with unknown or empty case names
                    if not case_name or case_name == "Unknown Case" or case_name.strip() == "":
                        return {
                            "citation": citation,
                            "verified": False,
                            "source": "CourtListener",
                            "case_name": case_name or "Unknown Case",
                            "url": case_url,
                            "details": {
                                "court": result.get("court", "Unknown Court"),
                                "date_filed": result.get("date_filed", "Unknown Date"),
                                "docket_number": result.get("docket_number", "Unknown Docket"),
                            },
                            "error": "Citation found but case name is unknown or missing",
                        }
                    
                    # Only verify if we have a proper case name
                    return {
                        "citation": citation,
                        "verified": True,
                        "source": "CourtListener",
                        "case_name": case_name,
                        "url": case_url,
                        "details": {
                            "court": result.get("court", "Unknown Court"),
                            "date_filed": result.get("date_filed", "Unknown Date"),
                            "docket_number": result.get("docket_number", "Unknown Docket"),
                        },
                    }
            
            return {
                "citation": citation,
                "verified": False,
                "source": "CourtListener",
                "case_name": None,
                "details": None,
                "error": "Citation not found in CourtListener database",
            }
            
        except Exception as e:
            return {
                "citation": citation,
                "verified": False,
                "source": "CourtListener",
                "case_name": None,
                "details": None,
                "error": str(e),
            }

    def _verify_citation_with_context(self, citation, content, source_name, url):
        """
        Verify a citation by looking for legal context around the citation in the content.
        This is more strict than simple string matching.
        
        Args:
            citation: The citation to verify
            content: The HTML/text content to search in
            source_name: Name of the source for the result
            url: URL of the search results
            
        Returns:
            dict: Verification result
        """
        citation_lower = citation.lower()
        content_lower = content.lower()
        
        # First check if citation appears at all
        if citation_lower not in content_lower and citation_lower.replace(" ", "") not in content_lower:
            return {
                "citation": citation,
                "verified": False,
                "source": source_name,
                "error": f"Citation not found in {source_name}",
            }
        
        # Split content into sentences to look for context
        sentences = re.split(r'[.!?]', content)
        citation_found_in_context = False
        case_name_found = None
        
        for sentence in sentences:
            if citation_lower in sentence.lower():
                # Check if this sentence contains legal context
                legal_indicators = [
                    'case', 'opinion', 'decision', 'court', 'judge', 'judgment',
                    'ruling', 'appeal', 'petition', 'motion', 'brief', 'argument',
                    'plaintiff', 'defendant', 'respondent', 'appellant', 'litigation',
                    'lawsuit', 'legal', 'jurisdiction', 'precedent', 'holding'
                ]
                
                sentence_lower = sentence.lower()
                has_legal_context = any(indicator in sentence_lower for indicator in legal_indicators)
                
                if has_legal_context:
                    citation_found_in_context = True
                    # Try to extract a case name from the sentence
                    case_patterns = [
                        r'in\s+([^,]+?)\s*,\s*\d+',  # "In Smith v. Jones, 123"
                        r'([^,]+?)\s+v\.\s+([^,]+?)\s*,\s*\d+',  # "Smith v. Jones, 123"
                        r'case\s+of\s+([^,]+?)\s*,\s*\d+',  # "case of Smith v. Jones, 123"
                        r'([^,]+?)\s+v\.\s+([^,]+?)\s*\(',  # "Smith v. Jones ("
                        r'([^,]+?)\s+v\.\s+([^,]+?)\s*$',  # "Smith v. Jones" at end
                    ]
                    
                    for pattern in case_patterns:
                        match = re.search(pattern, sentence, re.IGNORECASE)
                        if match:
                            if len(match.groups()) >= 2:
                                case_name_found = f"{match.group(1)} v. {match.group(2)}"
                            else:
                                case_name_found = match.group(1) if match.groups() else match.group(0)
                            break
                    break
        
        if citation_found_in_context:
            return {
                "citation": citation,
                "verified": True,
                "source": source_name,
                "case_name": case_name_found or f"Found in {source_name}",
                "url": url,
                "details": {"search_url": url},
            }
        else:
            return {
                "citation": citation,
                "verified": False,
                "source": source_name,
                "error": f"Citation found but lacks legal context in {source_name}",
            }

    def _try_google_scholar(self, citation):
        """Try to verify citation using Google Scholar."""
        try:
            # Construct search query
            query = f'"{citation}"'
            encoded_query = quote(query)
            url = f"https://scholar.google.com/scholar?q={encoded_query}&as_sdt=2006"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                return self._verify_citation_with_context(citation, response.text, "Google Scholar", url)
            
            return {
                "citation": citation,
                "verified": False,
                "source": "Google Scholar",
                "error": "Citation not found in Google Scholar",
            }
            
        except Exception as e:
            return {
                "citation": citation,
                "verified": False,
                "source": "Google Scholar",
                "error": str(e),
            }

    def _try_justia(self, citation):
        """Try to verify citation using Justia."""
        try:
            # Construct search query
            query = f'"{citation}"'
            encoded_query = quote(query)
            url = f"https://www.justia.com/search?q={encoded_query}"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                return self._verify_citation_with_context(citation, response.text, "Justia", url)
            
            return {
                "citation": citation,
                "verified": False,
                "source": "Justia",
                "error": "Citation not found in Justia",
            }
            
        except Exception as e:
            return {
                "citation": citation,
                "verified": False,
                "source": "Justia",
                "error": str(e),
            }

    def _try_leagle(self, citation):
        """Try to verify citation using Leagle."""
        try:
            # Construct search query
            query = f'"{citation}"'
            encoded_query = quote(query)
            url = f"https://www.leagle.com/search?q={encoded_query}"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                return self._verify_citation_with_context(citation, response.text, "Leagle", url)
            
            return {
                "citation": citation,
                "verified": False,
                "source": "Leagle",
                "error": "Citation not found in Leagle",
            }
            
        except Exception as e:
            return {
                "citation": citation,
                "verified": False,
                "source": "Leagle",
                "error": str(e),
            }

    def _try_findlaw(self, citation):
        """Try to verify citation using FindLaw."""
        try:
            # Construct search query
            query = f'"{citation}"'
            encoded_query = quote(query)
            url = f"https://caselaw.findlaw.com/search?q={encoded_query}"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                return self._verify_citation_with_context(citation, response.text, "FindLaw", url)
            
            return {
                "citation": citation,
                "verified": False,
                "source": "FindLaw",
                "error": "Citation not found in FindLaw",
            }
            
        except Exception as e:
            return {
                "citation": citation,
                "verified": False,
                "source": "FindLaw",
                "error": str(e),
            }

    def _try_casetext(self, citation):
        """Try to verify citation using CaseText."""
        try:
            # Construct search query
            query = f'"{citation}"'
            encoded_query = quote(query)
            url = f"https://casetext.com/search?q={encoded_query}"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                return self._verify_citation_with_context(citation, response.text, "CaseText", url)
            
            return {
                "citation": citation,
                "verified": False,
                "source": "CaseText",
                "error": "Citation not found in CaseText",
            }
            
        except Exception as e:
            return {
                "citation": citation,
                "verified": False,
                "source": "CaseText",
                "error": str(e),
            }

    def _try_openlegal(self, citation):
        """Try to verify citation using OpenLegal."""
        try:
            # Construct search query
            query = f'"{citation}"'
            encoded_query = quote(query)
            url = f"https://openlegal.com/search?q={encoded_query}"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                content = response.text.lower()
                citation_lower = citation.lower()
                
                if citation_lower in content or citation_lower.replace(" ", "") in content:
                    return {
                        "citation": citation,
                        "verified": True,
                        "source": "OpenLegal",
                        "case_name": "Found in OpenLegal",
                        "url": url,
                        "details": {"search_url": url},
                    }
            
            return {
                "citation": citation,
                "verified": False,
                "source": "OpenLegal",
                "error": "Citation not found in OpenLegal",
            }
            
        except Exception as e:
            return {
                "citation": citation,
                "verified": False,
                "source": "OpenLegal",
                "error": str(e),
            }

    def _try_supreme_court(self, citation):
        """Try to verify citation using Supreme Court resources."""
        try:
            # Check Supreme Court official site
            query = f'"{citation}"'
            encoded_query = quote(query)
            url = f"https://www.supremecourt.gov/search.aspx?filename=/docket/docketfiles/html/public/{encoded_query}"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                content = response.text.lower()
                citation_lower = citation.lower()
                
                if citation_lower in content or citation_lower.replace(" ", "") in content:
                    return {
                        "citation": citation,
                        "verified": True,
                        "source": "Supreme Court",
                        "case_name": "Found in Supreme Court",
                        "url": url,
                        "details": {"search_url": url},
                    }
            
            return {
                "citation": citation,
                "verified": False,
                "source": "Supreme Court",
                "error": "Citation not found in Supreme Court",
            }
            
        except Exception as e:
            return {
                "citation": citation,
                "verified": False,
                "source": "Supreme Court",
                "error": str(e),
            }

    def _try_federal_courts(self, citation):
        """Try to verify citation using Federal Courts resources."""
        try:
            # Check PACER/ECF systems (public access)
            query = f'"{citation}"'
            encoded_query = quote(query)
            url = f"https://www.pacer.gov/search?q={encoded_query}"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                content = response.text.lower()
                citation_lower = citation.lower()
                
                if citation_lower in content or citation_lower.replace(" ", "") in content:
                    return {
                        "citation": citation,
                        "verified": True,
                        "source": "Federal Courts",
                        "case_name": "Found in Federal Courts",
                        "url": url,
                        "details": {"search_url": url},
                    }
            
            return {
                "citation": citation,
                "verified": False,
                "source": "Federal Courts",
                "error": "Citation not found in Federal Courts",
            }
            
        except Exception as e:
            return {
                "citation": citation,
                "verified": False,
                "source": "Federal Courts",
                "error": str(e),
            }

    def _try_state_courts(self, citation):
        """Try to verify citation using State Courts resources."""
        try:
            # Check National Center for State Courts
            query = f'"{citation}"'
            encoded_query = quote(query)
            url = f"https://www.ncsc.org/search?q={encoded_query}"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                return self._verify_citation_with_context(citation, response.text, "State Courts", url)
            
            return {
                "citation": citation,
                "verified": False,
                "source": "State Courts",
                "error": "Citation not found in State Courts",
            }
            
        except Exception as e:
            return {
                "citation": citation,
                "verified": False,
                "source": "State Courts",
                "error": str(e),
            }

    def _try_openjurist(self, citation):
        """
        Try to verify citation using OpenJurist (https://openjurist.org/).
        Returns a dict with 'verified', 'case_name', and 'url' if found.
        """
        try:
            from bs4 import BeautifulSoup
            query = quote(citation)
            url = f"https://openjurist.org/search?query={query}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    text = a.get_text(strip=True)
                    if citation.replace(" ", "") in text.replace(" ", ""):
                        case_url = f"https://openjurist.org{href}" if href.startswith("/") else href
                        case_name = text
                        return {
                            "verified": True,
                            "source": "OpenJurist",
                            "case_name": case_name,
                            "url": case_url,
                        }
            return {
                "verified": False,
                "source": "OpenJurist",
                "error": "Citation not found in OpenJurist",
            }
        except Exception as e:
            return {
                "verified": False,
                "source": "OpenJurist",
                "error": str(e),
            }

    def _calculate_case_name_similarity(self, name1, name2):
        """
        Calculate similarity between two case names.
        
        Args:
            name1: First case name
            name2: Second case name
            
        Returns:
            Similarity score between 0 and 1
        """
        if not name1 or not name2:
            return 0.0
            
        # Normalize names
        norm1 = self._normalize_case_name(name1)
        norm2 = self._normalize_case_name(name2)
        
        if not norm1 or not norm2:
            return 0.0
            
        # Check for exact match
        if norm1 == norm2:
            return 1.0
            
        # Check for one name being a substring of the other
        if norm1 in norm2 or norm2 in norm1:
            return 0.8
            
        # Calculate word overlap
        words1 = set(norm1.split())
        words2 = set(norm2.split())
        
        if not words1 or not words2:
            return 0.0
            
        # Calculate Jaccard similarity
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0
    
    def _normalize_case_name(self, name):
        """
        Normalize a case name for comparison.
        
        Args:
            name: Case name to normalize
            
        Returns:
            Normalized case name
        """
        if not name:
            return ""
            
        # Convert to lowercase and remove punctuation
        normalized = re.sub(r'[^\w\s]', '', name.lower())
        
        # Remove common words that don't add meaning
        common_words = {
            'v', 'vs', 'versus', 'state', 'united', 'states', 'county', 'city', 'town',
            'corporation', 'corp', 'company', 'co', 'incorporated', 'inc', 'limited', 'ltd',
            'association', 'assoc', 'foundation', 'found', 'trust', 'estate', 'matter',
            'people', 'public', 'private', 'federal', 'national', 'international',
            'department', 'dept', 'agency', 'board', 'commission', 'committee',
            'district', 'school', 'university', 'college', 'hospital', 'medical',
            'health', 'insurance', 'bank', 'financial', 'investment', 'real', 'estate'
        }
        
        words = normalized.split()
        filtered_words = [word for word in words if word not in common_words and len(word) > 2]
        
        return ' '.join(filtered_words)

    def clear_cache(self):
        """Clear the verification cache to force fresh verification."""
        if self.cache:
            try:
                # Clear all citation-related cache entries
                if hasattr(self.cache, 'clear'):
                    self.cache.clear()
                elif hasattr(self.cache, 'flush'):
                    self.cache.flush()
                logger.info("Verification cache cleared")
            except Exception as e:
                logger.warning(f"Failed to clear cache: {str(e)}")

    def _identify_site_type(self, url: str) -> str:
        """Identify the type of legal website from the URL."""
        if not url:
            return "generic"
        
        url_lower = url.lower()
        
        if "courtlistener.com" in url_lower:
            return "courtlistener"
        elif "justia.com" in url_lower:
            return "justia"
        elif "findlaw.com" in url_lower or "caselaw.findlaw.com" in url_lower:
            return "findlaw"
        elif "casetext.com" in url_lower:
            return "casetext"
        elif "leagle.com" in url_lower:
            return "leagle"
        elif "supremecourt.gov" in url_lower:
            return "supreme_court"
        elif "law.cornell.edu" in url_lower:
            return "cornell"
        elif "scholar.google.com" in url_lower:
            return "google_scholar"
        elif "openlegal.com" in url_lower:
            return "openlegal"
        elif "openjurist.org" in url_lower:
            return "openjurist"
        else:
            return "generic"

    def _extract_case_name_by_site(self, html_content: str, citation: str, site_type: str) -> str:
        """Extract case name using site-specific patterns."""
        
        if site_type == "courtlistener":
            return self._extract_case_name_courtlistener(html_content, citation)
        elif site_type == "justia":
            return self._extract_case_name_justia(html_content, citation)
        elif site_type == "findlaw":
            return self._extract_case_name_findlaw(html_content, citation)
        elif site_type == "casetext":
            return self._extract_case_name_casetext(html_content, citation)
        elif site_type == "leagle":
            return self._extract_case_name_leagle(html_content, citation)
        elif site_type == "supreme_court":
            return self._extract_case_name_supreme_court(html_content, citation)
        elif site_type == "cornell":
            return self._extract_case_name_cornell(html_content, citation)
        elif site_type == "google_scholar":
            return self._extract_case_name_google_scholar(html_content, citation)
        else:
            return ""

    def _extract_case_name_courtlistener(self, html_content: str, citation: str) -> str:
        """Extract case name from CourtListener pages."""
        patterns = [
            r'<h1[^>]*class="[^"]*title[^"]*"[^>]*>([^<]+)</h1>',
            r'<h1[^>]*>([^<]*' + re.escape(citation) + r'[^<]*)</h1>',
            r'<title[^>]*>([^<]*' + re.escape(citation) + r'[^<]*)</title>',
            r'class="case-name"[^>]*>([^<]*)</',
            r'<span[^>]*class="[^"]*case-name[^"]*"[^>]*>([^<]*)</span>',
            r'<div[^>]*class="[^"]*case-name[^"]*"[^>]*>([^<]*)</div>'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html_content, re.IGNORECASE | re.DOTALL)
            if match:
                case_name = self._clean_case_name(match.group(1))
                if self._is_valid_case_name(case_name):
                    return case_name
        
        return ""

    def _extract_case_name_justia(self, html_content: str, citation: str) -> str:
        """Extract case name from Justia pages."""
        patterns = [
            r'<h1[^>]*class="[^"]*case-title[^"]*"[^>]*>([^<]+)</h1>',
            r'<h1[^>]*>([^<]*' + re.escape(citation) + r'[^<]*)</h1>',
            r'<title[^>]*>([^<]*' + re.escape(citation) + r'[^<]*)</title>',
            r'class="case-title"[^>]*>([^<]*)</',
            r'<span[^>]*class="[^"]*case-title[^"]*"[^>]*>([^<]*)</span>',
            r'<div[^>]*class="[^"]*case-title[^"]*"[^>]*>([^<]*)</div>'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html_content, re.IGNORECASE | re.DOTALL)
            if match:
                case_name = self._clean_case_name(match.group(1))
                if self._is_valid_case_name(case_name):
                    return case_name
        
        return ""

    def _extract_case_name_findlaw(self, html_content: str, citation: str) -> str:
        """Extract case name from FindLaw pages."""
        patterns = [
            r'<h1[^>]*class="[^"]*case-title[^"]*"[^>]*>([^<]+)</h1>',
            r'<h1[^>]*>([^<]*' + re.escape(citation) + r'[^<]*)</h1>',
            r'<title[^>]*>([^<]*' + re.escape(citation) + r'[^<]*)</title>',
            r'class="case-title"[^>]*>([^<]*)</',
            r'<span[^>]*class="[^"]*case-title[^"]*"[^>]*>([^<]*)</span>',
            r'<div[^>]*class="[^"]*case-title[^"]*"[^>]*>([^<]*)</div>'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html_content, re.IGNORECASE | re.DOTALL)
            if match:
                case_name = self._clean_case_name(match.group(1))
                if self._is_valid_case_name(case_name):
                    return case_name
        
        return ""

    def _extract_case_name_casetext(self, html_content: str, citation: str) -> str:
        """Extract case name from CaseText pages."""
        patterns = [
            r'<h1[^>]*class="[^"]*case-title[^"]*"[^>]*>([^<]+)</h1>',
            r'<h1[^>]*>([^<]*' + re.escape(citation) + r'[^<]*)</h1>',
            r'<title[^>]*>([^<]*' + re.escape(citation) + r'[^<]*)</title>',
            r'class="case-title"[^>]*>([^<]*)</',
            r'<span[^>]*class="[^"]*case-title[^"]*"[^>]*>([^<]*)</span>',
            r'<div[^>]*class="[^"]*case-title[^"]*"[^>]*>([^<]*)</div>'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html_content, re.IGNORECASE | re.DOTALL)
            if match:
                case_name = self._clean_case_name(match.group(1))
                if self._is_valid_case_name(case_name):
                    return case_name
        
        return ""

    def _extract_case_name_leagle(self, html_content: str, citation: str) -> str:
        """Extract case name from Leagle pages."""
        patterns = [
            r'<h1[^>]*class="[^"]*case-title[^"]*"[^>]*>([^<]+)</h1>',
            r'<h1[^>]*>([^<]*' + re.escape(citation) + r'[^<]*)</h1>',
            r'<title[^>]*>([^<]*' + re.escape(citation) + r'[^<]*)</title>',
            r'class="case-title"[^>]*>([^<]*)</',
            r'<span[^>]*class="[^"]*case-title[^"]*"[^>]*>([^<]*)</span>',
            r'<div[^>]*class="[^"]*case-title[^"]*"[^>]*>([^<]*)</div>'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html_content, re.IGNORECASE | re.DOTALL)
            if match:
                case_name = self._clean_case_name(match.group(1))
                if self._is_valid_case_name(case_name):
                    return case_name
        
        return ""

    def _extract_case_name_supreme_court(self, html_content: str, citation: str) -> str:
        """Extract case name from Supreme Court pages."""
        patterns = [
            r'<h1[^>]*class="[^"]*case-title[^"]*"[^>]*>([^<]+)</h1>',
            r'<h1[^>]*>([^<]*' + re.escape(citation) + r'[^<]*)</h1>',
            r'<title[^>]*>([^<]*' + re.escape(citation) + r'[^<]*)</title>',
            r'class="case-title"[^>]*>([^<]*)</',
            r'<span[^>]*class="[^"]*case-title[^"]*"[^>]*>([^<]*)</span>',
            r'<div[^>]*class="[^"]*case-title[^"]*"[^>]*>([^<]*)</div>'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html_content, re.IGNORECASE | re.DOTALL)
            if match:
                case_name = self._clean_case_name(match.group(1))
                if self._is_valid_case_name(case_name):
                    return case_name
        
        return ""

    def _extract_case_name_cornell(self, html_content: str, citation: str) -> str:
        """Extract case name from Cornell LII pages."""
        patterns = [
            r'<h1[^>]*class="[^"]*case-title[^"]*"[^>]*>([^<]+)</h1>',
            r'<h1[^>]*>([^<]*' + re.escape(citation) + r'[^<]*)</h1>',
            r'<title[^>]*>([^<]*' + re.escape(citation) + r'[^<]*)</title>',
            r'class="case-title"[^>]*>([^<]*)</',
            r'<span[^>]*class="[^"]*case-title[^"]*"[^>]*>([^<]*)</span>',
            r'<div[^>]*class="[^"]*case-title[^"]*"[^>]*>([^<]*)</div>'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html_content, re.IGNORECASE | re.DOTALL)
            if match:
                case_name = self._clean_case_name(match.group(1))
                if self._is_valid_case_name(case_name):
                    return case_name
        
        return ""

    def _extract_case_name_google_scholar(self, html_content: str, citation: str) -> str:
        """Extract case name from Google Scholar pages."""
        patterns = [
            r'<h3[^>]*class="[^"]*gs_rt[^"]*"[^>]*>([^<]+)</h3>',
            r'<h3[^>]*>([^<]*' + re.escape(citation) + r'[^<]*)</h3>',
            r'<title[^>]*>([^<]*' + re.escape(citation) + r'[^<]*)</title>',
            r'class="gs_rt"[^>]*>([^<]*)</',
            r'<span[^>]*class="[^"]*gs_rt[^"]*"[^>]*>([^<]*)</span>',
            r'<div[^>]*class="[^"]*gs_rt[^"]*"[^>]*>([^<]*)</div>'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html_content, re.IGNORECASE | re.DOTALL)
            if match:
                case_name = self._clean_case_name(match.group(1))
                if self._is_valid_case_name(case_name):
                    return case_name
        
        return ""

    def _extract_case_name_generic(self, html_content: str, citation: str) -> str:
        """Extract case name using generic patterns."""
        patterns = [
            r'<title[^>]*>([^<]*' + re.escape(citation) + r'[^<]*)</title>',
            r'<h1[^>]*>([^<]*' + re.escape(citation) + r'[^<]*)</h1>',
            r'<h2[^>]*>([^<]*' + re.escape(citation) + r'[^<]*)</h2>',
            r'class="case-name"[^>]*>([^<]*)</',
            r'class="title"[^>]*>([^<]*)</',
            r'class="case-title"[^>]*>([^<]*)</',
            r'<span[^>]*class="[^"]*case[^"]*"[^>]*>([^<]*)</span>',
            r'<div[^>]*class="[^"]*case[^"]*"[^>]*>([^<]*)</div>'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html_content, re.IGNORECASE | re.DOTALL)
            if match:
                case_name = self._clean_case_name(match.group(1))
                if self._is_valid_case_name(case_name):
                    return case_name
        
        return ""

    def _clean_case_name(self, case_name: str) -> str:
        """Clean and normalize a case name."""
        if not case_name:
            return ""
        
        # Remove HTML tags
        case_name = re.sub(r'<[^>]+>', '', case_name)
        
        # Clean up whitespace
        case_name = re.sub(r'\s+', ' ', case_name)
        case_name = case_name.strip()
        
        # Remove common unwanted text
        case_name = re.sub(r'^\s*-\s*', '', case_name)  # Remove leading dash
        case_name = re.sub(r'\s*-\s*$', '', case_name)  # Remove trailing dash
        
        # Remove citation from case name if present
        citation_patterns = [
            r'\d+\s+[A-Z]+\.[\d\w\.]+\s+\d+',  # e.g., "181 Wash.2d 391"
            r'\d+\s+[A-Z]+\s+\d+',  # e.g., "181 Wash 2d 391"
            r'\d+\s+[A-Z]+\.[\d\w\.]+',  # e.g., "181 Wash.2d"
        ]
        
        for pattern in citation_patterns:
            case_name = re.sub(pattern, '', case_name, flags=re.IGNORECASE)
        
        # Clean up again after citation removal
        case_name = re.sub(r'\s+', ' ', case_name)
        case_name = case_name.strip()
        
        return case_name

    def _is_valid_case_name(self, case_name: str) -> bool:
        """Check if a case name is valid."""
        if not case_name or len(case_name) < 5:
            return False
        
        # Must contain typical case name patterns
        case_patterns = [
            r'\b[A-Z][a-z]+\s+(?:v\.|vs\.|versus)\s+[A-Z][a-z]+',  # e.g., "Smith v. Jones"
            r'\bIn\s+re\s+[A-Z][a-z]+',  # e.g., "In re Smith"
            r'\b[A-Z][a-z]+\s+(?:ex\s+rel\.|ex\s+rel)\s+[A-Z][a-z]+',  # e.g., "State ex rel. Smith"
        ]
        
        for pattern in case_patterns:
            if re.search(pattern, case_name, re.IGNORECASE):
                return True
        
        return False

    def _extract_case_name_from_url_content(self, url: str, citation: str) -> str:
        """
        Extract case name by fetching the content from a URL.
        
        Args:
            url (str): The URL to fetch content from
            citation (str): The citation being searched for
            
        Returns:
            str: Extracted case name or empty string
        """
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                return self._extract_case_name_from_page(response.text, citation, url)
            
            return ""
            
        except Exception as e:
            logger.warning(f"Error fetching content from {url}: {e}")
            return ""

    def _get_cached_result(self, citation):
        """Get cached verification result for a citation."""
        try:
            cache_key = f"citation_verification:{citation}"
            cached_data = self.redis_client.get(cache_key)
            
            if cached_data:
                # Handle both string and bytes data
                if isinstance(cached_data, bytes):
                    cached_data = cached_data.decode('utf-8')
                
                # Try to parse as JSON
                try:
                    result = json.loads(cached_data)
                    if isinstance(result, dict):
                        logger.info(f"Cache hit for citation: {citation}")
                        return result
                    else:
                        logger.warning(f"Cache lookup failed: Cached result is not a dictionary")
                        return None
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Cache lookup failed: Invalid JSON in cache: {e}")
                    return None
            
            return None
        except Exception as e:
            logger.error(f"Cache lookup error: {e}")
            return None

    def _create_session(self):
        """Create a requests session with connection pooling and retry logic."""
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504, 522, 524],
            allowed_methods=["GET", "POST"],
            respect_retry_after_header=True,
        )
        
        # Configure connection pooling
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=20,  # Increased pool size
            pool_maxsize=50,      # Increased max connections
            pool_block=False      # Don't block when pool is full
        )
        
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Set default timeout
        session.timeout = 10
        
        return session

# Standalone function for backward compatibility
def verify_citation(citation, extracted_case_name=None, use_cache=True, use_database=False, use_api=True, force_refresh=False):
    """
    Standalone function to verify a citation using the EnhancedMultiSourceVerifier.
    
    Args:
        citation (str): The citation to verify
        extracted_case_name (str, optional): Case name extracted from source document
        use_cache (bool): Whether to use caching
        use_database (bool): Whether to use database lookup
        use_api (bool): Whether to use API verification
        force_refresh (bool): Whether to force refresh cache
        
    Returns:
        dict: Verification result
    """
    verifier = EnhancedMultiSourceVerifier()
    return verifier.verify_citation(
        citation=citation,
        extracted_case_name=extracted_case_name,
        use_cache=use_cache,
        use_database=use_database,
        use_api=use_api,
        force_refresh=force_refresh
    )
