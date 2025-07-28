"""
Performance Profiler for Citation Processing

This module provides tools for profiling and benchmarking citation processing performance.
"""

import time
import asyncio
import logging
import statistics
from typing import Dict, List, Any, Optional, Callable
from functools import wraps
from dataclasses import dataclass, field
import psutil
import os

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Container for performance metrics."""
    operation_name: str
    execution_time: float
    memory_usage_mb: float
    cpu_usage_percent: float
    input_size: int = 0
    output_size: int = 0
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


class PerformanceProfiler:
    """
    Performance profiler for citation processing operations.
    
    Tracks execution time, memory usage, and CPU utilization.
    """
    
    def __init__(self):
        self.metrics: List[PerformanceMetrics] = []
        self._process = psutil.Process(os.getpid())
    
    def profile_sync(self, operation_name: str, input_size: int = 0):
        """Decorator for profiling synchronous functions."""
        def decorator(func: Callable):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Pre-execution metrics
                start_time = time.time()
                start_memory = self._get_memory_usage()
                start_cpu = self._get_cpu_usage()
                
                try:
                    result = func(*args, **kwargs)
                    
                    # Post-execution metrics
                    end_time = time.time()
                    end_memory = self._get_memory_usage()
                    end_cpu = self._get_cpu_usage()
                    
                    # Calculate metrics
                    execution_time = end_time - start_time
                    memory_delta = end_memory - start_memory
                    avg_cpu = (start_cpu + end_cpu) / 2
                    
                    # Determine output size
                    output_size = 0
                    if isinstance(result, (list, dict, str)):
                        output_size = len(result)
                    elif hasattr(result, '__len__'):
                        output_size = len(result)
                    
                    # Store metrics
                    metrics = PerformanceMetrics(
                        operation_name=operation_name,
                        execution_time=execution_time,
                        memory_usage_mb=memory_delta,
                        cpu_usage_percent=avg_cpu,
                        input_size=input_size,
                        output_size=output_size
                    )
                    self.metrics.append(metrics)
                    
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"Performance: {operation_name} - {execution_time:.3f}s, {memory_delta:.1f}MB")
                    
                    return result
                    
                except Exception as e:
                    logger.error(f"Error in profiled function {operation_name}: {e}")
                    raise
            
            return wrapper
        return decorator
    
    def profile_async(self, operation_name: str, input_size: int = 0):
        """Decorator for profiling asynchronous functions."""
        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Pre-execution metrics
                start_time = time.time()
                start_memory = self._get_memory_usage()
                start_cpu = self._get_cpu_usage()
                
                try:
                    result = await func(*args, **kwargs)
                    
                    # Post-execution metrics
                    end_time = time.time()
                    end_memory = self._get_memory_usage()
                    end_cpu = self._get_cpu_usage()
                    
                    # Calculate metrics
                    execution_time = end_time - start_time
                    memory_delta = end_memory - start_memory
                    avg_cpu = (start_cpu + end_cpu) / 2
                    
                    # Determine output size
                    output_size = 0
                    if isinstance(result, (list, dict, str)):
                        output_size = len(result)
                    elif hasattr(result, '__len__'):
                        output_size = len(result)
                    
                    # Store metrics
                    metrics = PerformanceMetrics(
                        operation_name=operation_name,
                        execution_time=execution_time,
                        memory_usage_mb=memory_delta,
                        cpu_usage_percent=avg_cpu,
                        input_size=input_size,
                        output_size=output_size
                    )
                    self.metrics.append(metrics)
                    
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"Performance: {operation_name} - {execution_time:.3f}s, {memory_delta:.1f}MB")
                    
                    return result
                    
                except Exception as e:
                    logger.error(f"Error in profiled async function {operation_name}: {e}")
                    raise
            
            return wrapper
        return decorator
    
    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB."""
        try:
            return self._process.memory_info().rss / 1024 / 1024
        except Exception:
            return 0.0
    
    def _get_cpu_usage(self) -> float:
        """Get current CPU usage percentage."""
        try:
            return self._process.cpu_percent()
        except Exception:
            return 0.0
    
    def get_summary(self) -> Dict[str, Any]:
        """Get performance summary statistics."""
        if not self.metrics:
            return {"error": "No metrics collected"}
        
        # Group by operation
        by_operation = {}
        for metric in self.metrics:
            op_name = metric.operation_name
            if op_name not in by_operation:
                by_operation[op_name] = []
            by_operation[op_name].append(metric)
        
        # Calculate statistics
        summary = {}
        for op_name, metrics_list in by_operation.items():
            times = [m.execution_time for m in metrics_list]
            memory = [m.memory_usage_mb for m in metrics_list]
            
            summary[op_name] = {
                "count": len(metrics_list),
                "avg_time": statistics.mean(times),
                "min_time": min(times),
                "max_time": max(times),
                "total_time": sum(times),
                "avg_memory": statistics.mean(memory),
                "total_memory": sum(memory)
            }
            
            if len(times) > 1:
                summary[op_name]["std_time"] = statistics.stdev(times)
        
        return summary
    
    def get_bottlenecks(self, threshold_seconds: float = 1.0) -> List[Dict[str, Any]]:
        """Identify performance bottlenecks."""
        bottlenecks = []
        
        for metric in self.metrics:
            if metric.execution_time > threshold_seconds:
                bottlenecks.append({
                    "operation": metric.operation_name,
                    "time": metric.execution_time,
                    "memory": metric.memory_usage_mb,
                    "input_size": metric.input_size,
                    "timestamp": metric.timestamp
                })
        
        # Sort by execution time (worst first)
        bottlenecks.sort(key=lambda x: x["time"], reverse=True)
        return bottlenecks
    
    def clear_metrics(self):
        """Clear all collected metrics."""
        self.metrics.clear()
    
    def export_metrics(self, filename: str):
        """Export metrics to CSV file."""
        import csv
        
        with open(filename, 'w', newline='') as csvfile:
            if not self.metrics:
                return
            
            fieldnames = [
                'operation_name', 'execution_time', 'memory_usage_mb', 
                'cpu_usage_percent', 'input_size', 'output_size', 'timestamp'
            ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for metric in self.metrics:
                writer.writerow({
                    'operation_name': metric.operation_name,
                    'execution_time': metric.execution_time,
                    'memory_usage_mb': metric.memory_usage_mb,
                    'cpu_usage_percent': metric.cpu_usage_percent,
                    'input_size': metric.input_size,
                    'output_size': metric.output_size,
                    'timestamp': metric.timestamp
                })


# Global profiler instance
profiler = PerformanceProfiler()


class PerformanceBenchmark:
    """
    Benchmark suite for citation processing performance.
    """
    
    def __init__(self):
        self.test_cases = []
        self.results = {}
    
    def add_test_case(self, name: str, text: str, expected_citations: int = None):
        """Add a test case for benchmarking."""
        self.test_cases.append({
            "name": name,
            "text": text,
            "expected_citations": expected_citations,
            "text_length": len(text)
        })
    
    async def run_benchmark(self, processor_func: Callable, iterations: int = 3) -> Dict[str, Any]:
        """Run performance benchmark."""
        results = {}
        
        for test_case in self.test_cases:
            case_name = test_case["name"]
            text = test_case["text"]
            
            # Run multiple iterations
            times = []
            for i in range(iterations):
                start_time = time.time()
                
                if asyncio.iscoroutinefunction(processor_func):
                    result = await processor_func(text)
                else:
                    result = processor_func(text)
                
                end_time = time.time()
                times.append(end_time - start_time)
            
            # Calculate statistics
            results[case_name] = {
                "text_length": test_case["text_length"],
                "expected_citations": test_case.get("expected_citations"),
                "avg_time": statistics.mean(times),
                "min_time": min(times),
                "max_time": max(times),
                "std_time": statistics.stdev(times) if len(times) > 1 else 0,
                "iterations": iterations,
                "chars_per_second": test_case["text_length"] / statistics.mean(times)
            }
        
        self.results = results
        return results
    
    def print_benchmark_results(self):
        """Print benchmark results in a formatted table."""
        if not self.results:
            print("No benchmark results available")
            return
        
        print("\n" + "="*80)
        print("PERFORMANCE BENCHMARK RESULTS")
        print("="*80)
        
        print(f"{'Test Case':<25} {'Text Len':<10} {'Avg Time':<10} {'Min Time':<10} {'Max Time':<10} {'Chars/sec':<12}")
        print("-"*80)
        
        for case_name, metrics in self.results.items():
            print(f"{case_name:<25} {metrics['text_length']:<10} "
                  f"{metrics['avg_time']:<10.3f} {metrics['min_time']:<10.3f} "
                  f"{metrics['max_time']:<10.3f} {metrics['chars_per_second']:<12.0f}")
        
        print("="*80)


def create_standard_benchmark() -> PerformanceBenchmark:
    """Create a standard benchmark suite for citation processing."""
    benchmark = PerformanceBenchmark()
    
    # Small document
    benchmark.add_test_case(
        "small_doc",
        "Brown v. Board of Education, 347 U.S. 483 (1954) was a landmark case.",
        expected_citations=1
    )
    
    # Medium document
    benchmark.add_test_case(
        "medium_doc",
        """
        The Supreme Court has decided many important cases. Brown v. Board of Education, 347 U.S. 483 (1954)
        established important precedent. Gideon v. Wainwright, 372 U.S. 335 (1963) guaranteed the right to counsel.
        Miranda v. Arizona, 384 U.S. 436 (1966) established procedural rights. Roe v. Wade, 410 U.S. 113 (1973)
        was another significant decision.
        """,
        expected_citations=4
    )
    
    # Large document with parallel citations
    benchmark.add_test_case(
        "large_doc_parallels",
        """
        This document contains multiple parallel citations for testing clustering performance.
        
        Gideon v. Wainwright appears in multiple forms:
        - Gideon v. Wainwright, 372 U.S. 335 (1963)
        - Gideon v. Wainwright, 83 S. Ct. 792 (1963)
        - 9 L. Ed. 2d 799 (1963)
        
        Brown v. Board also has parallel citations:
        - Brown v. Board of Education, 347 U.S. 483 (1954)
        - Brown v. Board of Education, 74 S. Ct. 686 (1954)
        - 98 L. Ed. 873 (1954)
        
        Miranda v. Arizona citations:
        - Miranda v. Arizona, 384 U.S. 436 (1966)
        - Miranda v. Arizona, 86 S. Ct. 1602 (1966)
        - 16 L. Ed. 2d 694 (1966)
        
        Additional cases for complexity:
        - Marbury v. Madison, 5 U.S. 137 (1803)
        - McCulloch v. Maryland, 17 U.S. 316 (1819)
        - Gibbons v. Ogden, 22 U.S. 1 (1824)
        """,
        expected_citations=12
    )
    
    return benchmark
