import { TripsLayer } from '@deck.gl/geo-layers'
import type { Packet } from '../sim/state'
import { PACKET_TRAIL_MS } from '../data/config'

export function buildPacketLayer(packets: Packet[], currentTime: number) {
  return new TripsLayer({
    id: 'data-packets',
    data: packets,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    getPath: (d: Packet) => d.path as any,
    getTimestamps: (d: Packet) => d.timestamps,
    getColor: (d: Packet) => d.color,
    getWidth: 2.5,
    trailLength: PACKET_TRAIL_MS,
    currentTime,
    widthMinPixels: 2,
    pickable: false,
  })
}
