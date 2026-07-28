"""app/vendor/news_classifier(koscom-mini-project-4/newsstock-lib)에 nemo-stock 통합 시
추가한 수정(classifier.py::call_ai의 temperature 재시도, crawler.py의 병렬 fetch)에 대한
회귀 테스트. temperature 재시도는 app/ai/openai_client.py의 test_openai_client.py와 동일한
시나리오다.
"""

from __future__ import annotations

import threading
from datetime import datetime
from time import sleep as real_sleep  # crawler.time.sleep을 monkeypatch해도 영향받지 않는다
from unittest.mock import MagicMock

import httpx
import pytest
from openai import BadRequestError

from app.vendor.news_classifier import classifier, crawler, db
from app.vendor.news_classifier.api import NewsTrader
from app.vendor.news_classifier.config import Settings


def _temperature_error() -> BadRequestError:
    response = httpx.Response(status_code=400, request=httpx.Request("POST", "https://api.openai.com/v1/x"))
    return BadRequestError(
        "temperature unsupported",
        response=response,
        body={
            "message": "Unsupported value: 'temperature' does not support 0 with this model.",
            "type": "invalid_request_error",
            "param": "temperature",
            "code": "unsupported_value",
        },
    )


def _fake_response(content: str, usage: MagicMock | None = None) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=content))]
    resp.usage = usage
    return resp


def test_call_ai_retries_without_temperature_on_unsupported_value(monkeypatch):
    create_mock = MagicMock(side_effect=[_temperature_error(), _fake_response('{"cluster_id": null}')])
    fake_client = MagicMock()
    fake_client.chat.completions.create = create_mock
    monkeypatch.setattr(classifier, "_client_once", lambda api_key=None: fake_client)

    result = classifier.call_ai({"title": "t", "content": "c"}, [], model="gpt-5.6-luna", api_key="sk-test")

    assert result == {"cluster_id": None}
    assert create_mock.call_count == 2
    assert "temperature" in create_mock.call_args_list[0].kwargs
    assert "temperature" not in create_mock.call_args_list[1].kwargs


def test_call_ai_reports_usage_via_sink(monkeypatch):
    usage = MagicMock(prompt_tokens=50, completion_tokens=10, total_tokens=60)
    create_mock = MagicMock(side_effect=[_fake_response('{"cluster_id": null}', usage=usage)])
    fake_client = MagicMock()
    fake_client.chat.completions.create = create_mock
    monkeypatch.setattr(classifier, "_client_once", lambda api_key=None: fake_client)
    monkeypatch.setattr(classifier, "_usage_sink", None)  # 다른 테스트에서 새는 것 방지

    calls: list[tuple] = []
    classifier.set_usage_sink(lambda *args: calls.append(args))
    try:
        classifier.call_ai({"title": "t", "content": "c"}, [], model="gpt-5.6-luna", api_key="sk-test")
    finally:
        classifier.set_usage_sink(None)

    assert calls == [("newsstock_classify", "gpt-5.6-luna", 50, 10, 60)]


def test_call_ai_without_usage_sink_does_not_error(monkeypatch):
    create_mock = MagicMock(side_effect=[_fake_response('{"cluster_id": null}')])
    fake_client = MagicMock()
    fake_client.chat.completions.create = create_mock
    monkeypatch.setattr(classifier, "_client_once", lambda api_key=None: fake_client)
    monkeypatch.setattr(classifier, "_usage_sink", None)

    result = classifier.call_ai({"title": "t", "content": "c"}, [], model="gpt-5.6-luna", api_key="sk-test")

    assert result == {"cluster_id": None}


def test_call_ai_reraises_unrelated_bad_request_error(monkeypatch):
    response = httpx.Response(status_code=400, request=httpx.Request("POST", "https://api.openai.com/v1/x"))
    other_error = BadRequestError(
        "bad model",
        response=response,
        body={"message": "unknown model", "type": "invalid_request_error", "param": "model", "code": "invalid"},
    )
    create_mock = MagicMock(side_effect=other_error)
    fake_client = MagicMock()
    fake_client.chat.completions.create = create_mock
    monkeypatch.setattr(classifier, "_client_once", lambda api_key=None: fake_client)

    with pytest.raises(BadRequestError):
        classifier.call_ai({"title": "t", "content": "c"}, [], model="gpt-5.6-luna", api_key="sk-test")

    assert create_mock.call_count == 1


def _stub_session():
    return object()  # _list_page/_article를 스텁하므로 실제로 쓰이지 않는다


def _fake_article(url: str) -> dict:
    return {
        "url": url,
        "url_hash": crawler.url_hash(url),
        "title": f"제목 {url[-3:]}",
        "content": "본문",
        "summary": "본문",
        "published_at": "2026-07-28 09:00:00",
    }


def test_crawl_with_workers_collects_same_items_as_sequential(monkeypatch):
    """crawl(workers=N)이 순차(workers=1)와 동일한 결과 집합을 모으면서, 실제로 여러 스레드에서
    fetch되는지 확인한다(nemo-stock 통합 시 추가한 병렬 fetch에 대한 회귀 테스트).

    crawler.time.sleep(지연)을 무력화하면 각 fetch가 사실상 즉시 끝나버려 ThreadPoolExecutor가
    스레드를 재사용해 우연히 1개 스레드만 쓸 수도 있다(그 자체로는 버그가 아님 — 크롤러
    코드는 여전히 병렬 실행 가능한 구조임). 스레드 관여를 확실히 관찰하려면 fake_article
    안에서 실제로 아주 짧게(진짜 time.sleep) 블로킹해 여러 fetch가 실제로 겹치게 만든다.
    """
    monkeypatch.setattr(crawler, "_session", _stub_session)
    monkeypatch.setattr(crawler.time, "sleep", lambda *_: None)  # CRAWL_DELAY만 무력화

    urls = [f"https://n.news.naver.com/article/000/{i:03d}" for i in range(6)]
    seen_threads: set[int] = set()

    def fake_list_page(session, date_str, page):
        return [(u, f"제목 {u[-3:]}") for u in urls] if page == 1 else []

    def fake_article(session, url, fallback_date_str=None):
        seen_threads.add(threading.get_ident())
        real_sleep(0.02)  # fetch가 겹치도록 의도적으로 블로킹(네트워크 지연 흉내)
        return _fake_article(url)

    monkeypatch.setattr(crawler, "_list_page", fake_list_page)
    monkeypatch.setattr(crawler, "_article", fake_article)

    conn = db.connect(":memory:")
    collected = crawler.crawl(conn, days=1, max_pages=2, workers=4)

    assert {item["url"] for item in collected} == set(urls)
    assert len(seen_threads) > 1  # 실제로 여러 스레드가 fetch에 참여했는지 확인


def test_crawl_sequential_and_parallel_produce_identical_url_sets(monkeypatch):
    monkeypatch.setattr(crawler, "_session", _stub_session)
    monkeypatch.setattr(crawler.time, "sleep", lambda *_: None)

    urls = [f"https://n.news.naver.com/article/111/{i:03d}" for i in range(5)]

    def fake_list_page(session, date_str, page):
        return [(u, f"제목 {u[-3:]}") for u in urls] if page == 1 else []

    def fake_article(session, url, fallback_date_str=None):
        return _fake_article(url)

    monkeypatch.setattr(crawler, "_list_page", fake_list_page)
    monkeypatch.setattr(crawler, "_article", fake_article)

    sequential = crawler.crawl(db.connect(":memory:"), days=1, max_pages=2, workers=1)
    parallel = crawler.crawl(db.connect(":memory:"), days=1, max_pages=2, workers=4)

    assert {i["url"] for i in sequential} == {i["url"] for i in parallel} == set(urls)


def test_news_trader_update_overrides_days_and_keywords_without_mutating_settings(monkeypatch):
    """§0-12: NewsTrader.update(days=, keywords=)는 이번 호출에만 적용되고 self.settings의
    전역 crawl_days/crawl_keywords 값은 그대로 남아야 한다(1회성 오버라이드)."""
    captured = {}

    def fake_crawl(conn, days, max_pages, workers, progress, keywords):
        captured["days"] = days
        captured["keywords"] = keywords
        return []

    monkeypatch.setattr(crawler, "crawl", fake_crawl)

    trader = NewsTrader(Settings(db_path=":memory:", auto_update=False, crawl_days=1, crawl_keywords=None))
    trader.update(force=True, days=5, keywords=["하이닉스", "반도체", "삼성"])

    assert captured == {"days": 5, "keywords": ["하이닉스", "반도체", "삼성"]}
    assert trader.settings.crawl_days == 1  # 전역 설정은 그대로
    assert trader.settings.crawl_keywords is None
    trader.close()


def test_news_trader_update_without_overrides_uses_settings_defaults(monkeypatch):
    captured = {}

    def fake_crawl(conn, days, max_pages, workers, progress, keywords):
        captured["days"] = days
        captured["keywords"] = keywords
        return []

    monkeypatch.setattr(crawler, "crawl", fake_crawl)

    trader = NewsTrader(Settings(db_path=":memory:", auto_update=False, crawl_days=3, crawl_keywords=["기본키워드"]))
    trader.update(force=True)

    assert captured == {"days": 3, "keywords": ["기본키워드"]}
    trader.close()


class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code


class _FakeArticleSession:
    """_article()이 쓰는 session.get()만 흉내낸다. 발행일시 셀렉터(DATE_SELECTOR)가 없는
    기사 HTML을 반환해 파싱 실패(fallback 경로) 상황을 재현한다."""

    _HTML_NO_DATE = (
        '<html><body>'
        '<div id="title_area"><span>테스트 기사 제목</span></div>'
        '<div id="newsct_article">본문 내용입니다.</div>'
        '</body></html>'
    )

    def get(self, url, timeout=None):
        return _FakeResponse(self._HTML_NO_DATE)


def test_article_uses_crawled_day_not_now_when_date_parse_fails():
    """§0-12-1: 발행일시를 못 읽어오면 수집 시점(now)이 아니라 크롤링 중인 목록 날짜로
    채워야 한다 — 과거 날짜를 크롤링할 때 "오늘 막 발행됨"으로 잘못 찍히는 버그의 회귀 테스트
    (사용자 제보: "기사가 수집될 때 수집시점 말고 뉴스 기사 등록 시점 기준으로 판단되어야")."""
    item = crawler._article(
        _FakeArticleSession(), "https://n.news.naver.com/article/x/001", fallback_date_str="20260101"
    )
    assert item["published_at"] == "2026-01-01 12:00:00"


def test_article_falls_back_to_now_when_no_fallback_date_str_given():
    """fallback_date_str을 안 주는 기존 호출부(직접 _article을 부르는 다른 코드가 있다면)와의
    하위호환 — 여전히 datetime.now()로 떨어진다."""
    before = datetime.now().replace(microsecond=0)
    item = crawler._article(_FakeArticleSession(), "https://n.news.naver.com/article/x/002")
    after = datetime.now()
    published = datetime.strptime(item["published_at"], crawler.DATE_FMT)
    assert before <= published <= after


def test_fetch_one_passes_date_str_to_article_as_fallback(monkeypatch):
    """crawl()이 알고 있는 "지금 훑는 목록 날짜"가 실제로 _article()의 fallback까지
    전달되는지(배선 확인)."""
    monkeypatch.setattr(crawler.time, "sleep", lambda *_: None)
    captured = {}

    def fake_article(session, url, fallback_date_str=None):
        captured["fallback_date_str"] = fallback_date_str
        return _fake_article(url)

    monkeypatch.setattr(crawler, "_thread_session", lambda: object())
    monkeypatch.setattr(crawler, "_article", fake_article)

    crawler._fetch_one("https://n.news.naver.com/article/x/003", "20260115")

    assert captured["fallback_date_str"] == "20260115"


def test_matches_keywords_none_always_true():
    assert crawler._matches_keywords("아무 제목", None) is True
    assert crawler._matches_keywords("아무 제목", []) is True


def test_matches_keywords_partial_match_korean_no_case_folding_needed():
    assert crawler._matches_keywords("SK하이닉스 실적 발표", ["하이닉스"]) is True
    assert crawler._matches_keywords("삼성전자 신제품 공개", ["하이닉스", "삼성"]) is True
    assert crawler._matches_keywords("현대차 신차 출시", ["하이닉스", "반도체", "삼성"]) is False


def test_crawl_with_keywords_only_fetches_matching_titles(monkeypatch):
    """§0-12: 제목이 키워드에 안 걸리는 기사는 본문(_article)을 아예 가져오지 않아야 한다."""
    monkeypatch.setattr(crawler, "_session", _stub_session)
    monkeypatch.setattr(crawler.time, "sleep", lambda *_: None)

    titled_urls = [
        ("https://n.news.naver.com/article/a/001", "SK하이닉스 실적 서프라이즈"),
        ("https://n.news.naver.com/article/a/002", "현대차 신차 발표"),
        ("https://n.news.naver.com/article/a/003", "삼성전자 파운드리 확대"),
    ]
    fetched_urls: list[str] = []

    def fake_list_page(session, date_str, page):
        return titled_urls if page == 1 else []

    def fake_article(session, url, fallback_date_str=None):
        fetched_urls.append(url)
        return _fake_article(url)

    monkeypatch.setattr(crawler, "_list_page", fake_list_page)
    monkeypatch.setattr(crawler, "_article", fake_article)

    conn = db.connect(":memory:")
    collected = crawler.crawl(conn, days=1, max_pages=1, workers=1, keywords=["하이닉스", "삼성"])

    assert fetched_urls == ["https://n.news.naver.com/article/a/001", "https://n.news.naver.com/article/a/003"]
    assert {c["url"] for c in collected} == set(fetched_urls)


def test_crawl_page_full_of_non_matching_titles_still_continues_to_next_page(monkeypatch):
    """키워드에 안 걸리는 기사만 있는 페이지라도(하지만 전부 새 글이라 unseen은 비어있지
    않음), "전부 중복" 조기중단으로 오인해 다음 페이지를 건너뛰면 안 된다."""
    monkeypatch.setattr(crawler, "_session", _stub_session)
    monkeypatch.setattr(crawler.time, "sleep", lambda *_: None)

    page1 = [("https://n.news.naver.com/article/b/001", "현대차 신차 발표")]  # 키워드 불일치
    page2 = [("https://n.news.naver.com/article/b/002", "삼성전자 실적 발표")]  # 키워드 일치
    fetched_urls: list[str] = []

    def fake_list_page(session, date_str, page):
        if page == 1:
            return page1
        if page == 2:
            return page2
        return []

    def fake_article(session, url, fallback_date_str=None):
        fetched_urls.append(url)
        return _fake_article(url)

    monkeypatch.setattr(crawler, "_list_page", fake_list_page)
    monkeypatch.setattr(crawler, "_article", fake_article)

    conn = db.connect(":memory:")
    collected = crawler.crawl(conn, days=1, max_pages=3, workers=1, keywords=["삼성"])

    assert fetched_urls == ["https://n.news.naver.com/article/b/002"]
    assert len(collected) == 1


def test_crawl_without_keywords_is_unaffected_by_keyword_filter(monkeypatch):
    """keywords 생략 시 기존과 완전히 동일하게 전부 수집돼야 한다(회귀 방지)."""
    monkeypatch.setattr(crawler, "_session", _stub_session)
    monkeypatch.setattr(crawler.time, "sleep", lambda *_: None)

    titled_urls = [
        ("https://n.news.naver.com/article/c/001", "SK하이닉스 실적"),
        ("https://n.news.naver.com/article/c/002", "현대차 신차"),
    ]

    def fake_list_page(session, date_str, page):
        return titled_urls if page == 1 else []

    def fake_article(session, url, fallback_date_str=None):
        return _fake_article(url)

    monkeypatch.setattr(crawler, "_list_page", fake_list_page)
    monkeypatch.setattr(crawler, "_article", fake_article)

    conn = db.connect(":memory:")
    collected = crawler.crawl(conn, days=1, max_pages=1, workers=1)

    assert {c["url"] for c in collected} == {u for u, _ in titled_urls}


def test_list_page_prefers_headline_text_over_empty_thumbnail_anchor():
    """네이버 목록 HTML은 기사 하나당 <a>가 두 개(썸네일 이미지용 + 헤드라인 텍스트용) 나오고
    둘의 href가 같다. 썸네일 <a>가 먼저 나오면(실측상 대부분 이 순서) "첫 등장만 기록"하던
    예전 로직은 빈 제목("")을 저장해 crawl(keywords=...)의 키워드 매칭이 사실상 항상
    실패하는 버그가 있었다. 나중에 나온 비어있지 않은 텍스트로 덮어써야 한다."""
    html = """
    <html><body><ul class="type06_headline">
      <li>
        <dt><a href="/mnews/article/001/0000000001"><img src="thumb.jpg"/></a></dt>
        <dt><a href="/mnews/article/001/0000000001">진짜 헤드라인 제목</a></dt>
      </li>
      <li>
        <dt><a href="/mnews/article/002/0000000002">이미 텍스트 있는 첫 앵커</a></dt>
      </li>
    </ul></body></html>
    """
    session = MagicMock()
    session.get.return_value = MagicMock(status_code=200, text=html)

    items = crawler._list_page(session, "20260723", 1)

    assert ("https://n.news.naver.com/mnews/article/001/0000000001", "진짜 헤드라인 제목") in items
    assert ("https://n.news.naver.com/mnews/article/002/0000000002", "이미 텍스트 있는 첫 앵커") in items
    assert len(items) == 2  # 같은 href의 두 앵커가 중복 항목으로 남지 않는다
