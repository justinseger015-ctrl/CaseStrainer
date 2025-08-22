#!/usr/bin/env python3
"""
Performance Monitor for Enhanced Adaptive Learning Pipeline
Tracks processing metrics and provides performance optimization insights
"""

import os
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from collections import defaultdict
import statistics

@dataclass
class OperationMetrics:
    """Metrics for a single processing operation"""
    operation_id: str
    filename: str
    file_size: int
    start_time: float
    end_time: Optional[float] = None
    text_length: Optional[int] = None
    citations_found: Optional[int] = None
    clusters_created: Optional[int] = None
    cache_hits: Optional[int] = None
    cache_misses: Optional[int] = None
    error: Optional[str] = None
    processing_time: Optional[float] = None

class PerformanceMonitor:
    """
    Performance monitor for tracking and analyzing processing metrics
    """
    
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.operations: Dict[str, OperationMetrics] = {}
        self.session_start = time.time()
        self.performance_data = {
            'session_info': {
                'start_time': self.session_start,
                'total_operations': 0,
                'successful_operations': 0,
                'failed_operations': 0
            },
            'processing_metrics': {
                'total_processing_time': 0.0,
                'average_processing_time': 0.0,
                'fastest_operation': float('inf'),
                'slowest_operation': 0.0,
                'total_files_processed': 0,
                'total_text_processed': 0,
                'total_citations_found': 0,
                'total_clusters_created': 0
            },
            'cache_performance': {
                'total_cache_hits': 0,
                'total_cache_misses': 0,
                'hit_rate': 0.0
            },
            'error_analysis': {
                'error_types': defaultdict(int),
                'error_frequency': {}
            }
        }
    
    def start_operation(self, operation_id: str, filename: str, file_size: int):
        """Start monitoring an operation"""
        operation = OperationMetrics(
            operation_id=operation_id,
            filename=filename,
            file_size=file_size,
            start_time=time.time()
        )
        self.operations[operation_id] = operation
        self.performance_data['session_info']['total_operations'] += 1
    
    def end_operation(self, operation_id: str, **kwargs):
        """End monitoring an operation with results"""
        if operation_id not in self.operations:
            return
        
        operation = self.operations[operation_id]
        operation.end_time = time.time()
        operation.processing_time = operation.end_time - operation.start_time
        
        # Update operation with provided metrics
        for key, value in kwargs.items():
            if hasattr(operation, key):
                setattr(operation, key, value)
        
        # Update performance data
        self._update_performance_data(operation)
        
        # Determine success/failure
        if operation.error:
            self.performance_data['session_info']['failed_operations'] += 1
            self._record_error(operation.error)
        else:
            self.performance_data['session_info']['successful_operations'] += 1
    
    def _update_performance_data(self, operation: OperationMetrics):
        """Update performance data with operation metrics"""
        metrics = self.performance_data['processing_metrics']
        
        # Update processing time metrics
        if operation.processing_time:
            metrics['total_processing_time'] += operation.processing_time
            metrics['fastest_operation'] = min(metrics['fastest_operation'], operation.processing_time)
            metrics['slowest_operation'] = max(metrics['slowest_operation'], operation.processing_time)
        
        # Update file and content metrics
        if operation.text_length:
            metrics['total_text_processed'] += operation.text_length
        if operation.citations_found:
            metrics['total_citations_found'] += operation.citations_found
        if operation.clusters_created:
            metrics['total_clusters_created'] += operation.clusters_created
        
        metrics['total_files_processed'] += 1
        
        # Update cache performance
        cache_metrics = self.performance_data['cache_performance']
        if operation.cache_hits is not None:
            cache_metrics['total_cache_hits'] += operation.cache_hits
        if operation.cache_misses is not None:
            cache_metrics['total_cache_misses'] += operation.cache_misses
        
        # Calculate hit rate
        total_cache_ops = cache_metrics['total_cache_hits'] + cache_metrics['total_cache_misses']
        if total_cache_ops > 0:
            cache_metrics['hit_rate'] = cache_metrics['total_cache_hits'] / total_cache_ops
        
        # Calculate average processing time
        successful_ops = self.performance_data['session_info']['successful_operations']
        if successful_ops > 0:
            metrics['average_processing_time'] = metrics['total_processing_time'] / successful_ops
    
    def _record_error(self, error: str):
        """Record error for analysis"""
        error_analysis = self.performance_data['error_analysis']
        error_analysis['error_types'][error] += 1
    
    def get_operation_summary(self, operation_id: str) -> Optional[Dict[str, Any]]:
        """Get summary for a specific operation"""
        if operation_id not in self.operations:
            return None
        
        operation = self.operations[operation_id]
        return asdict(operation)
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get overall performance summary"""
        # Calculate additional metrics
        session_duration = time.time() - self.session_start
        throughput = self.performance_data['processing_metrics']['total_files_processed'] / session_duration if session_duration > 0 else 0
        
        summary = {
            'session_duration': session_duration,
            'throughput_files_per_second': throughput,
            'success_rate': self.performance_data['session_info']['successful_operations'] / max(1, self.performance_data['session_info']['total_operations']),
            **self.performance_data
        }
        
        # Add error frequency analysis
        error_analysis = self.performance_data['error_analysis']
        total_errors = sum(error_analysis['error_types'].values())
        if total_errors > 0:
            error_analysis['error_frequency'] = {
                error: count / total_errors 
                for error, count in error_analysis['error_types'].items()
            }
        
        return summary
    
    def print_summary(self):
        """Print performance summary to console"""
        summary = self.get_performance_summary()
        
        print("\n" + "="*60)
        print("PERFORMANCE SUMMARY")
        print("="*60)
        
        # Session info
        print(f"Session Duration: {summary['session_duration']:.2f}s")
        print(f"Total Operations: {summary['session_info']['total_operations']}")
        print(f"Successful: {summary['session_info']['successful_operations']}")
        print(f"Failed: {summary['session_info']['failed_operations']}")
        print(f"Success Rate: {summary['success_rate']:.1%}")
        
        # Processing metrics
        metrics = summary['processing_metrics']
        print(f"\nProcessing Metrics:")
        print(f"  Total Files: {metrics['total_files_processed']}")
        print(f"  Total Text: {metrics['total_text_processed']:,} characters")
        print(f"  Total Citations: {metrics['total_citations_found']}")
        print(f"  Total Clusters: {metrics['total_clusters_created']}")
        print(f"  Throughput: {summary['throughput_files_per_second']:.2f} files/sec")
        
        # Time metrics
        print(f"\nTime Metrics:")
        print(f"  Total Time: {metrics['total_processing_time']:.2f}s")
        print(f"  Average Time: {metrics['average_processing_time']:.2f}s")
        print(f"  Fastest: {metrics['fastest_operation']:.2f}s")
        print(f"  Slowest: {metrics['slowest_operation']:.2f}s")
        
        # Cache performance
        cache = summary['cache_performance']
        print(f"\nCache Performance:")
        print(f"  Hit Rate: {cache['hit_rate']:.1%}")
        print(f"  Hits: {cache['total_cache_hits']}")
        print(f"  Misses: {cache['total_cache_misses']}")
        
        # Error analysis
        if summary['error_analysis']['error_types']:
            print(f"\nError Analysis:")
            for error, count in summary['error_analysis']['error_types'].items():
                frequency = summary['error_analysis']['error_frequency'].get(error, 0)
                print(f"  {error}: {count} times ({frequency:.1%})")
        
        print("="*60)
    
    def save_performance_data(self, filename: str = "performance_data.json"):
        """Save performance data to file"""
        data = {
            'operations': {op_id: asdict(op) for op_id, op in self.operations.items()},
            'summary': self.get_performance_summary()
        }
        
        output_file = self.output_dir / filename
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        print(f"Performance data saved to: {output_file}")
    
    def get_recommendations(self) -> List[str]:
        """Get performance optimization recommendations"""
        recommendations = []
        summary = self.get_performance_summary()
        
        # Processing time recommendations
        avg_time = summary['processing_metrics']['average_processing_time']
        if avg_time > 30:
            recommendations.append("Consider implementing parallel processing for large files")
        elif avg_time > 10:
            recommendations.append("Optimize text extraction algorithms for better performance")
        
        # Cache recommendations
        hit_rate = summary['cache_performance']['hit_rate']
        if hit_rate < 0.5:
            recommendations.append("Improve caching strategy - low hit rate detected")
        elif hit_rate < 0.7:
            recommendations.append("Consider expanding cache size or improving cache keys")
        
        # Error recommendations
        success_rate = summary['success_rate']
        if success_rate < 0.8:
            recommendations.append("Investigate error patterns - low success rate detected")
        
        # Throughput recommendations
        throughput = summary['throughput_files_per_second']
        if throughput < 0.1:
            recommendations.append("Consider batch processing for better throughput")
        
        return recommendations 