import type { Category } from '../../types'
import styles from './CategoryBadge.module.css'

interface Props {
  category: Category | string
  size?: 'sm' | 'md'
}

export default function CategoryBadge({ category, size = 'md' }: Props) {
  return (
    <span
      className={`${styles.badge} ${styles[size]}`}
      style={{ '--cat-color': `var(--cat-${category}, #B2BEC3)` } as React.CSSProperties}
    >
      {category}
    </span>
  )
}
