export type SongStatus = 'pending' | 'classified' | 'error'

export type Category =
  | '관심' | '짝사랑' | '썸' | '사랑'
  | '권태기' | '갈등' | '이별'
  | '자기자신' | '일상' | '기타'

export type Emotions = Record<string, number>

export interface Song {
  spotify_id: string
  title: string
  artist: string
  category: Category | null
  mood: string | null
  emotions: Emotions | null
  primary_emotion: string | null
  emotional_arc: string | null
  tags: string[] | null
  narrative: string | null
  confidence: number | null
  status: SongStatus
  classified_at: string | null
}

export interface SongDetail extends Song {
  lyrics: string | null
  source_url: string | null
  error_message: string | null
  created_at: string
}

export interface SimilarSong {
  spotify_id: string
  title: string
  artist: string
  mood: string | null
  category: Category | null
  similarity: number
}

export interface SimilarSongsResponse {
  base_song: Pick<Song, 'spotify_id' | 'title' | 'artist' | 'mood'>
  similar: SimilarSong[]
}
