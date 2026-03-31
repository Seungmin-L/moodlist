import client from './client'
import type { SpotifyImportResult, SpotifyAuthStatus, SpotifyExportResult, SpotifyMyPlaylist, SpotifyPreviewTrack } from '../types/playlist'

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

export const getSpotifyLoginUrl = () =>
  client.get<{ auth_url: string }>('/spotify/login').then((r) => r.data.auth_url)

export const getMyPlaylists = () =>
  client.get<SpotifyMyPlaylist[]>('/spotify/me/playlists').then((r) => r.data)

export const previewPlaylist = (playlist_url: string) =>
  client.get<{ playlist: { name: string; total: number }; tracks: SpotifyPreviewTrack[] }>(
    '/spotify/preview', { params: { playlist_url } }
  ).then((r) => r.data)
