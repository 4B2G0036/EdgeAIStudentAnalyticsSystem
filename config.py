import os
import json
import logging
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# MongoDB settings
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "student_analytics")

# FastAPI settings
FASTAPI_BASE_URL = os.getenv("FASTAPI_BASE_URL", "http://localhost:8000")
FASTAPI_PORT = int(os.getenv("FASTAPI_PORT", "8000"))

# Hardware & Inference settings
CAMERA_ID = os.getenv("CAMERA_ID", "0")
if CAMERA_ID.isdigit():
    CAMERA_ID = int(CAMERA_ID)

TARGET_FPS = int(os.getenv("TARGET_FPS", "5"))
IMG_SZ = int(os.getenv("IMG_SZ", "640"))

# Scoring & Thresholds
POSE_CONF_THRESHOLD = float(os.getenv("POSE_CONF_THRESHOLD", "0.45"))
SLEEPING_RATIO = float(os.getenv("SLEEPING_RATIO", "0.20"))
PHONE_PITCH_THRESHOLD = float(os.getenv("PHONE_PITCH_THRESHOLD", "-35"))
BOARD_YAW_THRESHOLD = float(os.getenv("BOARD_YAW_THRESHOLD", "30"))
BOARD_PITCH_THRESHOLD = float(os.getenv("BOARD_PITCH_THRESHOLD", "25"))

# FSM logic windows
FSM_NOISE_WINDOW = float(os.getenv("FSM_NOISE_WINDOW", "3.0"))
FSM_CONFIRM_WINDOW = float(os.getenv("FSM_CONFIRM_WINDOW", "10.0"))

# Database batch write settings
DB_BATCH_SIZE = int(os.getenv("DB_BATCH_SIZE", "500"))
FLUSH_INTERVAL = float(os.getenv("FLUSH_INTERVAL", "3.0"))
AWAIT_FLUSH_TIMEOUT = float(os.getenv("AWAIT_FLUSH_TIMEOUT", "10.0"))

# CORS Settings
try:
    CORS_ORIGINS = json.loads(os.getenv("CORS_ORIGINS", '["*"]'))
except Exception:
    CORS_ORIGINS = ["*"]

# Localization & Timezone
TIMEZONE = os.getenv("TIMEZONE", "Asia/Taipei")

# Retention & Security settings
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "365"))
PII_BLUR_KERNEL = int(os.getenv("PII_BLUR_KERNEL", "31"))
HEARTBEAT_TIMEOUT = float(os.getenv("HEARTBEAT_TIMEOUT", "1.5"))
API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "5/minute")

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Trace ID Context Local for Logging
import threading
_trace_ctx = threading.local()

def get_current_trace_id():
    return getattr(_trace_ctx, "trace_id", "-")

def set_current_trace_id(trace_id: str):
    _trace_ctx.trace_id = trace_id

class TraceIdFilter(logging.Filter):
    def filter(self, record):
        record.trace_id = get_current_trace_id()
        return True

def setup_logging():
    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    logger = logging.getLogger()
    logger.setLevel(level)
    
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [trace_id: %(trace_id)s] [%(name)s:%(filename)s:%(lineno)d] %(message)s"
    )
    handler.setFormatter(formatter)
    handler.addFilter(TraceIdFilter())
    logger.addHandler(handler)
