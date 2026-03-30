import { useState, useEffect, useRef } from 'react'
import { Search } from 'lucide-react'
import { getSearchSuggestions } from '../../api/songs'
import type { SearchSuggestion } from '../../types/api'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import styles from './SearchBar.module.css'

interface Props {
  onSearch: (title: string, artist: string, spotifyId?: string, imageUrl?: string) => void
  isLoading: boolean
}

export default function SearchBar({ onSearch, isLoading }: Props) {
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState<SearchSuggestion[]>([])
  const [suggestLoading, setSuggestLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (!query.trim() || query.trim().length < 2) {
      setSuggestions([])
      setOpen(false)
      return
    }
    debounceRef.current = setTimeout(async () => {
      setSuggestLoading(true)
      try {
        const results = await getSearchSuggestions(query.trim())
        setSuggestions(results)
        setOpen(results.length > 0)
      } catch {
        setSuggestions([])
      } finally {
        setSuggestLoading(false)
      }
    }, 300)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [query])

  // 외부 클릭 시 드롭다운 닫기
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const handleSelect = (s: SearchSuggestion) => {
    setQuery(`${s.title} - ${s.artist}`)
    setOpen(false)
    onSearch(s.title, s.artist, s.spotify_id, s.image_url ?? undefined)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!query.trim() || isLoading) return
    setOpen(false)
    // 직접 입력 시 title/artist 분리 시도
    const parts = query.split(' - ')
    const title = parts[0].trim()
    const artist = parts[1]?.trim() ?? ''
    onSearch(title, artist)
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <div className={styles.inputWrap} ref={wrapRef}>
        <Search size={16} className={styles.inputIcon} />
        {suggestLoading && <span className={styles.spinnerRight}><LoadingSpinner size="sm" /></span>}
        <input
          className={styles.input}
          type="text"
          placeholder="곡명 또는 곡명 - 아티스트 입력..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => suggestions.length > 0 && setOpen(true)}
          disabled={isLoading}
          autoComplete="off"
        />

        {open && suggestions.length > 0 && (
          <ul className={styles.dropdown}>
            {suggestions.map((s) => (
              <li key={s.spotify_id} className={styles.suggestionItem} onMouseDown={() => handleSelect(s)}>
                {s.image_url
                  ? <img src={s.image_url} className={styles.thumb} alt="" />
                  : <div className={styles.thumbPlaceholder} />
                }
                <div className={styles.suggestionInfo}>
                  <span className={styles.suggestionTitle}>{s.title}</span>
                  <span className={styles.suggestionArtist}>{s.artist}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <button className={styles.btn} type="submit" disabled={isLoading || !query.trim()}>
        {isLoading ? <LoadingSpinner size="sm" /> : '분류하기'}
      </button>

      {isLoading && (
        <p className={styles.hint}>가사를 분석 중입니다... 최대 1분 소요될 수 있어요</p>
      )}
    </form>
  )
}
