import { lazy, Suspense } from 'react'
import { Routes, Route } from 'react-router-dom'
import Layout from './components/layout/Layout'
import LoadingSpinner from './components/common/LoadingSpinner'

const Home = lazy(() => import('./pages/Home'))
const SongDetail = lazy(() => import('./pages/SongDetail'))
const Browse = lazy(() => import('./pages/Browse'))
const Playlist = lazy(() => import('./pages/Playlist'))

export default function App() {
  return (
    <Layout>
      <Suspense fallback={<LoadingSpinner size="lg" />}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/song/:spotify_id" element={<SongDetail />} />
          <Route path="/browse" element={<Browse />} />
          <Route path="/playlist" element={<Playlist />} />
        </Routes>
      </Suspense>
    </Layout>
  )
}
