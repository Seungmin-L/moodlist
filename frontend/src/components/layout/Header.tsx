import { useState, useEffect } from 'react'
import { NavLink } from 'react-router-dom'
import { Music2, Menu, X } from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import { getSpotifyAuth } from '../../api/spotify'
import SettingsPanel from '../common/SettingsPanel'
import styles from './Header.module.css'

const NAV_LINKS = [
  { to: '/browse', label: 'Browse' },
  { to: '/playlist', label: 'Playlist' },
]

export default function Header() {
  const [menuOpen, setMenuOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const [spotifyConnected, setSpotifyConnected] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  useEffect(() => {
    getSpotifyAuth().then((s) => setSpotifyConnected(s.logged_in)).catch(() => {})
  }, [])

  return (
    <>
      <header className={`${styles.header} ${scrolled ? styles.scrolled : ''}`}>
        <div className={styles.inner}>
          <NavLink to="/" className={styles.logo}>
            <Music2 size={18} />
            <span>Moodlist</span>
          </NavLink>

          <nav className={styles.nav}>
            {NAV_LINKS.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) => `${styles.navLink} ${isActive ? styles.active : ''}`}
              >
                {label}
              </NavLink>
            ))}
          </nav>

          <div className={styles.actions}>
            {spotifyConnected && <span className={styles.spotifyDot} title="Spotify 연결됨" />}
            <SettingsPanel />
            <button className={styles.hamburger} onClick={() => setMenuOpen((v) => !v)} aria-label="메뉴 열기">
              {menuOpen ? <X size={18} /> : <Menu size={18} />}
            </button>
          </div>
        </div>
      </header>

      <AnimatePresence>
        {menuOpen && (
          <>
            <motion.div className={styles.backdrop} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setMenuOpen(false)} />
            <motion.nav
              className={styles.mobileMenu}
              initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
              transition={{ type: 'spring', damping: 28, stiffness: 300 }}
            >
              {NAV_LINKS.map(({ to, label }) => (
                <NavLink key={to} to={to}
                  className={({ isActive }) => `${styles.mobileLink} ${isActive ? styles.active : ''}`}
                  onClick={() => setMenuOpen(false)}
                >
                  {label}
                </NavLink>
              ))}
            </motion.nav>
          </>
        )}
      </AnimatePresence>
    </>
  )
}
