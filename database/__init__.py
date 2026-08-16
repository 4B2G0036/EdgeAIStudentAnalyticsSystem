# database module
from database.connection import get_db, get_db_client
from database.collections import initialize_database
from database.queries import (
    create_session,
    end_session,
    get_session_by_id,
    get_active_session,
    list_sessions,
    get_session_summary,
    update_session,
    delete_session,
    get_active_session_metrics
)

