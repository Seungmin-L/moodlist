import client from './client'
import type { SpotifyImportResult, SpotifyAuthStatus, SpotifyExportResult } from '../types/playlist'

export const importPlaylist = (playlist_url: string) =>
  client.post<SpotifyImportResult>('/spotify/import', { playlist_url }).then((r) => r.data)

export const exportPlaylist = (payload: {
  mood: string
  playlist_name: string
  description?: string
  public?: boolean
}) =>
  client.post<SpotifyExportResult>('/spotify/export', payload).then((r) => r.data)

export const getSpotifyAuth = () =>
  client.get<SpotifyAuthStatus>('/spotify/auth').then((r) => r.data)
