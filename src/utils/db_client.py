import logging
import sqlite3
import threading
from pathlib import Path
from .resource_path import get_resource_path

# Configure logging
logger = logging.getLogger(__name__)

# Global database path variable (only path, no connection)
db_path = None

# Lock for database initialization - moved to module level
_db_init_lock = threading.Lock()
_db_initialized = False  # Track initialization state

def get_db_path():
    """Get the database file path, initializing it if necessary
    
    Returns:
        Path: The database file path
    """
    global db_path
    if db_path is None:
        data_dir = Path(get_resource_path('data'))
        data_dir.mkdir(parents=True, exist_ok=True)
        db_path = data_dir / "creation_agent.db"
    return db_path

def initialize_db_schema(force_reset=False):
    """Initialize database schema using context manager
    
    Args:
        force_reset (bool, optional): Whether to reset the database tables
        
    Returns:
        bool: True if initialization was successful, False otherwise
    """
    global _db_initialized
    
    try:
        # Use a longer timeout for initialization
        db_file_path = get_db_path()
        conn = sqlite3.connect(db_file_path, timeout=60.0)
        
        try:
            # Enable WAL mode for better concurrent access
            conn.execute("PRAGMA journal_mode=WAL")
            # Set busy timeout
            conn.execute("PRAGMA busy_timeout=60000")
            cursor = conn.cursor()
            
            # Initialize database tables
            if force_reset:
                logger.info("Force reset enabled. Dropping existing tables...")
                cursor.execute("DROP TABLE IF EXISTS instagram_posts")
                cursor.execute("DROP TABLE IF EXISTS scraped_users")
                cursor.execute("DROP TABLE IF EXISTS caption_embeddings")
            
            # Create posts table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS instagram_posts (
                id TEXT PRIMARY KEY,
                code TEXT,
                taken_at TEXT,
                taken_at_formatted TEXT,
                media_type INTEGER,
                like_count INTEGER,
                comment_count INTEGER,
                play_count INTEGER,
                video_duration REAL,
                caption_text TEXT,
                username TEXT,
                full_name TEXT,
                is_verified INTEGER,
                image_url TEXT,
                video_url TEXT,
                location_name TEXT,
                location_city TEXT,
                post_url TEXT,
                is_paid_partnership INTEGER,
                commerciality_status TEXT,
                has_sponsorship_keywords INTEGER,
                tagged_users TEXT,
                scrape_date TEXT
            )
            """)
            
            # Create users tracking table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS scraped_users (
                username TEXT PRIMARY KEY,
                last_scraped TEXT
            )
            """)
            
            # Create caption embeddings table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS caption_embeddings (
                caption_hash TEXT PRIMARY KEY,
                caption_text TEXT NOT NULL,
                label TEXT NOT NULL,
                embedding_json TEXT
            )
            """)
            
            # Add index for label to improve query performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_caption_embeddings_label ON caption_embeddings(label)")
            # Add indexes for better performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_username ON instagram_posts(username)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_taken_at ON instagram_posts(taken_at)")
            
            conn.commit()
            cursor.close()
            
            _db_initialized = True
            logger.info(f"Database schema initialized at {get_db_path()}")
            return True
            
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error initializing database schema: {str(e)}")
        return False

class DatabaseConnection:
    """Context manager for database connections"""
    def __init__(self):
        self.connection = None
        self.cursor = None

    def __enter__(self):
        # Ensure database is initialized before creating connections
        ensure_db_initialized()
        
        # Create a new connection for each context manager instance
        db_file_path = get_db_path()
        
        # Use a reasonable timeout to prevent locks
        self.connection = sqlite3.connect(db_file_path, timeout=30.0)
        # Enable WAL mode for better concurrent access
        self.connection.execute("PRAGMA journal_mode=WAL")
        # Set busy timeout
        self.connection.execute("PRAGMA busy_timeout=30000")
        self.cursor = self.connection.cursor()
        return self.connection, self.cursor

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.cursor:
            self.cursor.close()
        if self.connection:
            if exc_type is None:
                # No exception occurred, commit changes
                self.connection.commit()
            else:
                # Exception occurred, rollback changes
                self.connection.rollback()
                logger.error(f"Database transaction rolled back due to: {exc_val}")
            # Close the connection when done
            self.connection.close()

def get_db_context():
    """Get a database context manager
    
    Returns:
        DatabaseConnection: A context manager for database operations
    """
    return DatabaseConnection()

def ensure_db_initialized(force_reset=False):
    """Ensure database schema is initialized. Call this explicitly when needed.
    
    Args:
        force_reset (bool): Whether to reset the database tables
    """
    global _db_initialized
    
    # Use a lock to prevent concurrent initialization
    with _db_init_lock:
        if force_reset:
            # If force_reset is True, always initialize with reset
            logger.info("Force reset requested, initializing schema with reset...")
            _db_initialized = False  # Reset the flag
            initialize_db_schema(force_reset=True)
            return
            
        # If already initialized and not forcing reset, skip
        if _db_initialized:
            return
            
        try:
            # Check if database file exists and has tables
            db_file_path = get_db_path()
            if not db_file_path.exists():
                logger.info("Database file not found, initializing schema...")
                initialize_db_schema()
                return
            
            # Check if tables exist with a quick connection
            conn = sqlite3.connect(db_file_path, timeout=10.0)
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='instagram_posts'")
                if not cursor.fetchone():
                    # Tables don't exist, initialize them
                    logger.info("Database tables not found, initializing schema...")
                    cursor.close()
                    conn.close()
                    initialize_db_schema()
                else:
                    # Tables exist, mark as initialized
                    _db_initialized = True
                    cursor.close()
                    conn.close()
            except Exception as e:
                conn.close()
                raise e
                
        except Exception as e:
            logger.info(f"Database not accessible, initializing schema: {str(e)}")
            initialize_db_schema()

# Optional: Add a function to explicitly initialize at application startup
def initialize_database_at_startup(force_reset=False):
    """
    Call this function once at application startup to ensure database is ready.
    This prevents multiple threads from trying to initialize simultaneously.
    """
    logger.info("Initializing database at application startup...")
    ensure_db_initialized(force_reset=force_reset)
    # Initialize the sent messages table separately
    initialize_sent_messages_table()

def initialize_sent_messages_table():
    """
    Initialize the sent_messages table which tracks Instagram profiles that have been messaged.
    This table is not reset when other tables are reset.
    """
    try:
        # Use a longer timeout for initialization
        db_file_path = get_db_path()
        conn = sqlite3.connect(db_file_path, timeout=60.0)
        
        try:
            # Enable WAL mode for better concurrent access
            conn.execute("PRAGMA journal_mode=WAL")
            # Set busy timeout
            conn.execute("PRAGMA busy_timeout=60000")
            cursor = conn.cursor()
            
            # Create sent messages tracking table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS sent_messages (
                profile_url TEXT PRIMARY KEY,
                username TEXT,
                message_text TEXT,
                sent_date TEXT,
                success INTEGER
            )
            """)
            
            # Add index for better performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sent_messages_username ON sent_messages(username)")
            
            conn.commit()
            cursor.close()
            
            logger.info(f"Sent messages table initialized at {get_db_path()}")
            return True
            
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error initializing sent messages table: {str(e)}")
        return False