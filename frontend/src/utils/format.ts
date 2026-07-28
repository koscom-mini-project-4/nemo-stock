/** 금액/시각 표시를 KST(Asia/Seoul)와 원화(KRW)로 일관되게 포맷하는 공용 유틸.
 *
 * 서버가 저장하는 시각(created_at/updated_at 등)은 naive datetime(타임존 정보 없는
 * `datetime.now()`)이지만, 서버 시스템 시간이 KST이므로 문자열의 시:분 값 자체가 이미
 * 한국 시각이다. `new Date(iso).toLocaleString()`으로 표시하면 브라우저가 이 문자열을
 * "브라우저 로컬 타임존의 시각"으로 잘못 해석해, 브라우저가 KST가 아닌 환경에서는 값이
 * 그대로 나오되(타임존 변환이 안 걸리는 게 오히려 우연히 맞는 경우) 어떤 브라우저/런타임은
 * 이를 UTC로 오인해 재변환하기도 해 표시가 흔들린다 — 그래서 Date 객체의 타임존 변환을
 * 아예 거치지 않고, 문자열에서 연/월/일/시/분을 직접 추출해 그대로 재포맷한다(이미 KST인
 * 값을 다시 "KST로 변환"하지 않는다).
 */

const KRW_FORMATTER = new Intl.NumberFormat('ko-KR', {
  style: 'currency',
  currency: 'KRW',
  maximumFractionDigits: 0,
})

export function formatKrw(value: number): string {
  return KRW_FORMATTER.format(value)
}

/** "YYYY-MM-DDTHH:mm:ss(.ffffff)?" (naive, 이미 KST) -> "YYYY.MM.DD HH:mm". 파싱 실패 시 원문 반환. */
export function formatDateTimeKst(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(iso)
  if (!m) return iso
  const [, y, mo, d, h, mi] = m
  return `${y}.${mo}.${d} ${h}:${mi}`
}
