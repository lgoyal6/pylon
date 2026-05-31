export const FOB_POSITION: [number, number] = [52.1, 32.9]
export const RELAY_COUNT = 10
export const RELAY_MIN_RADIUS_KM = 11
export const RELAY_MAX_RADIUS_KM = 17
// Range (km) assigned to a relay placed manually or via the ring.
export const RELAY_RANGE_MIN_KM = 9
export const RELAY_RANGE_SPREAD_KM = 5

export const DRONE_SPEED_KMH = 120
// Demo time-acceleration: real-world 120km/h would take ~20 min to cross the
// field, so scale movement up for a watchable simulation.
export const DRONE_SIM_SCALE = 400

// Hostile classes and their cruise speeds (km/h). Air is fastest; surface and
// ground threats are slower.
export type HostileType = 'AIR' | 'WATER' | 'GROUND'
export const HOSTILE_SPEED_KMH: Record<HostileType, number> = {
  AIR: 120,
  WATER: 55,
  GROUND: 95,
}

// Swarm spawn ring distance from FOB (degrees) and detonation/intercept radius.
export const SWARM_SPAWN_RADIUS_DEG = 0.62
export const SWARM_DEFAULT_SIZE = 5
export const SWARM_MAX_SIZE = 12
// Point-blank fail-safe radius — small, so the tracking interceptor (below) is
// what normally kills, not the FOB perimeter.
export const INTERCEPT_RADIUS_KM = 3

// Packet travel time through the mesh (ms) and trail fade length (ms).
export const PACKET_DURATION_MS = 700
export const PACKET_TRAIL_MS = 500

export const FOB_LINK_RANGE_KM = 22

// Ground-hostile slope slowdown: higher = steeper terrain slows vehicles more.
export const GROUND_SLOPE_FACTOR = 5

// Signal-transmission pulse: each online relay emits an expanding "ping" ring on
// this period (ms), phase-offset per node so they aren't synchronized.
export const TRANSMIT_PERIOD_MS = 2400

// FOB engagement: once a pylon's detection packet reaches the FOB, the FOB
// launches an interceptor. This is the reaction delay (ms) after packet arrival
// before launch — engages threats at range, not point-blank.
export const FOB_REACTION_MS = 150
// The interceptor is a tracking munition: it flies from the FOB and chases the
// drone. It moves faster than the drone so it runs the target down, and
// detonates within the impact radius.
export const INTERCEPTOR_SPEED_SCALE = 2.8
export const INTERCEPTOR_IMPACT_KM = 1.5
// Impact burst (expanding ring) shown when an interceptor detonates.
export const BURST_MS = 750
export const BURST_MAX_RADIUS_M = 2600

// RF telemetry emit cadence (sim ms). Faster than the sim step so the signal
// chart shows a dense, scrolling gated-carrier trace.
export const RF_EMIT_INTERVAL_MS = 70

// Gated-carrier model: relays transmit a pulsed RF carrier (carrier gated by a
// pulse train), like a real captured signal. PERIOD/DUTY are in samples.
export const RF_GATE_PERIOD = 26
export const RF_GATE_DUTY = 5
export const RF_NOISE_FLOOR_DBM = -95
export const RF_CARRIER_FREQ_MHZ = 349.7

// 3D terrain (DEM) exaggeration. 1 = true scale; >1 emphasizes relief.
export const TERRAIN_EXAGGERATION = 1.5

// Half-extent (degrees) of the square "pad" a relay/FOB sits on. Its corners
// sample terrain elevation so the pad slants to match the slope. ~0.008° ≈ 0.9km.
export const NODE_PAD_HALF_DEG = 0.008

export const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN || ''
