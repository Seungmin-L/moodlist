import client from './client'
import type { PlaylistGroupsResponse } from '../types/playlist'

export const getPlaylistGroups = (top_k = 20) =>
  client.get<PlaylistGroupsResponse>('/playlist/groups', { params: { top_k } }).then((r) => r.data)
