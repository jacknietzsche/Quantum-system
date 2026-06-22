import { get, post, del } from './request'

export const tasksApi = {
  list: (params?: any) => get('/api/tasks', params),
  getById: (id: string) => get(`/api/tasks/${id}`),
  cancel: (id: string) => post(`/api/tasks/${id}/cancel`),
  delete: (id: string) => del(`/api/tasks/${id}`),
  getQueue: () => get('/api/tasks/queue'),
}
