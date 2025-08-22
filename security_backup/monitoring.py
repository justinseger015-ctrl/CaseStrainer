#!/usr/bin/env python3
"""
Comprehensive monitoring system for CaseStrainer production server
Tracks uptime, component status, and provides detailed health metrics
"""

import time
import psutil
import threading
import json
import os
from datetime import datetime, timedelta
from collections import deque, defaultdict
import logging

logger = logging.getLogger(__name__)

class CaseStrainerMonitor:
    """Comprehensive monitoring system for CaseStrainer"""
    
    def __init__(self):
        self.start_time = time.time()
        self.last_restart = self.start_time
        self.restart_count = 0
        
        # Component status tracking
        self.component_status = {
            'flask_app': 'unknown',
            'redis': 'unknown',
            'rq_worker': 'unknown',
            'database': 'unknown',
            'citation_verifier': 'unknown',
            'file_processor': 'unknown'
        }
        
        # Performance metrics
        self.request_history = deque(maxlen=1000)  # Last 1000 requests
        self.error_history = deque(maxlen=100)     # Last 100 errors
        self.uptime_history = deque(maxlen=1440)   # 24 hours of uptime data (1-minute intervals)
        
        # System metrics
        self.system_metrics = {
            'cpu_usage': 0.0,
            'memory_usage': 0.0,
            'disk_usage': 0.0,
            'network_io': {'bytes_sent': 0, 'bytes_recv': 0}
        }
        
        # Start monitoring thread
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        
        logger.info("CaseStrainerMonitor initialized")
    
    def _monitoring_loop(self):
        """Background monitoring loop"""
        while True:
            try:
                self._update_system_metrics()
                self._update_uptime_history()
                time.sleep(60)  # Update every minute
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(60)
    
    def _update_system_metrics(self):
        """Update system resource usage"""
        try:
            # CPU usage
            self.system_metrics['cpu_usage'] = psutil.cpu_percent(interval=1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            self.system_metrics['memory_usage'] = memory.percent
            
            # Disk usage
            disk = psutil.disk_usage('/')
            self.system_metrics['disk_usage'] = (disk.used / disk.total) * 100
            
            # Network I/O
            network = psutil.net_io_counters()
            self.system_metrics['network_io'] = {
                'bytes_sent': network.bytes_sent,
                'bytes_recv': network.bytes_recv
            }
            
        except Exception as e:
            logger.error(f"Error updating system metrics: {e}")
    
    def _update_uptime_history(self):
        """Update uptime history"""
        uptime_seconds = time.time() - self.start_time
        self.uptime_history.append({
            'timestamp': time.time(),
            'uptime_seconds': uptime_seconds,
            'component_status': self.component_status.copy()
        })
    
    def update_component_status(self, component, status, details=None):
        """Update status of a specific component"""
        self.component_status[component] = status
        if details:
            logger.info(f"Component {component} status: {status} - {details}")
        else:
            logger.info(f"Component {component} status: {status}")
    
    def record_request(self, endpoint, duration, status_code, error=None):
        """Record a request for performance tracking"""
        request_data = {
            'timestamp': time.time(),
            'endpoint': endpoint,
            'duration': duration,
            'status_code': status_code,
            'error': error
        }
        self.request_history.append(request_data)
        
        if error or status_code >= 400:
            self.error_history.append(request_data)
    
    def record_error(self, error_type, error_message, stack_trace=None):
        """Record an error for tracking"""
        error_data = {
            'timestamp': time.time(),
            'type': error_type,
            'message': error_message,
            'stack_trace': stack_trace
        }
        self.error_history.append(error_data)
        logger.error(f"Recorded error: {error_type} - {error_message}")
    
    def get_uptime(self):
        """Get current uptime in various formats"""
        uptime_seconds = time.time() - self.start_time
        
        hours = int(uptime_seconds // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        seconds = int(uptime_seconds % 60)
        
        return {
            'seconds': int(uptime_seconds),
            'minutes': int(uptime_seconds // 60),
            'hours': hours,
            'days': int(uptime_seconds // 86400),
            'formatted': f"{hours:02d}:{minutes:02d}:{seconds:02d}",
            'human_readable': self._format_uptime(uptime_seconds)
        }
    
    def _format_uptime(self, seconds):
        """Format uptime in human-readable format"""
        if seconds < 60:
            return f"{int(seconds)} seconds"
        elif seconds < 3600:
            return f"{int(seconds // 60)} minutes"
        elif seconds < 86400:
            return f"{int(seconds // 3600)} hours, {int((seconds % 3600) // 60)} minutes"
        else:
            days = int(seconds // 86400)
            hours = int((seconds % 86400) // 3600)
            return f"{days} days, {hours} hours"
    
    def get_health_status(self):
        """Get overall health status"""
        uptime = self.get_uptime()
        
        # Calculate health score (0-100)
        health_score = 100
        
        # Deduct points for errors
        recent_errors = len([e for e in self.error_history if time.time() - e['timestamp'] < 3600])
        health_score -= min(recent_errors * 5, 30)  # Max 30 points for errors
        
        # Deduct points for high resource usage
        if self.system_metrics['cpu_usage'] > 80:
            health_score -= 10
        if self.system_metrics['memory_usage'] > 80:
            health_score -= 10
        if self.system_metrics['disk_usage'] > 90:
            health_score -= 20
        
        # Deduct points for component failures
        failed_components = sum(1 for status in self.component_status.values() if status == 'failed')
        health_score -= failed_components * 15
        
        health_score = max(0, health_score)
        
        # Determine overall status
        if health_score >= 90:
            status = 'excellent'
        elif health_score >= 75:
            status = 'good'
        elif health_score >= 50:
            status = 'fair'
        else:
            status = 'poor'
        
        return {
            'status': status,
            'score': health_score,
            'uptime': uptime,
            'components': self.component_status,
            'system_metrics': self.system_metrics,
            'recent_errors': recent_errors,
            'failed_components': failed_components
        }
    
    def get_performance_metrics(self):
        """Get performance metrics"""
        if not self.request_history:
            return {
                'total_requests': 0,
                'avg_response_time': 0,
                'error_rate': 0,
                'requests_per_minute': 0
            }
        
        recent_requests = [r for r in self.request_history if time.time() - r['timestamp'] < 3600]
        
        if recent_requests:
            avg_response_time = sum(r['duration'] for r in recent_requests) / len(recent_requests)
            error_count = sum(1 for r in recent_requests if r.get('error') or r.get('status_code', 200) >= 400)
            error_rate = (error_count / len(recent_requests)) * 100
            requests_per_minute = len(recent_requests) / 60
        else:
            avg_response_time = 0
            error_rate = 0
            requests_per_minute = 0
        
        return {
            'total_requests': len(self.request_history),
            'recent_requests': len(recent_requests),
            'avg_response_time': round(avg_response_time, 3),
            'error_rate': round(error_rate, 2),
            'requests_per_minute': round(requests_per_minute, 2),
            'uptime_seconds': self.get_uptime()['seconds']
        }
    
    def get_detailed_stats(self):
        """Get comprehensive statistics"""
        return {
            'timestamp': time.time(),
            'current_time': datetime.now().isoformat(),
            'health': self.get_health_status(),
            'performance': self.get_performance_metrics(),
            'system': self.system_metrics,
            'restart_info': {
                'start_time': self.start_time,
                'last_restart': self.last_restart,
                'restart_count': self.restart_count
            }
        }
    
    def restart_server(self):
        """Mark server restart"""
        self.last_restart = time.time()
        self.restart_count += 1
        logger.warning(f"Server restart detected (count: {self.restart_count})")

# Global monitor instance
monitor = CaseStrainerMonitor()

def get_monitor():
    """Get the global monitor instance"""
    return monitor 