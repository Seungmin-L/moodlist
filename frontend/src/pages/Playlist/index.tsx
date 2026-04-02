import { useEffect, useState, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronDown, ChevronUp, LogIn, Check, Music, X, ExternalLink, RotateCcw, Plus } from 'lucide-react'
import { exportTracks, getSpotifyAuth, getSpotifyLoginUrl, getMyPlaylists, previewPlaylist } from '../../api/spotify'
import { addSong } from '../../api/songs'
import type { AddSongResponse, Category } from '../../types'
import type { SpotifyAuthStatus, SpotifyMyPlaylist, SpotifyPreviewTrack } from '../../types'
import CategoryBadge from '../../components/common/CategoryBadge'
import AlbumArt from '../../components/common/AlbumArt'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import styles from './Playlist.module.css'

type Phase = 'input' | 'preview' | 'importing' | 'results'

// ── 카테고리별 그룹 ────────────────────────────────────────
interface CategoryGroup {
  category: string
  songs: AddSongResponse[]
}

function groupByCategory(songs: AddSongResponse[]): CategoryGroup[] {
  const map = new Map<string, AddSongResponse[]>()
  for (const song of songs) {
    const cat = song.category ?? '기타'
    if (!map.has(cat)) map.set(cat, [])
    map.get(cat)!.push(song)
  }
  return Array.from(map.entries()).map(([category, songs]) => ({ category, songs }))
}

// ── Spotify 저장 모달 ────────────────────────────────────────
function SaveModal({
  songs,
  category,
  myPlaylists,
  onClose,
}: {
  songs: AddSongResponse[]
  category: string
  myPlaylists: SpotifyMyPlaylist[]
  onClose: () => void
}) {
  const [mode, setMode] = useState<'choose' | 'new' | 'existing'>('choose')
  const [name, setName] = useState(`Moodlist — ${category}`)
  const [loading, setLoading] = useState(false)
  const [resultUrl, setResultUrl] = useState<string | null>(null)

  const ids = songs.map((s) => s.spotify_id)

  const handleCreateNew = async () => {
    setLoading(true)
    try {
      const r = await exportTracks({ spotify_ids: ids, playlist_name: name })
      setResultUrl(r.playlist_url)
    } finally {
      setLoading(false)
    }
  }

  const handleAddToExisting = async (playlistId: string) => {
    setLoading(true)
    try {
      const r = await exportTracks({ spotify_ids: ids, playlist_name: '', playlist_id: playlistId })
      setResultUrl(r.playlist_url)
    } finally {
      setLoading(false)
    }
  }

  return (
    <motion.div className={styles.modalOverlay} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
      <motion.div className={styles.modal} initial={{ y: 16, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 16, opacity: 0 }} onClick={(e) => e.stopPropagation()}>
        <div className={styles.modalHeader}>
          <span className={styles.modalTitle}>
            {resultUrl ? '저장 완료' : `${category} · ${songs.length}곡`}
          </span>
          <button className={styles.modalClose} onClick={onClose}><X size={16} /></button>
        </div>

        {resultUrl ? (
          <a href={resultUrl} target="_blank" rel="noopener noreferrer" className={styles.openBtn}>
            Spotify에서 열기 →
          </a>
        ) : mode === 'choose' ? (
          <div className={styles.saveChoices}>
            <button className={styles.saveChoice} onClick={() => setMode('new')}>
              <Plus size={16} />
              <div>
                <p className={styles.saveChoiceTitle}>새 플레이리스트 만들기</p>
                <p className={styles.saveChoiceSub}>Spotify에 새로 생성합니다</p>
              </div>
            </button>
            <button className={styles.saveChoice} onClick={() => setMode('existing')} disabled={myPlaylists.length === 0}>
              <Music size={16} />
              <div>
                <p className={styles.saveChoiceTitle}>기존 플레이리스트에 추가</p>
                <p className={styles.saveChoiceSub}>
                  {myPlaylists.length > 0 ? '내 플레이리스트에서 선택' : '로그인 필요'}
                </p>
              </div>
            </button>
          </div>
        ) : mode === 'new' ? (
          <div className={styles.saveNewForm}>
            <button className={styles.modalBack} onClick={() => setMode('choose')}>← 뒤로</button>
            <input className={styles.modalInput} value={name} onChange={(e) => setName(e.target.value)} placeholder="플레이리스트 이름" />
            <button className={styles.modalSave} onClick={handleCreateNew} disabled={loading || !name.trim()}>
              {loading ? <LoadingSpinner size="sm" /> : '만들기'}
            </button>
          </div>
        ) : (
          <div className={styles.saveExistingList}>
            <button className={styles.modalBack} onClick={() => setMode('choose')}>← 뒤로</button>
            <ul className={styles.myListsList}>
              {myPlaylists.map((pl) => (
                <li key={pl.id}>
                  <button className={styles.myListItem} onClick={() => handleAddToExisting(pl.id)} disabled={loading}>
                    {pl.image ? <img src={pl.image} className={styles.plThumb} alt="" /> : <div className={styles.plThumbPlaceholder} />}
                    <span className={styles.plName}>{pl.name}</span>
                    <span className={styles.plCount}>{pl.total}곡</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </motion.div>
    </motion.div>
  )
}

// ── 메인 Playlist 페이지 ─────────────────────────────────────
export default function Playlist() {
  const [phase, setPhase] = useState<Phase>('input')
  const [url, setUrl] = useState('')
  const [previewLoading, setPreviewLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showMyLists, setShowMyLists] = useState(false)

  const [playlistName, setPlaylistName] = useState('')
  const [tracks, setTracks] = useState<SpotifyPreviewTrack[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const [progress, setProgress] = useState({ done: 0, total: 0, current: '' })
  const [results, setResults] = useState<AddSongResponse[]>([])

  const [auth, setAuth] = useState<SpotifyAuthStatus | null>(null)
  const [myPlaylists, setMyPlaylists] = useState<SpotifyMyPlaylist[]>([])
  const [playlistsLoading, setPlaylistsLoading] = useState(false)

  // Save modal
  const [saveTarget, setSaveTarget] = useState<CategoryGroup | null>(null)

  useEffect(() => {
    getSpotifyAuth().then((s) => {
      setAuth(s)
      if (s.logged_in) {
        setPlaylistsLoading(true)
        getMyPlaylists().then(setMyPlaylists).finally(() => setPlaylistsLoading(false))
      }
    }).catch(() => setAuth({ logged_in: false }))
  }, [])

  const groups = useMemo(() => groupByCategory(results), [results])

  const handleLoginSpotify = async () => {
    const loginUrl = await getSpotifyLoginUrl()
    const popup = window.open(loginUrl, 'spotify-login', 'width=480,height=680')
    const timer = setInterval(() => {
      if (popup?.closed) {
        clearInterval(timer)
        getSpotifyAuth().then((s) => {
          setAuth(s)
          if (s.logged_in) getMyPlaylists().then(setMyPlaylists)
        })
      }
    }, 800)
  }

  const handlePreview = async (inputUrl: string) => {
    if (!inputUrl.trim()) return
    setError(null)
    setPreviewLoading(true)
    setShowMyLists(false)
    try {
      const data = await previewPlaylist(inputUrl.trim())
      setPlaylistName(data.playlist.name)
      setTracks(data.tracks)
      setSelected(new Set(data.tracks.map((t) => t.id)))
      setPhase('preview')
    } catch (err) {
      setError(err instanceof Error ? err.message : '조회에 실패했습니다')
    } finally {
      setPreviewLoading(false)
    }
  }

  const handleImport = async () => {
    const toImport = tracks.filter((t) => selected.has(t.id))
    if (!toImport.length) return
    setPhase('importing')
    setProgress({ done: 0, total: toImport.length, current: '' })
    const collected: AddSongResponse[] = []
    for (let i = 0; i < toImport.length; i++) {
      const t = toImport[i]
      setProgress({ done: i, total: toImport.length, current: t.title })
      try {
        const r = await addSong({ title: t.title, artist: t.artist, spotify_id: t.id })
        collected.push(r)
      } catch { /* skip */ }
    }
    setProgress((p) => ({ ...p, done: toImport.length }))
    setResults(collected)
    setPhase('results')
  }

  const resetAll = () => {
    setPhase('input')
    setUrl('')
    setTracks([])
    setSelected(new Set())
    setResults([])
    setError(null)
    setShowMyLists(false)
  }

  const toggleAll = () =>
    setSelected(selected.size === tracks.length ? new Set() : new Set(tracks.map((t) => t.id)))
  const toggleOne = (id: string) =>
    setSelected((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n })

  return (
    <div className={styles.page}>

      {/* ── 상단 바 ──────────────────────────────────────── */}
      <div className={styles.topBar}>
        <div className={styles.topBarLeft}>
          {!auth?.logged_in ? (
            <button className={styles.spotifyLoginBtn} onClick={handleLoginSpotify}>
              <LogIn size={13} /> Spotify 로그인
            </button>
          ) : (
            <span className={styles.authLabel}>
              <Check size={12} style={{ color: 'var(--color-spotify)' }} /> {auth.user}
            </span>
          )}
        </div>
        {phase === 'results' && (
          <button className={styles.resetBtn} onClick={resetAll}>
            <RotateCcw size={13} /> 새 플레이리스트
          </button>
        )}
      </div>

      {/* ── 링크 입력 ─────────────────────────────────────── */}
      {phase === 'input' && (
        <div className={styles.inputPhase}>
          <motion.div className={styles.linkCard} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
            <div className={styles.linkCardIcon}><Music size={22} strokeWidth={1.5} /></div>
            <h2 className={styles.linkCardTitle}>플레이리스트 가져오기</h2>
            <p className={styles.linkCardSub}>Spotify 플레이리스트 링크를 붙여넣으면<br />모든 곡의 감정을 분류해 드려요</p>

            <form className={styles.linkForm} onSubmit={(e) => { e.preventDefault(); handlePreview(url) }}>
              <input className={styles.linkInput} placeholder="https://open.spotify.com/playlist/..." value={url} onChange={(e) => setUrl(e.target.value)} disabled={previewLoading} />
              <button className={styles.linkBtn} type="submit" disabled={previewLoading || !url.trim()}>
                {previewLoading ? <LoadingSpinner size="sm" /> : '미리보기'}
              </button>
            </form>

            {error && <p className={styles.linkError}>{error}</p>}

            {auth?.logged_in && (
              <div className={styles.myListsWrap}>
                <button className={styles.myListsToggle} onClick={() => setShowMyLists((v) => !v)} disabled={playlistsLoading}>
                  <Music size={12} />
                  {playlistsLoading ? '불러오는 중...' : '내 플레이리스트에서 선택'}
                  {showMyLists ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                </button>
                <AnimatePresence>
                  {showMyLists && (
                    <motion.ul className={styles.myListsList} initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}>
                      {myPlaylists.map((pl) => (
                        <li key={pl.id}>
                          <button className={styles.myListItem} onClick={() => { const u = `https://open.spotify.com/playlist/${pl.id}`; setUrl(u); handlePreview(u) }}>
                            {pl.image ? <img src={pl.image} className={styles.plThumb} alt="" /> : <div className={styles.plThumbPlaceholder} />}
                            <span className={styles.plName}>{pl.name}</span>
                            <span className={styles.plCount}>{pl.total}곡</span>
                            {!pl.public && <span className={styles.plPrivate}>비공개</span>}
                          </button>
                        </li>
                      ))}
                    </motion.ul>
                  )}
                </AnimatePresence>
              </div>
            )}

            {!auth?.logged_in && (
              <p className={styles.loginHint}>Spotify에 로그인하면 비공개 플레이리스트도 가져올 수 있어요</p>
            )}
          </motion.div>
        </div>
      )}

      {/* ── 트랙 미리보기 ─────────────────────────────────── */}
      {phase === 'preview' && (
        <div className={styles.inputPhase}>
          <motion.div className={styles.linkCard} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}>
            <div className={styles.previewHeader}>
              <div>
                <p className={styles.previewName}>{playlistName}</p>
                <p className={styles.previewMeta}>{tracks.length}곡</p>
              </div>
              <button className={styles.modalClose} onClick={resetAll}><X size={16} /></button>
            </div>
            <label className={styles.checkRow}>
              <input type="checkbox" className={styles.checkbox} checked={selected.size === tracks.length} onChange={toggleAll} />
              <span className={styles.checkLabel}>전체 선택 ({selected.size}/{tracks.length})</span>
            </label>
            <ul className={styles.trackCheckList}>
              {tracks.map((t) => (
                <li key={t.id}>
                  <label className={styles.checkRow}>
                    <input type="checkbox" className={styles.checkbox} checked={selected.has(t.id)} onChange={() => toggleOne(t.id)} />
                    <div className={styles.checkInfo}>
                      <span className={styles.checkTitle}>{t.title}</span>
                      <span className={styles.checkArtist}>{t.artist}</span>
                    </div>
                  </label>
                </li>
              ))}
            </ul>
            <div className={styles.previewActions}>
              <button className={styles.backBtn} onClick={resetAll}>← 다시</button>
              <button className={styles.importBtn} onClick={handleImport} disabled={selected.size === 0}>{selected.size}곡 분류하기</button>
            </div>
          </motion.div>
        </div>
      )}

      {/* ── 분류 진행 중 ─────────────────────────────────── */}
      {phase === 'importing' && (
        <div className={styles.inputPhase}>
          <motion.div className={styles.linkCard} initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            <div className={styles.progressWrap}>
              <LoadingSpinner size="md" />
              <p className={styles.progressText}>{progress.done} / {progress.total}곡 분류 중</p>
              {progress.current && <p className={styles.progressCurrent}>{progress.current}</p>}
              <div className={styles.progressTrack}>
                <div className={styles.progressFill} style={{ width: `${progress.total ? (progress.done / progress.total) * 100 : 0}%` }} />
              </div>
            </div>
          </motion.div>
        </div>
      )}

      {/* ── 결과: 카테고리별 그룹 ─────────────────────────── */}
      {phase === 'results' && (
        <motion.div className={styles.resultsPhase} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
          <div className={styles.resultsHeader}>
            <div>
              <h2 className={styles.resultsTitle}>{playlistName || '분류 결과'}</h2>
              <p className={styles.resultsMeta}>{results.length}곡 · {groups.length}개 카테고리</p>
            </div>
          </div>

          <div className={styles.groupsList}>
            {groups.map((group) => (
              <div key={group.category} className={styles.groupCard}>
                <div className={styles.groupHeader}>
                  <div className={styles.groupHeaderLeft}>
                    <CategoryBadge category={group.category as Category} size="md" />
                    <span className={styles.groupCount}>{group.songs.length}곡</span>
                  </div>
                  <button
                    className={styles.groupSaveBtn}
                    onClick={() => setSaveTarget(group)}
                  >
                    <ExternalLink size={12} /> Spotify에 저장
                  </button>
                </div>

                <div className={styles.groupSongs}>
                  {group.songs.map((song, i) => (
                    <a
                      key={song.spotify_id}
                      className={styles.resultRow}
                      href={`/song/${song.spotify_id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <span className={styles.resultNum}>{i + 1}</span>
                      <AlbumArt artist={song.artist} category={song.category} imageUrl={song.album_art_url} shape="rounded" size={40} />
                      <div className={styles.resultInfo}>
                        <span className={styles.resultTitle}>{song.title}</span>
                        <span className={styles.resultArtist}>{song.artist}</span>
                        {song.narrative && <span className={styles.resultNarrative}>{song.narrative}</span>}
                      </div>
                      {song.confidence != null && (
                        <span className={styles.resultConf}>{Math.round(song.confidence * 100)}%</span>
                      )}
                    </a>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {/* ── Save 모달 ────────────────────────────────────── */}
      <AnimatePresence>
        {saveTarget && (
          <SaveModal
            songs={saveTarget.songs}
            category={saveTarget.category}
            myPlaylists={myPlaylists}
            onClose={() => setSaveTarget(null)}
          />
        )}
      </AnimatePresence>
    </div>
  )
}
