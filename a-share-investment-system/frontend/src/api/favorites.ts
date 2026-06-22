import { get, post, del } from './request'

export const favoritesApi = {
  list: () => get('/api/favorites'),
  add: (data: { stock_code: string; stock_name?: string }) => post('/api/favorites', data),
  remove: (code: string) => del(`/api/favorites/${code}`),
  check: (code: string) => get(`/api/favorites/${code}`),
}
