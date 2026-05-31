'use client'
import dynamic from 'next/dynamic'
import TopBar from '../components/TopBar'
import Controls from '../components/Controls'
import AssetRoster from '../components/AssetRoster'
import EventLog from '../components/EventLog'
import MeshStatus from '../components/MeshStatus'
import BottomDock from '../components/BottomDock'
import Legend from '../components/Legend'
import SelectionPanel from '../components/SelectionPanel'
import SearchBox from '../components/SearchBox'

const MapView = dynamic(() => import('../components/Map'), { ssr: false })

export default function Home() {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        background: '#08090a',
        overflow: 'hidden',
      }}
    >
      <TopBar />

      {/* Main content */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden', minHeight: 0 }}>
        {/* Map — 70% */}
        <div
          style={{
            flex: '0 0 70%',
            position: 'relative',
            borderRight: '1px solid #1a1b1e',
            background: '#08090a',
          }}
        >
          <MapView />
          <Legend />
          <SearchBox />
          <SelectionPanel />
        </div>

        {/* Right sidebar */}
        <div
          style={{
            flex: '0 0 30%',
            display: 'flex',
            flexDirection: 'column',
            background: '#0c0d0f',
            overflow: 'hidden',
          }}
        >
          {/* Controls — top */}
          <div style={{ flexShrink: 0, borderBottom: '1px solid #1a1b1e' }}>
            <Controls />
          </div>

          {/* Asset roster dropdown */}
          <div style={{ flexShrink: 0 }}>
            <AssetRoster />
          </div>

          {/* Event log — fills remaining space */}
          <div
            style={{
              flex: 1,
              borderBottom: '1px solid #1a1b1e',
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
              minHeight: 0,
            }}
          >
            <EventLog />
          </div>

          {/* Mesh status — bottom */}
          <div style={{ flexShrink: 0 }}>
            <MeshStatus />
          </div>
        </div>
      </div>

      <BottomDock />
    </div>
  )
}
