/** 손익(수익률/수익금액) 표시 공용 유틸. 한국 증시 관례에 맞춰 이익=빨강(positive), 손실=파랑(negative)
 * 클래스를 반환한다(실제 색상은 style.css --positive/--negative). */
import { formatKrw } from './format'

export function pnlClass(value: number): string {
  if (value > 0) return 'positive'
  if (value < 0) return 'negative'
  return ''
}

export function formatSignedPct(value: number, digits = 2): string {
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(digits)}%`
}

export function formatSignedKrw(value: number): string {
  const sign = value > 0 ? '+' : value < 0 ? '-' : ''
  return `${sign}${formatKrw(Math.abs(value))}`
}
