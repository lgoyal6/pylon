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
import TourOverlay from '../components/TourOverlay'
import TourController from '../components/TourController'

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
      <section aria-label="Operator task and evidence" style={{padding:'10px 16px',color:'#bdc8d2',fontSize:'12px',lineHeight:1.5,borderBottom:'1px solid #26303a'}}>
        <strong>Operator task: preserve a route after a relay fails.</strong> Deploy the ring, launch a simulated swarm, then remove a relay and inspect the rerouted alert.
        <details><summary>Simulation and RF evidence</summary>
          <p>This map uses synthetic RF and simulated assets. Its detections are separate from the physical RF prototype and held-out synthetic-IQ study.</p>
          <p>The detector’s calibration loads ambient captures before novelty scoring. The comparison uses an illustrative signature baseline, not a vendor implementation.</p>
          <a href="https://github.com/lgoyal6/pylon">Project source</a>{' | '}
          <a href="https://github.com/lgoyal6/pylon/blob/main/physical_demo/drone_detection/RUNBOOK.md">Physical capture and calibration runbook</a>{' | '}
          <a href="https://github.com/lgoyal6/pylon/tree/main/physical_demo/library_contrast">Synthetic-IQ evaluation and bounds</a>
        </details>
      </section>

      {/* Main content */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden', minHeight: 0 }}>
        {/* Map - 70% */}
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
          <TourOverlay />
          <TourController />
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
          {/* Controls - top */}
          <div style={{ flexShrink: 0, borderBottom: '1px solid #1a1b1e' }}>
            <Controls />
          </div>

          {/* Asset roster dropdown */}
          <div style={{ flexShrink: 0 }}>
            <AssetRoster />
          </div>

          {/* Event log - fills remaining space */}
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

          {/* Mesh status - bottom */}
          <div style={{ flexShrink: 0 }}>
            <MeshStatus />
          </div>
        </div>
      </div>

      <BottomDock />
    </div>
  )
}
