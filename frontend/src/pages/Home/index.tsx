import { useEffect, useState } from 'react'
import { addSong, getSongs } from '../../api/songs'
import type { AddSongResponse, Song } from '../../types'
import FadeInSection from '../../components/common/FadeInSection'
import SongCard from '../../components/common/SongCard'
import SearchBar from './SearchBar'
import SearchResult from './SearchResult'
import styles from './Home.module.css'

export default function Home() {
  const [isSearching, setIsSearching] = useState(false)
  const [searchResult, setSearchResult] = useState<AddSongResponse | null>(null)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [recentSongs, setRecentSongs] = useState<Song[]>([])

  useEffect(() => {
    getSongs().then((songs) => setRecentSongs(songs.slice(0, 12))).catch(() => {})
  }, [])

  const handleSearch = async (title: string, artist: string, spotifyId?: string, imageUrl?: string) => {
    setIsSearching(true)
    setSearchError(null)
    setSearchResult(null)
    try {
      const result = await addSong({
        title,
        artist,
        ...(spotifyId ? { spotify_id: spotifyId } : {}),
        ...(imageUrl ? { image_url: imageUrl } : {}),
      })
      setSearchResult(result)
      setRecentSongs((prev) => {
        const filtered = prev.filter((s) => s.spotify_id !== result.spotify_id)
        return [result as Song, ...filtered].slice(0, 12)
      })
    } catch (e) {
      setSearchError(e instanceof Error ? e.message : '곡을 찾을 수 없습니다')
    } finally {
      setIsSearching(false)
    }
  }

  return (
    <div className={styles.page}>
      <FadeInSection>
        <div className={styles.hero}>
          <h1 className={styles.heroTitle}>
            지금 내 감정에 맞는<br />노래를 찾아드려요
          </h1>
          <p className={styles.heroSub}>
            곡명과 아티스트를 입력하면 가사를 분석해 mood와 감정을 분류해 드립니다
          </p>
        </div>
      </FadeInSection>

      <FadeInSection delay={0.1}>
        <div className={styles.searchSection}>
          <SearchBar onSearch={handleSearch} isLoading={isSearching} />
        </div>
      </FadeInSection>

      {searchError && (
        <FadeInSection>
          <div className={styles.error}>{searchError}</div>
        </FadeInSection>
      )}

      {searchResult && (
        <FadeInSection>
          <SearchResult result={searchResult} />
        </FadeInSection>
      )}

      {recentSongs.length > 0 && (
        <FadeInSection delay={0.2}>
          <section className={styles.recentSection}>
            <h2 className={styles.sectionTitle}>최근 분류된 곡</h2>
            <div className={styles.grid}>
              {recentSongs.map((song) => (
                <SongCard key={song.spotify_id} song={song} />
              ))}
            </div>
          </section>
        </FadeInSection>
      )}
    </div>
  )
}
