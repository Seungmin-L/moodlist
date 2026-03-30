import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ExternalLink } from 'lucide-react'
import type { Song } from '../../types'
import CategoryBadge from './CategoryBadge'
import AlbumArt from './AlbumArt'
import styles from './SongCard.module.css'

interface Props {
  song: Song
}

export default function SongCard({ song }: Props) {
  const navigate = useNavigate()

  const handleClick = () => navigate(`/song/${song.spotify_id}`)

  const handleSpotify = (e: React.MouseEvent) => {
    e.stopPropagation()
    window.open(`https://open.spotify.com/track/${song.spotify_id}`, '_blank')
  }

  return (
    <motion.div
      className={styles.card}
      onClick={handleClick}
      whileHover={{ scale: 1.02, y: -2 }}
      whileTap={{ scale: 0.98 }}
      transition={{ duration: 0.2 }}
    >
      <AlbumArt
        artist={song.artist}
        category={song.category}
        imageUrl={song.album_art_url}
        shape="rounded"
        size={72}
      />

      <div className={styles.info}>
        <p className={styles.title}>{song.title}</p>
        <p className={styles.artist}>{song.artist}</p>
        <div className={styles.meta}>
          {song.category && <CategoryBadge category={song.category} size="sm" />}
          {song.confidence != null && (
            <span className={styles.confidence}>{Math.round(song.confidence * 100)}%</span>
          )}
        </div>
      </div>

      <button className={styles.spotifyBtn} onClick={handleSpotify} aria-label="Spotify에서 열기">
        <ExternalLink size={14} />
      </button>
    </motion.div>
  )
}
