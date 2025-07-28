"""
Comprehensive testing framework for citation processing.

This module provides testing utilities, mock data generation, and quality metrics.
"""

import unittest
import asyncio
import time
import random
import string
from typing import List, Dict, Any, Optional, Callable, Union
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
import json
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock

from ..models import CitationResult, ProcessingConfig
from .type_annotations import CitationDict, ClusterDict
from .error_handling import ErrorTracker, ErrorSeverity


@dataclass
class TestResult:
    """Result of a test execution."""
    test_name: str
    passed: bool
    execution_time: float
    error_message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


class CitationTestCase(unittest.TestCase):
    """Enhanced test case for citation processing tests."""
    
    def setUp(self):
        """Set up test environment."""
        self.config = ProcessingConfig(debug_mode=True)
        self.error_tracker = ErrorTracker()
        self.start_time = time.time()
    
    def tearDown(self):
        """Clean up after test."""
        self.execution_time = time.time() - self.start_time
    
    def assertCitationValid(self, citation: CitationResult, msg: str = None):
        """Assert that a citation result is valid."""
        self.assertIsInstance(citation, CitationResult, msg)
        self.assertIsNotNone(citation.citation, msg)
        self.assertGreaterEqual(citation.confidence, 0.0, msg)
        self.assertLessEqual(citation.confidence, 1.0, msg)
        self.assertGreaterEqual(citation.start_index, 0, msg)
        self.assertGreaterEqual(citation.end_index, citation.start_index, msg)
    
    def assertCitationListValid(self, citations: List[CitationResult], msg: str = None):
        """Assert that a list of citations is valid."""
        self.assertIsInstance(citations, list, msg)
        for i, citation in enumerate(citations):
            with self.subTest(citation_index=i):
                self.assertCitationValid(citation, f"Citation {i} invalid: {msg}")
    
    def assertClusterValid(self, cluster: Dict[str, Any], msg: str = None):
        """Assert that a citation cluster is valid."""
        self.assertIsInstance(cluster, dict, msg)
        self.assertIn('citations', cluster, msg)
        self.assertIn('size', cluster, msg)
        self.assertGreater(cluster['size'], 0, msg)
        self.assertEqual(len(cluster['citations']), cluster['size'], msg)
    
    def assertProcessingResultValid(self, result: Dict[str, Any], msg: str = None):
        """Assert that a processing result is valid."""
        self.assertIsInstance(result, dict, msg)
        self.assertIn('success', result, msg)
        self.assertIn('citations', result, msg)
        self.assertIn('clusters', result, msg)
        self.assertIn('summary', result, msg)
        
        if result['success']:
            self.assertIsInstance(result['citations'], list, msg)
            self.assertIsInstance(result['clusters'], list, msg)
            self.assertIsInstance(result['summary'], dict, msg)


class TestDataGenerator:
    """Generate test data for citation processing tests."""
    
    def __init__(self, seed: int = 42):
        """Initialize with optional random seed for reproducibility."""
        random.seed(seed)
        self.landmark_cases = [
            ("Brown v. Board of Education", "347 U.S. 483", "1954"),
            ("Gideon v. Wainwright", "372 U.S. 335", "1963"),
            ("Miranda v. Arizona", "384 U.S. 436", "1966"),
            ("Roe v. Wade", "410 U.S. 113", "1973"),
            ("Marbury v. Madison", "5 U.S. 137", "1803"),
        ]
    
    def generate_citation_text(self, case_name: str, volume: str, reporter: str, page: str, year: str) -> str:
        """Generate a properly formatted citation."""
        return f"{case_name}, {volume} {reporter} {page} ({year})"
    
    def generate_random_case_name(self) -> str:
        """Generate a random case name."""
        plaintiffs = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis"]
        defendants = ["State", "City", "County", "United States", "Department", "Board", "Corporation"]
        
        plaintiff = random.choice(plaintiffs)
        defendant = random.choice(defendants)
        
        return f"{plaintiff} v. {defendant}"
    
    def generate_test_citations(self, count: int = 5) -> List[CitationResult]:
        """Generate a list of test citations."""
        citations = []
        
        for i in range(count):
            if i < len(self.landmark_cases):
                # Use landmark cases first
                case_name, citation_text, year = self.landmark_cases[i]
                full_citation = f"{case_name}, {citation_text} ({year})"
            else:
                # Generate random citations
                case_name = self.generate_random_case_name()
                volume = random.randint(100, 999)
                page = random.randint(1, 999)
                year = random.randint(1950, 2023)
                full_citation = f"{case_name}, {volume} U.S. {page} ({year})"
            
            citation = CitationResult(
                citation=full_citation,
                start_index=i * 100,
                end_index=i * 100 + len(full_citation),
                method="test_generated",
                confidence=random.uniform(0.7, 1.0),
                extracted_case_name=case_name,
                extracted_date=str(year) if 'year' in locals() else year,
                verified=random.choice([True, False])
            )
            citations.append(citation)
        
        return citations
    
    def generate_test_document(self, citation_count: int = 3, include_parallels: bool = True) -> str:
        """Generate a test document with citations."""
        document_parts = [
            "This is a legal document discussing important precedents.",
            "The following cases are relevant to this analysis:"
        ]
        
        citations = []
        for i in range(citation_count):
            if i < len(self.landmark_cases):
                case_name, citation_text, year = self.landmark_cases[i]
                full_citation = f"{case_name}, {citation_text} ({year})"
                citations.append(full_citation)
                
                # Add parallel citations if requested
                if include_parallels and case_name == "Gideon v. Wainwright":
                    citations.extend([
                        "Gideon v. Wainwright, 83 S. Ct. 792 (1963)",
                        "9 L. Ed. 2d 799 (1963)"
                    ])
        
        # Integrate citations into document
        for citation in citations:
            sentence = f"In {citation}, the Court established important precedent."
            document_parts.append(sentence)
        
        document_parts.append("These cases demonstrate the evolution of legal doctrine.")
        
        return " ".join(document_parts)
    
    def generate_large_document(self, size_kb: int = 50) -> str:
        """Generate a large document for performance testing."""
        base_text = self.generate_test_document(citation_count=10, include_parallels=True)
        
        # Repeat and vary the text to reach desired size
        target_size = size_kb * 1024
        current_text = base_text
        
        while len(current_text) < target_size:
            # Add some variation
            additional_text = f"\n\nSection {len(current_text) // 1000}:\n"
            additional_text += base_text.replace("This is a legal document", 
                                               f"This is section {len(current_text) // 1000} of the legal document")
            current_text += additional_text
        
        return current_text[:target_size]


class MockAPIResponse:
    """Mock API response for testing."""
    
    def __init__(self, status_code: int = 200, data: Dict[str, Any] = None, delay: float = 0.0):
        self.status_code = status_code
        self.data = data or {}
        self.delay = delay
    
    async def json(self):
        """Simulate async JSON response."""
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        return self.data
    
    def raise_for_status(self):
        """Simulate HTTP error checking."""
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code} Error")


class TestRunner:
    """Run comprehensive test suites."""
    
    def __init__(self):
        self.results: List[TestResult] = []
        self.test_data_generator = TestDataGenerator()
    
    async def run_extraction_tests(self, extractor) -> List[TestResult]:
        """Run citation extraction tests."""
        results = []
        
        # Test 1: Basic extraction
        test_text = "Brown v. Board of Education, 347 U.S. 483 (1954) was important."
        start_time = time.time()
        
        try:
            citations = extractor.extract_citations(test_text)
            execution_time = time.time() - start_time
            
            passed = len(citations) > 0 and any("Brown" in c.citation for c in citations)
            results.append(TestResult(
                test_name="basic_extraction",
                passed=passed,
                execution_time=execution_time,
                details={'citations_found': len(citations)}
            ))
        except Exception as e:
            results.append(TestResult(
                test_name="basic_extraction",
                passed=False,
                execution_time=time.time() - start_time,
                error_message=str(e)
            ))
        
        # Test 2: Multiple citations
        test_text = self.test_data_generator.generate_test_document(citation_count=5)
        start_time = time.time()
        
        try:
            citations = extractor.extract_citations(test_text)
            execution_time = time.time() - start_time
            
            passed = len(citations) >= 3  # Should find at least 3 citations
            results.append(TestResult(
                test_name="multiple_citations",
                passed=passed,
                execution_time=execution_time,
                details={'citations_found': len(citations), 'text_length': len(test_text)}
            ))
        except Exception as e:
            results.append(TestResult(
                test_name="multiple_citations",
                passed=False,
                execution_time=time.time() - start_time,
                error_message=str(e)
            ))
        
        # Test 3: Large document performance
        large_text = self.test_data_generator.generate_large_document(size_kb=100)
        start_time = time.time()
        
        try:
            citations = extractor.extract_citations(large_text)
            execution_time = time.time() - start_time
            
            # Performance threshold: should complete within 10 seconds
            passed = execution_time < 10.0 and len(citations) > 0
            results.append(TestResult(
                test_name="large_document_performance",
                passed=passed,
                execution_time=execution_time,
                details={
                    'citations_found': len(citations), 
                    'text_size_kb': len(large_text) // 1024,
                    'citations_per_second': len(citations) / execution_time if execution_time > 0 else 0
                }
            ))
        except Exception as e:
            results.append(TestResult(
                test_name="large_document_performance",
                passed=False,
                execution_time=time.time() - start_time,
                error_message=str(e)
            ))
        
        return results
    
    async def run_verification_tests(self, verifier) -> List[TestResult]:
        """Run citation verification tests."""
        results = []
        
        # Generate test citations
        test_citations = self.test_data_generator.generate_test_citations(count=3)
        
        # Test 1: Basic verification
        start_time = time.time()
        
        try:
            verified_citations = await verifier.verify_citations(test_citations[:1])
            execution_time = time.time() - start_time
            
            passed = len(verified_citations) == 1
            results.append(TestResult(
                test_name="basic_verification",
                passed=passed,
                execution_time=execution_time,
                details={'verified_count': sum(1 for c in verified_citations if c.verified)}
            ))
        except Exception as e:
            results.append(TestResult(
                test_name="basic_verification",
                passed=False,
                execution_time=time.time() - start_time,
                error_message=str(e)
            ))
        
        # Test 2: Batch verification
        start_time = time.time()
        
        try:
            verified_citations = await verifier.verify_citations(test_citations)
            execution_time = time.time() - start_time
            
            passed = len(verified_citations) == len(test_citations)
            results.append(TestResult(
                test_name="batch_verification",
                passed=passed,
                execution_time=execution_time,
                details={
                    'input_count': len(test_citations),
                    'output_count': len(verified_citations),
                    'verified_count': sum(1 for c in verified_citations if c.verified)
                }
            ))
        except Exception as e:
            results.append(TestResult(
                test_name="batch_verification",
                passed=False,
                execution_time=time.time() - start_time,
                error_message=str(e)
            ))
        
        return results
    
    async def run_clustering_tests(self, clusterer) -> List[TestResult]:
        """Run citation clustering tests."""
        results = []
        
        # Generate test citations with known parallels
        test_text = self.test_data_generator.generate_test_document(include_parallels=True)
        test_citations = self.test_data_generator.generate_test_citations(count=5)
        
        # Test 1: Parallel detection
        start_time = time.time()
        
        try:
            citations_with_parallels = clusterer.detect_parallel_citations(test_citations, test_text)
            execution_time = time.time() - start_time
            
            parallel_count = sum(1 for c in citations_with_parallels if c.parallel_citations)
            passed = len(citations_with_parallels) == len(test_citations)
            
            results.append(TestResult(
                test_name="parallel_detection",
                passed=passed,
                execution_time=execution_time,
                details={
                    'input_count': len(test_citations),
                    'output_count': len(citations_with_parallels),
                    'parallel_count': parallel_count
                }
            ))
        except Exception as e:
            results.append(TestResult(
                test_name="parallel_detection",
                passed=False,
                execution_time=time.time() - start_time,
                error_message=str(e)
            ))
        
        # Test 2: Clustering
        start_time = time.time()
        
        try:
            clusters = clusterer.cluster_citations(test_citations)
            execution_time = time.time() - start_time
            
            passed = isinstance(clusters, list) and len(clusters) > 0
            results.append(TestResult(
                test_name="citation_clustering",
                passed=passed,
                execution_time=execution_time,
                details={
                    'input_count': len(test_citations),
                    'cluster_count': len(clusters),
                    'total_clustered': sum(c.get('size', 0) for c in clusters)
                }
            ))
        except Exception as e:
            results.append(TestResult(
                test_name="citation_clustering",
                passed=False,
                execution_time=time.time() - start_time,
                error_message=str(e)
            ))
        
        return results
    
    def print_test_results(self, results: List[TestResult]):
        """Print formatted test results."""
        print("\n" + "="*60)
        print("TEST RESULTS")
        print("="*60)
        
        passed_count = sum(1 for r in results if r.passed)
        total_count = len(results)
        
        print(f"Tests passed: {passed_count}/{total_count}")
        print(f"Success rate: {passed_count/total_count:.1%}")
        print()
        
        for result in results:
            status = "✅ PASS" if result.passed else "❌ FAIL"
            print(f"{status} {result.test_name} ({result.execution_time:.3f}s)")
            
            if result.error_message:
                print(f"    Error: {result.error_message}")
            
            if result.details:
                for key, value in result.details.items():
                    print(f"    {key}: {value}")
            print()


class PerformanceTestSuite:
    """Comprehensive performance testing suite."""
    
    def __init__(self):
        self.test_data_generator = TestDataGenerator()
        self.results = {}
    
    async def run_performance_benchmarks(self, services: Dict[str, Any]) -> Dict[str, Any]:
        """Run performance benchmarks on all services."""
        results = {}
        
        # Test different document sizes
        sizes = [1, 10, 50, 100]  # KB
        
        for size_kb in sizes:
            test_text = self.test_data_generator.generate_large_document(size_kb)
            size_results = {}
            
            # Test extraction performance
            if 'extractor' in services:
                start_time = time.time()
                citations = services['extractor'].extract_citations(test_text)
                extraction_time = time.time() - start_time
                
                size_results['extraction'] = {
                    'time': extraction_time,
                    'citations_found': len(citations),
                    'throughput_kb_per_sec': size_kb / extraction_time if extraction_time > 0 else 0
                }
            
            # Test verification performance (limited to avoid API rate limits)
            if 'verifier' in services and size_kb <= 10:  # Only test small documents
                test_citations = citations[:3] if 'citations' in locals() else []
                if test_citations:
                    start_time = time.time()
                    verified = await services['verifier'].verify_citations(test_citations)
                    verification_time = time.time() - start_time
                    
                    size_results['verification'] = {
                        'time': verification_time,
                        'citations_verified': sum(1 for c in verified if c.verified),
                        'throughput_citations_per_sec': len(test_citations) / verification_time if verification_time > 0 else 0
                    }
            
            # Test clustering performance
            if 'clusterer' in services and 'citations' in locals():
                start_time = time.time()
                clusters = services['clusterer'].cluster_citations(citations)
                clustering_time = time.time() - start_time
                
                size_results['clustering'] = {
                    'time': clustering_time,
                    'clusters_created': len(clusters),
                    'throughput_citations_per_sec': len(citations) / clustering_time if clustering_time > 0 else 0
                }
            
            results[f'{size_kb}kb'] = size_results
        
        return results


class QualityMetrics:
    """Calculate and track code quality metrics."""
    
    def __init__(self):
        self.metrics = {}
    
    def calculate_test_coverage(self, test_results: List[TestResult]) -> Dict[str, Any]:
        """Calculate test coverage metrics."""
        total_tests = len(test_results)
        passed_tests = sum(1 for r in test_results if r.passed)
        
        # Calculate average execution time
        avg_execution_time = sum(r.execution_time for r in test_results) / total_tests if total_tests > 0 else 0
        
        # Find slowest tests
        slowest_tests = sorted(test_results, key=lambda x: x.execution_time, reverse=True)[:3]
        
        return {
            'total_tests': total_tests,
            'passed_tests': passed_tests,
            'failed_tests': total_tests - passed_tests,
            'pass_rate': passed_tests / total_tests if total_tests > 0 else 0,
            'average_execution_time': avg_execution_time,
            'slowest_tests': [{'name': t.test_name, 'time': t.execution_time} for t in slowest_tests]
        }
    
    def calculate_error_metrics(self, error_tracker: ErrorTracker) -> Dict[str, Any]:
        """Calculate error and reliability metrics."""
        error_summary = error_tracker.get_error_summary()
        
        return {
            'total_errors': error_summary['total_errors'],
            'error_types': error_summary['error_types'],
            'most_common_errors': error_summary['most_common'],
            'error_rate': error_summary['total_errors'] / 100  # Assuming 100 operations for rate calculation
        }


class CodeCoverageAnalyzer:
    """Analyze code coverage for citation processing modules."""
    
    def __init__(self):
        self.covered_functions = set()
        self.total_functions = set()
    
    def track_function_call(self, module_name: str, function_name: str):
        """Track that a function was called during testing."""
        function_id = f"{module_name}.{function_name}"
        self.covered_functions.add(function_id)
        self.total_functions.add(function_id)
    
    def register_function(self, module_name: str, function_name: str):
        """Register a function that should be covered by tests."""
        function_id = f"{module_name}.{function_name}"
        self.total_functions.add(function_id)
    
    def get_coverage_report(self) -> Dict[str, Any]:
        """Get code coverage report."""
        total_count = len(self.total_functions)
        covered_count = len(self.covered_functions)
        
        uncovered = self.total_functions - self.covered_functions
        
        return {
            'total_functions': total_count,
            'covered_functions': covered_count,
            'coverage_percentage': covered_count / total_count if total_count > 0 else 0,
            'uncovered_functions': list(uncovered)
        }


# Export main components
__all__ = [
    'TestResult', 'CitationTestCase', 'TestDataGenerator', 'MockAPIResponse',
    'TestRunner', 'PerformanceTestSuite', 'QualityMetrics', 'CodeCoverageAnalyzer'
]
