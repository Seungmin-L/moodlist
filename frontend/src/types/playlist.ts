export interface PlaylistGroupSong {
  spotify_id: string
  title: string
  artist: string
  mood: string | null
  category: string | null
  similarity: number
}

export interface PlaylistGroup {
  mood: string
  category: string
  songs: PlaylistGroupSong[]
}

export interface PlaylistGroupsResponse {
  groups: PlaylistGroup[]
}

export interface SpotifyImportTrackResult {
  title: string
  artist: string
  status: 'ok' | 'error'
  already_exists?: boolean
  spotify_id?: string
  mood?: string
  category?: string
  error?: string
}

export interface SpotifyImportResult {
  playlist: { name: string; total: number }
  processed: number
  failed: number
  results: SpotifyImportTrackResult[]
}

export interface SpotifyAuthStatus {
  logged_in: boolean
  user?: string
  error?: string
}

export interface SpotifyExportResult {
  playlist_url: string
  added: number
}

export interface SpotifyPreviewTrack {
  id: string
  uri: string
  title: string
  artist: string
  album: string
}

export interface SpotifyMyPlaylist {
  id: string
  name: string
  total: number
  public: boolean
  image: string | null
}
