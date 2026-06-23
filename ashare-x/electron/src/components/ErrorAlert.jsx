import React from 'react'

export default function ErrorAlert({ message, onClose }) {
  if (!message) return null
  return (
    <div className="bg-rose-900/20 border border-rose-800 rounded-xl p-4 mb-5 text-sm text-rose-200 flex items-start justify-between gap-3">
      <span>{message}</span>
      {onClose && (
        <button
          onClick={onClose}
          className="text-rose-300 hover:text-rose-100 shrink-0"
          aria-label="关闭"
        >
          ✕
        </button>
      )}
    </div>
  )
}
