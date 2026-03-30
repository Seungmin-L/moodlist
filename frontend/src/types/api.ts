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
}

export interface AddSongResponse extends SongDetail {
  already_exists: boolean
}
