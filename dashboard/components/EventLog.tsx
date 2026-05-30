'use client'
import { useEffect, useRef } from 'react'
import { useSimStore } from '../sim/state'

export default function EventLog() {
  const log = useSimStore(s => s.log)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [log.length])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <div style={{ padding: '8px 12px', borderBottom: '1px solid #1a1b1e', flexShrink: 0 }}>
        <span style={{ fontSize: '10px', letterSpacing: '0.1em', textTransform: 'uppercase', color: '#3a3b3e' }}>
          EVENT LOG
        </span>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '4px 0' }}>
        {log.map((entry, i) => (
          <div
            key={i}
            style={{
              fontSize: '11px',
              padding: '3px 12px',
              borderBottom: '1px solid #1a1b1e',
              color: entry.level === 'kill'
                ? '#7a3a3a'
                : entry.level === 'alert' || entry.level === 'warn'
                ? '#7a6a3a'
                : '#5a5b5e',
              fontFamily: 'inherit',
            }}
          >
            <span style={{ color: '#3a3b3e', marginRight: '8px' }}>{entry.time}</span>
            {entry.text}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
