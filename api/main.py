import os
import sys
from datetime import datetime
import time
import logging

# Ensure current directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
import config
import database
from api.routers import sessions, stream, realtime, reports, system

# Configure project log formats
config.setup_logging()
logger = logging.getLogger("api.main")

app = FastAPI(
    title="學生專注度與異常行為分析系統 - API 後端服務",
    description="本後端 API 負責處理邊緣端即時 AI 視覺推論數據持久化、狀態機評分聚合、以及課程 Session 生命週期管理與實時攝影機串流。",
    version="1.1.0"
)

# Trace ID Middleware for log tracking and response headers
class TraceIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())
        request.state.trace_id = trace_id
        config.set_current_trace_id(trace_id)
        response = await call_next(request)
        response.headers["X-Trace-ID"] = trace_id
        return response

app.add_middleware(TraceIDMiddleware)

# CORS configuration - Allow all web origins (localhost, Cloudflare Tunnel, Firebase Hosting)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=r"^https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(sessions.router)
app.include_router(stream.router)
app.include_router(realtime.router)
app.include_router(reports.router)
app.include_router(system.router)



def self_heal_abnormal_events():
    """
    Requirement 2.5: Force-close on Restart (Self-Healing)
    When FastAPI starts, query all docs in Abnormal_Events where ended_at is null.
    For each doc:
    1. Set ended_at to current time (datetime.utcnow()).
    2. Set ended_reason to "server_restart".
    3. Re-calculate duration_seconds = ended_at - started_at.
    """
    logger.info("Executing database self-healing check for hanging Abnormal_Events...")
    try:
        db = database.get_db()
        now = datetime.utcnow()
        
        # Find all unclosed abnormal events
        unclosed_events = list(db["Abnormal_Events"].find({"ended_at": None}))
        if not unclosed_events:
            logger.info("No unclosed abnormal events found. Database is clean.")
            return
            
        logger.info(f"Found {len(unclosed_events)} hanging abnormal events. Force-closing them...")
        
        healed_count = 0
        for event in unclosed_events:
            started_at = event.get("started_at")
            if not started_at:
                # Fallback if started_at is missing
                started_at = now
                
            # Calculate duration in seconds (float)
            duration = (now - started_at).total_seconds()
            
            db["Abnormal_Events"].update_one(
                {"_id": event["_id"]},
                {
                    "$set": {
                        "ended_at": now,
                        "ended_reason": "server_restart",
                        "duration_seconds": float(duration)
                    }
                }
            )
            healed_count += 1
            
        logger.info(f"Self-healed {healed_count} abnormal events successfully.")
    except Exception as e:
        logger.critical(f"Database Self-Healing failed: {e}")

@app.on_event("startup")
async def startup_event():
    logger.info("Starting FastAPI server...")
    try:
        # Initialize Database connection & create collections/indexes
        database.initialize_database()
        
        # Perform Self-healing force-close on startup
        self_heal_abnormal_events()
    except Exception as e:
        logger.critical(f"FastAPI Startup failed due to DB initialization error: {e}")
        # Server will crash/exit to prevent starting with broken DB
        sys.exit(1)

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("FastAPI server is shutting down...")

@app.get("/", include_in_schema=False)
def read_root():
    db_status = "unknown"
    try:
        db = database.get_db()
        db.client.admin.command('ping')
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "online",
        "appName": "Student Analytics System API Backend",
        "database": db_status,
        "currentTime": datetime.utcnow().isoformat()
    }

@app.get("/health", tags=["系統與連線狀態"], summary="系統與資料庫健康檢查")
def health_check():
    db_status = "disconnected"
    latency_ms = None
    try:
        t0 = time.time()
        db = database.get_db()
        db.client.admin.command('ping')
        latency_ms = round((time.time() - t0) * 1000, 2)
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "database": {
            "status": db_status,
            "target": config.MONGO_URI,
            "name": config.MONGO_DB_NAME,
            "latency_ms": latency_ms
        },
        "currentTime": datetime.utcnow().isoformat()
    }

@app.get("/dashboard", include_in_schema=False)
def redirect_dashboard():
    return RedirectResponse(url="/dashboard/")

# Mount static dashboard files (must be after all routes)
_dashboard_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard")
if os.path.isdir(_dashboard_dir):
    app.mount("/dashboard", StaticFiles(directory=_dashboard_dir, html=True), name="dashboard")
    logger.info(f"Dashboard mounted at /dashboard -> {_dashboard_dir}")
