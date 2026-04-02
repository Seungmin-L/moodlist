const MOOD_COLORS: Record<string, string> = {
  '이별':    '#FF9AB5',
  '사랑':    '#A0A8FF',
  '갈등':    '#FF7B6B',
  '자기자신':'#6EDCB0',
  '일상':    '#FFD080',
  '관심':    '#A0C4FF',
  '짝사랑':  '#FFB3DE',
  '썸':      '#C4A0FF',
  '권태기':  '#9B9BB0',
  '기타':    '#7A8A9E',
}

export function getMoodColor(category: string | null | undefined): string {
  return MOOD_COLORS[category ?? ''] ?? '#A0A8FF'
}

export function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r},${g},${b},${alpha})`
}
