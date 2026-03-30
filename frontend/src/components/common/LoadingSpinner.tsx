import styles from './LoadingSpinner.module.css'

interface Props {
  size?: 'sm' | 'md' | 'lg'
  label?: string
}

export default function LoadingSpinner({ size = 'md', label = '로딩 중...' }: Props) {
  return (
    <div className={styles.wrapper} role="status" aria-label={label}>
      <div className={`${styles.spinner} ${styles[size]}`} />
      {size === 'lg' && <p className={styles.text}>{label}</p>}
    </div>
  )
}
