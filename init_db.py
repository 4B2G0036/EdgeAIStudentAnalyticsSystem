import os
import sys
# Ensure current directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import logging
import config
from database.collections import initialize_database


# Setup project logging format supporting trace_id
config.setup_logging()
logger = logging.getLogger("init_db")

def main():
    logger.info("==================================================")
    logger.info("Initializing MongoDB Environment for Project...")
    logger.info("==================================================")
    try:
        initialize_database()
        logger.info("==================================================")
        logger.info("SUCCESS: MongoDB database environment setup is ready!")
        logger.info("==================================================")
    except Exception as e:
        logger.critical(f"CRITICAL: Failed to initialize MongoDB environment: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
