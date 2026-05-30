# IRON VEIL — Dashboard

Mesh relay simulation. A staggered ring of autonomous relays deploys around a FOB,
discovers neighbors by proximity, forms a self-healing mesh, detects a hostile UAV,
routes the threat data to the FOB, intercepts the drone, then reroutes the mesh when
a relay is destroyed.

## Stack

- Next.js 14 (app router) + React 18 + TypeScript
- Mapbox GL + react-map-gl + deck.gl 9 (ScatterplotLayer, ArcLayer, IconLayer, PathLayer, TripsLayer, LineLayer)
- zustand for sim state, requestAnimationFrame phase loop

## Setup

1. Add a Mapbox token to `.env.local`:
   ```
   NEXT_PUBLIC_MAPBOX_TOKEN=pk.your_token_here
   ```
   Without a token the deck.gl layers still render, but the dark basemap will be blank.

2. Run:
   ```
   npm run dev
   ```
   Open http://localhost:3000

## Layout

- `app/page.tsx` — three-zone layout: map (70%) | event log + mesh status (30%) | timeline
- `components/` — Map, EventLog, MeshStatus, Timeline, TopBar
- `layers/` — one file per deck.gl layer
- `sim/` — `state.ts` (zustand store + phase machine), `mesh.ts` (placement/connection/heal),
  `pathfinding.ts` (BFS), all the simulation logic
- `data/config.ts` — FOB coords, relay count, ranges, drone speed/scale

## Controls (live sandbox)

The sim is a free-running sandbox you drive. Nothing is scripted.

**Right panel — CONTROLS:**
- **Deploy Ring** — drops a preset 10-relay ring around the primary FOB; mesh auto-forms.
- **Click places: Relay / FOB** — pick what a map click drops.
  - **Relay mode** — click the map to place a relay; links form automatically to any in-range neighbor. Online relays emit a muted "ping" pulse to show they're transmitting on the mesh.
  - **FOB mode** — click the map to place additional FOBs anywhere. Drones target the nearest FOB; each FOB intercepts threats on close approach.
- **Click a relay** — destroys it and triggers mesh self-heal (rerouted links render in muted purple). Works in either mode.
- **Clear** — wipes everything (a default FOB-1 remains).
- **Drone Swarm** — set the swarm size (1-12) with −/+, then **Launch Swarm**. Drones spawn from a random edge and fly toward the nearest FOB; relays detect them, route the threat through the mesh, and the FOB intercepts each one.

**Bottom transport bar:**
- ◄ reset · ►/■ play-pause · speed 0.5× / 1× / 2× / 4×
- live activity waveform, mission clock (T+mm:ss), quick Launch Swarm, and inbound-threat readout.

Live counts (relays online, threats active, neutralized) and the event log update in real time.
