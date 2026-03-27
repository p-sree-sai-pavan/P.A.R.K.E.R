"""
database.py — PostgreSQL connection management for Parker AI
"""
import time
import logging

from langgraph.store.postgres import PostgresStore
from langgraph.checkpoint.postgres import PostgresSaver

from config import DB_URI, DB_MAX_RETRIES, DB_RETRY_DELAY, EMBEDDING_DIMS
from models import embed_fn

logger = logging.getLogger(__name__)

_active_store_cm       = None
_active_checkpointer_cm = None


class DatabaseConnectionError(Exception):
    pass


def create_store() -> PostgresStore:
    """
    S4 fix: retry logic moved here so ALL entry points (app.py, main.py)
    benefit — not just get_db_connections() which was never called.
    """
    global _active_store_cm
    last_error = None

    for attempt in range(DB_MAX_RETRIES):
        try:
            cm    = PostgresStore.from_conn_string(
                DB_URI,
                index={
                    "dims":   EMBEDDING_DIMS,
                    "embed":  embed_fn,
                    "fields": ["text"],
                }
            )
            store            = cm.__enter__()
            _active_store_cm = cm
            return store
        except Exception as e:
            last_error = e
            wait       = DB_RETRY_DELAY * (attempt + 1)
            print(f"[DB] Store connection attempt {attempt + 1}/{DB_MAX_RETRIES} failed. Retrying in {wait}s... ({e})")
            time.sleep(wait)

    raise DatabaseConnectionError(
        f"Could not connect to PostgresStore after {DB_MAX_RETRIES} attempts: {last_error}"
    )


def create_checkpointer() -> PostgresSaver:
    """
    S4 fix: same retry logic for checkpointer.
    """
    global _active_checkpointer_cm
    last_error = None

    for attempt in range(DB_MAX_RETRIES):
        try:
            cm           = PostgresSaver.from_conn_string(DB_URI)
            checkpointer = cm.__enter__()
            _active_checkpointer_cm = cm
            return checkpointer
        except Exception as e:
            last_error = e
            wait       = DB_RETRY_DELAY * (attempt + 1)
            print(f"[DB] Checkpointer connection attempt {attempt + 1}/{DB_MAX_RETRIES} failed. Retrying in {wait}s... ({e})")
            time.sleep(wait)

    raise DatabaseConnectionError(
        f"Could not connect to PostgresSaver after {DB_MAX_RETRIES} attempts: {last_error}"
    )


def close_connections():
    global _active_store_cm, _active_checkpointer_cm
    for name, cm in [("store", _active_store_cm), ("checkpointer", _active_checkpointer_cm)]:
        if cm is not None:
            try:
                cm.__exit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error closing {name}: {e}")
    _active_store_cm        = None
    _active_checkpointer_cm = None


def setup_database(store: PostgresStore, checkpointer: PostgresSaver):
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