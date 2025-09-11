"""
Sample Citation Generator for CaseStrainer

This script generates sample citation data for the CaseStrainer application
to demonstrate the functionality of the Multitool and Unconfirmed citations tabs.
"""

import secrets
from src.config import DEFAULT_REQUEST_TIMEOUT, COURTLISTENER_TIMEOUT, CASEMINE_TIMEOUT, WEBSEARCH_TIMEOUT, SCRAPINGBEE_TIMEOUT

import os
import json
import sqlite3
import random
from datetime import datetime, timedelta
import logging
from .config import get_database_path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("sample_citations.log"), logging.StreamHandler()],
)
logger = logging.getLogger("sample_citation_generator")

DATABASE_FILE = get_database_path()

WA_CASES = [
    {"citation": "198 Wash.2d 492", "case_name": "State v. Johnson", "year": 2021},
    {
        "citation": "196 Wash.2d 725",
        "case_name": "In re Marriage of Black",
        "year": 2020,
    },
    {"citation": "195 Wash.2d 1", "case_name": "State v. Zamora", "year": 2020},
    {"citation": "194 Wash.2d 212", "case_name": "State v. Yishmael", "year": 2019},
    {"citation": "193 Wash.2d 970", "case_name": "State v. Arndt", "year": 2019},
    {"citation": "192 Wash.2d 1", "case_name": "State v. Prado", "year": 2018},
    {"citation": "191 Wash.2d 681", "case_name": "State v. Dennis", "year": 2018},
    {
        "citation": "190 Wash.2d 775",
        "case_name": "State v. Sassen Van Elsloo",
        "year": 2018,
    },
    {"citation": "189 Wash.2d 1", "case_name": "State v. Allen", "year": 2017},
    {
        "citation": "188 Wash.2d 1",
        "case_name": "State v. Arlene's Flowers",
        "year": 2017,
    },
]

FICTIONAL_CASES = [
    {"citation": "999 Wash.2d 123", "case_name": "State v. Fictional", "year": 2022},
    {
        "citation": "888 Wash.2d 456",
        "case_name": "Smith v. Imaginary Corp",
        "year": 2021,
    },
    {"citation": "777 Wash.2d 789", "case_name": "Doe v. Nonexistent", "year": 2020},
    {"citation": "666 Wash.2d 321", "case_name": "Washington v. Made Up", "year": 2019},
    {
        "citation": "555 Wash.2d 654",
        "case_name": "In re Estate of Nobody",
        "year": 2018,
    },
    {"citation": "444 Wash.2d 987", "case_name": "Fake v. Unreal", "year": 2017},
    {"citation": "333 Wash.2d 246", "case_name": "Imaginary v. Pretend", "year": 2016},
    {"citation": "222 Wash.2d 135", "case_name": "Fantasy v. Reality", "year": 2015},
    {"citation": "111 Wash.2d 579", "case_name": "Unicorn v. Dragon", "year": 2014},
    {"citation": "000 Wash.2d 864", "case_name": "Nowhere v. Nothing", "year": 2013},
]

WA_BRIEFS = [
    "State v. Johnson - Appellant's Opening Brief",
    "In re Marriage of Black - Respondent's Brief",
    "State v. Zamora - Reply Brief",
    "State v. Yishmael - Amicus Brief",
    "State v. Arndt - Supplemental Brief",
    "State v. Prado - Petition for Review",
    "State v. Dennis - Answer to Petition",
    "State v. Sassen Van Elsloo - Motion for Reconsideration",
    "State v. Allen - Brief of Appellant",
    "State v. Arlene's Flowers - Brief of Respondent",
]


def init_db():
    """Initialize the database with the necessary tables if they don't exist."""
    if not os.path.exists(os.path.dirname(DATABASE_FILE)):
        os.makedirs(os.path.dirname(DATABASE_FILE))

    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS citations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        citation_text TEXT NOT NULL,
        case_name TEXT,
        confidence REAL,
        found BOOLEAN,
        explanation TEXT,
        source TEXT,
        source_document TEXT,
        url TEXT,
        context TEXT,
        date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
    )

    conn.commit()
    conn.close()
    logger.info("Database initialized")


def generate_context(citation, case_name):
    """Generate a sample context for a citation."""
    contexts = [
        f"The court in {case_name} ({citation}) held that the defendant's rights were violated.",
        f"According to {case_name} ({citation}), the statute must be interpreted narrowly.",
        f"The precedent established in {case_name} ({citation}) guides our analysis in this case.",
        f"The plaintiff relies on {case_name} ({citation}) to support their argument.",
        f"The defendant cites {case_name} ({citation}) as controlling authority.",
        f"We find {case_name} ({citation}) to be distinguishable from the present case.",
        f"The reasoning in {case_name} ({citation}) applies with equal force here.",
        f"The court's decision in {case_name} ({citation}) represents a significant departure from prior precedent.",
        f"The dissent in {case_name} ({citation}) provides a compelling alternative analysis.",
        f"The concurrence in {case_name} ({citation}) offers additional insights.",
    ]
    return secrets.choice(contexts)


def generate_multitool_citations(num_citations=15):
    """Generate sample citations verified with multitool but not with CourtListener."""
    multitool_citations = []
    sources = ["Google Scholar", "Justia", "FindLaw", "HeinOnline"]

    for i in range(num_citations):
        case = secrets.choice(WA_CASES)

        citation = {
            "citation_text": case["citation"],
            "case_name": case["case_name"],
            "confidence": round(random.uniform(0.6, 0.95), 2),
            "found": True,
            "explanation": "Citation found in alternative source but not in CourtListener.",
            "source": secrets.choice(sources),
            "source_document": secrets.choice(WA_BRIEFS),
            "url": f"https://example.com/case/{case['year']}/{case['case_name'].replace(' ', '-').lower()}",
            "context": generate_context(case["citation"], case["case_name"]),
            "date_added": (
                datetime.now() - timedelta(days=secrets.randbelow(30))
            ).isoformat(),
        }

        multitool_citations.append(citation)

    return multitool_citations


def generate_unconfirmed_citations(num_citations=15):
    """Generate sample unconfirmed citations."""
    unconfirmed_citations = []

    for i in range(num_citations):
        case = secrets.choice(FICTIONAL_CASES)

        citation = {
            "citation_text": case["citation"],
            "case_name": case["case_name"],
            "confidence": round(random.uniform(0.1, 0.4), 2),
            "found": False,
            "explanation": f"Citation not found in any legal database. The Washington Reports volume {case['citation'].split(' ')[0]} does not exist.",
            "source": "None",
            "source_document": secrets.choice(WA_BRIEFS),
            "url": "",
            "context": generate_context(case["citation"], case["case_name"]),
            "date_added": (
                datetime.now() - timedelta(days=secrets.randbelow(30))
            ).isoformat(),
        }

        unconfirmed_citations.append(citation)

    return unconfirmed_citations


def save_citation_to_db(citation):
    """Save a processed citation to the database."""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id FROM citations WHERE citation_text = ?",
            (citation["citation_text"],),
        )
        existing = cursor.fetchone()

        if existing:
            cursor.execute(
                """
            UPDATE citations SET
                case_name = ?,
                confidence = ?,
                found = ?,
                explanation = ?,
                source = ?,
                source_document = ?,
                url = ?,
                context = ?,
                date_added = CURRENT_TIMESTAMP
            WHERE citation_text = ?
            """,
                (
                    citation["case_name"],
                    citation["confidence"],
                    citation["found"],
                    citation["explanation"],
                    citation["source"],
                    citation["source_document"],
                    citation["url"],
                    citation["context"],
                    citation["citation_text"],
                ),
            )
        else:
            cursor.execute(
                """
            INSERT INTO citations (
                citation_text, case_name, confidence, found, explanation,
                source, source_document, url, context
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    citation["citation_text"],
                    citation["case_name"],
                    citation["confidence"],
                    citation["found"],
                    citation["explanation"],
                    citation["source"],
                    citation["source_document"],
                    citation["url"],
                    citation["context"],
                ),
            )

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error saving citation to database: {str(e)}")
        return False


def update_citation_json_files(multitool_citations, unconfirmed_citations):
    """Update the citation verification results JSON files."""
    citation_file = os.path.join(
        os.path.dirname(__file__), "citation_verification_results.json"
    )
    citation_data = {"newly_confirmed": [], "still_unconfirmed": []}

    if os.path.exists(citation_file):
        try:
            with open(citation_file, "r") as f:
                citation_data = json.load(f)
        except Exception as e:
            logger.error(f"Error reading citation_verification_results.json: {e}")

    for citation in unconfirmed_citations:
        citation_data["still_unconfirmed"].append(
            {
                "citation": citation["citation_text"],
                "explanation": citation["explanation"],
                "confidence": citation["confidence"],
                "document": citation["source_document"],
            }
        )

    with open(citation_file, "w") as f:
        json.dump(citation_data, f, indent=2)

    database_file = os.path.join(
        os.path.dirname(__file__), "database_verification_results.json"
    )
    database_data = []

    if os.path.exists(database_file):
        try:
            with open(database_file, "r") as f:
                database_data = json.load(f)
        except Exception as e:
            logger.error(f"Error reading database_verification_results.json: {e}")

    for citation in multitool_citations:
        database_data.append(
            {
                "citation": citation["citation_text"],
                "case_name": citation["case_name"],
                "confidence": citation["confidence"],
                "source": citation["source"],
                "url": citation["url"],
                "explanation": citation["explanation"],
            }
        )

    with open(database_file, "w") as f:
        json.dump(database_data, f, indent=2)

    logger.info(f"Updated citation JSON files: {citation_file} and {database_file}")


def main():
    init_db()

    logger.info("Generating sample multitool citations...")
    multitool_citations = generate_multitool_citations(15)

    logger.info("Generating sample unconfirmed citations...")
    unconfirmed_citations = generate_unconfirmed_citations(15)

    logger.info("Saving citations to database...")
    for citation in multitool_citations:
        save_citation_to_db(citation)

    for citation in unconfirmed_citations:
        save_citation_to_db(citation)

    logger.info("Updating citation JSON files...")
    update_citation_json_files(multitool_citations, unconfirmed_citations)

    logger.info("Sample citation generation complete!")
    logger.info(f"Generated {len(multitool_citations)} citations verified with multitool")
    logger.info(f"Generated {len(unconfirmed_citations)} unconfirmed citations")


if __name__ == "__main__":
    main()
