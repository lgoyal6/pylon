import { PolygonLayer } from '@deck.gl/layers'
import type { Relay } from '../sim/mesh'
import type { Fob } from '../sim/state'

interface PadItem {
  pad: number[][]
  kind: 'relay' | 'fob'
  alert: boolean
}

// Slanted footprint under each relay/FOB. Each pad is a small quad whose corners
// sit at the terrain elevation, so it tilts to match the slope the node is on.
export function buildPadLayer(relays: Relay[], fobs: Fob[]) {
  const data: PadItem[] = [
    ...relays
      .filter(r => r.status === 'online' && r.pad)
      .map(r => ({ pad: r.pad as number[][], kind: 'relay' as const, alert: !!r.alert })),
    ...fobs
      .filter(f => f.pad)
      .map(f => ({ pad: f.pad as number[][], kind: 'fob' as const, alert: false })),
  ]

  return new PolygonLayer<PadItem>({
    id: 'node-pads',
    data,
    getPolygon: (d: PadItem) => d.pad,
    getFillColor: (d: PadItem): [number, number, number, number] =>
      d.kind === 'fob' ? [154, 155, 158, 38] : d.alert ? [122, 106, 58, 50] : [74, 106, 122, 42],
    getLineColor: (d: PadItem): [number, number, number, number] =>
      d.kind === 'fob' ? [154, 155, 158, 170] : d.alert ? [122, 106, 58, 180] : [74, 106, 122, 150],
    getLineWidth: 2,
    lineWidthMinPixels: 1,
    lineWidthMaxPixels: 2,
    stroked: true,
    filled: true,
    extruded: false,
    updateTriggers: {
      getFillColor: data.map(d => d.alert).join(),
      getLineColor: data.map(d => d.alert).join(),
    },
    pickable: false,
  })
}
