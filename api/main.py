import os
import sys
import asyncio
from datetime import datetime
import time
import logging
from contextlib import asynccontextmanager

# Ensure current directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
import config
import database
from api.routers import sessions, stream, realtime, reports, system

# Configure project log formats
config.setup_logging()
logger = logging.getLogger("api.main")

SERVER_STARTED_AT = None


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
                started_at = now
                
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Modern lifespan context manager managing startup initialization and graceful shutdown."""
    logger.info("Starting FastAPI server...")
    global SERVER_STARTED_AT
    SERVER_STARTED_AT = datetime.utcnow()

    # MongoDB connection retry & initialize
    max_attempts = 6
    for attempt in range(1, max_attempts + 1):
        try:
            database.initialize_database()
            self_heal_abnormal_events()
            # Start database batch writer
            database.get_metric_writer().start()
            break
        except Exception as e:
            if attempt >= max_attempts:
                logger.critical(f"FastAPI Startup failed due to DB initialization error after {max_attempts} attempts: {e}")
                sys.exit(1)
            logger.warning(f"DB initialization attempt {attempt}/{max_attempts} failed: {e}. Retrying in {attempt * 2}s...")
            await asyncio.sleep(attempt * 2)

    yield

    # Graceful shutdown: flush any pending metrics
    logger.info("FastAPI server is shutting down...")
    try:
        database.flush_attention_metrics()
        database.get_metric_writer().stop(timeout=3.0)
    except Exception as e:
        logger.warning(f"Shutdown metric flush error: {e}")


app = FastAPI(
    title="學生專注度與異常行為分析系統 - API 後端服務",
    description="本後端 API 負責處理邊緣端即時 AI 視覺推論數據持久化、狀態機評分聚合、以及課程 Session 生命週期管理與實時攝影機串流。",
    version="1.1.0",
    lifespan=lifespan
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


@app.middleware("http")
async def private_network_access_middleware(request: Request, call_next):
    """
    Chrome Private Network Access：雲端 (https) 儀表板存取 localhost 時，預檢請求 (OPTIONS) 會帶
    Access-Control-Request-Private-Network，伺服器須回應 Access-Control-Allow-Private-Network: true。
    此 middleware 位於 CORS 之外層，確保預檢回應一定帶有該標頭。
    """
    response = await call_next(request)
    if request.headers.get("access-control-request-private-network", "").lower() == "true":
        response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


# Global Exception Handlers ensuring standardized JSON format with trace_id
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    trace_id = getattr(request.state, "trace_id", "-")
    logger.warning(f"Validation error on {request.method} {request.url.path}: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={
            "status": "error",
            "message": "請求參數格式不正確 (Validation Error)",
            "detail": exc.errors(),
            "trace_id": trace_id
        },
        headers={"X-Trace-ID": trace_id}
    )


@app.exception_handler(Exception)
async def global_unhandled_exception_handler(request: Request, exc: Exception):
    trace_id = getattr(request.state, "trace_id", "-")
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "伺服器內部發生未預期異常 (Internal Server Error)",
            "detail": str(exc),
            "trace_id": trace_id
        },
        headers={"X-Trace-ID": trace_id}
    )


# Register routers
app.include_router(sessions.router)
app.include_router(stream.router)
app.include_router(realtime.router)
app.include_router(reports.router)
app.include_router(system.router)

# WebSocket root path alias
@app.websocket("/ws/realtime")
async def root_websocket_realtime(websocket: realtime.WebSocket):
    await realtime.websocket_realtime_endpoint(websocket)


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
        "api": "online",
        "version": app.version,
        "started_at": SERVER_STARTED_AT.isoformat() if SERVER_STARTED_AT else None,
        "uptime_seconds": round((datetime.utcnow() - SERVER_STARTED_AT).total_seconds(), 1) if SERVER_STARTED_AT else None,
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
