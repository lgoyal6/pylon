export const FOB_POSITION: [number, number] = [52.1, 32.9]
export const RELAY_COUNT = 10
export const RELAY_MIN_RADIUS_KM = 22
export const RELAY_MAX_RADIUS_KM = 32
// Range (km) assigned to a relay placed manually or via the ring.
export const RELAY_RANGE_MIN_KM = 22
export const RELAY_RANGE_SPREAD_KM = 8

export const DRONE_SPEED_KMH = 120
// Demo time-acceleration: real-world 120km/h would take ~20 min to cross the
// field, so scale drone movement up for a watchable simulation.
export const DRONE_SIM_SCALE = 400

// Swarm spawn ring distance from FOB (degrees) and detonation/intercept radius.
export const SWARM_SPAWN_RADIUS_DEG = 0.62
export const SWARM_DEFAULT_SIZE = 5
export const SWARM_MAX_SIZE = 12
export const INTERCEPT_RADIUS_KM = 6

// Packet travel time through the mesh (ms) and trail fade length (ms).
export const PACKET_DURATION_MS = 2500
export const PACKET_TRAIL_MS = 600

export const FOB_LINK_RANGE_KM = 36

// Signal-transmission pulse: each online relay emits an expanding "ping" ring on
// this period (ms), phase-offset per node so they aren't synchronized.
export const TRANSMIT_PERIOD_MS = 2400

// FOB engagement: once a pylon's detection packet reaches the FOB, the FOB
// launches an interceptor. This is the reaction delay (ms) after packet arrival
// before launch — engages threats at range, not point-blank.
export const FOB_REACTION_MS = 350
// The interceptor is a tracking munition: it flies from the FOB and chases the
// drone. It moves faster than the drone so it runs the target down, and
// detonates within the impact radius.
export const INTERCEPTOR_SPEED_SCALE = 2.4
export const INTERCEPTOR_IMPACT_KM = 1.5

// RF telemetry emit cadence (sim ms). Faster than the sim step so the signal
// chart shows a dense, scrolling gated-carrier trace.
export const RF_EMIT_INTERVAL_MS = 70

// Gated-carrier model: relays transmit a pulsed RF carrier (carrier gated by a
// pulse train), like a real captured signal. PERIOD/DUTY are in samples.
export const RF_GATE_PERIOD = 26
export const RF_GATE_DUTY = 5
export const RF_NOISE_FLOOR_DBM = -95
export const RF_CARRIER_FREQ_MHZ = 349.7

export const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN || ''
