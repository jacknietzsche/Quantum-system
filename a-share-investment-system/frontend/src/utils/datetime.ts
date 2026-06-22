import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-cn'

dayjs.extend(relativeTime)
dayjs.locale('zh-cn')

export function formatDateTime(time: string | Date, format = 'YYYY-MM-DD HH:mm:ss'): string {
  return dayjs(time).format(format)
}

export function formatDate(time: string | Date, format = 'YYYY-MM-DD'): string {
  return dayjs(time).format(format)
}

export function formatRelativeTime(time: string | Date): string {
  return dayjs(time).fromNow()
}

export function formatMoney(value: number): string {
  return value.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
}

export function formatPercent(value: number): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}
