"""Phase 23D-Q — GPU Resource Coordination.

Log capture uses the same "attach a handler directly" pattern as
app/tests/test_observability.py / test_narrative_trace.py, not
pytest's caplog — see those files for why (propagate=False once app
startup has happened anywhere earlier in the process, plus a
process-global logging.disable ceiling some other test in the full
suite leaves raised).
"""
import logging
import threading
import time

import pytest

from app.core.gpu_coordinator import _lock, gpu_heavy_operation
from app.core.logging import get_logger


class _RecordingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    @property
    def messages(self) -> list[str]:
        return [record.getMessage() for record in self.records]


def _capture_gpu_logs():
    logger = get_logger("gpu")
    handler = _RecordingHandler()
    original_level = logger.level
    original_disabled = logger.disabled
    original_disable = logging.Logger.manager.disable
    logging.disable(logging.NOTSET)
    logger.disabled = False
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    def teardown():
        logger.removeHandler(handler)
        logger.setLevel(original_level)
        logger.disabled = original_disabled
        logging.disable(original_disable)

    return handler, teardown


def test_gpu_heavy_operation_serializes_concurrent_callers():
    active_count = 0
    count_lock = threading.Lock()
    overlap_detected = threading.Event()

    def worker():
        nonlocal active_count
        with gpu_heavy_operation("TEST_TASK"):
            with count_lock:
                active_count += 1
                if active_count > 1:
                    overlap_detected.set()
            time.sleep(0.05)
            with count_lock:
                active_count -= 1

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert not overlap_detected.is_set()


def test_gpu_heavy_operation_releases_the_lock_even_when_the_block_raises():
    class _Boom(Exception):
        pass

    with pytest.raises(_Boom):
        with gpu_heavy_operation("TEST_TASK"):
            raise _Boom()

    # If the exception had skipped the release, this would hang and
    # eventually fail on the timeout instead of returning True.
    acquired = _lock.acquire(timeout=2)
    assert acquired
    _lock.release()


def test_gpu_heavy_operation_logs_acquired_and_released_without_contention():
    handler, teardown = _capture_gpu_logs()
    try:
        with gpu_heavy_operation("LLM_TASK"):
            pass
    finally:
        teardown()

    combined = "\n".join(handler.messages)
    assert "gpu_coordinator acquired task=LLM_TASK" in combined
    assert "gpu_coordinator released task=LLM_TASK" in combined
    assert "waiting" not in combined


def test_gpu_heavy_operation_logs_waiting_when_contended():
    handler, teardown = _capture_gpu_logs()
    ready = threading.Event()
    release = threading.Event()

    def holder():
        with gpu_heavy_operation("LLM_TASK"):
            ready.set()
            release.wait(timeout=5)

    def releaser():
        time.sleep(0.1)
        release.set()

    holder_thread = threading.Thread(target=holder)
    holder_thread.start()
    assert ready.wait(timeout=5)
    threading.Thread(target=releaser).start()

    try:
        with gpu_heavy_operation("VISUAL_TASK"):
            pass
    finally:
        holder_thread.join(timeout=5)
        teardown()

    combined = "\n".join(handler.messages)
    assert "gpu_coordinator waiting task=VISUAL_TASK" in combined
    assert "gpu_coordinator acquired task=VISUAL_TASK" in combined
