import json
import redis
import sqlite3
import gzip
import pickle
import time
import os
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timedelta
import logging
import hashlib
from functools import lru_cache

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UnifiedCacheManager:
    """
    Unified cache manager using Redis as primary cache with SQLite persistence.
    
    Features:
    - Redis for fast in-memory caching
    - SQLite for persistent storage
    - Automatic compression for large data
    - TTL management
    - Cache warming from SQLite
    - Memory usage monitoring
    """
    
    def __init__(self, config_file: str = "cache_config.json"):
        self.config = self._load_config(config_file)
        self.redis_client = None
        self.db_path = self.config['database_cache']['file']
        self._init_redis()
        self._init_database()
        
        # Initialize cache directories
        self.cache_dir = "citation_cache"
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # In-memory LRU cache for frequently accessed items
        self.memory_cache = {}
        self.memory_cache_max_size = 1000
        self.memory_cache_ttl = 3600  # 1 hour
        
    def _load_config(self, config_file: str) -> Dict[str, Any]:
        """Load cache configuration from JSON file."""
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"Config file {config_file} not found, using defaults")
            return {
                "redis": {
                    "host": "localhost",
                    "port": 6379,
                    "databases": {
                        "rq_queue": 0,
                        "citation_cache": 1,
                        "url_cache": 2,
                        "session_data": 3
                    }
                },
                "citation_cache": {
                    "ttl": 2592000,
                    "max_size": "100MB",
                    "compression": True
                },
                "url_cache": {
                    "ttl": 604800,
                    "max_size": "500MB",
                    "compression": True
                },
                "database_cache": {
                    "file": "data/citations.db",
                    "indexes": True,
                    "vacuum_interval": 86400
                }
            }
    
    def _init_redis(self):
        """Initialize Redis connection with retry mechanism."""
        import time
        max_retries = 5
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                # Use REDIS_URL environment variable if available, otherwise fallback to localhost
                redis_url = os.environ.get('REDIS_URL', 'redis://casestrainer-redis-prod:6379/0')
                if redis_url.startswith('redis://'):
                    # Parse redis://host:port/db format
                    from urllib.parse import urlparse
                    parsed = urlparse(redis_url)
                    redis_host = parsed.hostname or 'localhost'
                    redis_port = parsed.port or 6379
                    redis_db = int(parsed.path.lstrip('/')) if parsed.path else 0
                else:
                    # Fallback to localhost
                    redis_host = 'localhost'
                    redis_port = 6379
                    redis_db = 0
                
                self.redis_client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    db=redis_db,
                    decode_responses=False,
                    socket_connect_timeout=5,
                    socket_timeout=5
                )
                # Test connection
                self.redis_client.ping()
                logger.info(f"Redis connection established on attempt {attempt + 1} to {redis_host}:{redis_port}")
                return
            except Exception as e:
                logger.warning(f"Redis connection attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying Redis connection in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error(f"Redis connection failed after {max_retries} attempts: {e}")
                    self.redis_client = None
    
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
                
                # Create cache_stats table if it doesn't exist
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cache_stats'")
                stats_table_exists = cursor.fetchone() is not None
                
                if not stats_table_exists:
                    cursor.execute('''
                        CREATE TABLE cache_stats (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            cache_type TEXT NOT NULL,
                            hits INTEGER DEFAULT 0,
                            misses INTEGER DEFAULT 0,
                            size_bytes INTEGER DEFAULT 0,
                            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')
                
                # Create indexes if enabled
                if self.config['database_cache']['indexes']:
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_citation_text ON citations(citation_text)')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_case_name ON citations(case_name)')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_year ON citations(year)')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_updated_at ON citations(updated_at)')
                
                conn.commit()
                logger.info("SQLite database initialized")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
    
    def _compress_data(self, data: Any) -> bytes:
        """Compress data using gzip."""
        try:
            serialized = pickle.dumps(data)
            return gzip.compress(serialized)
        except Exception as e:
            logger.error(f"Compression failed: {e}")
            return pickle.dumps(data)
    
    def _decompress_data(self, data: bytes) -> Any:
        """Decompress data using gzip."""
        try:
            decompressed = gzip.decompress(data)
            return pickle.loads(decompressed)
        except Exception:
            # Fallback to direct pickle if not compressed
            return pickle.loads(data)
    
    def _get_redis_key(self, cache_type: str, key: str) -> str:
        """Generate Redis key with namespace."""
        return f"casestrainer:{cache_type}:{key}"
    
    def _get_cache_key(self, key: str, cache_type: str = "citation") -> str:
        """Generate a cache key with type prefix."""
        return f"{cache_type}:{hashlib.md5(key.encode()).hexdigest()}"

    def get_citation(self, citation: str) -> Optional[Dict[str, Any]]:
        """Get citation from cache (Redis -> Memory -> File -> Database)."""
        if not citation:
            return None
            
        cache_key = self._get_cache_key(citation, "citation")
        
        # 1. Check in-memory cache first (fastest)
        if cache_key in self.memory_cache:
            item = self.memory_cache[cache_key]
            if datetime.now() < item['expires']:
                logger.debug(f"Memory cache hit for: {citation}")
                return item['data']
            else:
                del self.memory_cache[cache_key]
        
        # 2. Check Redis cache
        if self.redis_client:
            try:
                cached_data = self.redis_client.get(cache_key)
                if cached_data:
                    data = json.loads(gzip.decompress(cached_data).decode())
                    # Store in memory cache for future access
                    self._set_memory_cache(cache_key, data)
                    logger.debug(f"Redis cache hit for: {citation}")
                    return data
            except Exception as e:
                logger.warning(f"Redis cache error: {e}")
        
        # 3. Check file cache
        file_data = self._get_file_cache(citation)
        if file_data:
            # Store in Redis and memory for future access
            if self.redis_client:
                try:
                    compressed_data = gzip.compress(json.dumps(file_data).encode())
                    self.redis_client.setex(cache_key, 86400, compressed_data)  # 24 hour TTL
                except Exception as e:
                    logger.warning(f"Failed to store in Redis: {e}")
            self._set_memory_cache(cache_key, file_data)
            logger.debug(f"File cache hit for: {citation}")
            return file_data
        
        # 4. Check database cache
        db_data = self._get_database_cache(citation)
        if db_data:
            # Store in all caches for future access
            if self.redis_client:
                try:
                    compressed_data = gzip.compress(json.dumps(db_data).encode())
                    self.redis_client.setex(cache_key, 86400, compressed_data)
                except Exception as e:
                    logger.warning(f"Failed to store in Redis: {e}")
            self._set_memory_cache(cache_key, db_data)
            logger.debug(f"Database cache hit for: {citation}")
            return db_data
        
        logger.debug(f"Cache miss for: {citation}")
        return None

    def set_citation(self, citation: str, data: Dict[str, Any]) -> bool:
        """Set citation in all cache layers."""
        if not citation:
            return False
            
        cache_key = self._get_cache_key(citation, "citation")
        
        # Store in all cache layers
        success = True
        
        # 1. Memory cache
        self._set_memory_cache(cache_key, data)
        
        # 2. Redis cache
        if self.redis_client:
            try:
                compressed_data = gzip.compress(json.dumps(data).encode())
                self.redis_client.setex(cache_key, 86400, compressed_data)
            except Exception as e:
                logger.warning(f"Failed to store in Redis: {e}")
                success = False
        
        # 3. File cache
        if not self._set_file_cache(citation, data):
            success = False
        
        # 4. Database cache
        if not self._set_database_cache(citation, data):
            success = False
        
        return success

    def _set_memory_cache(self, key: str, data: Dict[str, Any]):
        """Set item in memory cache with TTL."""
        # Implement LRU eviction if cache is full
        if len(self.memory_cache) >= self.memory_cache_max_size:
            # Remove oldest items
            oldest_key = min(self.memory_cache.keys(), 
                           key=lambda k: self.memory_cache[k]['expires'])
            del self.memory_cache[oldest_key]
        
        self.memory_cache[key] = {
            'data': data,
            'expires': datetime.now() + timedelta(seconds=self.memory_cache_ttl)
        }

    def _get_file_cache(self, citation: str) -> Optional[Dict[str, Any]]:
        """Get citation from file cache."""
        try:
            cache_file = os.path.join(self.cache_dir, f"{citation.replace(' ', '_')}.json")
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"File cache read error: {e}")
        return None

    def _set_file_cache(self, citation: str, data: Dict[str, Any]) -> bool:
        """Set citation in file cache."""
        try:
            cache_file = os.path.join(self.cache_dir, f"{citation.replace(' ', '_')}.json")
            with open(cache_file, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            logger.warning(f"File cache write error: {e}")
            return False

    def _get_database_cache(self, citation: str) -> Optional[Dict[str, Any]]:
        """Get citation from database cache."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                'SELECT verification_result FROM citations WHERE citation_text = ?',
                (citation,)
            )
            result = cursor.fetchone()
            conn.close()
            
            if result and result[0]:
                return json.loads(result[0])
        except Exception as e:
            logger.warning(f"Database cache read error: {e}")
        return None

    def _set_database_cache(self, citation: str, data: Dict[str, Any]) -> bool:
        """Set citation in database cache."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO citations 
                (citation_text, verification_result, updated_at) 
                VALUES (?, ?, ?)
            ''', (citation, json.dumps(data), datetime.now().isoformat()))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.warning(f"Database cache write error: {e}")
            return False

    def get_url_content(self, url: str) -> Optional[str]:
        """Get URL content from cache."""
        if not self.redis_client:
            return None
        
        redis_key = self._get_redis_key('url', url)
        try:
            cached_data = self.redis_client.get(redis_key)
            if cached_data:
                self._update_stats('url', 'hit')
                return self._decompress_data(cached_data)
            else:
                self._update_stats('url', 'miss')
                return None
        except Exception as e:
            logger.error(f"Error getting URL content {url}: {e}")
            return None
    
    def set_url_content(self, url: str, content: str) -> bool:
        """Set URL content in Redis."""
        if not self.redis_client:
            return False
        
        try:
            redis_key = self._get_redis_key('url', url)
            compressed_data = self._compress_data(content)
            self.redis_client.setex(
                redis_key,
                self.config['url_cache']['ttl'],
                compressed_data
            )
            return True
        except Exception as e:
            logger.error(f"Error setting URL content {url}: {e}")
            return False
    
    def _get_from_sqlite(self, table: str, key: str) -> Optional[Dict[str, Any]]:
        """Get data from SQLite database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Handle the existing schema which uses citation_text
                if table == 'citations':
                    cursor.execute('SELECT * FROM citations WHERE citation_text = ?', (key,))
                else:
                    cursor.execute(f'SELECT * FROM {table} WHERE citation = ?', (key,))
                
                row = cursor.fetchone()
                if row:
                    columns = [description[0] for description in cursor.description]
                    return dict(zip(columns, row))
                return None
        except Exception as e:
            logger.error(f"SQLite get failed: {e}")
            return None
    
    def _set_in_sqlite(self, table: str, key: str, data: Dict[str, Any]) -> bool:
        """Set data in SQLite database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Handle citations table specifically with existing schema
                if table == 'citations':
                    # Check if record exists
                    cursor.execute('SELECT id FROM citations WHERE citation_text = ?', (key,))
                    existing = cursor.fetchone()
                    
                    if existing:
                        # Update existing record
                        cursor.execute('''
                            UPDATE citations 
                            SET case_name = ?, year = ?, parallel_citations = ?, verification_result = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE citation_text = ?
                        ''', (
                            data.get('case_name'),
                            data.get('year'),
                            json.dumps(data.get('parallel_citations', [])),
                            json.dumps(data.get('verification_result', {})),
                            key
                        ))
                    else:
                        # Insert new record
                        cursor.execute('''
                            INSERT INTO citations 
                            (citation_text, case_name, year, parallel_citations, verification_result, found, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        ''', (
                            key,
                            data.get('case_name'),
                            data.get('year'),
                            json.dumps(data.get('parallel_citations', [])),
                            json.dumps(data.get('verification_result', {})),
                            data.get('verification_result', {}).get('valid', False)
                        ))
                
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"SQLite set failed: {e}")
            return False
    
    def _set_in_redis(self, cache_type: str, key: str, data: Any, ttl: int) -> bool:
        """Set data in Redis with TTL."""
        try:
            redis_key = self._get_redis_key(cache_type, key)
            compressed_data = self._compress_data(data)
            self.redis_client.setex(redis_key, ttl, compressed_data)
            return True
        except Exception as e:
            logger.error(f"Redis set failed: {e}")
            return False
    
    def _update_stats(self, cache_type: str, stat_type: str):
        """Update cache statistics."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO cache_stats (cache_type, hits, misses, last_updated)
                    VALUES (
                        ?,
                        CASE WHEN ? = 'hit' THEN 1 ELSE 0 END,
                        CASE WHEN ? = 'miss' THEN 1 ELSE 0 END,
                        CURRENT_TIMESTAMP
                    )
                ''', (cache_type, stat_type, stat_type))
                conn.commit()
        except Exception as e:
            logger.error(f"Stats update failed: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        stats = {
            'redis_connected': self.redis_client is not None,
            'cache_stats': {},
            'memory_usage': {}
        }
        
        # Get SQLite stats
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT cache_type, hits, misses FROM cache_stats')
                for row in cursor.fetchall():
                    cache_type, hits, misses = row
                    total = hits + misses
                    hit_rate = (hits / total * 100) if total > 0 else 0
                    stats['cache_stats'][cache_type] = {
                        'hits': hits,
                        'misses': misses,
                        'hit_rate': f"{hit_rate:.1f}%"
                    }
        except Exception as e:
            logger.error(f"Stats retrieval failed: {e}")
        
        # Get Redis memory usage
        if self.redis_client:
            try:
                info = self.redis_client.info('memory')
                stats['memory_usage']['redis'] = {
                    'used_memory': info.get('used_memory_human', 'N/A'),
                    'used_memory_peak': info.get('used_memory_peak_human', 'N/A')
                }
            except Exception as e:
                logger.error(f"Redis memory info failed: {e}")
        
        return stats
    
    def warm_cache(self, limit: int = 1000) -> int:
        """Warm Redis cache from SQLite database."""
        if not self.redis_client:
            return 0
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Use the existing schema with citation_text column
                cursor.execute('''
                    SELECT citation_text, case_name, year, parallel_citations, verification_result
                    FROM citations 
                    ORDER BY updated_at DESC 
                    LIMIT ?
                ''', (limit,))
                
                warmed = 0
                for row in cursor.fetchall():
                    citation, case_name, year, parallel_citations, verification_result = row
                    
                    # Convert existing data to new format
                    if verification_result:
                        try:
                            verification_data = json.loads(verification_result)
                        except:
                            verification_data = {
                                'valid': True,
                                'found': True,
                                'confidence': 0.8,
                                'source': 'database'
                            }
                    else:
                        verification_data = {
                            'valid': True,
                            'found': True,
                            'confidence': 0.8,
                            'source': 'database'
                        }
                    
                    data = {
                        'case_name': case_name or '',
                        'year': year,
                        'parallel_citations': json.loads(parallel_citations) if parallel_citations else [],
                        'verification_result': json.dumps(verification_data)
                    }
                    
                    if self._set_in_redis('citation', citation, data, 
                                        self.config['citation_cache']['ttl']):
                        warmed += 1
                
                logger.info(f"Warmed {warmed} citations in Redis cache")
                return warmed
        except Exception as e:
            logger.error(f"Cache warming failed: {e}")
            return 0
    
    def clear_cache(self, cache_type: str = "all"):
        """Clear specified cache type."""
        if cache_type in ["all", "memory"]:
            self.memory_cache.clear()
            logger.info("Memory cache cleared")
        
        if cache_type in ["all", "redis"] and self.redis_client:
            try:
                self.redis_client.flushdb()
                logger.info("Redis cache cleared")
            except Exception as e:
                logger.warning(f"Failed to clear Redis cache: {e}")
        
        if cache_type in ["all", "file"]:
            try:
                for file in os.listdir(self.cache_dir):
                    if file.endswith('.json'):
                        os.remove(os.path.join(self.cache_dir, file))
                logger.info("File cache cleared")
            except Exception as e:
                logger.warning(f"Failed to clear file cache: {e}")

# Global cache manager instance
_cache_manager = None

def get_cache_manager() -> UnifiedCacheManager:
    """Get or create the global cache manager instance."""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = UnifiedCacheManager()
    return _cache_manager 