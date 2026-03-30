import { useState } from 'react'
import { Search } from 'lucide-react'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import styles from './SearchBar.module.css'

interface Props {
  onSearch: (title: string, artist: string) => void
  isLoading: boolean
}

export default function SearchBar({ onSearch, isLoading }: Props) {
  const [title, setTitle] = useState('')
  const [artist, setArtist] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim() || isLoading) return
    onSearch(title.trim(), artist.trim())
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <div className={styles.inputs}>
        <div className={styles.inputWrap}>
          <Search size={16} className={styles.inputIcon} />
          <input
            className={styles.input}
            type="text"
            placeholder="곡명 입력..."
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            disabled={isLoading}
            required
          />
        </div>
        <div className={styles.inputWrap}>
          <input
            className={`${styles.input} ${styles.inputNoIcon}`}
            type="text"
            placeholder="아티스트 입력..."
            value={artist}
            onChange={(e) => setArtist(e.target.value)}
            disabled={isLoading}
          />
        </div>
      </div>

      <button className={styles.btn} type="submit" disabled={isLoading || !title.trim()}>
        {isLoading ? <LoadingSpinner size="sm" /> : '분류하기'}
      </button>

      {isLoading && (
        <p className={styles.hint}>Spotify에서 곡을 찾는 중... 최대 1분 소요될 수 있어요</p>
      )}
    </form>
  )
}
