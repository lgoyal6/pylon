import { IconLayer, PathLayer } from '@deck.gl/layers'
import { PathStyleExtension } from '@deck.gl/extensions'
import type { Drone } from '../sim/state'

export function buildDroneLayer(drones: Drone[]) {
  return new IconLayer({
    id: 'drones',
    data: drones.filter(d => d.alive),
    getPosition: (d: Drone) => d.position,
    getIcon: () => ({
      url: '/drone.svg',
      width: 64,
      height: 64,
      anchorY: 32,
    }),
    getSize: 24,
    getAngle: (d: Drone) => -d.heading,
    getColor: [122, 106, 58, 220],
    pickable: false,
  })
}

export function buildDroneTrackLayer(drones: Drone[]) {
  const data = drones
    .filter(d => d.track.length > 1)
    .map(d => ({ positions: d.track }))
  return new PathLayer({
    id: 'drone-tracks',
    data,
    getPath: (d: { positions: [number, number][] }) => d.positions,
    getColor: [122, 106, 58, 80],
    getWidth: 1,
    widthMinPixels: 1,
    getDashArray: [4, 4],
    dashJustified: true,
    extensions: [new PathStyleExtension({ dash: true })],
    pickable: false,
  })
}
