import logging
from pymongo import MongoClient
import config

logger = logging.getLogger("database.connection")

_client = None

def get_db_client():
    global _client
    if _client is None:
        try:
            logger.info(f"Connecting to MongoDB with URI: {config.MONGO_URI}")
            # Use connection string from config.py (.env)
            # Add timeout settings to avoid hanging forever if connection fails
            _client = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=5000)
            # Trigger serverSelectionTimeoutMS check by pinging
            _client.admin.command('ping')
            logger.info("Connected successfully to MongoDB.")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise ConnectionError(f"DatabaseConnectionError: Unable to connect to MongoDB at {config.MONGO_URI}. Details: {e}")
    return _client

def get_db():
    client = get_db_client()
    return client[config.MONGO_DB_NAME]
