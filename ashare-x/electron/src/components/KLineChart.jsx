import React, { useEffect, useRef } from 'react'
import { createChart } from 'lightweight-charts'

export default function KLineChart({ data, height = 360 }) {
  const chartContainerRef = useRef(null)
  const chartRef = useRef(null)

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
    chartRef.current = chart

    const series = chart.addCandlestickSeries({
      upColor: '#10b981',
      downColor: '#f43f5e',
      borderUpColor: '#10b981',
      borderDownColor: '#f43f5e',
      wickUpColor: '#10b981',
      wickDownColor: '#f43f5e',
    })

    const sorted = [...data]
      .filter((d) => d.date && d.open && d.high && d.low && d.close)
      .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())

    series.setData(
      sorted.map((d) => ({
        time: d.date.replace(/-/g, '/'),
        open: Number(d.open),
        high: Number(d.high),
        low: Number(d.low),
        close: Number(d.close),
      })),
    )

    chart.timeScale().fitContent()

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
