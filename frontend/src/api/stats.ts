import client from './client'
import type { Stats } from '../types/api'

export const getStats = () =>
  client.get<Stats>('/stats').then((r) => r.data)

export const getCategories = () =>
  client.get<string[]>('/categories').then((r) => r.data)
