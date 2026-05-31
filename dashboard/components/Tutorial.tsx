'use client'
import { useEffect, useRef, useState } from 'react'
import { useSimStore } from '../sim/state'
import { getViewport } from '../sim/geo'
import { FOB_POSITION } from '../data/config'

interface Step {
  key: string
  title: string
  body: string
  cta: string
}

const STEPS: Step[] = [
  { key: 'welcome', title: 'Welcome to Lattice', body: 'Lattice is a self-healing mesh relay network that detects and intercepts aerial, ground, and naval threats. Want a guided walkthrough?', cta: 'Start demo' },
  { key: 'fob', title: '1 · Forward Operating Base', body: 'This is the FOB — the command node we protect. Detected threats are routed here, and the FOB launches interceptors to neutralize them before they get close.', cta: 'Deploy relays →' },
  { key: 'nodes', title: '2 · Relay Nodes', body: 'Autonomous relay nodes are deployed around the FOB. Each has a detection + comm range and sits on the terrain (the faint square is its footprint). No links yet.', cta: 'Form mesh →' },
  { key: 'connect', title: '3 · Mesh Links', body: 'Nodes within range of each other auto-connect into a resilient mesh (teal). Yellow links can reach the FOB directly. If a node dies, the mesh reroutes around it.', cta: 'Spawn threat →' },
  { key: 'drone', title: '4 · Inbound Hostile', body: 'A hostile UAV (red) is inbound toward the FOB. Release it and watch it approach the sensor mesh.', cta: 'Release UAV ▶' },
  { key: 'detect', title: '5 · Threat Detected', body: 'A relay sensed the UAV inside its range and is routing the alert through the mesh to the FOB — the white packet is the detection signal hopping node-to-node.', cta: 'Continue ▶' },
  { key: 'defend', title: '6 · Interception', body: 'The FOB launched a tracking interceptor (orange). It flies out, chases the UAV down, and detonates in an impact burst before the threat reaches the base.', cta: 'Finish' },
  { key: 'done', title: 'You have control', body: 'Demo complete — you are now in free sandbox mode. Deploy relays, place FOBs anywhere, search the globe, and launch swarms. Hit GUIDED DEMO any time to replay.', cta: 'Done' },
]

export default function Tutorial() {
  const demoNonce = useSimStore(s => s.demoNonce)
  const clearAll = useSimStore(s => s.clearAll)
  const placeFob = useSimStore(s => s.placeFob)
  const deployRingNoConnect = useSimStore(s => s.deployRingNoConnect)
  const formMesh = useSimStore(s => s.formMesh)
  const spawnTutorialDrone = useSimStore(s => s.spawnTutorialDrone)
  const play = useSimStore(s => s.play)
  const pause = useSimStore(s => s.pause)
  const setSpeed = useSimStore(s => s.setSpeed)

  const detected = useSimStore(s => s.drones.some(d => d.detected))
  const interceptorActive = useSimStore(s => s.interceptors.length > 0)

  const [active, setActive] = useState(false)
  const [step, setStep] = useState(0)
  const [running, setRunning] = useState(false) // sim released, card hidden, watching for an event
  const centerRef = useRef<[number, number]>(FOB_POSITION)

  // Auto-start on first visit.
  useEffect(() => {
    try {
      if (!localStorage.getItem('lattice_demo_seen')) {
        localStorage.setItem('lattice_demo_seen', '1')
        begin()
      }
    } catch { /* ignore */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Start when the DEMO button bumps demoNonce.
  useEffect(() => {
    if (demoNonce > 0) begin()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [demoNonce])

  function begin() {
    const vp = getViewport()
    centerRef.current = vp ? [vp.centerLng, vp.centerLat] : FOB_POSITION
    clearAll()
    pause()
    setSpeed(0.5)
    setRunning(false)
    setStep(0)
    setActive(true)
  }

  function exit() {
    setActive(false)
    setRunning(false)
    setSpeed(1)
    // Make sure sandbox has a FOB to work with.
    if (useSimStore.getState().fobs.length === 0) placeFob(centerRef.current)
    play()
  }

  // Perform the scripted action for a step, then advance.
  function advance() {
    const key = STEPS[step].key
    if (key === 'welcome') {
      placeFob(centerRef.current)
      setStep(1)
    } else if (key === 'fob') {
      deployRingNoConnect(centerRef.current)
      setStep(2)
    } else if (key === 'nodes') {
      formMesh()
      setStep(3)
    } else if (key === 'connect') {
      spawnTutorialDrone()
      setStep(4)
    } else if (key === 'drone') {
      // Release the UAV: run the sim and watch for detection.
      setRunning(true)
      play()
    } else if (key === 'detect') {
      // Continue: run and watch for the interceptor launch.
      setRunning(true)
      play()
    } else if (key === 'defend') {
      play()
      setStep(7)
    } else {
      exit()
    }
  }

  // Event-driven transitions while the sim is running.
  useEffect(() => {
    if (!active || !running) return
    if (STEPS[step].key === 'drone' && detected) {
      setRunning(false)
      pause()
      setStep(5)
    } else if (STEPS[step].key === 'detect' && interceptorActive) {
      setRunning(false)
      pause()
      setStep(6)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, running, step, detected, interceptorActive])

  if (!active || running) return null

  const s = STEPS[step]
  return (
    <div
      style={{
        position: 'absolute',
        bottom: 24,
        left: '50%',
        transform: 'translateX(-50%)',
        width: '440px',
        maxWidth: 'calc(100% - 32px)',
        background: '#0c0d0f',
        border: '1px solid #1a1b1e',
        zIndex: 8,
        padding: '16px 18px',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '8px' }}>
        <span style={{ fontSize: '13px', color: '#9a9b9e', letterSpacing: '0.04em' }}>{s.title}</span>
        <span style={{ fontSize: '10px', color: '#3a3b3e' }}>{step + 1}/{STEPS.length}</span>
      </div>
      <p style={{ fontSize: '11px', lineHeight: 1.6, color: '#5a5b5e', margin: '0 0 14px' }}>{s.body}</p>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <button
          onClick={exit}
          style={{ background: 'none', border: 'none', color: '#3a3b3e', cursor: 'pointer', fontFamily: 'inherit', fontSize: '10px', letterSpacing: '0.05em', textTransform: 'uppercase' }}
        >
          Skip tour
        </button>
        <button
          onClick={advance}
          style={{ background: '#111214', border: '1px solid #3a3b3e', color: '#9a9b9e', cursor: 'pointer', fontFamily: 'inherit', fontSize: '11px', letterSpacing: '0.05em', padding: '6px 14px', textTransform: 'uppercase' }}
        >
          {s.cta}
        </button>
      </div>
    </div>
  )
}
