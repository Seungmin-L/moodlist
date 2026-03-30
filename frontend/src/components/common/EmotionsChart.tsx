import { motion } from 'framer-motion'
import type { Emotions } from '../../types'
import styles from './EmotionsChart.module.css'

const EMOTION_COLORS = [
  '#8b5cf6', '#06b6d4', '#f472b6',
  '#34d399', '#fbbf24', '#f87171',
]

interface Props {
  emotions: Emotions
  primaryEmotion?: string | null
  compact?: boolean
}

export default function EmotionsChart({ emotions, primaryEmotion, compact = false }: Props) {
  const sorted = Object.entries(emotions)
    .sort(([, a], [, b]) => b - a)
    .slice(0, compact ? 3 : undefined)

  return (
    <div className={styles.list}>
      {sorted.map(([name, score], i) => {
        const color = EMOTION_COLORS[i % EMOTION_COLORS.length]
        const isPrimary = name === primaryEmotion
        const pct = Math.round(score * 100)

        return (
          <div key={name} className={`${styles.pill} ${isPrimary ? styles.primary : ''}`}>
            <span className={styles.name}>{name}</span>
            <div className={styles.barTrack}>
              <motion.div
                className={styles.barFill}
                style={{ background: color }}
                initial={{ width: 0 }}
                animate={{ width: `${pct}%` }}
                transition={{ duration: 0.6, delay: i * 0.1, ease: 'easeOut' }}
              />
            </div>
            <span className={styles.pct} style={{ color }}>{pct}%</span>
          </div>
        )
      })}
    </div>
  )
}
