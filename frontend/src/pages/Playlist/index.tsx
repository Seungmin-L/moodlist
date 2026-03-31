import { useEffect, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronDown, ChevronUp, ExternalLink, Plus, Music, LogIn, Check } from 'lucide-react'
import { getPlaylistGroups } from '../../api/playlist'
import { exportPlaylist, getSpotifyAuth, getSpotifyLoginUrl, getMyPlaylists, previewPlaylist } from '../../api/spotify'
import { addSong } from '../../api/songs'
import type { PlaylistGroup, SpotifyAuthStatus, SpotifyMyPlaylist, SpotifyPreviewTrack } from '../../types'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import CategoryBadge from '../../components/common/CategoryBadge'
import FadeInSection from '../../components/common/FadeInSection'
import styles from './Playlist.module.css'

type Tab = 'analyze' | 'mygroups'
type ImportStep = 'input' | 'preview' | 'importing' | 'done'

export default function Playlist() {
  const [tab, setTab] = useState<Tab>('analyze')
  const [groups, setGroups] = useState<PlaylistGroup[]>([])
  const [groupsLoading, setGroupsLoading] = useState(true)

  const [auth, setAuth] = useState<SpotifyAuthStatus | null>(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [myPlaylists, setMyPlaylists] = useState<SpotifyMyPlaylist[]>([])
  const [playlistsLoading, setPlaylistsLoading] = useState(false)
  const [showMyPlaylists, setShowMyPlaylists] = useState(false)

  // Import 흐름
  const [importUrl, setImportUrl] = useState('')
  const [step, setStep] = useState<ImportStep>('input')
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewName, setPreviewName] = useState('')
  const [tracks, setTracks] = useState<SpotifyPreviewTrack[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [importProgress, setImportProgress] = useState({ done: 0, total: 0, current: '' })
  const [importError, setImportError] = useState<string | null>(null)
  const [analyzedGroups, setAnalyzedGroups] = useState<PlaylistGroup[]>([])

  const fetchAuth = useCallback(async () => {
    setAuthLoading(true)
    try {
      const status = await getSpotifyAuth()
      setAuth(status)
      if (status.logged_in) {
        setPlaylistsLoading(true)
        const lists = await getMyPlaylists()
        setMyPlaylists(lists)
        setPlaylistsLoading(false)
      }
    } catch {
      setAuth({ logged_in: false })
    } finally {
      setAuthLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchAuth()
    getPlaylistGroups().then((r) => setGroups(r.groups)).catch(() => {}).finally(() => setGroupsLoading(false))
  }, [fetchAuth])

  const handleLogin = async () => {
    const url = await getSpotifyLoginUrl()
    const popup = window.open(url, 'spotify-login', 'width=480,height=680')
    const timer = setInterval(() => {
      if (popup?.closed) {
        clearInterval(timer)
        fetchAuth()
      }
    }, 800)
  }

  // 1단계: 트랙 목록 미리보기
  const handlePreview = async (url: string) => {
    const target = url || importUrl
    if (!target.trim()) return
    setImportError(null)
    setPreviewLoading(true)
    setShowMyPlaylists(false)
    try {
      const data = await previewPlaylist(target.trim())
      setPreviewName(data.playlist.name)
      setTracks(data.tracks)
      setSelected(new Set(data.tracks.map((t) => t.id)))
      setStep('preview')
    } catch (err) {
      setImportError(err instanceof Error ? err.message : '플레이리스트 조회 실패')
    } finally {
      setPreviewLoading(false)
    }
  }

  const toggleAll = () => {
    if (selected.size === tracks.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(tracks.map((t) => t.id)))
    }
  }

  const toggleOne = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  // 2단계: 선택한 곡 순차 분류
  const handleImport = async () => {
    const toImport = tracks.filter((t) => selected.has(t.id))
    if (!toImport.length) return
    setStep('importing')
    setImportProgress({ done: 0, total: toImport.length, current: '' })
    setAnalyzedGroups([])

    for (let i = 0; i < toImport.length; i++) {
      const t = toImport[i]
      setImportProgress({ done: i, total: toImport.length, current: `${t.title} - ${t.artist}` })
      try {
        await addSong({ title: t.title, artist: t.artist, spotify_id: t.id })
      } catch {
        // 실패한 곡은 스킵
      }
    }

    setImportProgress({ done: toImport.length, total: toImport.length, current: '' })
    const updated = await getPlaylistGroups()
    setAnalyzedGroups(updated.groups ?? [])
    setStep('done')
  }

  const handleReset = () => {
    setStep('input')
    setTracks([])
    setSelected(new Set())
    setImportUrl('')
    setImportError(null)
  }

  const displayGroups = tab === 'analyze' ? analyzedGroups : groups

  return (
    <div className={styles.page}>
      <FadeInSection>
        <h1 className={styles.pageTitle}>Playlist</h1>
      </FadeInSection>

      <FadeInSection delay={0.05}>
        <div className={styles.tabs}>
          {(['analyze', 'mygroups'] as Tab[]).map((t) => (
            <button
              key={t}
              className={`${styles.tab} ${tab === t ? styles.active : ''}`}
              onClick={() => setTab(t)}
            >
              {t === 'analyze' ? '플레이리스트 분석' : '나의 무드 그룹'}
            </button>
          ))}
        </div>
      </FadeInSection>

      {/* Spotify 로그인 배너 */}
      <FadeInSection delay={0.08}>
        <div className={styles.authBanner}>
          {authLoading ? (
            <LoadingSpinner size="sm" />
          ) : auth?.logged_in ? (
            <div className={styles.authLoggedIn}>
              <Check size={14} className={styles.authCheck} />
              <span>{auth.user}로 로그인됨</span>
              <span className={styles.authSub}>· 비공개 플레이리스트 접근 가능</span>
            </div>
          ) : (
            <div className={styles.authLoggedOut}>
              <span className={styles.authSub}>비공개 플레이리스트를 가져오려면</span>
              <button className={styles.loginBtn} onClick={handleLogin}>
                <LogIn size={13} />
                Spotify 로그인
              </button>
            </div>
          )}
        </div>
      </FadeInSection>

      {tab === 'analyze' && (
        <FadeInSection delay={0.1}>
          {/* Step 1: URL 입력 */}
          {step === 'input' && (
            <form className={styles.importForm} onSubmit={(e) => { e.preventDefault(); handlePreview(importUrl) }}>
              <p className={styles.importDesc}>
                Spotify 플레이리스트 URL을 입력하면 곡 목록을 불러옵니다
              </p>
              <div className={styles.importRow}>
                <input
                  className={styles.importInput}
                  type="text"
                  placeholder="https://open.spotify.com/playlist/..."
                  value={importUrl}
                  onChange={(e) => setImportUrl(e.target.value)}
                  disabled={previewLoading}
                />
                <button className={styles.importBtn} type="submit" disabled={previewLoading || !importUrl.trim()}>
                  {previewLoading ? <LoadingSpinner size="sm" /> : '미리보기'}
                </button>
              </div>

              {/* 내 플레이리스트 선택 */}
              {auth?.logged_in && (
                <div className={styles.myPlaylistsWrap}>
                  <button
                    type="button"
                    className={styles.myPlaylistsToggle}
                    onClick={() => setShowMyPlaylists((v) => !v)}
                    disabled={playlistsLoading}
                  >
                    <Music size={13} />
                    {playlistsLoading ? '불러오는 중...' : '내 플레이리스트에서 선택'}
                    {showMyPlaylists ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                  </button>

                  <AnimatePresence>
                    {showMyPlaylists && (
                      <motion.ul
                        className={styles.myPlaylistsList}
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                      >
                        {myPlaylists.map((pl) => (
                          <li key={pl.id}>
                            <button
                              type="button"
                              className={styles.myPlaylistItem}
                              onClick={() => {
                                const url = `https://open.spotify.com/playlist/${pl.id}`
                                setImportUrl(url)
                                handlePreview(url)
                              }}
                            >
                              {pl.image
                                ? <img src={pl.image} className={styles.plThumb} alt="" />
                                : <div className={styles.plThumbPlaceholder} />
                              }
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
            </form>
          )}

          {/* Step 2: 트랙 선택 */}
          {step === 'preview' && (
            <div className={styles.importForm}>
              <div className={styles.previewHeader}>
                <div>
                  <p className={styles.previewTitle}>{previewName}</p>
                  <p className={styles.importDesc}>{tracks.length}곡 · 분류할 곡을 선택하세요</p>
                </div>
                <button className={styles.resetBtn} onClick={handleReset}>다시 선택</button>
              </div>

              <div className={styles.selectAllRow}>
                <label className={styles.checkRow}>
                  <input
                    type="checkbox"
                    className={styles.checkbox}
                    checked={selected.size === tracks.length}
                    onChange={toggleAll}
                  />
                  <span className={styles.checkLabel}>전체 선택 ({selected.size}/{tracks.length})</span>
                </label>
              </div>

              <ul className={styles.trackList}>
                {tracks.map((t) => (
                  <li key={t.id}>
                    <label className={styles.checkRow}>
                      <input
                        type="checkbox"
                        className={styles.checkbox}
                        checked={selected.has(t.id)}
                        onChange={() => toggleOne(t.id)}
                      />
                      <div className={styles.trackInfo}>
                        <span className={styles.trackTitle}>{t.title}</span>
                        <span className={styles.trackArtist}>{t.artist}</span>
                      </div>
                    </label>
                  </li>
                ))}
              </ul>

              <button
                className={styles.importBtn}
                onClick={handleImport}
                disabled={selected.size === 0}
              >
                선택한 곡 분류하기 ({selected.size}곡)
              </button>
            </div>
          )}

          {/* Step 3: 분류 중 */}
          {step === 'importing' && (
            <div className={styles.importForm}>
              <div className={styles.progressWrap}>
                <LoadingSpinner size="md" />
                <p className={styles.progressText}>
                  {importProgress.done} / {importProgress.total}곡 분류 중
                </p>
                {importProgress.current && (
                  <p className={styles.progressCurrent}>{importProgress.current}</p>
                )}
                <div className={styles.progressTrack}>
                  <div
                    className={styles.progressFill}
                    style={{ width: `${(importProgress.done / importProgress.total) * 100}%` }}
                  />
                </div>
              </div>
            </div>
          )}

          {/* Step 4: 완료 */}
          {step === 'done' && (
            <div className={styles.importSummary}>
              <strong>분류 완료!</strong> {importProgress.total}곡 처리됨
              <button className={styles.resetBtn} onClick={handleReset} style={{ marginLeft: 'auto' }}>
                새로 가져오기
              </button>
            </div>
          )}

          {importError && <div className={styles.error}>{importError}</div>}
        </FadeInSection>
      )}

      {tab === 'mygroups' && groupsLoading && <LoadingSpinner size="md" />}

      {displayGroups.length > 0 && (
        <div className={styles.groups}>
          {displayGroups.map((group, i) => (
            <FadeInSection key={`${group.mood}-${i}`} delay={i * 0.05}>
              <GroupCard group={group} />
            </FadeInSection>
          ))}
        </div>
      )}

      {!groupsLoading && tab === 'mygroups' && groups.length === 0 && (
        <p className={styles.empty}>분류된 곡이 없습니다. 먼저 곡을 추가해보세요.</p>
      )}
    </div>
  )
}

function GroupCard({ group }: { group: PlaylistGroup }) {
  const [open, setOpen] = useState(false)
  const [showExport, setShowExport] = useState(false)
  const [playlistName, setPlaylistName] = useState(`Moodlist - ${group.mood}`)
  const [exporting, setExporting] = useState(false)
  const [exportUrl, setExportUrl] = useState<string | null>(null)

  const handleExport = async () => {
    setExporting(true)
    try {
      const result = await exportPlaylist({ mood: group.mood, playlist_name: playlistName })
      setExportUrl(result.playlist_url)
      setShowExport(false)
    } catch {
      // Spotify OAuth 필요
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className={styles.groupCard}>
      <button className={styles.groupHeader} onClick={() => setOpen((v) => !v)}>
        <div className={styles.groupHeaderLeft}>
          {group.category && <CategoryBadge category={group.category} size="sm" />}
          <span className={styles.groupMood}>"{group.mood}"</span>
          <span className={styles.groupCount}>{group.songs.length}곡</span>
        </div>
        {open ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className={styles.groupBody}
          >
            <div className={styles.songList}>
              {group.songs.slice(0, 5).map((s) => (
                <div key={s.spotify_id} className={styles.songRow}>
                  <div className={styles.songInfo}>
                    <span className={styles.songTitle}>{s.title}</span>
                    <span className={styles.songArtist}>{s.artist}</span>
                  </div>
                  <a
                    href={`https://open.spotify.com/track/${s.spotify_id}`}
                    target="_blank" rel="noopener noreferrer"
                    className={styles.songSpotify}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <ExternalLink size={13} />
                  </a>
                </div>
              ))}
              {group.songs.length > 5 && (
                <p className={styles.moreCount}>+{group.songs.length - 5}곡 더</p>
              )}
            </div>

            <div className={styles.exportArea}>
              {exportUrl ? (
                <a href={exportUrl} target="_blank" rel="noopener noreferrer" className={styles.exportLink}>
                  <ExternalLink size={14} /> Spotify에서 보기
                </a>
              ) : showExport ? (
                <div className={styles.exportForm}>
                  <input
                    className={styles.exportInput}
                    value={playlistName}
                    onChange={(e) => setPlaylistName(e.target.value)}
                    placeholder="플레이리스트 이름"
                  />
                  <button className={styles.exportConfirm} onClick={handleExport} disabled={exporting}>
                    {exporting ? '만드는 중...' : '만들기'}
                  </button>
                  <button className={styles.exportCancel} onClick={() => setShowExport(false)}>취소</button>
                </div>
              ) : (
                <button className={styles.exportBtn} onClick={() => setShowExport(true)}>
                  <Plus size={14} /> 새 플레이리스트 만들기
                </button>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
