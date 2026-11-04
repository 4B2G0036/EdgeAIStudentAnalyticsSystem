"""
api/persistence.py
==================
即時影格分析結果的資料庫寫入協調器 (串流廣播器與 /realtime/frame 共用)。

解決的問題
----------
1. 每個影格 (5 FPS) 都同步查詢一次「進行中課程」並對每個異常事件各打一次 MongoDB
   → 改為短 TTL 快取課程 ID，且異常事件僅在「開始 / 定期續期 / 結束」時寫入。
2. 異常事件從未被關閉 (`close_abnormal_event` 無人呼叫)：同一學生同一行為在整堂課只會有一筆
   永遠未結束的紀錄，無法記錄持續時間，也無法區分第二次發生。
   → 行為消失連續 `close_grace_frames` 幀後才關閉事件 (避免姿態判定閃爍切碎事件)。
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Dict, Iterable, Optional, Tuple

import database

logger = logging.getLogger("api.persistence")

EventKey = Tuple[str, str]  # (student_id, event_type)


def parse_event(ev: str) -> EventKey:
    """'ID001: 趴睡 (SLEEPING)' -> ('ID001', '趴睡 (SLEEPING)')"""
    parts = ev.split(":", 1)
    student_id = parts[0].strip()
    event_type = parts[1].strip() if len(parts) > 1 else "abnormal"
    return student_id, event_type


class FrameResultPersister:
    def __init__(
        self,
        session_ttl_s: float = 1.0,
        refresh_interval_s: float = 5.0,
        close_grace_frames: int = 3,
    ) -> None:
        self.session_ttl_s = session_ttl_s
        self.refresh_interval_s = refresh_interval_s
        self.close_grace_frames = max(1, close_grace_frames)

        self._lock = threading.Lock()
        self._session_id: Optional[str] = None
        self._session_checked_at: float = 0.0
        # (student, type) -> {"miss": int, "refreshed": float}
        self._active: Dict[EventKey, dict] = {}

    # ── Session cache ──────────────────────────────────────────────────────────
    def _resolve_session_id(self) -> Optional[str]:
        now = time.time()
        if now - self._session_checked_at >= self.session_ttl_s:
            self._session_checked_at = now
            try:
                session = database.get_active_session()
            except Exception as exc:  # DB 暫時不可用不應中斷串流
                logger.warning("get_active_session failed: %s", exc)
                session = None
            new_sid = session["session_id"] if session else None
            if new_sid != self._session_id:
                # 課程切換或結束：舊課程的事件交由 end_session 路徑關閉，這裡只重置本地狀態
                self._active.clear()
                self._session_id = new_sid
        return self._session_id

    def invalidate_session_cache(self) -> None:
        """課程開始 / 結束時呼叫，讓下一幀立刻重新查詢。"""
        with self._lock:
            self._session_checked_at = 0.0

    # ── Main entry ─────────────────────────────────────────────────────────────
    def persist(self, score: float, count: int, events: Iterable[str]) -> None:
        with self._lock:
            sid = self._resolve_session_id()
            if not sid:
                return

            if count > 0:
                database.write_attention_metric(sid, score, count)

            now = time.time()
            current = {parse_event(ev) for ev in events}

            for key in current:
                state = self._active.get(key)
                if state is None:
                    database.write_abnormal_event(sid, key[0], key[1])
                    self._active[key] = {"miss": 0, "refreshed": now}
                else:
                    state["miss"] = 0
                    if now - state["refreshed"] >= self.refresh_interval_s:
                        database.write_abnormal_event(sid, key[0], key[1])  # 續期 updated_at
                        state["refreshed"] = now

            for key in list(self._active.keys()):
                if key in current:
                    continue
                state = self._active[key]
                state["miss"] += 1
                if state["miss"] >= self.close_grace_frames:
                    database.close_abnormal_event(sid, key[0], key[1], reason="normal_restored")
                    del self._active[key]


_persister: Optional[FrameResultPersister] = None
_persister_lock = threading.Lock()


def get_persister() -> FrameResultPersister:
    global _persister
    with _persister_lock:
        if _persister is None:
            _persister = FrameResultPersister()
        return _persister

