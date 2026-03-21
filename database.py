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


class DatabaseConnectionError(Exception):
    """Raised when database connection fails after retries."""
    pass


def create_store() -> PostgresStore:
    """Create a PostgresStore with proper configuration."""
    return PostgresStore.from_conn_string(
        DB_URI,
        index={
            "dims": EMBEDDING_DIMS,
            "embed": embed_fn,
            "fields": ["text"],
        }
    )


def create_checkpointer() -> PostgresSaver:
    """Create a PostgresSaver for conversation checkpoints."""
    return PostgresSaver.from_conn_string(DB_URI)


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
        # Cleanup connections
        try:
            if store:
                store.__exit__(None, None, None)
        except Exception as e:
            logger.warning(f"Error closing store: {e}")

        try:
            if checkpointer:
                checkpointer.__exit__(None, None, None)
        except Exception as e:
            logger.warning(f"Error closing checkpointer: {e}")


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