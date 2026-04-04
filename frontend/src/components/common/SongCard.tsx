import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import type { Song } from '../../types'
import CategoryBadge from './CategoryBadge'
import AlbumArt from './AlbumArt'
import styles from './SongCard.module.css'

interface Props {
  song: Song
  index?: number
}

export default function SongCard({ song, index }: Props) {
  const navigate = useNavigate()
  const hasIndex = index != null

  return (
    <motion.div
      className={`${styles.row} ${hasIndex ? '' : styles.rowNoIndex}`}
      onClick={() => navigate(`/song/${song.spotify_id}`)}
      whileTap={{ scale: 0.99 }}
      transition={{ duration: 0.1 }}
    >
      {hasIndex && <span className={styles.index}>{index}</span>}

      <AlbumArt
        artist={song.artist}
        category={song.category}
        imageUrl={song.album_art_url}
        shape="rounded"
        size={40}
      />

      <div className={styles.info}>
        <span className={styles.title}>{song.title}</span>
        <span className={styles.artist}>{song.artist}</span>
        {song.category && <CategoryBadge category={song.category} size="sm" />}
      </div>

    </motion.div>
  )
}
