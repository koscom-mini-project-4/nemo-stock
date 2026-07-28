# vendored from koscom-mini-project-4/newsstock-lib

이 디렉터리는 `koscom-mini-project-4/newsstock-lib`의 `news_classifier` 패키지를 그대로
가져온 것이다(2026-07-28, `8b5cae8` 기준).

## nemo-stock 통합 시 수정한 부분

- `classifier.py::call_ai`: OpenAI 호출의 `temperature=0` 하드코딩이 nemo-stock 메인 모델
  `gpt-5.6-luna`(reasoning 계열, 기본값 외 temperature 거부)와 충돌해, `app/ai/openai_client.py`
  와 동일한 "BadRequestError(param=temperature) 시 temperature 없이 1회 재시도" 로직을 추가했다.

그 외 파일은 원본 그대로다. 사용 방법은 `README.md`/`docs/API.md`(원본 문서, 그대로 유지) 참고.
nemo-stock 쪽 배선(Container.news_trader_factory, ai.news_signal 노드, /data/news/update
엔드포인트)은 `DESIGN.md` §0-5 참조.
