"""
Optimized Document Processing Module
Integrates fast PDF extraction with reduced citation verification overhead.
"""

import os
import time
import logging
from typing import Dict, Any, Optional
from pdf_extraction_optimized import extract_text_from_pdf_ultra_fast, extract_text_from_pdf_smart

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OptimizedDocumentProcessor:
    """
    Optimized document processor that prioritizes speed over comprehensive processing.
    """
    
    def __init__(self):
        self.processing_stats = {
            'extraction_time': 0.0,
            'verification_time': 0.0,
            'total_time': 0.0
        }
    
    def process_document_fast(self, 
                            content: Optional[str] = None,
                            file_path: Optional[str] = None,
                            url: Optional[str] = None,
                            skip_verification: bool = True) -> Dict[str, Any]:
        """
        Fast document processing with minimal overhead.
        
        Args:
            content: Direct text content
            file_path: Path to file
            url: URL to process
            skip_verification: Skip citation verification for speed
            
        Returns:
            Processing results
        """
        start_time = time.time()
        
        # Extract text content
        text = self._extract_text_fast(content, file_path, url)
        if not text or text.startswith("Error:"):
            return {
                'success': False,
                'error': text,
                'processing_time_ms': (time.time() - start_time) * 1000
            }
        
        extraction_time = time.time() - start_time
        self.processing_stats['extraction_time'] = extraction_time
        
        # Process citations (optional)
        citations = []
        verification_time = 0.0
        
        if not skip_verification:
            verification_start = time.time()
            citations = self._extract_citations_fast(text)
            verification_time = time.time() - verification_start
            self.processing_stats['verification_time'] = verification_time
        
        total_time = time.time() - start_time
        self.processing_stats['total_time'] = total_time
        
        logger.info(f"Fast processing completed in {total_time:.2f}s "
                   f"(extraction: {extraction_time:.2f}s, "
                   f"verification: {verification_time:.2f}s)")
        
        return {
            'success': True,
            'text': text,
            'citations': citations,
            'processing_time_ms': total_time * 1000,
            'stats': self.processing_stats.copy()
        }
    
    def _extract_text_fast(self, content: Optional[str], file_path: Optional[str], url: Optional[str]) -> str:
        """Fast text extraction from various sources."""
        if content:
            return content
        
        if file_path:
            return self._extract_from_file_fast(file_path)
        
        if url:
            return self._extract_from_url_fast(url)
        
        return "Error: No content, file, or URL provided"
    
    def _extract_from_file_fast(self, file_path: str) -> str:
        """Fast file extraction."""
        if not os.path.exists(file_path):
            return "Error: File not found"
        
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext == '.pdf':
            return extract_text_from_pdf_ultra_fast(file_path)
        elif file_ext in ['.txt', '.md']:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except UnicodeDecodeError:
                try:
                    with open(file_path, 'r', encoding='latin-1') as f:
                        return f.read()
                except Exception as e:
                    return f"Error: {str(e)}"
        else:
            return "Error: Unsupported file type"
    
    def _extract_from_url_fast(self, url: str) -> str:
        """Fast URL extraction."""
        try:
            import requests
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.text
        except Exception as e:
            return f"Error: {str(e)}"
    
    def _extract_citations_fast(self, text: str) -> list:
        """Fast citation extraction without external API calls."""
        # Simple regex-based citation extraction
        import re
        
        citations = []
        
        # Common citation patterns
        patterns = [
            r'(\d+)\s*U\.\s*S\.\s*(\d+)',
            r'(\d+)\s*S\.\s*Ct\.\s*(\d+)',
            r'(\d+)\s*F\.\s*(2d|3d|4th)?\s*(\d+)',
            r'(\d+)\s*L\.\s*Ed\.\s*(\d+)'
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                citations.append({
                    'citation': match.group(0),
                    'start_index': match.start(),
                    'end_index': match.end(),
                    'verified': False,
                    'source': 'regex'
                })
        
        return citations


# Drop-in replacement functions
def process_document_fast(content: Optional[str] = None,
                         file_path: Optional[str] = None,
                         url: Optional[str] = None,
                         skip_verification: bool = True) -> Dict[str, Any]:
    """
    Fast document processing - drop-in replacement for slow methods.
    
    Args:
        content: Direct text content
        file_path: Path to file
        url: URL to process
        skip_verification: Skip citation verification for speed
        
    Returns:
        Processing results
    """
    processor = OptimizedDocumentProcessor()
    return processor.process_document_fast(content, file_path, url, skip_verification)


def extract_text_from_file_fast(file_path: str) -> str:
    """
    Fast file extraction - drop-in replacement for slow methods.
    
    Args:
        file_path: Path to file
        
    Returns:
        Extracted text
    """
    processor = OptimizedDocumentProcessor()
    return processor._extract_from_file_fast(file_path)


if __name__ == "__main__":
    # Test the optimized processing
    import sys
    
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        if os.path.exists(file_path):
            print(f"Testing optimized document processing on: {file_path}")
            
            start_time = time.time()
            result = process_document_fast(file_path=file_path, skip_verification=True)
            total_time = time.time() - start_time
            
            print(f"\nPROCESSING RESULTS:")
            print(f"  Success: {result['success']}")
            print(f"  Total Time: {total_time:.2f}s")
            print(f"  Processing Time: {result.get('processing_time_ms', 0):.0f}ms")
            print(f"  Text Length: {len(result.get('text', ''))}")
            
            if 'stats' in result:
                stats = result['stats']
                print(f"  Extraction Time: {stats.get('extraction_time', 0):.2f}s")
                print(f"  Verification Time: {stats.get('verification_time', 0):.2f}s")
        else:
            print(f"File not found: {file_path}")
    else:
        print("Usage: python document_processing_optimized.py <file_path>") 