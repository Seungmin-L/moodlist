import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowLeft, RefreshCw, ExternalLink } from 'lucide-react'
import { getSong, getSimilarSongs, reclassifySong } from '../../api/songs'
import type { SongDetail, SimilarSong } from '../../types'
import CategoryBadge from '../../components/common/CategoryBadge'
import EmotionsChart from '../../components/common/EmotionsChart'
import AlbumArt from '../../components/common/AlbumArt'
import SongCard from '../../components/common/SongCard'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import FadeInSection from '../../components/common/FadeInSection'
import styles from './SongDetail.module.css'

export default function SongDetail() {
  const { spotify_id } = useParams<{ spotify_id: string }>()
  const navigate = useNavigate()
  const [song, setSong] = useState<SongDetail | null>(null)
  const [similar, setSimilar] = useState<SimilarSong[]>([])
  const [loading, setLoading] = useState(true)
  const [reclassifying, setReclassifying] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!spotify_id) return
    setLoading(true)
    Promise.all([
      getSong(spotify_id),
      getSimilarSongs(spotify_id, 8).catch(() => ({ similar: [] })),
    ])
      .then(([songData, simData]) => {
        setSong(songData)
        setSimilar('similar' in simData ? simData.similar : [])
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [spotify_id])

  const handleReclassify = async () => {
    if (!spotify_id) return
    setReclassifying(true)
    try {
      await reclassifySong(spotify_id)
      const updated = await getSong(spotify_id)
      setSong(updated)
    } catch (e) {
      setError(e instanceof Error ? e.message : '재분류 실패')
    } finally {
      setReclassifying(false)
    }
  }

  if (loading) return <LoadingSpinner size="lg" label="곡 정보를 불러오는 중..." />
  if (error || !song) return (
    <div className={styles.errorWrap}>
      <p>{error ?? '곡을 찾을 수 없습니다'}</p>
      <button onClick={() => navigate('/')}>홈으로</button>
    </div>
  )

  return (
    <div className={styles.page}>
      <div className={styles.topBar}>
        <button className={styles.backBtn} onClick={() => navigate(-1)}>
          <ArrowLeft size={18} /> 뒤로
        </button>
        <button className={styles.reclassifyBtn} onClick={handleReclassify} disabled={reclassifying}>
          <RefreshCw size={16} className={reclassifying ? styles.spinning : ''} />
          {reclassifying ? '재분류 중...' : '재분류'}
        </button>
      </div>

      <FadeInSection>
        <motion.div className={styles.mainCard}
          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          <div className={styles.cardTop}>
            <AlbumArt artist={song.artist} category={song.category} imageUrl={song.album_art_url} shape="circle" size={96} />
            <div className={styles.info}>
              <div className={styles.badges}>
                {song.category && <CategoryBadge category={song.category} />}
                {song.confidence != null && (
                  <span className={styles.confidence}>{Math.round(song.confidence * 100)}%</span>
                )}
              </div>
              <h1 className={styles.title}>{song.title}</h1>
              <p className={styles.artist}>{song.artist}</p>
              {song.emotional_arc && (
                <p className={styles.arc}>{song.emotional_arc}</p>
              )}
            </div>
          </div>

          {song.mood && (
            <div className={styles.moodBlock}>
              <span className={styles.moodLabel}>mood</span>
              <p className={styles.mood}>"{song.mood}"</p>
            </div>
          )}

          <div className={styles.spotifyRow}>
            <a
              href={`https://open.spotify.com/track/${song.spotify_id}`}
              target="_blank" rel="noopener noreferrer"
              className={styles.spotifyBtn}
            >
              <ExternalLink size={15} /> Spotify에서 열기
            </a>
          </div>
        </motion.div>
      </FadeInSection>

      {song.emotions && Object.keys(song.emotions).length > 0 && (
        <FadeInSection delay={0.1}>
          <div className={styles.section}>
            <h2 className={styles.sectionTitle}>감정 분석</h2>
            <EmotionsChart emotions={song.emotions} primaryEmotion={song.primary_emotion} />
          </div>
        </FadeInSection>
      )}

      {song.narrative && (
        <FadeInSection delay={0.15}>
          <div className={styles.section}>
            <h2 className={styles.sectionTitle}>분석</h2>
            <div className={styles.narrativeCard}>
              <p className={styles.narrative}>{song.narrative}</p>
              {song.tags && song.tags.length > 0 && (
                <div className={styles.tags}>
                  {song.tags.map((t) => <span key={t} className={styles.tag}>#{t}</span>)}
                </div>
              )}
            </div>
          </div>
        </FadeInSection>
      )}

      {similar.length > 0 && (
        <FadeInSection delay={0.2}>
          <div className={styles.section}>
            <h2 className={styles.sectionTitle}>유사한 곡들</h2>
            <div className={styles.similarGrid}>
              {similar.map((s) => (
                <SongCard key={s.spotify_id} song={{ ...s, status: 'classified', classified_at: null, emotions: null, primary_emotion: null, emotional_arc: null, tags: null, narrative: null, confidence: null, album_art_url: s.album_art_url ?? null }} />
              ))}
            </div>
          </div>
        </FadeInSection>
      )}
    </div>
  )
}
