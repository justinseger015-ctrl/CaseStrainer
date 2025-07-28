#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Citation Export Module for CaseStrainer

This module provides comprehensive functionality to export citation analysis results
to various formats commonly used in academic and legal research.
"""

import os
import re
import json
import csv
import datetime
import logging
from typing import List, Dict, Any, Optional, Union
from pathlib import Path

# Import the CitationResult model and Bluebook formatter
try:
    from .models import CitationResult
    from .bluebook_formatter import BluebookFormatter
except ImportError:
    from models import CitationResult
    from bluebook_formatter import BluebookFormatter

# Setup logger
logger = logging.getLogger(__name__)

# Default export directory
DEFAULT_EXPORT_DIR = "exports"


class CitationExporter:
    """
    Comprehensive citation export system for CaseStrainer.
    """
    
    def __init__(self, export_dir: Optional[str] = None, use_bluebook: bool = True):
        self.export_dir = Path(export_dir) if export_dir else Path(DEFAULT_EXPORT_DIR)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.use_bluebook = use_bluebook
        self.bluebook_formatter = BluebookFormatter() if use_bluebook else None
        logger.info(f"CitationExporter initialized with export directory: {self.export_dir}, Bluebook formatting: {use_bluebook}")
    
    def _generate_filename(self, base_name: str, extension: str, include_timestamp: bool = True) -> str:
        if include_timestamp:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            return f"{base_name}_{timestamp}.{extension}"
        else:
            return f"{base_name}.{extension}"
    
    def _citation_to_dict(self, citation: Union[CitationResult, Dict[str, Any]]) -> Dict[str, Any]:
        """Convert CitationResult object to dictionary for export."""
        if isinstance(citation, CitationResult):
            return {
                'citation': citation.citation,
                'extracted_case_name': citation.extracted_case_name,
                'extracted_date': citation.extracted_date,
                'canonical_name': citation.canonical_name,
                'canonical_date': citation.canonical_date,
                'verified': citation.verified,
                'url': citation.url,
                'court': citation.court,
                'docket_number': citation.docket_number,
                'confidence': citation.confidence,
                'method': citation.method,
                'is_parallel': citation.is_parallel,
                'parallel_citations': citation.parallel_citations,
                'cluster_id': citation.cluster_id,
                'source': citation.source
            }
        else:
            return citation
    
    def _format_citation_bluebook(self, citation: Union[CitationResult, Dict[str, Any]]) -> str:
        """
        Format a citation in proper Bluebook format.
        
        Args:
            citation: CitationResult object or dictionary
            
        Returns:
            Properly formatted Bluebook citation string
        """
        if not self.use_bluebook or not self.bluebook_formatter:
            # Fallback to basic formatting
            citation_data = self._citation_to_dict(citation)
            case_name = citation_data.get('canonical_name') or citation_data.get('extracted_case_name', '')
            cite = citation_data.get('citation', '')
            return f"{case_name}, {cite}" if case_name and cite else cite
        
        citation_data = self._citation_to_dict(citation)
        return self.bluebook_formatter.format_citation_for_export(citation_data)
    
    def export_to_text(self, citations: List[Union[CitationResult, Dict[str, Any]]], 
                      filename: Optional[str] = None) -> str:
        """Export citations to a plain text file."""
        if not filename:
            filename = self._generate_filename("citations_export", "txt")
        
        filepath = self.export_dir / filename
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("CaseStrainer Citation Export Report\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total Citations: {len(citations)}\n\n")
            
            for i, citation in enumerate(citations, 1):
                citation_data = self._citation_to_dict(citation)
                
                # Use Bluebook formatting for the main citation
                if self.use_bluebook and self.bluebook_formatter:
                    bluebook_citation = self._format_citation_bluebook(citation)
                    f.write(f"{i}. {bluebook_citation}\n")
                else:
                    f.write(f"{i}. {citation_data.get('citation', 'Unknown Citation')}\n")
                
                # Add metadata
                if citation_data.get('canonical_name'):
                    f.write(f"   Case Name: {citation_data['canonical_name']}\n")
                if citation_data.get('canonical_date'):
                    f.write(f"   Date: {citation_data['canonical_date']}\n")
                if citation_data.get('court'):
                    f.write(f"   Court: {citation_data['court']}\n")
                if citation_data.get('docket_number'):
                    f.write(f"   Docket: {citation_data['docket_number']}\n")
                if citation_data.get('parallel_citations'):
                    parallel_list = citation_data['parallel_citations']
                    if parallel_list:
                        f.write(f"   Parallel Citations: {', '.join(parallel_list)}\n")
                f.write(f"   Verified: {'Yes' if citation_data.get('verified') else 'No'}\n")
                f.write(f"   Confidence: {citation_data.get('confidence', 0.0):.2f}\n")
                if self.use_bluebook:
                    f.write(f"   Format: Bluebook Standard\n")
                f.write("\n")
        
        logger.info(f"Citations exported to text file: {filepath}")
        return str(filepath)
    
    def export_to_bibtex(self, citations: List[Union[CitationResult, Dict[str, Any]]], 
                        filename: Optional[str] = None) -> str:
        """Export citations to BibTeX format."""
        if not filename:
            filename = self._generate_filename("citations_export", "bib")
        
        filepath = self.export_dir / filename
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("% CaseStrainer Citation Export - BibTeX Format\n")
            f.write(f"% Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            for i, citation in enumerate(citations, 1):
                citation_data = self._citation_to_dict(citation)
                
                case_name = citation_data.get('canonical_name') or citation_data.get('extracted_case_name', 'Unknown')
                year = citation_data.get('canonical_date') or citation_data.get('extracted_date', '')
                
                # Clean case name for BibTeX key
                if ' v. ' in case_name:
                    clean_name = re.sub(r'[^a-zA-Z0-9]', '', case_name.split(' v. ')[0])
                else:
                    clean_name = re.sub(r'[^a-zA-Z0-9]', '', case_name)
                
                # Extract year from date
                if year and len(year) > 4:
                    year_match = re.search(r'\b(19|20)\d{2}\b', year)
                    if year_match:
                        year = year_match.group()
                
                bibtex_key = f"{clean_name}{year}" if year else f"{clean_name}{i:03d}"
                
                f.write(f"@misc{{{bibtex_key},\n")
                f.write(f"  title = {{{case_name}}},\n")
                if year:
                    f.write(f"  year = {{{year}}},\n")
                f.write(f"  note = {{{citation_data.get('citation', 'Unknown Citation')}}},\n")
                if citation_data.get('court'):
                    f.write(f"  institution = {{{citation_data['court']}}},\n")
                if citation_data.get('url'):
                    f.write(f"  url = {{{citation_data['url']}}},\n")
                f.write(f"  howpublished = {{Legal Citation}}\n")
                f.write("}\n\n")
        
        logger.info(f"Citations exported to BibTeX file: {filepath}")
        return str(filepath)
    
    def export_to_endnote(self, citations: List[Union[CitationResult, Dict[str, Any]]], 
                         filename: Optional[str] = None) -> str:
        """Export citations to EndNote/RIS format."""
        if not filename:
            filename = self._generate_filename("citations_export", "ris")
        
        filepath = self.export_dir / filename
        
        with open(filepath, "w", encoding="utf-8") as f:
            for citation in citations:
                citation_data = self._citation_to_dict(citation)
                
                f.write("TY  - CASE\n")
                
                case_name = citation_data.get('canonical_name') or citation_data.get('extracted_case_name', 'Unknown Case')
                f.write(f"TI  - {case_name}\n")
                
                year = citation_data.get('canonical_date') or citation_data.get('extracted_date', '')
                if year:
                    if len(year) > 4:
                        year_match = re.search(r'\b(19|20)\d{2}\b', year)
                        if year_match:
                            year = year_match.group()
                    f.write(f"PY  - {year}\n")
                
                f.write(f"N1  - {citation_data.get('citation', 'Unknown Citation')}\n")
                
                if citation_data.get('court'):
                    f.write(f"PB  - {citation_data['court']}\n")
                
                if citation_data.get('url'):
                    f.write(f"UR  - {citation_data['url']}\n")
                
                f.write(f"AB  - Verified: {citation_data.get('verified', False)}, Confidence: {citation_data.get('confidence', 0.0):.2f}\n")
                f.write("ER  - \n\n")
        
        logger.info(f"Citations exported to EndNote file: {filepath}")
        return str(filepath)
    
    def export_to_csv(self, citations: List[Union[CitationResult, Dict[str, Any]]], 
                     filename: Optional[str] = None) -> str:
        """Export citations to CSV format."""
        if not filename:
            filename = self._generate_filename("citations_export", "csv")
        
        filepath = self.export_dir / filename
        
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            if not citations:
                return str(filepath)
            
            fieldnames = [
                'citation', 'canonical_name', 'canonical_date', 'extracted_case_name', 
                'extracted_date', 'verified', 'confidence', 'court', 'docket_number',
                'url', 'method', 'is_parallel', 'parallel_citations', 'cluster_id'
            ]
            
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for citation in citations:
                citation_data = self._citation_to_dict(citation)
                row = {}
                for field in fieldnames:
                    value = citation_data.get(field, '')
                    if isinstance(value, list):
                        value = ', '.join(str(v) for v in value if v)
                    elif value is None:
                        value = ''
                    row[field] = value
                writer.writerow(row)
        
        logger.info(f"Citations exported to CSV file: {filepath}")
        return str(filepath)
    
    def export_to_json(self, citations: List[Union[CitationResult, Dict[str, Any]]], 
                      filename: Optional[str] = None) -> str:
        """Export citations to JSON format."""
        if not filename:
            filename = self._generate_filename("citations_export", "json")
        
        filepath = self.export_dir / filename
        
        citation_dicts = [self._citation_to_dict(c) for c in citations]
        export_data = {
            "export_info": {
                "generated": datetime.datetime.now().isoformat(),
                "total_citations": len(citations),
                "source": "CaseStrainer Citation Analysis"
            },
            "citations": citation_dicts
        }
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Citations exported to JSON file: {filepath}")
        return str(filepath)
    
    def export_citations(self, citations: List[Union[CitationResult, Dict[str, Any]]], 
                        format_type: str, filename: Optional[str] = None) -> str:
        """Export citations in the specified format."""
        format_type = format_type.lower()
        
        if format_type in ["text", "txt"]:
            return self.export_to_text(citations, filename)
        elif format_type in ["bibtex", "bib"]:
            return self.export_to_bibtex(citations, filename)
        elif format_type in ["endnote", "ris"]:
            return self.export_to_endnote(citations, filename)
        elif format_type == "csv":
            return self.export_to_csv(citations, filename)
        elif format_type == "json":
            return self.export_to_json(citations, filename)
        else:
            raise ValueError(f"Unsupported export format: {format_type}")


# Convenience functions for backward compatibility
def export_citations_to_format(citations: List[Union[CitationResult, Dict[str, Any]]], 
                              format_type: str, 
                              filename: Optional[str] = None,
                              export_dir: Optional[str] = None) -> str:
    """
    Convenience function to export citations using the CitationExporter class.
    
    Args:
        citations: List of citations to export
        format_type: Export format (text, bibtex, endnote, csv, json)
        filename: Optional filename
        export_dir: Optional export directory
        
    Returns:
        Path to the exported file
    """
    exporter = CitationExporter(export_dir)
    return exporter.export_citations(citations, format_type, filename)


def create_citation_report(citations: List[Union[CitationResult, Dict[str, Any]]], 
                          export_dir: Optional[str] = None) -> Dict[str, str]:
    """
    Create a comprehensive citation report in multiple formats.
    
    Args:
        citations: List of citations to export
        export_dir: Optional export directory
        
    Returns:
        Dictionary mapping format names to file paths
    """
    exporter = CitationExporter(export_dir)
    
    report_files = {}
    formats = ["text", "csv", "json", "bibtex", "endnote"]
    
    for fmt in formats:
        try:
            filepath = exporter.export_citations(citations, fmt)
            report_files[fmt] = filepath
            logger.info(f"Successfully exported {fmt} format: {filepath}")
        except Exception as e:
            logger.error(f"Failed to export {fmt} format: {e}")
            report_files[fmt] = None
    
    return report_files


if __name__ == "__main__":
    # Test the citation export functionality
    from .models import CitationResult
    
    # Create sample citations for testing
    sample_citations = [
        CitationResult(
            citation="171 Wash. 2d 486",
            canonical_name="State v. Sample",
            canonical_date="2011",
            verified=True,
            confidence=0.95,
            court="Washington Supreme Court",
            url="https://example.com/case1"
        ),
        CitationResult(
            citation="123 F.3d 456",
            canonical_name="Federal Case v. Example",
            canonical_date="2020",
            verified=False,
            confidence=0.75,
            court="9th Circuit Court of Appeals"
        )
    ]
    
    print(f"Testing citation export with {len(sample_citations)} sample citations...")
    
    # Test individual format exports
    exporter = CitationExporter("test_exports")
    
    for fmt in ["text", "bibtex", "endnote", "csv", "json"]:
        try:
            filepath = exporter.export_citations(sample_citations, fmt)
            print(f" Exported {fmt}: {filepath}")
        except Exception as e:
            print(f" Failed to export {fmt}: {e}")
    
    # Test comprehensive report
    try:
        report_files = create_citation_report(sample_citations, "test_reports")
        print(f"\n Created comprehensive report with {len([f for f in report_files.values() if f])} files")
        for fmt, filepath in report_files.items():
            if filepath:
                print(f"  - {fmt}: {filepath}")
    except Exception as e:
        print(f" Failed to create comprehensive report: {e}")
