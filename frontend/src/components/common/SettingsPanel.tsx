import { useState, useEffect, useRef } from 'react'
import { Settings, LogIn, LogOut, Check } from 'lucide-react'
import { getSpotifyAuth, getSpotifyLoginUrl, disconnectSpotify } from '../../api/spotify'
import type { SpotifyAuthStatus } from '../../types/playlist'
import styles from './SettingsPanel.module.css'

export default function SettingsPanel() {
  const [open, setOpen] = useState(false)
  const [auth, setAuth] = useState<SpotifyAuthStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)

  const fetchAuth = async () => {
    try {
      const status = await getSpotifyAuth()
      setAuth(status)
    } catch {
      setAuth({ logged_in: false })
    }
  }

  useEffect(() => {
    if (open && auth === null) fetchAuth()
  }, [open])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

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

  const handleDisconnect = async () => {
    setLoading(true)
    try {
      await disconnectSpotify()
      setAuth({ logged_in: false })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.wrap} ref={panelRef}>
      <button
        className={styles.btn}
        onClick={() => setOpen((v) => !v)}
        aria-label="설정"
      >
        <Settings size={16} />
      </button>

      {open && (
        <div className={styles.panel}>
          <p className={styles.sectionLabel}>Spotify 연동</p>

          {auth === null ? (
            <p className={styles.loading}>확인 중...</p>
          ) : auth.logged_in ? (
            <div className={styles.connectedRow}>
              <div className={styles.connectedInfo}>
                <Check size={13} className={styles.checkIcon} />
                <span className={styles.username}>{auth.user}</span>
              </div>
              <button
                className={styles.disconnectBtn}
                onClick={handleDisconnect}
                disabled={loading}
              >
                <LogOut size={12} />
                연동 해제
              </button>
            </div>
          ) : (
            <div className={styles.disconnectedRow}>
              <span className={styles.notConnected}>연동 안 됨</span>
              <button className={styles.loginBtn} onClick={handleLogin}>
                <LogIn size={12} />
                로그인
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
