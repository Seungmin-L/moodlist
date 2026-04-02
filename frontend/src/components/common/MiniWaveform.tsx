import { useMemo } from 'react'

interface Props {
  color?: string
  bars?: number
  opacity?: number
  width?: number
  height?: number
}

export default function MiniWaveform({ color = '#FF9AB5', bars = 12, opacity = 0.3, width = 56, height = 20 }: Props) {
  const heights = useMemo(
    () => Array.from({ length: bars }, () => 20 + Math.random() * 80),
    [bars]
  )
  const barW = 2
  const gap = (width - bars * barW) / (bars - 1)

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden>
      {heights.map((h, i) => {
        const barH = (h / 100) * height
        return (
          <rect
            key={i}
            x={i * (barW + gap)}
            y={height - barH}
            width={barW}
            height={barH}
            rx={1}
            fill={color}
            opacity={opacity}
          />
        )
      })}
    </svg>
  )
}
