"""뉴스 신호 파이프라인.

AI는 텍스트를 파싱해 라벨(Depth 1/2/3)만 붙이고, 이 패키지의 메인 서버 로직이
그 라벨들을 가중치·통계로 수치화해 매매 지표를 만든다.

- impact.py   : Phase 1 — 단일 뉴스 충격량(Impact) 계산(수집 시점 실시간 적재)
- aggregate.py: Phase 2 — 시계열 누적 지표(섹터 모멘텀 / 공포 지수 / 테마 Z-Score)
노드(Phase 3)는 app/nodes/data/news_signal.py 참조.
"""
