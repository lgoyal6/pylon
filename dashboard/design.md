# design.md — Lattice

> Living design doc. Kept in sync with the implementation. Sections marked
> **[v2]** changed when the dashboard became an interactive live sandbox
> (manual relay/FOB deployment, drone swarms, signal-transmission pulses).
> **[v3]** added a filterable roster dropdown with inspect, and ambient
> inter-node signal traffic.
> **[v4]** Foundry-style console: RF telemetry ingestion (simulated + live
> WebSocket), bottom signal dock, right Selection/Properties panel, left legend,
> tracking interceptors. **Asset types were removed — every node is just a relay
> with links** (plus COMMAND/FOB).

## Visual Rules

No border-radius on anything. Every element is sharp-cornered: panels, buttons, badges, inputs, cards, map container. Zero rounded corners across the entire UI.

Color palette is muted. No saturated blues, no bright greens. Everything sits in the black-to-dark-gray range with desaturated accent colors at low opacity.

```
Background:
  page:           #08090a
  panel:          #0c0d0f
  panel-border:   #1a1b1e
  panel-hover:    #111214

Text:
  primary:        #9a9b9e
  secondary:      #5a5b5e
  label:          #3a3b3e
  dim:            #2a2b2e

Accents (muted, used sparingly):
  node-healthy:   #4a6a7a      (desaturated steel blue)
  node-glow:      #4a6a7a18    (same at 10% opacity)
  transmit-ring:  #4a6a7a      (signal pulse, alpha fades 45->0) [v2]
  connection:     #3a5a4a      (muted teal-green)
  connection-alt: #5a4a6a      (muted purple, rerouted paths only)
  threat-warn:    #7a6a3a      (dark amber)
  threat-kill:    #7a3a3a      (dark red)
  data-packet:    #4a7a5a      (muted green)
  destroyed:      #3a3a3a      (gray, dead node)
```

All accent colors are heavily desaturated. Nothing glows bright. The UI should feel like looking at a screen in a dark room with the brightness turned down.

Typography is monospaced everywhere. No sans-serif anywhere in the app.

```
font-family: 'JetBrains Mono', 'Fira Code', monospace
font-size:
  data values:    12px
  labels:         10px, uppercase, letter-spacing: 0.1em
  log entries:    11px
  phase title:    13px
  top bar:        11px
```

Borders are 1px solid #1a1b1e. Never thicker. Never brighter.

No shadows, no glows, no gradients, no blur effects.

**[v2] Motion exception — signal transmission.** The original rule forbade
"pulsing dots." That is relaxed to show that nodes are actively transmitting.
Two ambient animations are permitted, both dim, neither a glow:
- **Transmit pulse [v2]** — online relays emit an expanding "ping" ring (1px
  stroked, fades alpha ~45→0 from node to range). Shows a node is live.
- **Inter-node signals [v3]** — small muted dots slide along every active mesh
  link, showing nodes transmitting *to each other*. Muted green
  (#5a96... ~[90,150,110]), muted purple on rerouted links.

No other pulsing, blinking, or decorative motion is allowed.

**[v4] Node colors.** All relays share one muted steel fill [74,106,122]; amber
[122,106,58] when on alert; gray [58,58,58] when destroyed. COMMAND/FOB is the
brightest element [154,155,158]. (Asset types from v3 were removed — nodes are
relays, not decorative unit types.)

---

## Layout

```
┌──────────────────────────────────────────────────────────┐
│  // LATTICE                                   10:24 UTC  │
├────────────────────────────────┬─────────────────────────┤
│                                │  CONTROLS          [v2] │
│                                │  ──────────────────     │
│                                │  [Deploy Ring] [Clear]  │
│                                │  Click places: Relay/FOB│
│      MAP (mapbox + deck.gl)    │  Swarm: − 5 + [Launch]  │
│      70% width                 │  relays/fobs/threats... │
│      pitch: 45                 ├─────────────────────────┤
│      dark basemap              │  EVENT LOG              │
│                                │  10:24:03 R-01 ONLINE   │
│                                │  ...                    │
│                                ├─────────────────────────┤
│                                │  MESH STATUS            │
│                                │  nodes 10/10  links 13  │
│                                │  latency 8ms health 1.00│
├────────────────────────────────┴─────────────────────────┤
│  ◄  ■   SPEED 0.5× 1× 2× 4×   ▁▃▅▂▆  T+00:42  [LAUNCH] │
└──────────────────────────────────────────────────────────┘
```

The right column is three stacked panels: **CONTROLS** (top), **EVENT LOG**
(middle, fills), **MESH STATUS** (bottom). The top bar is the project name
left-aligned and a UTC clock right-aligned. **[v2]** The bottom bar is a
transport: reset · play/pause · speed (0.5/1/2/4×) · an activity waveform that
animates when threats are inbound · mission clock (T+mm:ss) · quick Launch Swarm
· inbound readout.

No decorative elements beyond the transmit pulse and the activity waveform.

---

## Simulation Model **[v2 — replaces the scripted phase machine]**

The sim is a **free-running interactive sandbox**, not a scripted scene. Nothing
auto-plays a storyline; the operator drives it. A single
`requestAnimationFrame` loop calls `tick(dt)` on the zustand store every frame;
`dt` is scaled by the transport speed.

Operator actions:

- **Deploy Ring** — places a preset staggered ring of relays around the primary
  FOB; mesh links auto-form.
- **Click map (Relay mode)** — drops one relay at the clicked coordinate; links
  re-form to any in-range neighbor.
- **Click map (FOB mode)** — drops a new FOB at the clicked coordinate. Multiple
  FOBs are supported; a default FOB-1 always exists. **[v2]**
- **Click a relay** — destroys it and triggers mesh self-heal (rerouted links go
  muted purple). Works in any placement mode.
- **Launch Swarm** — spawns N hostile drones (size 1–12) from a random edge
  around the primary FOB. Each flies to the **nearest** FOB; relays detect them
  and route threat packets through the mesh; the FOB intercepts on close
  approach.
- **Transport** — play/pause, speed 0.5–4×, Clear/reset.

State is continuous: detection, packet propagation, interception, and self-heal
all happen live and concurrently for any number of drones.

---

## Mesh Algorithm

Relays are not manually connected to each other. They discover each other by
proximity and form bidirectional links autonomously. When a relay dies, the mesh
reroutes through survivors.

### Node Placement

```ts
interface Relay {
  id: string
  position: [number, number]  // [lng, lat]
  range: number               // km, detection + comm radius
  status: 'offline' | 'booting' | 'online' | 'destroyed'
  connections: string[]
  alert?: boolean             // true while a live threat is in range [v2]
}
```

Ring placement uses polar coordinates with jitter around a center (the primary
FOB). Config **[v5.2 — ranges reduced]**: `RELAY_MIN_RADIUS_KM = 11`,
`RELAY_MAX_RADIUS_KM = 17`, relay `range = RELAY_RANGE_MIN_KM(9) +
rand*RELAY_RANGE_SPREAD_KM(5)` km, `FOB_LINK_RANGE_KM = 22`. Tuned so the ring
stays connected at the smaller scale (~10 links for a 10-node ring).

### Connection Formation

When relays are online, every pair within each other's range forms a
bidirectional link. Latency ≈ `dist * 0.3 + rand*5` ms.

### Mesh Self-Healing

On destroy: mark `destroyed`, drop all its links, clear it from neighbor arrays,
then re-run `formConnections()` on survivors. Connections that did not exist
before are marked `rerouted` and render muted purple (#5a4a6a).

### Shortest Path (packet routing) **[v2 — multi-FOB]**

BFS from the detecting relay to the **nearest reachable FOB**. A virtual SINK
node is connected to every FOB so one BFS finds the closest; the SINK is then
stripped, leaving `relay → … → FOB` waypoints. Relays within
`FOB_LINK_RANGE_KM = 36` of a FOB connect to it.

---

## Nodes & Roster **[v4 — types removed]**

Every deployed node is a **relay** (mesh node with links). FOBs are COMMAND
nodes; drones are HOSTILE. There are no relay sub-types. **Roster dropdown**
(`AssetRoster.tsx`): collapsed header `ASSETS · N`, expands to filter chips
(All / Relay / FOB / Hostile) and a scrollable list — each row id · kind ·
status · `links · latency · range` (distance-to-FOB for drones). Clicking a row
sets `selectedId`, which draws a bright highlight ring on the map
(`buildSelectionLayer`) and opens the Selection panel. Click again to deselect.

## RF Telemetry **[v4]**

The dashboard ingests RF signal telemetry through one stream. `sim/rf.ts`
defines `RFSample { nodeId, t, rssiDbm, snrDb, freqMhz }` and two sources behind
an `RFSource` interface:
- **SimulatedRFSource** (default) — synthesizes plausible per-relay samples;
  rssi tracks link count, degrades on alert.
- **WebSocketRFSource** — connects to a real receiver/SDR bridge; same
  `ingestRf` entry point feeds every consumer. Point it at a `ws://…` URL via
  the bottom dock's **Connect Live** control.

Store: `rfMode`, `rfLatest[nodeId]`, `rfSeries[nodeId]` (ring buffer),
`rfAggregate` (the mesh carrier over time). The Selection "Series" tab and the
bottom dock plot these. To go live: `connectRfSource(url)`.

**Gated-carrier model [v4.1].** Synthetic RF is modeled as a real gated RF
carrier: each relay transmits the carrier pulsed on/off by a gate
(`RF_GATE_PERIOD`/`RF_GATE_DUTY`), producing short bursts up to the carrier
power on a noise floor (`RF_NOISE_FLOOR_DBM ≈ -95`). Per-node gates are
phase-offset; the aggregate uses one shared gate so the default view reads as a
clean pulsed carrier. Band is 349.7 MHz. Emit cadence 70 ms, buffer 256. This
matches the look of a captured gated-carrier signal rather than a smooth line.

## Tracking Interceptor **[v4 / v5.4]**

When a pylon detects a drone, threat data routes to the nearest FOB. Once it
lands (+ `FOB_REACTION_MS`), the FOB **launches a tracking interceptor** — a fast
munition (`INTERCEPTOR_SPEED_SCALE = 2.8× drone speed`) that flies from the FOB
and chases the drone's live position, detonating within `INTERCEPTOR_IMPACT_KM`.
Rendered as a bright orange dot + trail (`layers/interceptor.ts`); on impact an
**expanding red burst ring** plays (`layers/burst.ts`, `Burst` in the store) —
there are no straight intercept lines. A point-blank kill at the small
`INTERCEPT_RADIUS_KM (3)` perimeter remains only as a fail-safe.

**[v5.4] Engagement timing.** With the reduced relay ranges, packet travel
(`PACKET_DURATION_MS`) and reaction (`FOB_REACTION_MS`) were shortened so the
interceptor launches and reaches the drone *before* it hits the perimeter — the
projectile makes the kill, not the fail-safe.

## Location Search **[v5.4]**

`SearchBox.tsx` (floats top-center over the map) geocodes a query via the Mapbox
Geocoding API and calls `flyToLocation(lng, lat, zoom)` (zoom chosen by place
type). The Map runs a **controlled** `viewState` and animates there with a
`FlyToInterpolator`. Search "Japan" → the camera flies to Japan.

## Panels **[v4]**

- **Legend** (`Legend.tsx`, floats top-left over map): node / mesh / threat
  color key.
- **SearchBox** (`SearchBox.tsx`, floats top-center): geocode + fly-to.
- **SelectionPanel** (`SelectionPanel.tsx`, floats top-right): Properties /
  Series / Events tabs for the selected node, with a Filter box. Series shows
  the node's RF chart; Events filters the log to that id.
- **BottomDock** (`BottomDock.tsx`): transport (play/pause/speed), mission
  clock, RF source status + Connect Live, a SERIES list, and the live RF signal
  chart (selected node, else mesh aggregate). Replaces the v2 transport bar.

## FOBs **[v2]**

```ts
interface Fob { id: string; position: [number, number] }
```

- A default `FOB-1` exists at the configured center; operators add more by
  clicking the map in FOB mode.
- Drones target the nearest FOB and are intercepted within
  `INTERCEPT_RADIUS_KM = 6` of it.
- Rendered as the brightest element on the map (#9a9b9e), same ScatterplotLayer
  spec as before but data is now the FOB array.

---

## Hostiles & Swarms **[v4.2 — typed hostiles]**

```ts
type HostileType = 'AIR' | 'WATER' | 'GROUND'
interface Drone {
  id: string
  kind: HostileType
  position, heading, alive, detected, track, killAt, engageAt, engaged
  targetFobId: string | null
}
```

Three hostile classes, chosen by the **Hostile Swarm** selector (AIR / WATER /
GROUND): air UAVs (fastest, amber chevron `/drone.svg`), surface vessels
(`HOSTILE_SPEED_KMH.WATER`, steel-blue `/vessel.svg`), ground vehicles (slowest,
olive `/vehicle.svg`). Per-kind speed scales `baseStepDeg`.

**Spawning [v4.3 / v5.5].** Two ways: **Launch Swarm** spawns N **within the
current on-screen viewport** (near a random edge, via `getViewport()` registered
by the Map), or **Hostile placement mode** (CLICK PLACES → Hostile) drops one per
map click. Viewport spawning lets you run the sim anywhere: fly/search to a
region, place a FOB on screen, and launched hostiles spawn on-screen and head to
the nearest FOB. If no FOB is in view, a warning is logged. Vessels/vehicles fall
back to a random valid in-view point (water / land) when the edge is the wrong
surface. Falls back to a ring around the primary FOB when no map is present.

**Terrain-constrained hostiles [v4.3 / v5.2].** `sim/geo.ts` holds a land/water
tester and an elevation sampler, both registered by the Map (water via
`queryRenderedFeatures` on the `water` layer; elevation via
`queryTerrainElevation`; off-screen/unknown → allow / 0).
- **WATER** hostiles can only be *placed* on water and only move over water.
- **GROUND** hostiles can only be *placed* on land and only move over land, and
  are **slowed by slope** — each step samples elevation at current vs. next
  position and scales speed by `1/(1 + GROUND_SLOPE_FACTOR·slope)`, so climbing
  steep terrain is slow.
- Both deflect (±40/75/110/150°) to follow the shoreline when blocked, else hold.
  Air is unconstrained.

**Nodes follow the surface [v5.2].** Relays and FOBs sample terrain elevation on
placement (`elevationAt`) and store it; every node/mesh layer (relay dots,
detection rings, transmit pulses, FOBs, arcs, signal dots, packets, selection
ring) renders at `[lng, lat, elevation]` so they sit on the 3D terrain instead
of floating at sea level. `refreshElevations()` re-samples once DEM tiles load
(map `idle`) so the default FOB-1 and anything placed early gets its height.

**Slanted pads [v5.3].** Each relay/FOB also stores a `pad`: a small square
footprint (`NODE_PAD_HALF_DEG ≈ 0.9km`) whose four corners sample terrain
elevation (`computePad`). `layers/pads.ts` draws these as a `PolygonLayer` with
3D vertices, so the pad **tilts to match the slope** the node sits on — relays on
a hillside visibly slant. Filled translucent + stroked edge, colored by kind
(relay steel / FOB gray / amber on alert). Recomputed in `refreshElevations`.

Each frame every live hostile steers toward its **nearest FOB** — placing a new,
closer FOB **reroutes live hostiles** to it (logged `REROUTING → FOB-x`), tracked
via `targetFobId`. On first entering a relay's range it is detected (relay goes
amber, a **white** threat packet routes to the nearest FOB). The FOB then
launches a tracking interceptor (see below). Demo-accelerated speed
(`* DRONE_SIM_SCALE`).

---

## deck.gl Layer Specs

Render order (bottom → top): detection rings, transmit pulses, mesh arcs,
inter-node signals, selection ring, relay nodes, FOBs, drone tracks, drones,
**interceptor trails + interceptors [v4]**, data packets, intercept flashes.

### Relay Nodes — ScatterplotLayer
`getFillColor` by **asset type [v3]** when online (amber `[122,106,58,220]` when
`alert`), booting dim, destroyed `[58,58,58,120]`. `pickable: true` so map
clicks can destroy a relay. Color/radius transitions 500/300 ms.

### Inter-node Signals — ScatterplotLayer **[v3 — new]**
Two muted dots per active link slide from `from`→`to`, position =
`lerp(a, b, ((animationTime/1600)+offset+phase)%1)`, offset hashed from the
connection id. Green `[90,150,110,180]` for normal mesh traffic, purple
`[120,100,140,180]` on rerouted links, and **white `[230,232,236]` when either
endpoint relay is on alert** — a link carrying threat-detection data transmits
white, not green **[v4.2]**. Detection packets (TripsLayer) are likewise white.
`radiusMinPixels: 1.5`. Computed each frame; nothing stored in the sim.

### Selection Ring — ScatterplotLayer (stroked) **[v3 — new]**
Single bright stroked ring `[154,155,158,230]` around `selectedId` (relay or
FOB). Empty layer when nothing selected.

### Detection Rings — ScatterplotLayer (stroked)
Per online relay, radius = `range * 1000` m. Line color amber when alert, else
barely-visible steel `[74,106,122,25]`. Transparent fill.

### Transmit Pulses — ScatterplotLayer (stroked) **[v2 — new]**
Per online relay, an expanding ring showing active transmission. Phase =
`((animationTime / TRANSMIT_PERIOD_MS) + perNodeOffset) % 1`; radius =
`phase * range * 1000` m; line alpha = `(1 - phase) * 45` (×70 when alert).
`perNodeOffset` is hashed from the relay id so pulses are desynchronized.
`updateTriggers` keyed on `animationTime`. Color steel `#4a6a7a` (amber when
alert). `TRANSMIT_PERIOD_MS = 2400`.

### Mesh Connections — ArcLayer
Source/target colors muted teal `[58,90,74,160]`, or muted purple
`[90,74,106,160]` when `rerouted`. `getHeight: 0.35` **[v4.1 — lowered from 1.0;
the tall arcs were too much]**; `greatCircle: false`; `widthMinPixels: 1.5`,
`widthMaxPixels: 3`.

### Data Packets — TripsLayer
Per packet: `path` waypoints + absolute `timestamps`. `currentTime =
animationTime`; `trailLength = PACKET_TRAIL_MS (600)`. Color muted green
`[74,122,90,220]`. Multiple concurrent packets supported (each carries its own
start/end time). `PACKET_DURATION_MS = 2500`.

### Drone — IconLayer **[v4.2 — per-kind icon/color]**
Data is the live-hostile array. Icon + color by `kind`: AIR `/drone.svg` amber
(rotated by heading), WATER `/vessel.svg` steel-blue, GROUND `/vehicle.svg`
olive (ground/surface icons aren't rotated).

### Drone Track — PathLayer
One dashed faint-amber path per drone (`PathStyleExtension({ dash: true })`),
track capped at 60 points.

### Intercept Lines — LineLayer
Data is the active intercept-line array (FOB → drone), muted red
`[122,58,58,200]`, expire ~700 ms after firing.

### FOB — ScatterplotLayer
Data is the FOB array. Fill `[154,155,158,200]` — brightest element.

---

## Mapbox Configuration

```ts
const INITIAL_VIEW = {
  longitude: 52.1, latitude: 32.9,  // primary FOB
  zoom: 9,
  pitch: 55,        // [v5] raised from 45 to show 3D terrain
  bearing: -15,
  maxPitch: 75,
}
```

On `style.load`: background and water → `#08090a`; all symbol label text →
`#2a2b2e` with `#08090a` halo; boundary/admin lines → `#1a1b1e` at 0.3 opacity.

**3D terrain [v5].** Adds a `mapbox-dem` raster-dem source and
`map.setTerrain({ source: 'mapbox-dem', exaggeration: TERRAIN_EXAGGERATION })`
(1.5) so relief shows under the pitch. A subtle dark `hillshade` layer
(`iv-hillshade`, exaggeration 0.45, near-black shadows, `#26282c` highlights) is
inserted below the first symbol layer so labels stay readable. `setFog` adds
dark atmospheric depth. deck.gl overlays draw on top of the terrain (no
occlusion), so nodes/arcs stay visible. Requires terrain tiles (a GPU).

**Topographic contours [v5.1].** A `mapbox-terrain-v2` vector source feeds two
line layers below the labels: `iv-contour` (all elevation isolines, muted amber
`#6a5836` at ~0.26 opacity, width interpolated by zoom) and `iv-contour-index`
(index contours via `['has','index']`, brighter `#8a7344` at ~0.42, thicker).
Gives the dark map a topographic-isoline read without breaking the palette.

DeckGL `controller: true`; `getCursor` is crosshair normally, pointer when
hovering a relay; top-level `onClick` routes to destroy (hit a relay) or place
(empty map, by mode). Requires `NEXT_PUBLIC_MAPBOX_TOKEN` in `.env.local`.

---

## File Structure

```
dashboard/
  app/            page.tsx, layout.tsx, globals.css
  components/     Map, Controls [v2], AssetRoster [v3], SelectionPanel [v4], Legend [v4],
                  BottomDock [v4], SignalChart [v4], EventLog, MeshStatus, TopBar
  layers/         relays (+ rings, selection), transmit, signals, arcs, drone,
                  interceptor [v4], packets, intercept (+ fob)
  sim/            state.ts (zustand sandbox store), mesh.ts, pathfinding.ts, rf.ts [v4], geo.ts [v4.3]
  data/           config.ts
  public/         drone.svg, vessel.svg [v4.2], vehicle.svg [v4.2]
  public/         drone.svg
```

---

## CSS Baseline

`* { border-radius: 0 }` globally. Page/panel/border/text variables as in the
palette. JetBrains Mono everywhere, 12px base, antialiased. Log entries colored
by level (warn/alert amber, kill red). `.stat-value` uses tabular-nums.

---

## Dependencies

next ^14.2, react ^18.3, mapbox-gl ^3.4, react-map-gl ^8 (imported via
`react-map-gl/mapbox`), @deck.gl/{core,react,layers,geo-layers,extensions} ^9,
zustand ^4.5, tailwindcss ^3.4.
