import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ExternalLink, ChevronRight } from 'lucide-react'
import type { AddSongResponse } from '../../types'
import CategoryBadge from '../../components/common/CategoryBadge'
import EmotionsChart from '../../components/common/EmotionsChart'
import AlbumArt from '../../components/common/AlbumArt'
import styles from './SearchResult.module.css'

interface Props {
  result: AddSongResponse
}

export default function SearchResult({ result }: Props) {
  const navigate = useNavigate()
  const [expanded, setExpanded] = useState(false)

  return (
    <motion.div
      className={styles.card}
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: 'easeOut' }}
    >
      {result.already_exists && (
        <div className={styles.existsBanner}>이미 분류된 곡입니다</div>
      )}

      <div className={styles.top}>
        <AlbumArt artist={result.artist} category={result.category} size={80} />
        <div className={styles.titleArea}>
          <div className={styles.badges}>
            {result.category && <CategoryBadge category={result.category} />}
            {result.confidence != null && (
              <span className={styles.confidence}>{Math.round(result.confidence * 100)}%</span>
            )}
          </div>
          <h2 className={styles.title}>{result.title}</h2>
          <p className={styles.artist}>{result.artist}</p>
        </div>
      </div>

      {result.mood && (
        <div className={styles.moodBlock}>
          <span className={styles.moodLabel}>mood</span>
          <p className={styles.mood}>"{result.mood}"</p>
        </div>
      )}

      {result.emotions && Object.keys(result.emotions).length > 0 && (
        <EmotionsChart
          emotions={result.emotions}
          primaryEmotion={result.primary_emotion}
          compact
        />
      )}

      {result.narrative && (
        <div className={styles.narrative}>
          <p className={expanded ? styles.narrativeFull : styles.narrativeClamp}>
            {result.narrative}
          </p>
          <button className={styles.expandBtn} onClick={() => setExpanded((v) => !v)}>
            {expanded ? '접기' : '더보기'}
          </button>
        </div>
      )}

      {result.tags && result.tags.length > 0 && (
        <div className={styles.tags}>
          {result.tags.map((tag) => (
            <span key={tag} className={styles.tag}>#{tag}</span>
          ))}
        </div>
      )}

      <div className={styles.actions}>
        <a
          href={`https://open.spotify.com/track/${result.spotify_id}`}
          target="_blank"
          rel="noopener noreferrer"
          className={styles.spotifyBtn}
          onClick={(e) => e.stopPropagation()}
        >
          <ExternalLink size={16} />
          Spotify에서 열기
        </a>

        <button
          className={styles.similarBtn}
          onClick={() => navigate(`/song/${result.spotify_id}`)}
        >
          유사곡 보기
          <ChevronRight size={16} />
        </button>
      </div>
    </motion.div>
  )
}
