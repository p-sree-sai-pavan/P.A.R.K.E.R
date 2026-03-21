"""
database.py — PostgreSQL connection management for Parker AI
Handles connection establishment, retries, and graceful shutdown.
"""
import time
import logging
from contextlib import contextmanager

from langgraph.store.postgres import PostgresStore
from langgraph.checkpoint.postgres import PostgresSaver

from config import DB_URI, DB_MAX_RETRIES, DB_RETRY_DELAY, EMBEDDING_DIMS
from models import embed_fn

logger = logging.getLogger(__name__)

# Keep references to the context managers so we can close them on shutdown
_active_store_cm = None
_active_checkpointer_cm = None


class DatabaseConnectionError(Exception):
    """Raised when database connection fails after retries."""
    pass


def create_store() -> PostgresStore:
    """Create a PostgresStore with proper configuration.

    In langgraph-checkpoint-postgres >= 3.x, from_conn_string() returns
    a context manager. We enter it immediately and keep a reference to
    the context manager for later cleanup.
    """
    global _active_store_cm
    cm = PostgresStore.from_conn_string(
        DB_URI,
        index={
            "dims": EMBEDDING_DIMS,
            "embed": embed_fn,
            "fields": ["text"],
        }
    )
    store = cm.__enter__()
    _active_store_cm = cm
    return store


def create_checkpointer() -> PostgresSaver:
    """Create a PostgresSaver for conversation checkpoints.

    In langgraph-checkpoint-postgres >= 3.x, from_conn_string() returns
    a context manager. We enter it immediately and keep a reference to
    the context manager for later cleanup.
    """
    global _active_checkpointer_cm
    cm = PostgresSaver.from_conn_string(DB_URI)
    checkpointer = cm.__enter__()
    _active_checkpointer_cm = cm
    return checkpointer


def close_connections():
    """Gracefully close active database connections."""
    global _active_store_cm, _active_checkpointer_cm
    for name, cm in [("store", _active_store_cm), ("checkpointer", _active_checkpointer_cm)]:
        if cm is not None:
            try:
                cm.__exit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error closing {name}: {e}")
    _active_store_cm = None
    _active_checkpointer_cm = None


@contextmanager
def get_db_connections():
    """
    Context manager for database connections with proper cleanup.
    Handles connection failures with retries.

    Usage:
        with get_db_connections() as (store, checkpointer):
            store.setup()
            checkpointer.setup()
            # use store and checkpointer...
    """
    store = None
    checkpointer = None
    last_error = None

    for attempt in range(DB_MAX_RETRIES):
        try:
            store = create_store()
            checkpointer = create_checkpointer()
            break
        except Exception as e:
            last_error = e
            logger.warning(f"Database connection attempt {attempt + 1} failed: {e}")
            if attempt < DB_MAX_RETRIES - 1:
                time.sleep(DB_RETRY_DELAY * (attempt + 1))

    if store is None or checkpointer is None:
        raise DatabaseConnectionError(
            f"Failed to connect to database after {DB_MAX_RETRIES} attempts. "
            f"Last error: {last_error}"
        )

    try:
        yield store, checkpointer
    finally:
        close_connections()


def setup_database(store: PostgresStore, checkpointer: PostgresSaver):
    """
    Initialize database tables if they don't exist.
    Safe to call on every startup.
    """
    try:
        store.setup()
        logger.info("PostgresStore initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize PostgresStore: {e}")
        raise

    try:
        checkpointer.setup()
        logger.info("PostgresSaver initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize PostgresSaver: {e}")
        raise


def test_connection() -> bool:
    """
    Test database connection without full setup.
    Returns True if connection successful, False otherwise.
    """
    try:
        with get_db_connections() as (store, _):
            # Simple query to test connection
            return True
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        return False