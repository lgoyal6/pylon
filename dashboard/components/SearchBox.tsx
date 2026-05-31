'use client'
import { useState } from 'react'
import { useSimStore } from '../sim/state'
import { MAPBOX_TOKEN } from '../data/config'

// Zoom level to fly to, by Mapbox place type.
const ZOOM_BY_TYPE: Record<string, number> = {
  country: 4,
  region: 6,
  district: 7,
  postcode: 10,
  place: 9,
  locality: 10,
  neighborhood: 12,
  address: 14,
  poi: 14,
}

export default function SearchBox() {
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const flyToLocation = useSimStore(s => s.flyToLocation)

  async function search(e: React.FormEvent) {
    e.preventDefault()
    const query = q.trim()
    if (!query || busy) return
    setBusy(true)
    setError('')
    try {
      const url = `https://api.mapbox.com/geocoding/v5/mapbox.places/${encodeURIComponent(query)}.json?limit=1&access_token=${MAPBOX_TOKEN}`
      const res = await fetch(url)
      const data = await res.json()
      const feat = data?.features?.[0]
      if (!feat) {
        setError('not found')
        return
      }
      const [lng, lat] = feat.center
      const type: string = feat.place_type?.[0] ?? 'place'
      flyToLocation(lng, lat, ZOOM_BY_TYPE[type] ?? 8)
    } catch {
      setError('search failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form
      onSubmit={search}
      style={{
        position: 'absolute',
        top: 12,
        left: '50%',
        transform: 'translateX(-50%)',
        zIndex: 5,
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
        background: '#0c0d0f',
        border: '1px solid #1a1b1e',
        padding: '5px 8px',
      }}
    >
      <span style={{ fontSize: '11px', color: '#3a3b3e' }}>⌕</span>
      <input
        value={q}
        onChange={e => { setQ(e.target.value); setError('') }}
        placeholder="Search location — e.g. Japan"
        spellCheck={false}
        style={{
          background: 'transparent',
          border: 'none',
          outline: 'none',
          color: '#9a9b9e',
          fontFamily: 'inherit',
          fontSize: '11px',
          width: '240px',
        }}
      />
      {error && <span style={{ fontSize: '10px', color: '#7a3a3a' }}>{error}</span>}
      <button
        type="submit"
        disabled={busy}
        style={{
          background: 'none',
          border: '1px solid #1a1b1e',
          color: busy ? '#3a3b3e' : '#9a9b9e',
          cursor: busy ? 'default' : 'pointer',
          fontFamily: 'inherit',
          fontSize: '10px',
          letterSpacing: '0.05em',
          padding: '3px 8px',
          textTransform: 'uppercase',
        }}
      >
        {busy ? '...' : 'Go'}
      </button>
    </form>
  )
}
