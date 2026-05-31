import { ScatterplotLayer, PathLayer } from '@deck.gl/layers'
import type { Interceptor } from '../sim/state'

// Fast tracking munition fired by the FOB. Rendered as a bright dot with a
// short solid trail so you can see it run the drone down.
export function buildInterceptorLayer(interceptors: Interceptor[]) {
  return new ScatterplotLayer({
    id: 'interceptors',
    data: interceptors.filter(x => x.alive),
    getPosition: (d: Interceptor) => d.position,
    getRadius: 450,
    getFillColor: [235, 130, 90, 255],
    radiusMinPixels: 3.5,
    radiusMaxPixels: 7,
    pickable: false,
  })
}

export function buildInterceptorTrailLayer(interceptors: Interceptor[]) {
  const data = interceptors.filter(x => x.track.length > 1).map(x => ({ positions: x.track }))
  return new PathLayer({
    id: 'interceptor-trails',
    data,
    getPath: (d: { positions: [number, number][] }) => d.positions,
    getColor: [220, 110, 80, 200],
    getWidth: 2.5,
    widthMinPixels: 1.5,
    pickable: false,
  })
}
