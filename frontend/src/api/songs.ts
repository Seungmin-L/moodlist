import client from './client'
import type { Song, SongDetail, SimilarSongsResponse } from '../types/song'
import type { AddSongRequest, AddSongResponse } from '../types/api'

export const addSong = (req: AddSongRequest) =>
  client.post<AddSongResponse>('/songs', req).then((r) => r.data)

export const getSongs = (category?: string) =>
  client.get<Song[]>('/songs', { params: category ? { category } : {} }).then((r) => r.data)

export const getSong = (spotify_id: string) =>
  client.get<SongDetail>(`/songs/${spotify_id}`).then((r) => r.data)

export const getSimilarSongs = (spotify_id: string, top_k = 10) =>
  client.get<SimilarSongsResponse>(`/songs/${spotify_id}/similar`, { params: { top_k } }).then((r) => r.data)

export const reclassifySong = (spotify_id: string) =>
  client.post<SongDetail>(`/songs/${spotify_id}/reclassify`).then((r) => r.data)
