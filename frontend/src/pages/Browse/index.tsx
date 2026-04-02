import { useEffect, useState, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { getSongs } from '../../api/songs'
import type { Song, Category } from '../../types'
import AlbumArt from '../../components/common/AlbumArt'
import CategoryBadge from '../../components/common/CategoryBadge'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import styles from './Browse.module.css'

const CATEGORIES: Array<Category | 'all'> = [
  'all', '관심', '짝사랑', '썸', '사랑', '권태기', '갈등', '이별', '자기자신', '일상', '기타'
]
const LABELS: Record<string, string> = { all: '전체' }

export default function Browse() {
  const [searchParams, setSearchParams] = useSearchParams()
  const activeCategory = (searchParams.get('category') as Category) || null
  const [songs, setSongs] = useState<Song[]>([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')

  useEffect(() => {
    setLoading(true)
    getSongs(activeCategory ?? undefined)
      .then((data) => setSongs(data))
      .catch(() => setSongs([]))
      .finally(() => setLoading(false))
  }, [activeCategory])

  const filtered = useMemo(() => {
    if (!query.trim()) return songs
    const q = query.toLowerCase()
    return songs.filter((s) =>
      s.title.toLowerCase().includes(q) || s.artist.toLowerCase().includes(q)
    )
  }, [songs, query])

  const handleCategory = (cat: Category | 'all') => {
    setQuery('')
    if (cat === 'all') setSearchParams({})
    else setSearchParams({ category: cat })
  }

  return (
    <div className={styles.layout}>
      {/* Header */}
      <div className={styles.libraryHeader}>
        <h1 className={styles.libraryTitle}>라이브러리</h1>
      </div>

      {/* Search */}
      <div className={styles.searchWrap}>
        <svg className={styles.searchIcon} viewBox="0 0 16 16" fill="none" aria-hidden>
          <circle cx="6.5" cy="6.5" r="4.5" stroke="currentColor" strokeWidth="1.5" />
          <path d="M10.5 10.5L14 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        <input
          className={styles.searchInput}
          placeholder="검색"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      {/* Category Pills */}
      <div className={styles.pillsWrap}>
        <div className={styles.pills}>
          {CATEGORIES.map((cat) => {
            const isActive = cat === 'all' ? !activeCategory : activeCategory === cat
            return (
              <button
                key={cat}
                className={`${styles.pill} ${isActive ? styles.pillActive : ''}`}
                onClick={() => handleCategory(cat)}
              >
                {LABELS[cat] ?? cat}
              </button>
            )
          })}
        </div>
      </div>

      {/* Song List */}
      {loading ? (
        <LoadingSpinner size="md" />
      ) : filtered.length === 0 ? (
        <p className={styles.empty}>곡이 없습니다</p>
      ) : (
        <AnimatePresence mode="wait">
          <motion.div
            key={activeCategory ?? 'all'}
            className={styles.songList}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            {filtered.map((song) => (
              <a
                key={song.spotify_id}
                className={styles.songRow}
                href={`/song/${song.spotify_id}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                <AlbumArt
                  artist={song.artist}
                  category={song.category}
                  imageUrl={song.album_art_url}
                  shape="rounded"
                  size={44}
                />
                <div className={styles.songInfo}>
                  <span className={styles.songTitle}>{song.title}</span>
                  <span className={styles.songMeta}>
                    {song.artist}
                    {song.category && <> · <CategoryBadge category={song.category} size="sm" /></>}
                    {song.confidence != null && (
                      <span className={styles.songConf}> · {Math.round(song.confidence * 100)}%</span>
                    )}
                  </span>
                </div>
                {song.classified_at && (
                  <span className={styles.songDuration}>
                    {new Date(song.classified_at).toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' })}
                  </span>
                )}
              </a>
            ))}
          </motion.div>
        </AnimatePresence>
      )}
    </div>
  )
}
