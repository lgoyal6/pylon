import { ScatterplotLayer, PathLayer } from '@deck.gl/layers'
import type { Interceptor } from '../sim/state'

// Fast tracking munition fired by the FOB. Rendered as a bright dot with a
// short solid trail so you can see it run the drone down.
export function buildInterceptorLayer(interceptors: Interceptor[]) {
  return new ScatterplotLayer({
    id: 'interceptors',
    data: interceptors.filter(x => x.alive),
    getPosition: (d: Interceptor) => d.position,
    getRadius: 300,
    getFillColor: [180, 90, 90, 230],
    radiusMinPixels: 2.5,
    radiusMaxPixels: 5,
    pickable: false,
  })
}

export function buildInterceptorTrailLayer(interceptors: Interceptor[]) {
  const data = interceptors.filter(x => x.track.length > 1).map(x => ({ positions: x.track }))
  return new PathLayer({
    id: 'interceptor-trails',
    data,
    getPath: (d: { positions: [number, number][] }) => d.positions,
    getColor: [150, 70, 70, 150],
    getWidth: 1.5,
    widthMinPixels: 1,
    pickable: false,
  })
}
