import logging
from pymongo import IndexModel, ASCENDING, DESCENDING
from database.connection import get_db
import config

logger = logging.getLogger("database.collections")

def initialize_database():
    try:
        db = get_db()
        existing_collections = db.list_collection_names()
        logger.info(f"Existing collections: {existing_collections}")
        
        # 1. Classes_Session Collection Setup
        col_session = "Classes_Session"
        if col_session not in existing_collections:
            logger.info(f"Creating collection: {col_session}")
            db.create_collection(col_session)
        
        # Create indexes for Classes_Session
        # session_id unique index
        db[col_session].create_index([("session_id", ASCENDING)], unique=True)
        # class_name + teacher + started_at compound unique index
        db[col_session].create_index(
            [("class_name", ASCENDING), ("teacher", ASCENDING), ("started_at", ASCENDING)],
            unique=True
        )
        logger.info(f"Indexes verified for {col_session}")

        # 2. Attention_Metrics Time Series Collection Setup
        col_metrics = "Attention_Metrics"
        retention_seconds = config.RETENTION_DAYS * 86400
        
        if col_metrics not in existing_collections:
            logger.info(f"Creating Time Series collection: {col_metrics} with TTL = {retention_seconds} seconds")
            db.create_collection(
                col_metrics,
                timeseries={
                    "timeField": "timestamp",
                    "metaField": "metadata",
                    "granularity": "seconds"
                },
                expireAfterSeconds=retention_seconds
            )
        else:
            # If exists, update its expireAfterSeconds using collMod command
            logger.info(f"Updating TTL index on Time Series {col_metrics} using collMod.")
            try:
                db.command("collMod", col_metrics, expireAfterSeconds=retention_seconds)
                logger.info(f"Successfully modified TTL to {retention_seconds} seconds for {col_metrics}")
            except Exception as e:
                logger.warning(f"Could not modify TTL via collMod: {e}")
                
        # Compound index on metadata.session_id and timestamp to optimize time-series query
        db[col_metrics].create_index([("metadata.session_id", ASCENDING), ("timestamp", DESCENDING)])
        logger.info(f"Indexes verified for {col_metrics}")

        # 3. Abnormal_Events Collection Setup
        col_events = "Abnormal_Events"
        if col_events not in existing_collections:
            logger.info(f"Creating collection: {col_events}")
            db.create_collection(col_events)
            
        # Compound index on session_id and started_at
        db[col_events].create_index([("session_id", ASCENDING), ("started_at", ASCENDING)])
        logger.info(f"Indexes verified for {col_events}")
        
        logger.info("MongoDB database initialization completed successfully.")
        
    except Exception as e:
        logger.error(f"Error initializing MongoDB environment: {e}")
        raise e
