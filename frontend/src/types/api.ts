import type { SongDetail } from './song'

export interface ApiError {
  detail: string
}

export interface Stats {
  total: number
  status_distribution: Record<string, number>
  category_distribution: Record<string, number>
}

export interface AddSongRequest {
  title: string
  artist: string
  spotify_id?: string
  image_url?: string
}

export interface SearchSuggestion {
  spotify_id: string
  title: string
  artist: string
  image_url: string | null
}

export interface AddSongResponse extends SongDetail {
  already_exists: boolean
}
