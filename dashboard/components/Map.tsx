'use client'
import React, { useEffect, useRef, useCallback } from 'react'
import Map, { useControl } from 'react-map-gl/mapbox'
import type { MapRef } from 'react-map-gl/mapbox'
import { MapboxOverlay } from '@deck.gl/mapbox'
import { useSimStore } from '../sim/state'
import { buildRelayLayer, buildRingLayer, buildSelectionLayer } from '../layers/relays'
import { buildPadLayer } from '../layers/pads'
import { buildTransmitLayer } from '../layers/transmit'
import { buildSignalLayer } from '../layers/signals'
import { buildArcLayer } from '../layers/arcs'
import { buildDroneLayer, buildDroneTrackLayer } from '../layers/drone'
import { buildPacketLayer } from '../layers/packets'
import { buildFobLayer } from '../layers/intercept'
import { buildBurstLayer } from '../layers/burst'
import { buildInterceptorLayer, buildInterceptorTrailLayer } from '../layers/interceptor'
import { MAPBOX_TOKEN, FOB_POSITION, TERRAIN_EXAGGERATION } from '../data/config'
import { setWaterTest, setElevationFn, setViewportFn } from '../sim/geo'
import 'mapbox-gl/dist/mapbox-gl.css'

const INITIAL_VIEW = {
  longitude: FOB_POSITION[0],
  latitude: FOB_POSITION[1],
  zoom: 9,
  pitch: 55,
  bearing: -15,
}

// deck.gl rendered INTERLEAVED inside Mapbox's GL context. In this mode deck
// follows the basemap projection — including the 3D globe when zoomed out — so
// the markers stick to the globe instead of floating in flat-mercator space.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function DeckOverlay(props: { layers: any[]; onClick: (info: any) => void }) {
  const overlay = useControl(
    () =>
      new MapboxOverlay({
        interleaved: true,
        layers: props.layers,
        onClick: props.onClick,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        getCursor: ({ isHovering }: any) => (isHovering ? 'pointer' : 'crosshair'),
      })
  )
  overlay.setProps({ layers: props.layers, onClick: props.onClick })
  return null
}

export default function MapView() {
  const relays = useSimStore(s => s.relays)
  const connections = useSimStore(s => s.connections)
  const drones = useSimStore(s => s.drones)
  const interceptors = useSimStore(s => s.interceptors)
  const packets = useSimStore(s => s.packets)
  const animationTime = useSimStore(s => s.animationTime)
  const bursts = useSimStore(s => s.bursts)
  const flyTarget = useSimStore(s => s.flyTarget)
  const fobs = useSimStore(s => s.fobs)
  const selectedId = useSimStore(s => s.selectedId)
  const tick = useSimStore(s => s.tick)
  const placeAt = useSimStore(s => s.placeAt)
  const destroyRelayById = useSimStore(s => s.destroyRelayById)

  const mapRef = useRef<MapRef | null>(null)

  // Fly to a searched location (Mapbox owns the camera now).
  useEffect(() => {
    if (!flyTarget) return
    mapRef.current?.getMap()?.flyTo({
      center: [flyTarget.longitude, flyTarget.latitude],
      zoom: flyTarget.zoom,
      duration: 2600,
      essential: true,
    })
  }, [flyTarget])

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
    buildPadLayer(relays, fobs),
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
    buildBurstLayer(bursts, animationTime),
  ]

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  function handleClick(info: any) {
    // Clicked an existing relay -> remove it (triggers self-heal)
    if (info?.object && info.object.id && info.layer?.id === 'relay-nodes') {
      destroyRelayById(info.object.id)
      return
    }
    // Clicked empty map -> place a relay / FOB / hostile depending on mode
    if (info?.coordinate) {
      placeAt([info.coordinate[0], info.coordinate[1]])
    }
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  function handleMapLoad(e: any) {
    const map = e.target

    // Register a land/water tester for the sim (vessels stay on water).
    const waterLayers = (map.getStyle()?.layers || [])
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .filter((l: any) => l.id === 'water' || l['source-layer'] === 'water')
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .map((l: any) => l.id)
    setWaterTest((lng: number, lat: number) => {
      try {
        const p = map.project([lng, lat])
        const c = map.getContainer()
        if (p.x < 0 || p.y < 0 || p.x > c.clientWidth || p.y > c.clientHeight) return true
        const feats = map.queryRenderedFeatures(p, waterLayers.length ? { layers: waterLayers } : undefined)
        if (!waterLayers.length) {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          return feats.some((f: any) => f.sourceLayer === 'water' || f.layer?.id === 'water')
        }
        return feats.length > 0
      } catch {
        return true
      }
    })

    try {
      map.setPaintProperty('background', 'background-color', '#08090a')
      map.setPaintProperty('water', 'fill-color', '#08090a')
    } catch {}

    // 3D terrain.
    try {
      if (!map.getSource('mapbox-dem')) {
        map.addSource('mapbox-dem', {
          type: 'raster-dem',
          url: 'mapbox://mapbox.mapbox-terrain-dem-v1',
          tileSize: 512,
          maxzoom: 14,
        })
      }
      map.setTerrain({ source: 'mapbox-dem', exaggeration: TERRAIN_EXAGGERATION })
      setElevationFn((lng: number, lat: number) => {
        try {
          const el = map.queryTerrainElevation([lng, lat], { exaggerated: true })
          return typeof el === 'number' ? el : 0
        } catch {
          return 0
        }
      })
      map.once('idle', () => useSimStore.getState().refreshElevations())

      setViewportFn(() => {
        try {
          const b = map.getBounds()
          const c = map.getCenter()
          if (!b) return null
          return {
            west: b.getWest(), south: b.getSouth(), east: b.getEast(), north: b.getNorth(),
            centerLng: c.lng, centerLat: c.lat,
          }
        } catch {
          return null
        }
      })
      map.setFog({
        range: [1, 12],
        color: '#0c0d0f',
        'high-color': '#0c0d0f',
        'horizon-blend': 0.08,
        'space-color': '#08090a',
        'star-intensity': 0,
      })
    } catch {}

    const style = map.getStyle()
    if (!style?.layers) return
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const firstSymbol = style.layers.find((l: any) => l.type === 'symbol')?.id
    try {
      if (!map.getLayer('iv-hillshade')) {
        map.addLayer({
          id: 'iv-hillshade',
          type: 'hillshade',
          source: 'mapbox-dem',
          paint: {
            'hillshade-exaggeration': 0.45,
            'hillshade-shadow-color': '#000000',
            'hillshade-highlight-color': '#26282c',
            'hillshade-accent-color': '#000000',
          },
        }, firstSymbol)
      }
    } catch {}

    // Topographic contour lines.
    try {
      if (!map.getSource('mapbox-terrain-v2')) {
        map.addSource('mapbox-terrain-v2', {
          type: 'vector',
          url: 'mapbox://mapbox.mapbox-terrain-v2',
        })
      }
      if (!map.getLayer('iv-contour')) {
        map.addLayer({
          id: 'iv-contour',
          type: 'line',
          source: 'mapbox-terrain-v2',
          'source-layer': 'contour',
          paint: {
            'line-color': '#6a5836',
            'line-width': ['interpolate', ['linear'], ['zoom'], 8, 0.3, 14, 0.8],
            'line-opacity': 0.26,
          },
        }, firstSymbol)
      }
      if (!map.getLayer('iv-contour-index')) {
        map.addLayer({
          id: 'iv-contour-index',
          type: 'line',
          source: 'mapbox-terrain-v2',
          'source-layer': 'contour',
          filter: ['has', 'index'],
          paint: {
            'line-color': '#8a7344',
            'line-width': ['interpolate', ['linear'], ['zoom'], 8, 0.6, 14, 1.4],
            'line-opacity': 0.42,
          },
        }, firstSymbol)
      }
    } catch {}

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
    <Map
      ref={mapRef}
      initialViewState={INITIAL_VIEW}
      maxPitch={75}
      mapboxAccessToken={MAPBOX_TOKEN}
      mapStyle="mapbox://styles/mapbox/dark-v11"
      projection={{ name: 'globe' }}
      onLoad={handleMapLoad}
      style={{ position: 'absolute', width: '100%', height: '100%' }}
    >
      <DeckOverlay layers={layers} onClick={handleClick} />
    </Map>
  )
}
