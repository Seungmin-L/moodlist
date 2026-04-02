import styles from './LoadingSpinner.module.css'

interface Props {
  size?: 'sm' | 'md' | 'lg'
  label?: string
  color?: string
}

export default function LoadingSpinner({ size = 'md', label, color = 'var(--text-secondary)' }: Props) {
  const bars = size === 'sm' ? 5 : 7
  return (
    <div className={`${styles.wrapper} ${styles[size]}`} role="status" aria-label={label ?? '로딩 중'}>
      <svg
        className={styles.wave}
        viewBox={`0 0 ${bars * 6 - 2} 24`}
        aria-hidden
      >
        {Array.from({ length: bars }).map((_, i) => (
          <rect
            key={i}
            className={styles.bar}
            x={i * 6}
            width={4}
            rx={2}
            fill={color}
            style={{ animationDelay: `${i * 0.1}s` }}
          />
        ))}
      </svg>
      {size === 'lg' && label && <p className={styles.label}>{label}</p>}
    </div>
  )
}
