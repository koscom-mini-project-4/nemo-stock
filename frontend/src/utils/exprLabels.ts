/** logic.if_else의 expr(조건식)에 흔히 쓰이는 필드명 -> 한글 라벨.
 * expr는 symbols[code]의 아무 키나 참조할 수 있어(연결된 상위 노드에 따라 동적) 전부를
 * 다 알 수는 없다 — 엔진이 항상 채워주는 핵심 필드(가격/포트폴리오)와 대표 노드 출력만 다룬다.
 * 화면 표시용 변환일 뿐, 저장되는 원본 expr 문자열은 그대로 유지된다(편집 시 원본 노출). */
export const EXPR_FIELD_LABELS: Record<string, string> = {
  price: '현재가',
  prev_close: '전일종가',
  volume: '거래량',
  change_pct: '등락률',
  held_qty: '보유수량',
  held_avg_price: '보유평단가',
  cash: '현금',
  equity: '평가자산',
  open: '시가',
  high: '고가',
  low: '저가',
  close: '종가',
  news_text: '뉴스본문',
  news_id: '뉴스ID',
  disclosure_text: '공시본문',
  disclosure_id: '공시ID',
  sentiment_score: '감성점수',
  sentiment_summary: '감성요약',
  target_qty: '목표수량',
  volume_ratio: '거래량비율',
}

const IDENTIFIER_RE = /[A-Za-z_][A-Za-z0-9_]*/g

/** expr 문자열에서 알려진 필드명만 한글 라벨로 치환해 보여준다(원본 문자열은 건드리지 않음). */
export function translateExpr(expr: string): string {
  return expr.replace(IDENTIFIER_RE, (token) => EXPR_FIELD_LABELS[token] ?? token)
}
