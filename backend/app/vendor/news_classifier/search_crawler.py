"""네이버 뉴스 검색(search.naver.com) 기반 키워드 딥 크롤러.

`crawler.py`(경제 섹션 목록 페이지, news.naver.com 헤드라인만 순회)와 달리 이 모듈은
검색어로 전체 언론사 기사를 최신순(sort=1)으로 훑는다. 코스닥/코스피 소형주처럼 경제
섹션 헤드라인에 잘 안 실리는 종목의 뉴스를 찾을 때 쓴다(신설 계기: 2026-07-29,
"아이씨에이치" 8일치 수집 요청 — 경제 섹션 크롤로는 0건이었으나 검색으로는 실제 관련
기사 다수 확인됨).

검색 결과 링크는 news.naver.com이 아니라 각 언론사 자체 사이트로 연결된다(네이버
검색 페이지 자체는 최근 컴포넌트 시스템(`fds-*`/`sds-comps-*`)으로 개편되어 클래스명이
빌드마다 바뀌는 해시라 불안정 — 대신 실측으로 확인한 안정적인 속성 조합
`nocr="1"` + 경로 있음 + naver.com 아님으로 기사 링크만 골라낸다). 언론사마다 HTML
구조가 달라 crawler.py의 Naver 전용 셀렉터를 재사용할 수 없어, 다수 언론사 표본 조사로
확인한 범용 규칙(og:title/og:description + 흔한 본문 셀렉터 후보 + article:published_time
메타 우선, 없으면 본문 텍스트에서 날짜 정규식)으로 제네릭 추출한다. 완벽하지 않을 수
있어(언론사별 예외 존재) 제목/본문/날짜 중 하나라도 못 찾으면 그 기사는 건너뛴다 —
날짜를 신뢰할 수 없는 기사를 억지로 포함시키지 않는다(§0-12-1에서 겪은 "발행일시 파싱
실패 시 수집 시점으로 잘못 채워짐" 사고를 반복하지 않기 위함).
"""
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from urllib.parse import urlparse

from . import db
from .config import CRAWL_DELAY, CRAWL_TIMEOUT, DATE_FMT, HTTP_HEADERS
from .crawler import url_hash

SEARCH_URL = "https://search.naver.com/search.naver"

BODY_SELECTORS = [
    "#articleBody", "#article-view-content-div", ".article-body", ".article_view",
    "#news_body_area", ".view_con", "article",
]

_DATE_RE = re.compile(r"20\d{2}[.\-]\d{2}[.\-]\d{2}\.?\s+\d{2}:\d{2}")

_thread_local = threading.local()


def _session():
    import requests
    s = requests.Session()
    s.headers.update(HTTP_HEADERS)
    return s


def _thread_session():
    s = getattr(_thread_local, "session", None)
    if s is None:
        s = _session()
        _thread_local.session = s
    return s


def _is_article_link(a) -> bool:
    """검색 결과에서 기사 제목/스니펫 링크만 고른다(언론사 프로필 링크·UI 잡음 제외).

    실측 결과 기사 링크는 전부 `nocr="1"`(외부 이동 로깅용 속성)을 달고 있고, 언론사
    홈페이지 링크(경로 없음)나 naver.com 자체 링크와는 겹치지 않아 이 조합만으로
    해시 클래스명 없이도 안정적으로 구분된다.
    """
    if a.get("nocr") != "1":
        return False
    href = a.get("href", "")
    if "naver.com" in href:
        return False
    return len(urlparse(href).path) > 1


def _search_page(session, query: str, start: int) -> list[tuple[str, str]]:
    """검색 결과 한 페이지에서 (기사 URL, 제목) 목록을 뽑는다.

    한 기사가 제목 링크 + 본문 스니펫 링크 두 개로 나오는데(둘 다 같은 href), 먼저
    나오는 쪽이 제목이라 첫 등장 텍스트를 유지한다(crawler.py::_list_page의 동일한
    중복 처리 방식).
    """
    from bs4 import BeautifulSoup
    res = session.get(
        SEARCH_URL,
        params={"where": "news", "query": query, "sort": "1", "start": start},
        timeout=CRAWL_TIMEOUT,
    )
    if res.status_code != 200:
        return []
    soup = BeautifulSoup(res.text, "html.parser")
    container = soup.select_one(".group_news")
    if not container:
        return []
    items: list[list[str]] = []
    index_by_url: dict[str, int] = {}
    for a in container.find_all("a", href=True):
        if not _is_article_link(a):
            continue
        href = a["href"]
        text = a.get_text(strip=True)
        if href not in index_by_url:
            index_by_url[href] = len(items)
            items.append([href, text])
        elif text and not items[index_by_url[href]][1]:
            items[index_by_url[href]][1] = text
    return [(u, t) for u, t in items]


def _parse_published(soup, full_text: str) -> str | None:
    tag = soup.find("meta", attrs={"property": "article:published_time"})
    if tag and tag.get("content"):
        try:
            return datetime.fromisoformat(tag["content"].strip()).strftime(DATE_FMT)
        except ValueError:
            pass
    m = _DATE_RE.search(full_text)
    if m:
        raw = re.sub(r"\s+", " ", m.group()).replace(".", "-").rstrip("-")
        try:
            return datetime.strptime(raw, "%Y-%m-%d %H:%M").strftime(DATE_FMT)
        except ValueError:
            pass
    return None


def _article(session, url: str) -> dict | None:
    """언론사 기사 페이지에서 제목/본문/발행일시를 범용 규칙으로 추출한다."""
    from bs4 import BeautifulSoup
    res = session.get(url, timeout=CRAWL_TIMEOUT)
    if res.status_code != 200:
        return None
    soup = BeautifulSoup(res.text, "html.parser")

    title_tag = soup.find("meta", attrs={"property": "og:title"})
    title = (title_tag.get("content") or "").strip() if title_tag else ""
    if not title and soup.title:
        title = soup.title.get_text(strip=True)

    content = ""
    for sel in BODY_SELECTORS:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(" ", strip=True)
            if len(text) > len(content):
                content = text
    if len(content) < 80:
        desc_tag = soup.find("meta", attrs={"property": "og:description"})
        desc = (desc_tag.get("content") or "").strip() if desc_tag else ""
        if len(desc) > len(content):
            content = desc

    if not title or not content:
        return None

    published = _parse_published(soup, soup.get_text(" ", strip=True))
    if not published:
        return None

    return {
        "url": url,
        "url_hash": url_hash(url),
        "title": title,
        "content": content,
        "summary": content[:200] + "..." if len(content) > 200 else content,
        "published_at": published,
    }


def crawl_search(conn, query: str, days: int = 8, max_results: int = 100,
                  workers: int = 4, progress=None) -> list[dict]:
    """검색어로 최신순 결과를 훑어 지정 기간 내 새 기사만 수집해 `crawled`에 저장한다.

    query      : 네이버 뉴스 검색어(제목/본문 어디든 이 단어가 있으면 걸리는 네이버 자체
                 검색이라 crawler.py의 제목 전용 키워드 필터보다 훨씬 넓게 잡는다).
    days       : published_at 기준 최근 며칠까지 포함할지(그보다 오래된 기사는 버림).
    max_results: 검토할 검색 결과 후보 상한(10개씩 페이지네이션, 안전판).
    """
    seen = db.seen_hashes(conn)
    session = _session()
    cutoff = datetime.now() - timedelta(days=days)

    candidates: list[tuple[str, str]] = []
    start = 1
    empty_pages = 0
    while len(candidates) < max_results and empty_pages < 2 and start <= max_results * 3:
        page_items = _search_page(session, query, start)
        if not page_items:
            empty_pages += 1
            start += 10
            continue
        empty_pages = 0
        new_items = [(u, t) for u, t in page_items if url_hash(u) not in seen]
        candidates.extend(new_items)
        if progress:
            progress(len(candidates), f"검색 start={start}: 후보 {len(new_items)}건 추가")
        start += 10
        time.sleep(1.0)

    candidates = candidates[:max_results]

    def _fetch(pair: tuple[str, str]):
        u, _t = pair
        time.sleep(random.uniform(*CRAWL_DELAY))
        try:
            return u, _article(_thread_session(), u), None
        except Exception as e:  # noqa: BLE001 - 개별 기사 실패는 나머지에 영향 없이 건너뛴다
            return u, None, e

    collected: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_fetch, c) for c in candidates]
        for future in as_completed(futures):
            u, item, err = future.result()
            if err is not None or item is None:
                if progress:
                    progress(len(collected), f"스킵(본문/날짜 추출 실패): {u}")
                continue
            published = datetime.strptime(item["published_at"], DATE_FMT)
            if published < cutoff:
                continue
            seen.add(item["url_hash"])
            collected.append(item)
            if progress:
                progress(len(collected), item["title"][:30])

    db.mark_crawled(conn, collected)
    db.set_meta(conn, "last_crawl_at", datetime.now().strftime(DATE_FMT))
    return collected
