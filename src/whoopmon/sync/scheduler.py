"""Run the sync engine on a fixed interval until SIGINT/SIGTERM."""

import signal
import threading
from types import FrameType

from whoopmon.observability import get_logger
from whoopmon.sync.engine import SyncEngine

log = get_logger(__name__)


def run_forever(engine: SyncEngine, interval_seconds: int) -> None:
    stop = threading.Event()

    def _stop(signum: int, _frame: FrameType | None) -> None:
        log.info("scheduler.stopping", signal=signal.Signals(signum).name)
        stop.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    log.info("scheduler.started", interval_s=interval_seconds)
    while not stop.is_set():
        engine.run()
        stop.wait(interval_seconds)
    log.info("scheduler.stopped")
