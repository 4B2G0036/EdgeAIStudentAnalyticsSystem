"""
database/writer.py
==================
Time-Series 指標非同步批量寫入器 (MetricBatchWriter):
  1. 高頻姿態分析時序指標 (Attention_Metrics) 暫存於記憶體佇列。
  2. 達到批次量 (預設 15 筆) 或超逾定時週期 (預設 2.0 秒) 自動觸發 insert_many 批次寫入。
  3. 支援主動排空 (flush)，於課程結束 (PATCH /sessions/{id}/end) 或服務關閉 (shutdown) 時安全落盤。
"""
import time
import queue
import logging
import threading
from datetime import datetime
from typing import Optional, List
from database.connection import get_db

logger = logging.getLogger("database.writer")


class MetricBatchWriter:
    """
    Thread-safe In-Memory Metric Buffer & Asynchronous Batch Writer.
    Collects high-frequency time-series metrics and flushes them to MongoDB using insert_many,
    reducing network round trips by ~90% and preventing DB I/O saturation.
    """
    def __init__(self, batch_size: int = 15, flush_interval_s: float = 2.0):
        self.batch_size = batch_size
        self.flush_interval_s = flush_interval_s
        self._queue = queue.Queue()
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            if self._worker_thread is None or not self._worker_thread.is_alive():
                self._stop_event.clear()
                self._worker_thread = threading.Thread(
                    target=self._worker_loop,
                    name="MetricBatchWriterThread",
                    daemon=True
                )
                self._worker_thread.start()
                logger.info("MetricBatchWriter worker thread started.")

    def stop(self, timeout: float = 5.0):
        self._stop_event.set()
        self.flush()
        with self._lock:
            if self._worker_thread and self._worker_thread.is_alive():
                self._worker_thread.join(timeout=timeout)
                self._worker_thread = None
        logger.info("MetricBatchWriter stopped cleanly.")

    def write_metric(self, session_id: str, attention_score: float, student_count: int, ts: Optional[datetime] = None) -> bool:
        doc = {
            "timestamp": ts or datetime.utcnow(),
            "metadata": {"session_id": session_id},
            "attention_score": float(attention_score),
            "student_count": int(student_count)
        }
        self._queue.put(doc)
        if not (self._worker_thread and self._worker_thread.is_alive()):
            self.start()
        return True

    def flush(self) -> int:
        """Drain all pending metrics in queue and bulk insert them into MongoDB."""
        batch = []
        while not self._queue.empty():
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break

        if not batch:
            return 0

        try:
            db = get_db()
            db["Attention_Metrics"].insert_many(batch, ordered=False)
            logger.info(f"Successfully batch-flushed {len(batch)} metrics to MongoDB.")
            return len(batch)
        except Exception as e:
            logger.error(f"Error during metric batch flush ({len(batch)} items): {e}")
            return 0

    def _worker_loop(self):
        last_flush = time.time()
        while not self._stop_event.is_set():
            time.sleep(0.5)
            now = time.time()
            if self._queue.qsize() >= self.batch_size or ((now - last_flush) >= self.flush_interval_s and not self._queue.empty()):
                self.flush()
                last_flush = now


_metric_writer: Optional[MetricBatchWriter] = None


def get_metric_writer() -> MetricBatchWriter:
    global _metric_writer
    if _metric_writer is None:
        _metric_writer = MetricBatchWriter()
    return _metric_writer


def flush_attention_metrics() -> int:
    """Helper function to drain all queued metrics and write to MongoDB."""
    return get_metric_writer().flush()

