"""통제된 투자 테마 어휘(controlled vocabulary).

AI가 테마를 자유 생성하면 "월드컵"·"투표용지 부족" 같은 비-투자 잡음이 섞여 theme_zscore 등
테마 지표가 흔들린다. 그래서 한국 증시에서 실제로 통용되는 투자 테마만 미리 정의해두고,
AI에는 이 목록에서 고르도록 지시하며(프롬프트), 응답도 이 어휘로 정규화(별칭 매핑)한다.

참고: 2025~2026 국내 증시 주도 테마(반도체·AI·2차전지·로봇·원전·조선·방산·바이오 등).
  - 네이트/한경 "2026 주도 섹터" (AI·원전·조선·반도체), 테마별 대장주 정리 등 공개 자료 기반.

구조:
- THEME_TAXONOMY: 카테고리 → 대표(정식) 테마명 목록(프론트 그룹 표시/프롬프트용)
- ALIASES: 정식 테마명 → 별칭 목록(정규화용)
- ALL_THEMES: 정식 테마명 평면 리스트(노드 select 옵션)
- normalize_theme()/normalize_themes(): AI 원본 테마 문자열 → 정식 테마명(없으면 None/드롭)
"""

from __future__ import annotations

# 카테고리 → 정식 테마명. 순서가 프론트 드롭다운/프롬프트 노출 순서다.
THEME_TAXONOMY: dict[str, list[str]] = {
    "반도체·AI": [
        "HBM", "파운드리", "온디바이스 AI", "AI 반도체", "반도체 소부장",
        "시스템반도체", "유리기판", "AI", "생성형 AI", "데이터센터", "클라우드",
    ],
    "2차전지·전기차": [
        "2차전지", "양극재", "전고체", "LFP", "폐배터리", "리튬", "전기차", "자율주행",
    ],
    "로봇·기계": ["로봇", "휴머노이드", "협동로봇", "스마트팩토리"],
    "방산·우주": ["방산", "우주항공", "위성"],
    "에너지·원전": ["원전", "SMR", "태양광", "풍력", "수소", "신재생에너지", "전력설비", "ESS"],
    "바이오·헬스": ["비만치료제", "바이오시밀러", "신약개발", "CDMO", "의료기기", "제약"],
    "조선·중공업": ["조선", "조선기자재", "철강"],
    "소재·차세대": ["초전도체", "양자컴퓨터", "화장품"],
    "인터넷·콘텐츠": ["게임", "엔터", "미디어·콘텐츠", "플랫폼", "웹툰", "이커머스"],
    "금융·자산": ["은행", "증권", "보험", "가상자산", "밸류업"],
    "정책·매크로테마": ["리쇼어링", "우크라이나 재건", "탄소중립"],
}

# 정식 테마명 → 별칭(정규화용). 별칭이 원본에 포함되면 정식명으로 매핑한다.
ALIASES: dict[str, list[str]] = {
    "HBM": ["고대역폭메모리", "HBM3", "HBM3E", "HBM4"],
    "AI 반도체": ["AI가속기", "GPU", "NPU", "엔비디아", "AI칩"],
    "생성형 AI": ["생성형AI", "챗GPT", "ChatGPT", "LLM", "거대언어모델", "챗봇"],
    "AI": ["인공지능", "AI 서비스"],
    "온디바이스 AI": ["온디바이스AI"],
    "2차전지": ["이차전지", "배터리"],
    "양극재": ["양극활물질"],
    "전고체": ["전고체배터리"],
    "전기차": ["EV", "전기자동차"],
    "자율주행": ["자율주행차", "로보택시"],
    "원전": ["원자력", "원자력발전"],
    "SMR": ["소형모듈원전", "소형모듈원자로"],
    "신재생에너지": ["재생에너지", "신재생"],
    "방산": ["방위산업", "K방산", "무기"],
    "우주항공": ["항공우주", "우주"],
    "비만치료제": ["GLP-1", "비만약", "위고비", "비만"],
    "가상자산": ["비트코인", "코인", "암호화폐", "블록체인", "가상화폐"],
    "밸류업": ["기업가치제고", "저PBR", "밸류업 프로그램"],
    "엔터": ["엔터테인먼트", "K팝", "K-POP", "케이팝"],
    "게임": ["게임주"],
    "로봇": ["로보틱스"],
    "휴머노이드": ["휴머노이드로봇"],
    "조선": ["선박", "造船"],
    "제약": ["바이오"],
}

ALL_THEMES: list[str] = [t for themes in THEME_TAXONOMY.values() for t in themes]


def _norm(s: str) -> str:
    return "".join(str(s).split()).lower()


# 정규화 조회 테이블: 정규화 문자열 → 정식 테마명.
_LOOKUP: dict[str, str] = {}
for _canon in ALL_THEMES:
    _LOOKUP[_norm(_canon)] = _canon
for _canon, _aliases in ALIASES.items():
    for _a in _aliases:
        _LOOKUP.setdefault(_norm(_a), _canon)


def normalize_theme(raw: str) -> str | None:
    """AI 원본 테마 문자열을 정식 테마명으로 매핑한다. 어휘에 없으면 None(드롭)."""
    if not raw:
        return None
    n = _norm(raw)
    if not n:
        return None
    if n in _LOOKUP:
        return _LOOKUP[n]
    # 부분 일치: 별칭/정식명(길이 3+)이 원본에 포함되거나 그 반대일 때(긴 것 우선).
    for key, canon in sorted(_LOOKUP.items(), key=lambda kv: -len(kv[0])):
        if len(key) >= 3 and (key in n or n in key):
            return canon
    return None


def normalize_themes(raw_themes: list[str] | None, limit: int = 2) -> list[str]:
    """원본 테마 리스트를 정식 테마명으로 정규화(중복 제거, 최대 limit개)."""
    result: list[str] = []
    for raw in raw_themes or []:
        canon = normalize_theme(str(raw))
        if canon and canon not in result:
            result.append(canon)
        if len(result) >= limit:
            break
    return result


def theme_prompt_block() -> str:
    """AI 시스템 프롬프트에 넣을 '허용 테마 목록'(카테고리별)."""
    lines = ["[허용 테마 목록] themes는 반드시 아래에서만 최대 2개 고르고(정확히 이 표기 사용), "
             "해당하는 투자 테마가 없으면 빈 배열 []로 두세요:"]
    for category, themes in THEME_TAXONOMY.items():
        lines.append(f"  - {category}: {', '.join(themes)}")
    return "\n".join(lines)
