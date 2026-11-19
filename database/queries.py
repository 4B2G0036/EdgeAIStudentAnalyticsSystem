import os
import re
import logging
from datetime import datetime
from pymongo import ASCENDING, DESCENDING
from database.connection import get_db
from database.writer import get_metric_writer, flush_attention_metrics

logger = logging.getLogger("database.queries")


def extract_event_code(event_type: str) -> str:
    """Extract canonical event code (e.g. 'SLEEPING') from descriptive string '趴睡 (SLEEPING)'."""
    if not event_type:
        return "UNKNOWN"
    upper = str(event_type).upper()
    for code in ("SLEEPING", "PHONE_SUSPECTED", "DISTRACTED", "HEAD_SUPPORT", "HAND_RAISED"):
        if code in upper:
            return code
    if "趴睡" in upper:
        return "SLEEPING"
    if "手機" in upper:
        return "PHONE_SUSPECTED"
    if "東張西望" in upper or "分心" in upper:
        return "DISTRACTED"
    if "托腮" in upper or "撐頭" in upper:
        return "HEAD_SUPPORT"
    if "舉手" in upper:
        return "HAND_RAISED"
    return str(event_type)

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
        escaped_search = re.escape(search_query.strip())
        query["$or"] = [
            {"class_name": {"$regex": escaped_search, "$options": "i"}},
            {"teacher": {"$regex": escaped_search, "$options": "i"}}
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

def update_session_max_students(session_id: str, student_count: int) -> bool:
    """Update Classes_Session.student_count with the peak concurrent student count using $max."""
    if not session_id or student_count <= 0:
        return False
    db = get_db()
    try:
        db["Classes_Session"].update_one(
            {"session_id": session_id},
            {"$max": {"student_count": int(student_count)}}
        )
        return True
    except Exception as e:
        logger.warning(f"Failed to update max student count for {session_id}: {e}")
        return False


def get_session_summary(session_id: str) -> dict:
    flush_attention_metrics()
    db = get_db()
    try:
        session = db["Classes_Session"].find_one({"session_id": session_id}, {"_id": 0})
        if not session:
            return None
            
        # Compile summary from Attention_Metrics and Abnormal_Events
        # 1. Total negative anomalies count (excluding positive HAND_RAISED interactions)
        anomalies_count = db["Abnormal_Events"].count_documents({
            "session_id": session_id,
            "event_type": {"$not": {"$regex": "HAND_RAISED|舉手", "$options": "i"}}
        })
        
        # 2. Query average attention score and peak student count from Attention_Metrics
        pipeline = [
            {"$match": {"metadata.session_id": session_id}},
            {"$group": {
                "_id": None,
                "avg_score": {"$avg": "$attention_score"},
                "max_students": {"$max": "$student_count"},
                "min_score": {"$min": "$attention_score"},
                "max_score": {"$max": "$attention_score"},
            }}
        ]
        agg_result = list(db["Attention_Metrics"].aggregate(pipeline))
        avg_score = agg_result[0]["avg_score"] if agg_result else 100.0
        min_score = agg_result[0]["min_score"] if (agg_result and agg_result[0].get("min_score") is not None) else avg_score
        max_score = agg_result[0]["max_score"] if (agg_result and agg_result[0].get("max_score") is not None) else avg_score
        agg_max_students = int(agg_result[0].get("max_students") or 0) if agg_result else 0
        stored_students = int(session.get("student_count", 0) or 0)
        max_student_count = max(stored_students, agg_max_students)

        # Backfill Classes_Session.student_count if metrics recorded a higher peak
        if max_student_count > stored_students:
            update_session_max_students(session_id, max_student_count)
        
        return {
            "session_id": session_id,
            "class_name": session.get("class_name"),
            "teacher": session.get("teacher"),
            "room": session.get("room", ""),
            "notes": session.get("notes", ""),
            "started_at": session.get("started_at"),
            "ended_at": session.get("ended_at"),
            "max_student_count": max_student_count,
            "avg_attention_score": round(avg_score, 2) if avg_score is not None else 100.0,
            "min_attention_score": round(min_score, 2) if min_score is not None else 100.0,
            "max_attention_score": round(max_score, 2) if max_score is not None else 100.0,
            "total_abnormal_events": anomalies_count
        }
    except Exception as e:
        logger.error(f"Error generating session summary for {session_id}: {e}")
        return None


def invalidate_cached_reports(session_id: str) -> None:
    """Remove any cached PDF report files for a session when metadata changes or session is deleted."""
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    reports_dir = os.path.join(root_dir, "scratch", "reports")
    for fname in (f"report_{session_id}.pdf", f"report_v2_{session_id}.pdf"):
        fpath = os.path.join(reports_dir, fname)
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
            except Exception:
                pass


def delete_session(session_id: str) -> bool:
    """Delete session metadata, time series metrics, abnormal events, and cached PDF reports."""
    db = get_db()
    try:
        res = db["Classes_Session"].delete_one({"session_id": session_id})
        db["Attention_Metrics"].delete_many({"metadata.session_id": session_id})
        db["Abnormal_Events"].delete_many({"session_id": session_id})
        invalidate_cached_reports(session_id)
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
        
        abnormal_count = db["Abnormal_Events"].count_documents({
            "session_id": session_id,
            "event_type": {"$not": {"$regex": "HAND_RAISED|舉手", "$options": "i"}}
        })
        
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
    flush_attention_metrics()
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
    """Query abnormal events for a specific session with normalized fields."""
    db = get_db()
    query = {"session_id": session_id}
    if event_type:
        query["event_type"] = {"$regex": re.escape(event_type.strip()), "$options": "i"}

    try:
        cursor = db["Abnormal_Events"].find(query, {"_id": 0}).sort("started_at", DESCENDING)
        results = list(cursor)
        now = datetime.utcnow()
        for r in results:
            started_dt = r.get("started_at")
            updated_dt = r.get("updated_at")
            ended_dt = r.get("ended_at")

            # Compute dynamic duration_seconds if event is still ongoing or missing duration_seconds
            if r.get("duration_seconds") is None:
                if isinstance(started_dt, datetime):
                    ref_end = ended_dt if isinstance(ended_dt, datetime) else (updated_dt if isinstance(updated_dt, datetime) else now)
                    r["duration_seconds"] = round(max(0.0, float((ref_end - started_dt).total_seconds())), 1)
                else:
                    r["duration_seconds"] = 0.0

            if isinstance(started_dt, datetime):
                r["started_at"] = started_dt.isoformat()
            if isinstance(updated_dt, datetime):
                r["updated_at"] = updated_dt.isoformat()
            if isinstance(ended_dt, datetime):
                r["ended_at"] = ended_dt.isoformat()

            # Provide canonical aliases for frontend & PDF report consumers
            r["timestamp"] = r.get("timestamp") or r.get("started_at")
            r["tracking_id"] = r.get("tracking_id") or r.get("student_id") or "S000"
            r["student_id"] = r.get("student_id") or r["tracking_id"]
            r["event_code"] = extract_event_code(r.get("event_type", ""))
        return results
    except Exception as e:
        logger.error(f"Error querying abnormal events for {session_id}: {e}")
        return []



def write_attention_metric(session_id, attention_score, student_count):
    """Write an attention metric point via thread-safe asynchronous batch buffer."""
    try:
        return get_metric_writer().write_metric(session_id, attention_score, student_count)
    except Exception as e:
        logger.error(f"Failed metric write: {e}")
        return False


def write_abnormal_event(session_id, student_id, event_type):
    """
    Write or update an abnormal event record in Abnormal_Events collection.
    Lifecycle-aware: If an event of the same type is already active (ended_at is None),
    updates updated_at instead of creating duplicate records every frame.
    """
    db = get_db()
    now = datetime.utcnow()
    try:
        # Check for currently active event for this student and event type
        existing = db["Abnormal_Events"].find_one_and_update(
            {
                "session_id": session_id,
                "student_id": student_id,
                "event_type": event_type,
                "ended_at": None
            },
            {"$set": {"updated_at": now}},
            return_document=True
        )
        if existing:
            return True

        # Otherwise insert a new active abnormal event
        doc = {
            "session_id": session_id,
            "student_id": student_id,
            "event_type": event_type,
            "started_at": now,
            "updated_at": now,
            "ended_at": None,
            "ended_reason": None
        }
        db["Abnormal_Events"].insert_one(doc)
        return True
    except Exception as e:
        logger.error(f"Failed event write: {e}")
        return False


def close_all_active_events(session_id, reason="session_ended"):
    """Close every still-active abnormal event of a session (e.g. when the class ends)."""
    db = get_db()
    now = datetime.utcnow()
    try:
        active_events = list(db["Abnormal_Events"].find({"session_id": session_id, "ended_at": None}))
        for ev in active_events:
            started = ev.get("started_at", now)
            db["Abnormal_Events"].update_one(
                {"_id": ev["_id"]},
                {"$set": {
                    "ended_at": now,
                    "ended_reason": reason,
                    "duration_seconds": float((now - started).total_seconds()),
                }},
            )
        return len(active_events)
    except Exception as e:
        logger.error(f"Failed to close active events for session {session_id}: {e}")
        return 0


def close_abnormal_event(session_id, student_id, event_type=None, reason="normal_restored"):
    """Close active abnormal events for a student when normal posture is restored."""
    db = get_db()
    now = datetime.utcnow()
    query = {"session_id": session_id, "student_id": student_id, "ended_at": None}
    if event_type:
        query["event_type"] = event_type
    try:
        active_events = list(db["Abnormal_Events"].find(query))
        for ev in active_events:
            started = ev.get("started_at", now)
            duration = float((now - started).total_seconds())
            db["Abnormal_Events"].update_one(
                {"_id": ev["_id"]},
                {"$set": {"ended_at": now, "ended_reason": reason, "duration_seconds": duration}}
            )
        return len(active_events)
    except Exception as e:
        logger.error(f"Failed to close abnormal event: {e}")
        return 0


