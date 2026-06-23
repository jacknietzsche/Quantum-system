export function isValidStockCode(code) {
  if (!code || typeof code !== 'string') return false
  const trimmed = code.trim()
  if (!/^\d{6}$/.test(trimmed)) return false
  // 沪市: 600/601/603/605/688, 深市: 000/001/002/003/300/301
  const prefixes = ['600', '601', '603', '605', '688', '000', '001', '002', '003', '300', '301']
  return prefixes.some((p) => trimmed.startsWith(p))
}

export function normalizeStockCode(code) {
  return (code || '').trim()
}

export function validateStockCode(code) {
  const normalized = normalizeStockCode(code)
  if (!normalized) return '请输入股票代码'
  if (!/^\d{6}$/.test(normalized)) return '股票代码应为 6 位数字'
  if (!isValidStockCode(normalized)) return '不支持的股票代码'
  return ''
}

export function validatePositiveNumber(value, label = '数值') {
  const num = Number(value)
  if (value === '' || value === null || value === undefined || Number.isNaN(num)) {
    return `${label}必须是数字`
  }
  if (num <= 0) return `${label}必须大于 0`
  return ''
}
