import { IconLayer, PathLayer } from '@deck.gl/layers'
import { PathStyleExtension } from '@deck.gl/extensions'
import type { Drone } from '../sim/state'

const ICON_URL: Record<Drone['kind'], string> = {
  AIR: '/drone.svg',
  WATER: '/vessel.svg',
  GROUND: '/vehicle.svg',
}

// Hostiles render red for contrast; shape (chevron / diamond / square) tells the
// class apart. Slight shade variation keeps them distinguishable.
const HOSTILE_COLOR: Record<Drone['kind'], [number, number, number, number]> = {
  AIR: [235, 80, 70, 245],      // bright red
  WATER: [225, 95, 125, 245],   // red-pink (reads on blue water)
  GROUND: [205, 65, 55, 245],   // deep red
}

export function buildDroneLayer(drones: Drone[]) {
  return new IconLayer({
    id: 'drones',
    data: drones.filter(d => d.alive),
    getPosition: (d: Drone) => d.position,
    getIcon: (d: Drone) => ({
      url: ICON_URL[d.kind],
      width: 64,
      height: 64,
      anchorY: 32,
      mask: true, // use the SVG as a shape mask so getColor tints it red
    }),
    getSize: (d: Drone) => (d.kind === 'AIR' ? 26 : 24),
    // Ground/surface icons aren't directional chevrons, so only rotate the UAV.
    getAngle: (d: Drone) => (d.kind === 'AIR' ? -d.heading : 0),
    getColor: (d: Drone) => HOSTILE_COLOR[d.kind],
    updateTriggers: { getIcon: drones.map(d => d.kind).join(), getColor: drones.map(d => d.kind).join() },
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
    getColor: [210, 80, 70, 90],
    getWidth: 1,
    widthMinPixels: 1,
    getDashArray: [4, 4],
    dashJustified: true,
    extensions: [new PathStyleExtension({ dash: true })],
    pickable: false,
  })
}
