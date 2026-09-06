import logging
from datetime import datetime
from pymongo import ASCENDING, DESCENDING
from database.connection import get_db

logger = logging.getLogger("database.queries")

def create_session(session_id: str, class_name: str, teacher: str, room: str = "", roi_polygon: list = None, notes: str = "") -> dict:
    db = get_db()
    session_doc = {
        "session_id": session_id,
        "class_name": class_name,
        "teacher": teacher,
        "room": room,
        "started_at": datetime.utcnow(),
        "ended_at": None,
        "student_count": 0,
        "roi_polygon": roi_polygon if roi_polygon is not None else [],
        "notes": notes
    }
    
    try:
        # Check if there is an active session with the same compound index to prevent duplicate
        # MongoDB index: class_name + teacher + started_at is unique, but we also want to avoid having
        # two concurrent active sessions for the same teacher/class.
        # Although the compound index checks uniqueness including started_at (which is highly unlikely to conflict down to the millisecond),
        # we can do an application-level check for safety.
        db["Classes_Session"].insert_one(session_doc)
        logger.info(f"Session {session_id} created in DB for class '{class_name}'.")
        return session_doc
    except Exception as e:
        logger.error(f"Failed to create session {session_id} in DB: {e}")
        raise e

def end_session(session_id: str) -> dict:
    db = get_db()
    ended_at = datetime.utcnow()
    
    try:
        result = db["Classes_Session"].find_one_and_update(
            {"session_id": session_id},
            {"$set": {"ended_at": ended_at}},
            return_document=True
        )
        if result:
            logger.info(f"Session {session_id} ended at {ended_at} in DB.")
            return result
        else:
            logger.warning(f"Session {session_id} not found to end.")
            return None
    except Exception as e:
        logger.error(f"Failed to end session {session_id} in DB: {e}")
        raise e

def update_session(session_id: str, fields: dict) -> dict:
    """Update editable metadata fields for a session (class_name, teacher, room, notes)."""
    db = get_db()
    allowed_fields = {"class_name", "teacher", "room", "notes"}
    update_data = {k: v for k, v in fields.items() if k in allowed_fields}
    if not update_data:
        return None
    try:
        result = db["Classes_Session"].find_one_and_update(
            {"session_id": session_id},
            {"$set": update_data},
            return_document=True
        )
        if result:
            logger.info(f"Session {session_id} updated with fields: {update_data}")
            return result
        else:
            logger.warning(f"Session {session_id} not found to update.")
            return None
    except Exception as e:
        logger.error(f"Failed to update session {session_id}: {e}")
        raise e

def get_session_by_id(session_id: str) -> dict:
    db = get_db()
    try:
        return db["Classes_Session"].find_one({"session_id": session_id}, {"_id": 0})
    except Exception as e:
        logger.error(f"Error fetching session {session_id}: {e}")
        return None

def get_active_session() -> dict:
    # Helper to find if there is currently an ongoing session (ended_at is null)
    db = get_db()
    try:
        return db["Classes_Session"].find_one({"ended_at": None}, {"_id": 0})
    except Exception as e:
        logger.error(f"Error checking active session: {e}")
        return None

def list_sessions(limit: int = 10, offset: int = 0, search_query: str = None, status_filter: str = None) -> list[dict]:
    db = get_db()
    query = {}
    if search_query:
        query["$or"] = [
            {"class_name": {"$regex": search_query, "$options": "i"}},
            {"teacher": {"$regex": search_query, "$options": "i"}}
        ]
    if status_filter:
        if status_filter == "active":
            query["ended_at"] = None
        elif status_filter == "ended":
            query["ended_at"] = {"$ne": None}
            
    try:
        cursor = db["Classes_Session"].find(query, {"_id": 0})\
                                      .sort("started_at", DESCENDING)\
                                      .skip(offset)\
                                      .limit(limit)
        return list(cursor)
    except Exception as e:
        logger.error(f"Error listing sessions: {e}")
        return []

def get_session_summary(session_id: str) -> dict:
    db = get_db()
    try:
        session = db["Classes_Session"].find_one({"session_id": session_id}, {"_id": 0})
        if not session:
            return None
            
        # Compile a basic summary from Attention_Metrics and Abnormal_Events
        # 1. Total anomalies count
        anomalies_count = db["Abnormal_Events"].count_documents({"session_id": session_id})
        
        # 2. Query average attention score from Attention_Metrics
        # Time-series collection aggregation
        pipeline = [
            {"$match": {"metadata.session_id": session_id}},
            {"$group": {
                "_id": None,
                "avg_score": {"$avg": "$attention_score"}
            }}
        ]
        agg_result = list(db["Attention_Metrics"].aggregate(pipeline))
        avg_score = agg_result[0]["avg_score"] if agg_result else 100.0
        
        return {
            "session_id": session_id,
            "class_name": session.get("class_name"),
            "teacher": session.get("teacher"),
            "started_at": session.get("started_at"),
            "ended_at": session.get("ended_at"),
            "max_student_count": session.get("student_count", 0),
            "avg_attention_score": round(avg_score, 2) if avg_score is not None else 100.0,
            "total_abnormal_events": anomalies_count
        }
    except Exception as e:
        logger.error(f"Error generating session summary for {session_id}: {e}")
        return None

def delete_session(session_id: str) -> bool:
    """Delete session metadata, time series metrics, and abnormal events."""
    db = get_db()
    try:
        res = db["Classes_Session"].delete_one({"session_id": session_id})
        db["Attention_Metrics"].delete_many({"metadata.session_id": session_id})
        db["Abnormal_Events"].delete_many({"session_id": session_id})
        logger.info(f"Session {session_id} and all related metrics/events deleted.")
        return res.deleted_count > 0
    except Exception as e:
        logger.error(f"Failed to delete session {session_id}: {e}")
        raise e

def get_active_session_metrics(session_id: str) -> dict:
    """Fetch live metrics (student count, average attention score, and latest event) for a session."""
    db = get_db()
    try:
        latest_metric = db["Attention_Metrics"].find_one(
            {"metadata.session_id": session_id},
            sort=[("timestamp", DESCENDING)]
        )
        live_score = latest_metric.get("attention_score", 100.0) if latest_metric else 100.0
        student_count = latest_metric.get("student_count", 0) if latest_metric else 0
        
        abnormal_count = db["Abnormal_Events"].count_documents({"session_id": session_id})
        
        latest_event = db["Abnormal_Events"].find_one(
            {"session_id": session_id},
            sort=[("started_at", DESCENDING)]
        )
        latest_event_str = ""
        if latest_event:
            event_type = latest_event.get("event_type", "未知行為")
            student_id = latest_event.get("student_id", "未知ID")
            latest_event_str = f"學生 {student_id}: {event_type}"
            
        return {
            "session_id": session_id,
            "attention_score": float(live_score),
            "student_count": int(student_count),
            "total_abnormal_events": int(abnormal_count),
            "latest_event": latest_event_str
        }
    except Exception as e:
        logger.error(f"Error fetching active session metrics for {session_id}: {e}")
        return None

def get_session_metrics(session_id: str, start_ts: float = None, end_ts: float = None, limit: int = 500) -> list[dict]:
    """Query time-series attention metrics for a specific session."""
    db = get_db()
    query = {"metadata.session_id": session_id}
    
    if start_ts is not None or end_ts is not None:
        time_cond = {}
        if start_ts is not None:
            time_cond["$gte"] = datetime.utcfromtimestamp(start_ts)
        if end_ts is not None:
            time_cond["$lte"] = datetime.utcfromtimestamp(end_ts)
        query["timestamp"] = time_cond

    try:
        cursor = db["Attention_Metrics"].find(query, {"_id": 0})\
                                       .sort("timestamp", ASCENDING)\
                                       .limit(limit)
        results = list(cursor)
        for r in results:
            if isinstance(r.get("timestamp"), datetime):
                r["timestamp"] = r["timestamp"].isoformat()
        return results
    except Exception as e:
        logger.error(f"Error querying session metrics for {session_id}: {e}")
        return []

def get_session_events(session_id: str, event_type: str = None) -> list[dict]:
    """Query abnormal events for a specific session."""
    db = get_db()
    query = {"session_id": session_id}
    if event_type:
        query["event_type"] = event_type

    try:
        cursor = db["Abnormal_Events"].find(query, {"_id": 0}).sort("started_at", DESCENDING)
        results = list(cursor)
        for r in results:
            if isinstance(r.get("started_at"), datetime):
                r["started_at"] = r["started_at"].isoformat()
            if isinstance(r.get("updated_at"), datetime):
                r["updated_at"] = r["updated_at"].isoformat()
            if isinstance(r.get("ended_at"), datetime):
                r["ended_at"] = r["ended_at"].isoformat()
        return results
    except Exception as e:
        logger.error(f"Error querying abnormal events for {session_id}: {e}")
        return []

