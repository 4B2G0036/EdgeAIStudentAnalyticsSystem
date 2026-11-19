import logging
import threading
from pymongo import MongoClient
import config

logger = logging.getLogger("database.connection")

_client = None
_client_lock = threading.Lock()


def get_db_client():
    global _client
    if _client is not None:
        return _client

    with _client_lock:
        if _client is not None:
            return _client
        try:
            logger.info(f"Connecting to MongoDB with URI: {config.MONGO_URI}")
            # Create local instance first; only assign to global _client after ping succeeds
            candidate = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=5000)
            candidate.admin.command('ping')
            _client = candidate
            logger.info("Connected successfully to MongoDB.")
        except Exception as e:
            _client = None
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise ConnectionError(f"DatabaseConnectionError: Unable to connect to MongoDB at {config.MONGO_URI}. Details: {e}")
    return _client


def get_db():
    client = get_db_client()
    return client[config.MONGO_DB_NAME]
