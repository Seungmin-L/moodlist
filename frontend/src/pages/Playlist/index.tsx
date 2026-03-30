import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronDown, ChevronUp, ExternalLink, Plus } from 'lucide-react'
import { getPlaylistGroups } from '../../api/playlist'
import { importPlaylist, exportPlaylist } from '../../api/spotify'
import type { PlaylistGroup, SpotifyImportResult } from '../../types'
import LoadingSpinner from '../../components/common/LoadingSpinner'
import CategoryBadge from '../../components/common/CategoryBadge'
import FadeInSection from '../../components/common/FadeInSection'
import styles from './Playlist.module.css'

type Tab = 'analyze' | 'mygroups'

export default function Playlist() {
  const [tab, setTab] = useState<Tab>('analyze')
  const [groups, setGroups] = useState<PlaylistGroup[]>([])
  const [groupsLoading, setGroupsLoading] = useState(true)
  const [importUrl, setImportUrl] = useState('')
  const [importLoading, setImportLoading] = useState(false)
  const [importResult, setImportResult] = useState<SpotifyImportResult | null>(null)
  const [importError, setImportError] = useState<string | null>(null)
  const [analyzedGroups, setAnalyzedGroups] = useState<PlaylistGroup[]>([])

  useEffect(() => {
    getPlaylistGroups().then((r) => setGroups(r.groups)).catch(() => {}).finally(() => setGroupsLoading(false))
  }, [])

  const handleImport = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!importUrl.trim()) return
    setImportLoading(true)
    setImportError(null)
    setImportResult(null)
    setAnalyzedGroups([])
    try {
      const result = await importPlaylist(importUrl.trim())
      setImportResult(result)
      const updated = await getPlaylistGroups()
      setAnalyzedGroups(updated.groups ?? [])
    } catch (err) {
      setImportError(err instanceof Error ? err.message : '가져오기 실패')
    } finally {
      setImportLoading(false)
    }
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

      {tab === 'analyze' && (
        <FadeInSection delay={0.1}>
          <form className={styles.importForm} onSubmit={handleImport}>
            <p className={styles.importDesc}>
              Spotify 플레이리스트 URL을 입력하면 mood/category 기준으로 재분류해 드립니다
            </p>
            <div className={styles.importRow}>
              <input
                className={styles.importInput}
                type="text"
                placeholder="https://open.spotify.com/playlist/..."
                value={importUrl}
                onChange={(e) => setImportUrl(e.target.value)}
                disabled={importLoading}
              />
              <button className={styles.importBtn} type="submit" disabled={importLoading || !importUrl.trim()}>
                {importLoading ? <LoadingSpinner size="sm" /> : '불러오기'}
              </button>
            </div>
            {importLoading && (
              <p className={styles.importHint}>플레이리스트를 분석 중입니다... 곡 수에 따라 시간이 걸릴 수 있어요</p>
            )}
          </form>

          {importError && <div className={styles.error}>{importError}</div>}

          {importResult && (
            <div className={styles.importSummary}>
              <strong>{importResult.playlist.name}</strong> —
              성공 {importResult.processed}곡 / 실패 {importResult.failed}곡
            </div>
          )}
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
      // 에러 표시 생략 (Spotify OAuth 필요)
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
