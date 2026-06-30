import React, { useEffect, useRef } from 'react'
import { createChart, CandlestickSeries } from 'lightweight-charts'

export default function KLineChart({ data, height = 360 }) {
  const chartContainerRef = useRef(null)

  useEffect(() => {
    if (!chartContainerRef.current || !data?.length) return

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { color: '#0f172a' },
        textColor: '#94a3b8',
      },
      grid: {
        vertLines: { color: '#1e293b' },
        horzLines: { color: '#1e293b' },
      },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor: '#1e293b' },
      timeScale: { borderColor: '#1e293b' },
      height,
    })

    const series = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#f43f5e',
      borderUpColor: '#10b981',
      borderDownColor: '#f43f5e',
      wickUpColor: '#10b981',
      wickDownColor: '#f43f5e',
    })

    const normalizeDate = (d) => {
      if (!d) return null
      const s = typeof d === 'string' ? d : new Date(d).toISOString().slice(0, 10)
      return s.replace(/\//g, '-')
    }

    const sorted = [...data]
      .map((d) => ({
        ...d,
        date: normalizeDate(d.date),
      }))
      .filter((d) => d.date != null && d.open != null && d.high != null && d.low != null && d.close != null)
      .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())

    try {
      series.setData(
        sorted.map((d) => ({
          time: d.date,
          open: Number(d.open),
          high: Number(d.high),
          low: Number(d.low),
          close: Number(d.close),
        })),
      )
      chart.timeScale().fitContent()
    } catch (err) {
      console.error('[KLineChart] setData failed:', err)
    }

    const handleResize = () => {
      chart.applyOptions({ width: chartContainerRef.current.clientWidth })
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
    }
  }, [data, height])

  if (!data?.length) return null

  return <div ref={chartContainerRef} className="w-full" style={{ height }} />
}
