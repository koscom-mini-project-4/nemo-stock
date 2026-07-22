"""EventBus 히스토리를 NodeEventRecord로 변환하는 공용 헬퍼.

WorkerPool(라이브/테스트 트리거)과 BacktestRunner(백테스트 일자별 틱)가 실행 완료 후
run_events를 DB에 저장할 때 동일한 변환 로직을 쓰도록 여기 한 곳에 둔다.
"""

from __future__ import annotations

import uuid

from app.dao.base import NodeEventRecord
from app.workflow.events import EventBus


def events_to_records(event_bus: EventBus, run_id: str) -> list[NodeEventRecord]:
    return [
        NodeEventRecord(
            id=str(uuid.uuid4()),
            run_id=e.run_id,
            node_id=e.node_id,
            node_type=e.node_type,
            status=e.status,
            timestamp=e.timestamp,
            input_json=e.input_snapshot,
            output_json=e.output_snapshot,
            error=e.error,
            duration_ms=e.duration_ms,
        )
        for e in event_bus.get_history(run_id)
    ]
