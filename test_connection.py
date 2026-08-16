import os
import sys
# Ensure current directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import time
import config
from database.connection import get_db

config.setup_logging()
import logging
logger = logging.getLogger("test_connection")

def test_conn():
    logger.info("=========================================")
    logger.info("Starting Live MongoDB Connection Test...")
    logger.info("=========================================")
    try:
        t0 = time.time()
        db = get_db()
        # Ping database
        db.client.admin.command('ping')
        latency = (time.time() - t0) * 1000
        logger.info(f"Successfully Pinged Server! Latency: {latency:.2f} ms")
        
        # Display database details
        logger.info(f"Connected database name: '{db.name}'")
        collections = db.list_collection_names()
        logger.info(f"Collections present on your Atlas Cluster: {collections}")
        
        for col_name in collections:
            indexes = list(db[col_name].index_information().keys())
            logger.info(f"  -> Collection [{col_name}] has indexes: {indexes}")
            
        logger.info("=========================================")
        logger.info("STATUS: MongoDB is fully CONNECTED and ACTIVE!")
        logger.info("=========================================")
    except Exception as e:
        logger.error(f"Connection check failed: {e}")

if __name__ == "__main__":
    test_conn()
