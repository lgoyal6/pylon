'use client'
import { useEffect, useRef } from 'react'
import { useSimStore } from '../sim/state'
import { placeRelays } from '../sim/mesh'
import {
  FOB_POSITION,
  RELAY_COUNT,
  RELAY_MIN_RADIUS_KM,
  RELAY_MAX_RADIUS_KM,
} from '../data/config'

// Where the tour's demo drone spawns: offset east+south of the FOB so it
// flies in diagonally and crosses the perimeter on a clear line.
const TOUR_DRONE_OFFSET: [number, number] = [0.55, 0.08]
const RELAY_PLACE_INTERVAL_MS = 280

/**
 * Orchestrates the scripted intro tour: camera shots, procedural relay
 * placement, drone spawn, and auto-advance triggers. All UI lives in
 * TourOverlay; this component is invisible and only fires side-effects.
 */
export default function TourController() {
  const step = useSimStore(s => s.tour.step)
  const active = useSimStore(s => s.tour.active)
  const drones = useSimStore(s => s.drones)
  const bursts = useSimStore(s => s.bursts)
  const fobs = useSimStore(s => s.fobs)
  const flyToLocation = useSimStore(s => s.flyToLocation)
  const placeRelay = useSimStore(s => s.placeRelay)
  const placeHostile = useSimStore(s => s.placeHostile)
  const setHostileType = useSimStore(s => s.setHostileType)
  const setTourStep = useSimStore(s => s.setTourStep)
  const play = useSimStore(s => s.play)
  const pause = useSimStore(s => s.pause)

  // Guard so deploy / spawn fire exactly once per visit to that step even
  // under React 18 StrictMode (which double-invokes effects in dev).
  const firedRef = useRef<Set<string>>(new Set())

  // Camera + sim play/pause per step.
  useEffect(() => {
    if (!active) return
    const fob = fobs[0] ?? { position: FOB_POSITION }
    const [flng, flat] = fob.position

    switch (step) {
      case 'intro':
        pause()
        flyToLocation(flng, flat, 11.5, { pitch: 55, bearing: -15, duration: 1800 })
        break
      case 'deploy':
        pause()
        flyToLocation(flng, flat, 10.2, { pitch: 50, bearing: -15, duration: 1400 })
        break
      case 'meshed':
        pause()
        flyToLocation(flng, flat, 10.2, { pitch: 50, bearing: -15, duration: 600 })
        break
      case 'incoming':
        flyToLocation(flng + 0.25, flat + 0.04, 8.6, { pitch: 45, bearing: -15, duration: 2200 })
        play()
        break
      case 'detected': {
        // Frame the most recently detected drone alongside the FOB.
        const d = drones.find(x => x.detected && x.alive) ?? drones[0]
        const tx = d ? (d.position[0] + flng) / 2 : flng
        const ty = d ? (d.position[1] + flat) / 2 : flat
        flyToLocation(tx, ty, 10.8, { pitch: 55, bearing: -15, duration: 1500 })
        pause()
        break
      }
      case 'routing':
        flyToLocation(flng + 0.18, flat + 0.04, 9.6, { pitch: 50, bearing: -15, duration: 1800 })
        play()
        break
      case 'neutralized': {
        const b = bursts[bursts.length - 1]
        const tx = b?.position[0] ?? flng
        const ty = b?.position[1] ?? flat
        flyToLocation(tx, ty, 11.2, { pitch: 55, bearing: -15, duration: 1400 })
        pause()
        break
      }
      case 'done':
        play()
        break
    }
    // step is the only meaningful trigger — re-firing on drone/burst array
    // identity changes would yank the camera around.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, active])

  // Procedural relay placement.
  useEffect(() => {
    if (!active || step !== 'deploy') return
    if (firedRef.current.has('deploy')) return
    firedRef.current.add('deploy')

    const fob = fobs[0] ?? { position: FOB_POSITION }
    const positions = placeRelays(
      fob.position,
      RELAY_COUNT,
      RELAY_MIN_RADIUS_KM,
      RELAY_MAX_RADIUS_KM
    ).map(r => r.position)

    let i = 0
    const id = window.setInterval(() => {
      if (i >= positions.length) {
        window.clearInterval(id)
        // Brief beat after the last relay lands before we cut to the popup.
        window.setTimeout(() => setTourStep('meshed'), 500)
        return
      }
      placeRelay(positions[i])
      i += 1
    }, RELAY_PLACE_INTERVAL_MS)

    return () => window.clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, active])

  // Drone spawn for the 'incoming' step.
  useEffect(() => {
    if (!active || step !== 'incoming') return
    if (firedRef.current.has('incoming')) return
    firedRef.current.add('incoming')

    const fob = fobs[0] ?? { position: FOB_POSITION }
    const spawn: [number, number] = [
      fob.position[0] + TOUR_DRONE_OFFSET[0],
      fob.position[1] + TOUR_DRONE_OFFSET[1],
    ]
    setHostileType('AIR')
    // Small delay so the spawn happens after the camera starts pulling back.
    const id = window.setTimeout(() => placeHostile(spawn), 600)
    return () => window.clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, active])

  // Auto-advance: 'incoming' -> 'detected' when any drone is detected.
  useEffect(() => {
    if (!active || step !== 'incoming') return
    if (drones.some(d => d.detected)) setTourStep('detected')
  }, [step, active, drones, setTourStep])

  // Auto-advance: 'routing' -> 'neutralized' when an impact burst appears.
  useEffect(() => {
    if (!active || step !== 'routing') return
    if (bursts.length > 0) setTourStep('neutralized')
  }, [step, active, bursts, setTourStep])

  return null
}
