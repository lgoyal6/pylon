import { create } from 'zustand'
import type { Relay, Connection } from './mesh'
import {
  placeRelays,
  formConnections,
  destroyRelay,
  healMesh,
  distanceKm,
} from './mesh'
import { findPath } from './pathfinding'
import { isWater, elevationAt, getViewport, isInViewport, type Viewport } from './geo'
import {
  type RFSample,
  type RFMode,
  type RFSource,
  RF_BUFFER,
  RF_BASE_FREQ_MHZ,
  WebSocketRFSource,
} from './rf'
import {
  FOB_POSITION,
  RELAY_COUNT,
  RELAY_MIN_RADIUS_KM,
  RELAY_MAX_RADIUS_KM,
  RELAY_RANGE_MIN_KM,
  RELAY_RANGE_SPREAD_KM,
  DRONE_SPEED_KMH,
  DRONE_SIM_SCALE,
  HOSTILE_SPEED_KMH,
  type HostileType,
  SWARM_SPAWN_RADIUS_DEG,
  SWARM_DEFAULT_SIZE,
  INTERCEPT_RADIUS_KM,
  PACKET_DURATION_MS,
  PACKET_TRAIL_MS,
  GROUND_SLOPE_FACTOR,
  NODE_PAD_HALF_DEG,
  FOB_REACTION_MS,
  INTERCEPTOR_SPEED_SCALE,
  INTERCEPTOR_IMPACT_KM,
  BURST_MS,
  RF_EMIT_INTERVAL_MS,
  RF_GATE_PERIOD,
  RF_GATE_DUTY,
  RF_NOISE_FLOOR_DBM,
} from '../data/config'

export interface Fob {
  id: string
  position: [number, number]
  elevation?: number
  pad?: number[][]
}

export type PlacementMode = 'relay' | 'fob' | 'hostile'

export interface Drone {
  id: string
  kind: HostileType         // AIR | WATER | GROUND
  position: [number, number]
  heading: number
  alive: boolean
  detected: boolean
  track: [number, number][]
  killAt: number | null
  engageAt: number | null   // when the FOB launches its interceptor
  engaged: boolean          // interceptor has been launched at this drone
  targetFobId: string | null
}

export interface Interceptor {
  id: string
  position: [number, number]
  heading: number
  targetId: string
  fobId: string
  alive: boolean
  track: [number, number][]
}

export interface Packet {
  id: string
  path: number[][]
  timestamps: number[]
  startTime: number
  endTime: number
  color: [number, number, number, number]
}

export interface Burst {
  id: string
  position: [number, number]
  elevation: number
  startedAt: number
}

export interface FlyTarget {
  longitude: number
  latitude: number
  zoom: number
  pitch?: number
  bearing?: number
  duration?: number
  nonce: number
}

// Guided-intro tour: a scripted sequence (camera + procedural events + popups)
// that plays once on first load to explain the system to a new viewer. After
// 'done' the sandbox is fully interactive in the normal way.
export type TourStep =
  | 'intro'        // popup: situation briefing, camera in on FOB
  | 'deploy'       // procedurally placing relays one at a time
  | 'meshed'       // popup: relays self-organized into a mesh
  | 'incoming'     // drone spawned far out, approaching the perimeter
  | 'detected'     // popup: drone has entered detection range
  | 'routing'      // signal hops through mesh, FOB launches interceptor
  | 'neutralized'  // popup: drone neutralized
  | 'done'         // tour finished — normal sandbox mode

export interface TourState {
  active: boolean
  step: TourStep
}

export interface LogEntry {
  time: string
  text: string
  level: 'info' | 'warn' | 'alert' | 'kill'
}

export interface MeshHealth {
  nodes: number
  totalNodes: number
  links: number
  latency: number
  health: number
}

export interface SandboxState {
  relays: Relay[]
  connections: Connection[]
  fobs: Fob[]
  drones: Drone[]
  interceptors: Interceptor[]
  packets: Packet[]
  bursts: Burst[]
  flyTarget: FlyTarget | null
  log: LogEntry[]
  meshHealth: MeshHealth
  playing: boolean
  speed: number
  swarmSize: number
  placementMode: PlacementMode
  hostileType: HostileType
  selectedId: string | null
  animationTime: number
  threatsNeutralized: number
  // RF telemetry
  rfMode: RFMode
  rfStatus: string
  rfLatest: Record<string, RFSample>
  rfSeries: Record<string, number[]>  // per-node rssi ring buffer
  rfAggregate: number[]               // mean rssi across online nodes over time
  tour: TourState
  _relaySeq: number
  _fobSeq: number
  _droneSeq: number
  _packetSeq: number
  _interceptorSeq: number
  _rfLastEmit: number
  _rfPhase: number
}

function now() {
  const d = new Date()
  return `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}:${String(d.getUTCSeconds()).padStart(2, '0')}`
}

function pushLog(log: LogEntry[], text: string, level: LogEntry['level']): LogEntry[] {
  const next = [...log, { time: now(), text, level }]
  return next.length > 200 ? next.slice(next.length - 200) : next
}

function computeHealth(relays: Relay[], connections: Connection[]): MeshHealth {
  const online = relays.filter(r => r.status === 'online')
  const active = connections.filter(c => c.status === 'active' || c.status === 'rerouted')
  const avgLatency = active.length
    ? Math.round(active.reduce((s, c) => s + c.latency, 0) / active.length)
    : 0
  const standing = relays.filter(r => r.status !== 'destroyed').length
  const health = standing ? online.length / standing : 0
  return {
    nodes: online.length,
    totalNodes: standing,
    links: active.length,
    latency: avgLatency,
    health: Math.round(health * 100) / 100,
  }
}

// A small square footprint whose corners sample terrain elevation, so the pad
// slants to match the slope the node sits on.
function computePad(lng: number, lat: number): number[][] {
  const d = NODE_PAD_HALF_DEG
  const corners: [number, number][] = [
    [lng - d, lat - d], [lng + d, lat - d], [lng + d, lat + d], [lng - d, lat + d],
  ]
  return corners.map(c => [c[0], c[1], elevationAt(c[0], c[1])])
}

// A spawn point near the edge of the current viewport, for hostile member i of
// n on a chosen side. Vessels/vehicles fall back to a random valid in-view point
// (water for vessels, land for vehicles) if the edge point is the wrong surface.
function viewportSpawn(vp: Viewport, kind: HostileType, side: number, i: number, n: number): [number, number] {
  const w = vp.east - vp.west
  const h = vp.north - vp.south
  const insetX = w * 0.06
  const insetY = h * 0.06
  const t = Math.min(0.92, Math.max(0.08, 0.2 + Math.random() * 0.6 + (i - (n - 1) / 2) * 0.05))
  let p: [number, number]
  switch (side) {
    case 0: p = [vp.west + insetX, vp.south + t * h]; break       // west edge
    case 1: p = [vp.east - insetX, vp.south + t * h]; break       // east edge
    case 2: p = [vp.west + t * w, vp.south + insetY]; break       // south edge
    default: p = [vp.west + t * w, vp.north - insetY]; break      // north edge
  }
  if (kind === 'AIR') return p
  const needWater = kind === 'WATER'
  const ok = (x: number, y: number) => (needWater ? isWater(x, y) : !isWater(x, y))
  if (ok(p[0], p[1])) return p
  for (let k = 0; k < 30; k++) {
    const lng = vp.west + Math.random() * w
    const lat = vp.south + Math.random() * h
    if (ok(lng, lat)) return [lng, lat]
  }
  return p
}

function nearestFob(pos: [number, number], fobs: Fob[]): Fob | null {
  if (fobs.length === 0) return null
  let best = fobs[0]
  let bd = Infinity
  for (const f of fobs) {
    const d = distanceKm(pos, f.position)
    if (d < bd) { bd = d; best = f }
  }
  return best
}

// BFS a path relay -> nearest reachable FOB through the mesh. A virtual SINK is
// connected to every FOB so a single BFS finds the closest one; the SINK is then
// stripped, leaving relay -> ... -> FOB waypoints.
function routeToFob(
  fromRelayId: string,
  relays: Relay[],
  connections: Connection[],
  fobs: Fob[]
): number[][] | null {
  if (fobs.length === 0) return null
  const SINK = '__SINK__'
  const onlineRelays = relays.filter(r => r.status === 'online')
  const fobNodes = fobs.map(f => ({
    id: f.id, position: f.position, range: 999, status: 'online' as const, connections: [], elevation: f.elevation,
  }))
  const allNodes = [
    ...onlineRelays,
    ...fobNodes,
    { id: SINK, position: [0, 0] as [number, number], range: 999, status: 'online' as const, connections: [], elevation: 0 },
  ]
  // A relay can hand the packet to a FOB only if the FOB is within that relay's
  // own range. If the detecting node can't reach the FOB directly, BFS routes the
  // packet hop-by-hop through neighboring relays until one is in range of a FOB.
  const fobLinks: Connection[] = []
  onlineRelays.forEach(r =>
    fobs.forEach(f => {
      if (distanceKm(r.position, f.position) <= r.range) {
        fobLinks.push({ id: `${r.id}-${f.id}`, from: r.id, to: f.id, status: 'active', latency: 5 })
      }
    })
  )
  const sinkLinks: Connection[] = fobs.map(f => ({
    id: `${f.id}-SINK`, from: f.id, to: SINK, status: 'active', latency: 0,
  }))
  const allConns = [...connections, ...fobLinks, ...sinkLinks]
  const path = findPath(fromRelayId, SINK, allNodes, allConns)
  if (!path || path.length < 3) return null
  const trimmed = path.slice(0, path.length - 1) // drop SINK; ends at a FOB
  const posMap = new Map<string, number[]>()
  allNodes.forEach(n => posMap.set(n.id, [n.position[0], n.position[1], n.elevation ?? 0]))
  return trimmed.map(id => posMap.get(id)!).filter(Boolean)
}

function makePacket(waypoints: number[][], startTime: number, seq: number): Packet {
  const d2 = (a: number[], b: number[]) => distanceKm([a[0], a[1]], [b[0], b[1]])
  const total = waypoints.reduce((sum, wp, i) =>
    i === 0 ? 0 : sum + d2(waypoints[i - 1], wp), 0) || 1
  let cum = 0
  const timestamps = waypoints.map((wp, i) => {
    if (i === 0) return startTime
    cum += d2(waypoints[i - 1], wp)
    return startTime + (cum / total) * PACKET_DURATION_MS
  })
  return {
    id: `p${seq}`,
    path: waypoints,
    timestamps,
    startTime,
    endTime: startTime + PACKET_DURATION_MS,
    // Threat-detection signal transmits WHITE (distinct from green mesh traffic).
    color: [230, 232, 236, 235],
  }
}

const DEFAULT_FOBS: Fob[] = [{ id: 'FOB-1', position: FOB_POSITION }]
const EMPTY_HEALTH: MeshHealth = { nodes: 0, totalNodes: 0, links: 0, latency: 0, health: 0 }

export interface SandboxStore extends SandboxState {
  tick: (dt: number) => void
  deployRing: () => void
  placeRelay: (lngLat: [number, number]) => void
  placeFob: (lngLat: [number, number]) => void
  placeHostile: (lngLat: [number, number]) => void
  placeAt: (lngLat: [number, number]) => void
  destroyRelayById: (id: string) => void
  launchSwarm: () => void
  setSwarmSize: (n: number) => void
  setSpeed: (s: number) => void
  setPlacementMode: (m: PlacementMode) => void
  setHostileType: (t: HostileType) => void
  setSelectedId: (id: string | null) => void
  flyToLocation: (
    longitude: number,
    latitude: number,
    zoom: number,
    opts?: { pitch?: number; bearing?: number; duration?: number }
  ) => void
  refreshElevations: () => void
  startTour: () => void
  setTourStep: (step: TourStep) => void
  skipTour: () => void
  ingestRf: (sample: RFSample) => void
  connectRfSource: (url: string) => void
  disconnectRfSource: () => void
  play: () => void
  pause: () => void
  reset: () => void
}

const initialState: SandboxState = {
  relays: [],
  connections: [],
  fobs: DEFAULT_FOBS,
  drones: [],
  interceptors: [],
  packets: [],
  bursts: [],
  flyTarget: null,
  log: [],
  meshHealth: EMPTY_HEALTH,
  // Sim is paused on first paint — the tour resumes it during action steps.
  playing: false,
  speed: 1,
  swarmSize: SWARM_DEFAULT_SIZE,
  placementMode: 'relay',
  hostileType: 'AIR',
  selectedId: null,
  animationTime: 0,
  threatsNeutralized: 0,
  rfMode: 'SIMULATED',
  rfStatus: 'simulated feed',
  rfLatest: {},
  rfSeries: {},
  rfAggregate: [],
  tour: { active: true, step: 'intro' },
  _relaySeq: 0,
  _fobSeq: 1,
  _droneSeq: 0,
  _packetSeq: 0,
  _interceptorSeq: 0,
  _rfLastEmit: 0,
  _rfPhase: 0,
}

// Stable per-id hash for de-syncing each node's gate phase.
function idHash(id: string): number {
  let h = 0
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) % 997
  return h
}

// Active live RF source (WebSocket). Kept outside the store so it isn't part of
// React state; the store only holds the samples it produces.
let liveRfSource: RFSource | null = null

function pushBuf(buf: number[] | undefined, v: number): number[] {
  const next = buf ? [...buf, v] : [v]
  return next.length > RF_BUFFER ? next.slice(next.length - RF_BUFFER) : next
}

export const useSimStore = create<SandboxStore>((set, get) => ({
  ...initialState,

  play: () => set({ playing: true }),
  pause: () => set({ playing: false }),
  setSpeed: (s: number) => set({ speed: s }),
  setSwarmSize: (n: number) => set({ swarmSize: n }),
  setPlacementMode: (m: PlacementMode) => set({ placementMode: m }),
  setHostileType: (t: HostileType) => set({ hostileType: t }),
  setSelectedId: (id: string | null) => set({ selectedId: id }),

  flyToLocation: (
    longitude: number,
    latitude: number,
    zoom: number,
    opts?: { pitch?: number; bearing?: number; duration?: number }
  ) =>
    set({
      flyTarget: {
        longitude,
        latitude,
        zoom,
        pitch: opts?.pitch,
        bearing: opts?.bearing,
        duration: opts?.duration,
        nonce: Date.now(),
      },
    }),

  startTour: () =>
    set({
      ...initialState,
      fobs: [...DEFAULT_FOBS],
      tour: { active: true, step: 'intro' },
      playing: false,
    }),

  setTourStep: (step: TourStep) =>
    set(state => ({ tour: { ...state.tour, step } })),

  skipTour: () =>
    set({ tour: { active: false, step: 'done' }, playing: true }),

  // Re-sample terrain elevation for all nodes (called once terrain tiles load).
  refreshElevations: () => {
    const s = get()
    set({
      relays: s.relays.map(r => ({
        ...r,
        elevation: elevationAt(r.position[0], r.position[1]),
        pad: computePad(r.position[0], r.position[1]),
      })),
      fobs: s.fobs.map(f => ({
        ...f,
        elevation: elevationAt(f.position[0], f.position[1]),
        pad: computePad(f.position[0], f.position[1]),
      })),
    })
  },

  // Single entry point for all RF telemetry — simulated or live. Updates the
  // per-node ring buffer + latest sample. Aggregate is recomputed in tick.
  ingestRf: (sample: RFSample) => {
    const state = get()
    set({
      rfLatest: { ...state.rfLatest, [sample.nodeId]: sample },
      rfSeries: { ...state.rfSeries, [sample.nodeId]: pushBuf(state.rfSeries[sample.nodeId], sample.rssiDbm) },
    })
  },

  connectRfSource: (url: string) => {
    if (liveRfSource) liveRfSource.stop()
    try {
      const src = new WebSocketRFSource(url)
      src.start(s => get().ingestRf(s))
      liveRfSource = src
      set({
        rfMode: 'LIVE',
        rfStatus: `live · ${url}`,
        log: pushLog(get().log, `RF SOURCE connected — ${url}`, 'info'),
      })
    } catch {
      set({ rfStatus: 'connection failed' })
    }
  },

  disconnectRfSource: () => {
    if (liveRfSource) { liveRfSource.stop(); liveRfSource = null }
    set({
      rfMode: 'SIMULATED',
      rfStatus: 'simulated feed',
      log: pushLog(get().log, 'RF SOURCE disconnected — reverting to simulated', 'info'),
    })
  },

  // Reset returns to a clean sandbox in normal (interactive) mode — the tour
  // doesn't replay on reset, only on first load. Use startTour() explicitly to
  // re-run the guided intro.
  reset: () => set({
    ...initialState,
    fobs: [...DEFAULT_FOBS],
    drones: [],
    interceptors: [],
    rfLatest: {},
    rfSeries: {},
    rfAggregate: [],
    log: [],
    animationTime: 0,
    playing: true,
    tour: { active: false, step: 'done' },
  }),

  deployRing: () => {
    const state = get()
    const center = state.fobs[0]?.position ?? FOB_POSITION
    const ring = placeRelays(center, RELAY_COUNT, RELAY_MIN_RADIUS_KM, RELAY_MAX_RADIUS_KM)
      .map((r, i) => ({
        ...r,
        id: `R-${String(state._relaySeq + i + 1).padStart(2, '0')}`,
        status: 'online' as const,
        elevation: elevationAt(r.position[0], r.position[1]),
        pad: computePad(r.position[0], r.position[1]),
      }))
    const relays = [...state.relays, ...ring]
    const conns = formConnections(relays)
    set({
      relays,
      connections: conns,
      _relaySeq: state._relaySeq + RELAY_COUNT,
      meshHealth: computeHealth(relays, conns),
      log: pushLog(state.log, `RING DEPLOYED — ${ring.length} relays, ${conns.length} links`, 'info'),
    })
  },

  placeRelay: (lngLat: [number, number]) => {
    const state = get()
    const seq = state._relaySeq + 1
    const relay: Relay = {
      id: `R-${String(seq).padStart(2, '0')}`,
      position: lngLat,
      range: RELAY_RANGE_MIN_KM + Math.random() * RELAY_RANGE_SPREAD_KM,
      status: 'online',
      connections: [],
      elevation: elevationAt(lngLat[0], lngLat[1]),
      pad: computePad(lngLat[0], lngLat[1]),
    }
    const relays = [...state.relays, relay]
    const conns = formConnections(relays)
    set({
      relays,
      connections: conns,
      _relaySeq: seq,
      meshHealth: computeHealth(relays, conns),
      log: pushLog(state.log, `${relay.id} DEPLOYED — ${conns.length} links`, 'info'),
    })
  },

  placeFob: (lngLat: [number, number]) => {
    const state = get()
    const seq = state._fobSeq + 1
    const fob: Fob = {
      id: `FOB-${seq}`,
      position: lngLat,
      elevation: elevationAt(lngLat[0], lngLat[1]),
      pad: computePad(lngLat[0], lngLat[1]),
    }
    // New FOB may give relays a shorter path — recolor mesh via heal pass.
    const conns = healMesh(state.relays, state.connections)
    set({
      fobs: [...state.fobs, fob],
      connections: conns,
      _fobSeq: seq,
      meshHealth: computeHealth(state.relays, conns),
      log: pushLog(state.log, `${fob.id} ESTABLISHED`, 'info'),
    })
  },

  placeHostile: (lngLat: [number, number]) => {
    const state = get()
    const kind = state.hostileType
    // Sea hostiles can only be placed on water; ground vehicles only on land.
    if (kind === 'WATER' && !isWater(lngLat[0], lngLat[1])) {
      set({ log: pushLog(state.log, 'Cannot place surface vessel on land — pick water', 'warn') })
      return
    }
    if (kind === 'GROUND' && isWater(lngLat[0], lngLat[1])) {
      set({ log: pushLog(state.log, 'Cannot place ground vehicle on water — pick land', 'warn') })
      return
    }
    const seq = state._droneSeq + 1
    const target = nearestFob(lngLat, state.fobs)
    const heading = target
      ? (Math.atan2(target.position[0] - lngLat[0], target.position[1] - lngLat[1]) * 180) / Math.PI
      : 0
    const drone: Drone = {
      id: `D-${seq}`,
      kind,
      position: lngLat,
      heading,
      alive: true,
      detected: false,
      track: [lngLat],
      killAt: null,
      engageAt: null,
      engaged: false,
      targetFobId: null,
    }
    const label = kind === 'AIR' ? 'UAV' : kind === 'WATER' ? 'surface vessel' : 'ground vehicle'
    set({
      drones: [...state.drones, drone],
      _droneSeq: seq,
      log: pushLog(state.log, `${drone.id} PLACED — hostile ${label}`, 'warn'),
    })
  },

  placeAt: (lngLat: [number, number]) => {
    const mode = get().placementMode
    if (mode === 'fob') get().placeFob(lngLat)
    else if (mode === 'hostile') get().placeHostile(lngLat)
    else get().placeRelay(lngLat)
  },

  destroyRelayById: (id: string) => {
    const state = get()
    const target = state.relays.find(r => r.id === id)
    if (!target || target.status === 'destroyed') return
    const { relays, connections } = destroyRelay(id, state.relays, state.connections)
    const healed = healMesh(relays, connections)
    const rerouted = healed.filter(c => c.status === 'rerouted').length
    set({
      relays,
      connections: healed,
      meshHealth: computeHealth(relays, healed),
      log: pushLog(
        pushLog(state.log, `${id} DESTROYED — mesh degraded`, 'kill'),
        rerouted ? `MESH self-healing — ${rerouted} paths rerouted` : 'MESH stable — no reroute needed',
        'warn'
      ),
    })
  },

  launchSwarm: () => {
    const state = get()
    const n = state.swarmSize
    const kind = state.hostileType
    const vp = getViewport()
    const newDrones: Drone[] = []

    // Spawn within the current on-screen view (edge of the viewport) when we have
    // a map; otherwise fall back to a ring around the primary FOB.
    const side = Math.floor(Math.random() * 4)
    for (let i = 0; i < n; i++) {
      let pos: [number, number]
      if (vp) {
        pos = viewportSpawn(vp, kind, side, i, n)
      } else {
        const center = state.fobs[0]?.position ?? FOB_POSITION
        const b = Math.random() * Math.PI * 2 + (i - (n - 1) / 2) * 0.045
        const r = SWARM_SPAWN_RADIUS_DEG + Math.random() * 0.08
        pos = [center[0] + r * Math.cos(b), center[1] + r * Math.sin(b)]
      }
      const target = nearestFob(pos, state.fobs)
      const heading = target
        ? (Math.atan2(target.position[0] - pos[0], target.position[1] - pos[1]) * 180) / Math.PI
        : 0
      newDrones.push({
        id: `D-${state._droneSeq + i + 1}`,
        kind,
        position: pos,
        heading,
        alive: true,
        detected: false,
        track: [pos],
        killAt: null,
        engageAt: null,
        engaged: false,
        targetFobId: null,
      })
    }

    const label = kind === 'AIR' ? 'UAV' : kind === 'WATER' ? 'surface vessel' : 'ground vehicle'
    let log = pushLog(state.log, `SWARM INBOUND — ${n} hostile ${label}${n > 1 ? 's' : ''}`, 'warn')
    // Warn if there's no FOB on screen for them to attack.
    const fobInView = state.fobs.some(f => isInViewport(f.position[0], f.position[1]))
    if (vp && !fobInView) {
      log = pushLog(log, 'No FOB in view — place a FOB on screen for hostiles to target', 'warn')
    }
    set({
      drones: [...state.drones, ...newDrones],
      _droneSeq: state._droneSeq + n,
      log,
    })
  },

  tick: (dt: number) => {
    const state = get()
    if (!state.playing) return
    const sdt = dt * state.speed
    const at = state.animationTime + sdt
    const baseStepDeg = ((DRONE_SPEED_KMH * DRONE_SIM_SCALE) / 111) / 3600000 * sdt
    const fobs = state.fobs

    let relays = state.relays
    let log = state.log
    let packets = state.packets
    let bursts = state.bursts
    let packetSeq = state._packetSeq
    let kills = 0

    const drones: Drone[] = state.drones.map(d => {
      if (!d.alive) return d
      // Always steer toward the closest FOB — placing a new, nearer FOB
      // reroutes live hostiles to it.
      const target = nearestFob(d.position, fobs)
      let targetFobId = d.targetFobId
      if (target && target.id !== d.targetFobId) {
        if (d.targetFobId !== null) {
          log = pushLog(log, `${d.id}: REROUTING → ${target.id} (closer FOB)`, 'warn')
        }
        targetFobId = target.id
      }
      const tgt = target ? target.position : FOB_POSITION
      const dLng = tgt[0] - d.position[0]
      const dLat = tgt[1] - d.position[1]
      const mag = Math.sqrt(dLng * dLng + dLat * dLat) || 1
      let stepDeg = baseStepDeg * (HOSTILE_SPEED_KMH[d.kind] / DRONE_SPEED_KMH)

      // Ground hostiles are slowed by terrain: the steeper the climb toward the
      // next position, the slower they go.
      if (d.kind === 'GROUND') {
        const probeLng = d.position[0] + (dLng / mag) * stepDeg
        const probeLat = d.position[1] + (dLat / mag) * stepDeg
        const e0 = elevationAt(d.position[0], d.position[1])
        const e1 = elevationAt(probeLng, probeLat)
        const stepKm = stepDeg * 111
        const slope = Math.abs(e1 - e0) / (stepKm * 1000 + 1) // rise/run
        stepDeg *= 1 / (1 + GROUND_SLOPE_FACTOR * slope)
      }

      let mvLng = dLng / mag
      let mvLat = dLat / mag
      let newPos: [number, number] = [
        d.position[0] + mvLng * stepDeg,
        d.position[1] + mvLat * stepDeg,
      ]

      // Terrain constraints: vessels must stay on water, vehicles on land. If the
      // direct step violates that, try deflected headings to follow the shoreline;
      // hold if none work.
      const needWater = d.kind === 'WATER'
      const needLand = d.kind === 'GROUND'
      const blocked = (needWater && !isWater(newPos[0], newPos[1])) || (needLand && isWater(newPos[0], newPos[1]))
      if (blocked) {
        let found = false
        for (const deg of [40, -40, 75, -75, 110, -110, 150, -150]) {
          const th = (deg * Math.PI) / 180
          const rx = dLng * Math.cos(th) - dLat * Math.sin(th)
          const ry = dLng * Math.sin(th) + dLat * Math.cos(th)
          const rm = Math.sqrt(rx * rx + ry * ry) || 1
          const cand: [number, number] = [
            d.position[0] + (rx / rm) * stepDeg,
            d.position[1] + (ry / rm) * stepDeg,
          ]
          const ok = needWater ? isWater(cand[0], cand[1]) : !isWater(cand[0], cand[1])
          if (ok) {
            newPos = cand
            mvLng = rx / rm
            mvLat = ry / rm
            found = true
            break
          }
        }
        if (!found) newPos = [d.position[0], d.position[1]]
      }
      const heading = (Math.atan2(mvLng, mvLat) * 180) / Math.PI
      const track = d.track.length > 60 ? [...d.track.slice(-60), newPos] : [...d.track, newPos]
      let detected = d.detected
      let engageAt = d.engageAt

      // First detection by any pylon: route threat data to the FOB, and schedule
      // the FOB's interceptor to arrive once that data lands (+ reaction delay).
      // This takes the drone out at range, not point-blank.
      if (!detected) {
        for (const relay of relays) {
          if (relay.status !== 'online') continue
          if (distanceKm(relay.position, newPos) <= relay.range) {
            detected = true
            const waypoints = routeToFob(relay.id, relays, state.connections, fobs)
            const arrival = PACKET_DURATION_MS
            if (waypoints) {
              packetSeq += 1
              packets = [...packets, makePacket(waypoints, at, packetSeq)]
            }
            engageAt = at + arrival + FOB_REACTION_MS
            log = pushLog(log, `${relay.id}: THREAT DETECTED — routing to ${target?.id ?? 'FOB'}`, 'alert')
            break
          }
        }
      }

      // Fail-safe only: if an uncommitted drone reaches the FOB, kill at the
      // base. Normal kills happen via the tracking interceptor below.
      const pointBlank = target && distanceKm(newPos, target.position) <= INTERCEPT_RADIUS_KM
      if (pointBlank && target && !d.engaged) {
        kills += 1
        bursts = [...bursts, { id: `b${d.id}`, position: newPos, elevation: elevationAt(newPos[0], newPos[1]), startedAt: at }]
        log = pushLog(log, `${d.id}: NEUTRALIZED at ${target.id} perimeter`, 'kill')
        return { ...d, position: newPos, heading, track, detected, engageAt, targetFobId, alive: false, killAt: at }
      }

      return { ...d, position: newPos, heading, track, detected, engageAt, targetFobId }
    })

    // Launch a tracking interceptor for each committed drone whose engage time
    // has arrived (detection data has reached the FOB + reaction delay).
    let interceptors = state.interceptors
    let interceptorSeq = state._interceptorSeq
    const launches: Interceptor[] = []
    const dronesCommitted = drones.map(d => {
      if (d.alive && d.detected && !d.engaged && d.engageAt !== null && at >= d.engageAt) {
        const fob = nearestFob(d.position, fobs)
        if (fob) {
          interceptorSeq += 1
          const hLng = d.position[0] - fob.position[0]
          const hLat = d.position[1] - fob.position[1]
          launches.push({
            id: `X-${interceptorSeq}`,
            position: [...fob.position] as [number, number],
            heading: (Math.atan2(hLng, hLat) * 180) / Math.PI,
            targetId: d.id,
            fobId: fob.id,
            alive: true,
            track: [fob.position],
          })
          log = pushLog(log, `${fob.id}: INTERCEPTOR ${`X-${interceptorSeq}`} LAUNCHED → ${d.id}`, 'warn')
          return { ...d, engaged: true }
        }
      }
      return d
    })

    // Advance interceptors toward their target drones; detonate on impact.
    const interceptorStep = baseStepDeg * INTERCEPTOR_SPEED_SCALE
    const droneById = new Map(dronesCommitted.map(d => [d.id, d]))
    const impacted = new Set<string>()
    interceptors = [...interceptors, ...launches].map(x => {
      if (!x.alive) return x
      const tgt = droneById.get(x.targetId)
      if (!tgt || !tgt.alive) return { ...x, alive: false } // target already gone
      const dLng = tgt.position[0] - x.position[0]
      const dLat = tgt.position[1] - x.position[1]
      const mag = Math.sqrt(dLng * dLng + dLat * dLat) || 1
      const np: [number, number] = [
        x.position[0] + (dLng / mag) * interceptorStep,
        x.position[1] + (dLat / mag) * interceptorStep,
      ]
      const heading = (Math.atan2(dLng, dLat) * 180) / Math.PI
      const trk = x.track.length > 40 ? [...x.track.slice(-40), np] : [...x.track, np]
      if (distanceKm(np, tgt.position) <= INTERCEPTOR_IMPACT_KM) {
        impacted.add(x.targetId)
        bursts = [...bursts, { id: `b${x.id}`, position: np, elevation: elevationAt(np[0], np[1]), startedAt: at }]
        log = pushLog(log, `${x.targetId}: NEUTRALIZED by ${x.id} — tracking intercept`, 'kill')
        return { ...x, position: np, heading, track: trk, alive: false }
      }
      return { ...x, position: np, heading, track: trk }
    })

    // Apply interceptor kills to the drones.
    const drones2 = dronesCommitted.map(d =>
      impacted.has(d.id) && d.alive ? { ...d, alive: false, killAt: at } : d
    )
    kills += impacted.size

    relays = relays.map(r => {
      if (r.status !== 'online') return r
      const alert = drones2.some(d => d.alive && distanceKm(d.position, r.position) <= r.range)
      return alert === !!r.alert ? r : { ...r, alert }
    })

    const liveDrones = drones2.filter(d => d.alive || (d.killAt !== null && at - d.killAt < 1200))
    const liveInterceptors = interceptors.filter(x => x.alive)
    bursts = bursts.filter(b => at - b.startedAt < BURST_MS)
    packets = packets.filter(p => at - p.endTime < PACKET_TRAIL_MS)

    // RF telemetry — a gated RF carrier (carrier pulsed on/off by a gate),
    // matching how a real captured signal looks: short bursts up to the carrier
    // power on a noise floor. In SIMULATED mode we synthesize per-relay bursts;
    // in LIVE mode samples arrive via ingestRf and we only roll the carrier here.
    let rfLatest = state.rfLatest
    let rfSeries = state.rfSeries
    let rfAggregate = state.rfAggregate
    let rfLastEmit = state._rfLastEmit
    let rfPhase = state._rfPhase
    if (at - rfLastEmit >= RF_EMIT_INTERVAL_MS) {
      rfLastEmit = at
      rfPhase += 1
      const online = relays.filter(r => r.status === 'online')
      if (state.rfMode === 'SIMULATED') {
        const nextLatest = { ...rfLatest }
        const nextSeries = { ...rfSeries }
        for (const r of online) {
          // Gate this node, phase-offset so nodes don't burst in unison.
          const gateOn = ((rfPhase + idHash(r.id)) % RF_GATE_PERIOD) < RF_GATE_DUTY
          const floor = RF_NOISE_FLOOR_DBM + (Math.random() - 0.5) * 3
          const peak = -58 + Math.min(r.connections.length, 4) * 3 + (Math.random() - 0.5) * 4 - (r.alert ? 6 : 0)
          const rssiDbm = Math.round(gateOn ? peak : floor)
          const snrDb = Math.round(18 + (Math.random() - 0.5) * 4 - (r.alert ? 8 : 0))
          const freqMhz = Math.round((RF_BASE_FREQ_MHZ + (Math.random() - 0.5) * 0.4) * 10) / 10
          nextLatest[r.id] = { nodeId: r.id, t: Date.now(), rssiDbm, snrDb, freqMhz }
          nextSeries[r.id] = pushBuf(nextSeries[r.id], rssiDbm)
        }
        rfLatest = nextLatest
        rfSeries = nextSeries
      }
      // Aggregate "mesh carrier": one shared gate so the default view reads as a
      // clean pulsed RF carrier; amplitude grows with the live mesh.
      const onlineCount = online.length
      const aggGate = (rfPhase % RF_GATE_PERIOD) < RF_GATE_DUTY
      const aggFloor = RF_NOISE_FLOOR_DBM + (Math.random() - 0.5) * 2
      const aggPeak = -54 + Math.min(onlineCount, 12) * 0.7 + (Math.random() - 0.5) * 3
      const aggVal = Math.round(onlineCount ? (aggGate ? aggPeak : aggFloor) : -100)
      rfAggregate = pushBuf(rfAggregate, aggVal)
    }

    set({
      animationTime: at,
      drones: liveDrones,
      interceptors: liveInterceptors,
      relays,
      packets,
      bursts,
      log,
      threatsNeutralized: state.threatsNeutralized + kills,
      _packetSeq: packetSeq,
      _interceptorSeq: interceptorSeq,
      rfLatest,
      rfSeries,
      rfAggregate,
      _rfLastEmit: rfLastEmit,
      _rfPhase: rfPhase,
    })
  },
}))
