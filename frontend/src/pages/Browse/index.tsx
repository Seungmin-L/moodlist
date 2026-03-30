import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { getSongs } from '../../api/songs'
import type { Song, Category } from '../../types'
import SongCard from '../../components/common/SongCard'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import FadeInSection from '../../components/common/FadeInSection'
import styles from './Browse.module.css'

const CATEGORIES: Array<Category | 'all'> = [
  'all', '관심', '짝사랑', '썸', '사랑', '권태기', '갈등', '이별', '자기자신', '일상', '기타'
]
const LABELS: Record<string, string> = { all: '전체' }

const PAGE_SIZE = 12

export default function Browse() {
  const [searchParams, setSearchParams] = useSearchParams()
  const activeCategory = (searchParams.get('category') as Category) || null
  const [songs, setSongs] = useState<Song[]>([])
  const [visible, setVisible] = useState(PAGE_SIZE)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    setVisible(PAGE_SIZE)
    getSongs(activeCategory ?? undefined)
      .then(setSongs)
      .catch(() => setSongs([]))
      .finally(() => setLoading(false))
  }, [activeCategory])

  const handleCategory = (cat: Category | 'all') => {
    if (cat === 'all') setSearchParams({})
    else setSearchParams({ category: cat })
  }

  return (
    <div className={styles.page}>
      <FadeInSection>
        <h1 className={styles.pageTitle}>Browse</h1>
      </FadeInSection>

      <FadeInSection delay={0.05}>
        <div className={styles.tabsWrap}>
          <div className={styles.tabs}>
            {CATEGORIES.map((cat) => (
              <button
                key={cat}
                className={`${styles.tab} ${(cat === 'all' ? !activeCategory : activeCategory === cat) ? styles.active : ''}`}
                onClick={() => handleCategory(cat)}
              >
                {LABELS[cat] ?? cat}
              </button>
            ))}
          </div>
        </div>
      </FadeInSection>

      {loading ? (
        <LoadingSpinner size="md" />
      ) : (
        <AnimatePresence mode="wait">
          <motion.div
            key={activeCategory ?? 'all'}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
          >
            {songs.length === 0 ? (
              <p className={styles.empty}>분류된 곡이 없습니다</p>
            ) : (
              <>
                <div className={styles.grid}>
                  {songs.slice(0, visible).map((song) => (
                    <SongCard key={song.spotify_id} song={song} />
                  ))}
                </div>
                {visible < songs.length && (
                  <button className={styles.loadMore} onClick={() => setVisible((v) => v + PAGE_SIZE)}>
                    더 보기 ({songs.length - visible}곡 남음)
                  </button>
                )}
              </>
            )}
          </motion.div>
        </AnimatePresence>
      )}
    </div>
  )
}
