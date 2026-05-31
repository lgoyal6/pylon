import { ArcLayer } from '@deck.gl/layers'
import { distanceKm } from '../sim/mesh'
import type { Relay } from '../sim/mesh'
import type { Fob } from '../sim/state'

interface FobLink {
  from: [number, number, number]
  to: [number, number, number]
}

// Direct relay → FOB links: drawn whenever a FOB is within a relay's range.
// Yellow, to set them apart from the teal relay-to-relay mesh arcs.
export function buildFobLinkLayer(relays: Relay[], fobs: Fob[]) {
  const links: FobLink[] = []
  for (const r of relays) {
    if (r.status !== 'online') continue
    for (const f of fobs) {
      if (distanceKm(r.position, f.position) <= r.range) {
        links.push({
          from: [r.position[0], r.position[1], r.elevation ?? 0],
          to: [f.position[0], f.position[1], f.elevation ?? 0],
        })
      }
    }
  }

  return new ArcLayer({
    id: 'fob-links',
    data: links,
    getSourcePosition: (d: FobLink) => d.from,
    getTargetPosition: (d: FobLink) => d.to,
    getSourceColor: [150, 138, 78, 140],
    getTargetColor: [150, 138, 78, 140],
    getWidth: 1.5,
    getHeight: 0.35,
    greatCircle: false,
    widthMinPixels: 1.5,
    widthMaxPixels: 3,
    pickable: false,
  })
}
