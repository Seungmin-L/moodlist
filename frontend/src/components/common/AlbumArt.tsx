import { useState } from 'react'
import type { Category } from '../../types'
import styles from './AlbumArt.module.css'

const CAT_GRADIENTS: Record<string, string> = {
  관심:    'linear-gradient(135deg, #FFB347, #FFCC80)',
  짝사랑:  'linear-gradient(135deg, #FF6B9D, #FFB3CC)',
  썸:      'linear-gradient(135deg, #C3A6FF, #E0D4FF)',
  사랑:    'linear-gradient(135deg, #FF4B4B, #FF8A80)',
  권태기:  'linear-gradient(135deg, #95A5A6, #BDC3C7)',
  갈등:    'linear-gradient(135deg, #E74C3C, #FF7675)',
  이별:    'linear-gradient(135deg, #74B9FF, #A8D8FF)',
  자기자신:'linear-gradient(135deg, #55EFC4, #81ECEC)',
  일상:    'linear-gradient(135deg, #FFEAA7, #FFF3CD)',
  기타:    'linear-gradient(135deg, #B2BEC3, #DFE6E9)',
}

interface Props {
  artist: string
  category?: Category | string | null
  imageUrl?: string | null
  shape?: 'rounded' | 'circle'
  size?: number
}

export default function AlbumArt({ artist, category, imageUrl, shape = 'rounded', size = 80 }: Props) {
  const [imgError, setImgError] = useState(false)
  const gradient = CAT_GRADIENTS[category ?? ''] ?? CAT_GRADIENTS['기타']
  const showImage = imageUrl && !imgError

  return (
    <div
      className={`${styles.art} ${styles[shape]}`}
      style={{
        width: size,
        height: size,
        minWidth: size,
        background: showImage ? 'transparent' : gradient,
      }}
      aria-hidden="true"
    >
      {showImage ? (
        <img
          src={imageUrl}
          alt={artist}
          className={styles.img}
          onError={() => setImgError(true)}
        />
      ) : (
        <span className={styles.text} style={{ fontSize: Math.max(10, size * 0.2) }}>
          {artist.slice(0, 6).toUpperCase()}
        </span>
      )}
    </div>
  )
}
