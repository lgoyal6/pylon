'use client'
import { useEffect, useState } from 'react'

export default function TopBar() {
  const [time, setTime] = useState('')

  useEffect(() => {
    const update = () => {
      const d = new Date()
      setTime(
        `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')} UTC`
      )
    }
    update()
    const id = setInterval(update, 1000)
    return () => clearInterval(id)
  }, [])

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 16px',
        height: '36px',
        borderBottom: '1px solid #1a1b1e',
        background: '#0c0d0f',
        flexShrink: 0,
      }}
    >
      <span style={{ fontSize: '11px', letterSpacing: '0.15em', color: '#9a9b9e' }}>
        // LATTICE
      </span>
      <span style={{ fontSize: '11px', letterSpacing: '0.1em', color: '#5a5b5e' }}>
        {time}
      </span>
    </div>
  )
}
