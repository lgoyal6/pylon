import { IconLayer } from '@deck.gl/layers'
import type { Fob } from '../sim/state'

// FOB renders as a small white square (the "command post" footprint) instead
// of a circle. Drawn as an SVG icon so it stays the same pixel size across
// zoom levels rather than scaling with the map.
const FOB_ICON_URL =
  'data:image/svg+xml;utf8,' +
  encodeURIComponent(
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32' width='32' height='32'>" +
      "<rect x='4' y='4' width='24' height='24' fill='#dcdde0' stroke='#ffffff' stroke-width='1.5'/>" +
      '</svg>'
  )

export function buildFobLayer(fobs: Fob[]) {
  return new IconLayer<Fob>({
    id: 'fobs',
    data: fobs,
    getPosition: (d: Fob): [number, number, number] => [d.position[0], d.position[1], d.elevation ?? 0],
    getIcon: () => ({ url: FOB_ICON_URL, width: 32, height: 32, anchorX: 16, anchorY: 16 }),
    getSize: 22,
    sizeUnits: 'pixels',
    pickable: false,
  })
}
