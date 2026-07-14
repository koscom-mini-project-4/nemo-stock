"""배치 전용 진입점.

`python -m app.batch.worker`로 스케줄러/워커풀만 별도 프로세스로 기동할 수 있다.
현재는 InMemoryTriggerQueue를 사용하므로 API 프로세스와 큐를 공유하지 못해 실질적인
분리 효과는 없다(같은 프로세스 내에서만 유효). TriggerQueue를 Redis 등 프로세스 간
공유 가능한 구현으로 교체하면 이 스크립트만으로 진짜 분리 배치 프로세스가 된다.
"""

from __future__ import annotations

import signal
import time

from app.config import get_settings
from app.dependencies import build_container


def main() -> None:
    settings = get_settings()
    container = build_container(settings)
    container.scheduler_service.start()
    container.worker_pool.start()

    stop = False

    def _handle_signal(signum, frame):  # noqa: ANN001
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    print("nemo-stock batch worker started.")
    while not stop:
        time.sleep(1)

    container.scheduler_service.stop()
    container.worker_pool.stop()
    print("nemo-stock batch worker stopped.")


if __name__ == "__main__":
    main()
