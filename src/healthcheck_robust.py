#!/usr/bin/env python3
"""
Robust health check script for CaseStrainer production environment.
This script provides comprehensive health checking with better error handling and diagnostics.
"""

import os
import sys
import time
import json
import logging
import requests
import redis
import sqlite3
from pathlib import Path
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class HealthChecker:
    def __init__(self):
        self.health_status = {
            "timestamp": time.time(),
            "overall": "healthy",
            "services": {},
            "errors": []
        }
        
        # Configuration
        self.backend_url = "http://localhost:5000/casestrainer/api/health"
        self.redis_host = "localhost"
        self.redis_port = 6379
        self.db_path = "data/citations.db"
        self.timeout = 10
        
    def check_redis(self) -> Dict[str, Any]:
        """Check Redis connectivity and health."""
        try:
            r = redis.Redis(host=self.redis_host, port=self.redis_port, db=0, socket_timeout=5)
            r.ping()
            
            # Check Redis info
            info = r.info()
            memory_usage = info.get('used_memory_human', 'N/A')
            connected_clients = info.get('connected_clients', 0)
            
            return {
                "status": "healthy",
                "memory_usage": memory_usage,
                "connected_clients": connected_clients,
                "error": None
            }
        except Exception as e:
            error_msg = f"Redis check failed: {str(e)}"
            logger.error(error_msg)
            return {
                "status": "unhealthy",
                "error": error_msg
            }
    
    def check_database(self) -> Dict[str, Any]:
        """Check database connectivity and health."""
        try:
            if not os.path.exists(self.db_path):
                return {
                    "status": "unhealthy",
                    "error": f"Database file not found: {self.db_path}"
                }
            
            conn = sqlite3.connect(self.db_path, timeout=5)
            cursor = conn.cursor()
            
            # Check if tables exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            # Check citations table specifically
            if 'citations' in tables:
                cursor.execute("SELECT COUNT(*) FROM citations")
                citation_count = cursor.fetchone()[0]
            else:
                citation_count = 0
            
            conn.close()
            
            return {
                "status": "healthy",
                "tables": tables,
                "citation_count": citation_count,
                "error": None
            }
        except Exception as e:
            error_msg = f"Database check failed: {str(e)}"
            logger.error(error_msg)
            return {
                "status": "unhealthy",
                "error": error_msg
            }
    
    def check_backend(self) -> Dict[str, Any]:
        """Check backend API health."""
        try:
            response = requests.get(self.backend_url, timeout=self.timeout)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    return {
                        "status": "healthy",
                        "response_time": response.elapsed.total_seconds(),
                        "data": data,
                        "error": None
                    }
                except json.JSONDecodeError:
                    return {
                        "status": "healthy",
                        "response_time": response.elapsed.total_seconds(),
                        "data": "Non-JSON response",
                        "error": None
                    }
            else:
                return {
                    "status": "unhealthy",
                    "status_code": response.status_code,
                    "error": f"Backend returned status code {response.status_code}"
                }
        except requests.exceptions.Timeout:
            error_msg = "Backend health check timed out"
            logger.error(error_msg)
            return {
                "status": "unhealthy",
                "error": error_msg
            }
        except requests.exceptions.ConnectionError:
            error_msg = "Backend connection refused"
            logger.error(error_msg)
            return {
                "status": "unhealthy",
                "error": error_msg
            }
        except Exception as e:
            error_msg = f"Backend check failed: {str(e)}"
            logger.error(error_msg)
            return {
                "status": "unhealthy",
                "error": error_msg
            }
    
    def check_rq_worker(self) -> Dict[str, Any]:
        """Check RQ worker status."""
        try:
            r = redis.Redis(host=self.redis_host, port=self.redis_port, db=0, socket_timeout=5)
            
            # Check for active workers
            workers = r.smembers('rq:workers')
            if workers:
                return {
                    "status": "healthy",
                    "active_workers": len(workers),
                    "worker_names": [w.decode('utf-8') for w in workers],
                    "error": None
                }
            else:
                return {
                    "status": "unhealthy",
                    "error": "No active RQ workers found"
                }
        except Exception as e:
            error_msg = f"RQ worker check failed: {str(e)}"
            logger.error(error_msg)
            return {
                "status": "unhealthy",
                "error": error_msg
            }
    
    def check_system_resources(self) -> Dict[str, Any]:
        """Check system resource usage."""
        try:
            import psutil
            
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            return {
                "status": "healthy",
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "disk_percent": disk.percent,
                "error": None
            }
        except ImportError:
            return {
                "status": "unknown",
                "error": "psutil not available for system resource monitoring"
            }
        except Exception as e:
            error_msg = f"System resource check failed: {str(e)}"
            logger.error(error_msg)
            return {
                "status": "unhealthy",
                "error": error_msg
            }
    
    def run_all_checks(self) -> Dict[str, Any]:
        """Run all health checks and return comprehensive status."""
        logger.info("Starting comprehensive health check...")
        
        # Run all checks
        self.health_status["services"]["redis"] = self.check_redis()
        self.health_status["services"]["database"] = self.check_database()
        self.health_status["services"]["backend"] = self.check_backend()
        self.health_status["services"]["rq_worker"] = self.check_rq_worker()
        self.health_status["services"]["system"] = self.check_system_resources()
        
        # Determine overall health
        unhealthy_services = []
        for service_name, service_status in self.health_status["services"].items():
            if service_status.get("status") == "unhealthy":
                unhealthy_services.append(service_name)
                self.health_status["errors"].append(f"{service_name}: {service_status.get('error', 'Unknown error')}")
        
        if unhealthy_services:
            self.health_status["overall"] = "unhealthy"
            logger.error(f"Unhealthy services detected: {', '.join(unhealthy_services)}")
        else:
            self.health_status["overall"] = "healthy"
            logger.info("All services are healthy")
        
        self.health_status["timestamp"] = time.time()
        return self.health_status
    
    def save_health_log(self, log_file: str = "logs/health_check.log"):
        """Save health check results to log file."""
        try:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            with open(log_file, 'a') as f:
                f.write(f"{json.dumps(self.health_status)}\n")
        except Exception as e:
            logger.error(f"Failed to save health log: {str(e)}")

def main():
    """Main function for health check script."""
    checker = HealthChecker()
    health_status = checker.run_all_checks()
    
    # Save to log file
    checker.save_health_log()
    
    # Print results
    print(json.dumps(health_status, indent=2))
    
    # Exit with appropriate code
    if health_status["overall"] == "healthy":
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main() 