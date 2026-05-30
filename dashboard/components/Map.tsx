'use client'
import React, { useEffect, useRef, useCallback } from 'react'
import DeckGL from '@deck.gl/react'
import Map from 'react-map-gl/mapbox'
import { useSimStore } from '../sim/state'
import { buildRelayLayer, buildRingLayer, buildSelectionLayer } from '../layers/relays'
import { buildTransmitLayer } from '../layers/transmit'
import { buildSignalLayer } from '../layers/signals'
import { buildArcLayer } from '../layers/arcs'
import { buildDroneLayer, buildDroneTrackLayer } from '../layers/drone'
import { buildPacketLayer } from '../layers/packets'
import { buildInterceptLayer, buildFobLayer } from '../layers/intercept'
import { buildInterceptorLayer, buildInterceptorTrailLayer } from '../layers/interceptor'
import { MAPBOX_TOKEN, FOB_POSITION } from '../data/config'
import 'mapbox-gl/dist/mapbox-gl.css'

const INITIAL_VIEW = {
  longitude: FOB_POSITION[0],
  latitude: FOB_POSITION[1],
  zoom: 9,
  pitch: 45,
  bearing: -15,
}

export default function MapView() {
  const relays = useSimStore(s => s.relays)
  const connections = useSimStore(s => s.connections)
  const drones = useSimStore(s => s.drones)
  const interceptors = useSimStore(s => s.interceptors)
  const packets = useSimStore(s => s.packets)
  const animationTime = useSimStore(s => s.animationTime)
  const interceptLines = useSimStore(s => s.interceptLines)
  const fobs = useSimStore(s => s.fobs)
  const selectedId = useSimStore(s => s.selectedId)
  const tick = useSimStore(s => s.tick)
  const placeAt = useSimStore(s => s.placeAt)
  const destroyRelayById = useSimStore(s => s.destroyRelayById)

  const rafRef = useRef<number | null>(null)
  const lastTimeRef = useRef<number>(0)

  const animate = useCallback((timestamp: number) => {
    if (lastTimeRef.current === 0) lastTimeRef.current = timestamp
    const dt = Math.min(timestamp - lastTimeRef.current, 100)
    lastTimeRef.current = timestamp
    tick(dt)
    rafRef.current = requestAnimationFrame(animate)
  }, [tick])

  useEffect(() => {
    lastTimeRef.current = 0
    rafRef.current = requestAnimationFrame(animate)
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current) }
  }, [animate])

  const layers = [
    buildRingLayer(relays),
    buildTransmitLayer(relays, animationTime),
    buildArcLayer(connections, relays),
    buildSignalLayer(connections, relays, fobs, animationTime),
    buildSelectionLayer(relays, fobs, selectedId),
    buildRelayLayer(relays),
    buildFobLayer(fobs),
    buildDroneTrackLayer(drones),
    buildDroneLayer(drones),
    buildInterceptorTrailLayer(interceptors),
    buildInterceptorLayer(interceptors),
    buildPacketLayer(packets, animationTime),
    buildInterceptLayer(interceptLines),
  ]

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  function handleClick(info: any) {
    // Clicked an existing relay -> destroy it (triggers self-heal)
    if (info?.object && info.object.id && info.layer?.id === 'relay-nodes') {
      if (info.object.status !== 'destroyed') {
        destroyRelayById(info.object.id)
        return
      }
    }
    // Clicked empty map -> place a relay or FOB depending on current mode
    if (info?.coordinate) {
      placeAt([info.coordinate[0], info.coordinate[1]])
    }
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  function handleMapLoad(e: any) {
    const map = e.target
    try {
      map.setPaintProperty('background', 'background-color', '#08090a')
      map.setPaintProperty('water', 'fill-color', '#08090a')
    } catch {}
    const style = map.getStyle()
    if (!style?.layers) return
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    style.layers.forEach((l: any) => {
      if (l.type === 'symbol') {
        try {
          map.setPaintProperty(l.id, 'text-color', '#2a2b2e')
          map.setPaintProperty(l.id, 'text-halo-color', '#08090a')
        } catch {}
      }
      if (l.id.includes('boundary') || l.id.includes('admin')) {
        try {
          map.setPaintProperty(l.id, 'line-color', '#1a1b1e')
          map.setPaintProperty(l.id, 'line-opacity', 0.3)
        } catch {}
      }
    })
  }

  return (
    <DeckGL
      initialViewState={INITIAL_VIEW}
      controller={true}
      layers={layers}
      onClick={handleClick}
      getCursor={({ isHovering }) => (isHovering ? 'pointer' : 'crosshair')}
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      style={{ position: 'absolute', top: '0', left: '0', right: '0', bottom: '0' } as any}
    >
      <Map
        mapboxAccessToken={MAPBOX_TOKEN}
        mapStyle="mapbox://styles/mapbox/dark-v11"
        onLoad={handleMapLoad}
      />
    </DeckGL>
  )
}
