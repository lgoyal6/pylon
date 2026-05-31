// Land/water test, backed by the Mapbox basemap's `water` layer.
//
// The sim (zustand store) has no map instance, so the Map component registers a
// tester on load via setWaterTest. Until then — or for points outside the
// rendered viewport — isWater returns true (unknown → allow movement), so the
// constraint only ever *restricts* vessels where we can actually confirm land.

type WaterTest = (lng: number, lat: number) => boolean
type ElevationFn = (lng: number, lat: number) => number

export interface Viewport {
  west: number
  south: number
  east: number
  north: number
  centerLng: number
  centerLat: number
}
type ViewportFn = () => Viewport | null

let waterTest: WaterTest | null = null
let elevationFn: ElevationFn | null = null
let viewportFn: ViewportFn | null = null

export function setViewportFn(fn: ViewportFn | null) {
  viewportFn = fn
}

// Current map viewport bounds (used to spawn hostiles on-screen). null if no map.
export function getViewport(): Viewport | null {
  if (!viewportFn) return null
  try {
    return viewportFn()
  } catch {
    return null
  }
}

export function isInViewport(lng: number, lat: number): boolean {
  const vp = getViewport()
  if (!vp) return true
  return lng >= vp.west && lng <= vp.east && lat >= vp.south && lat <= vp.north
}

export function setWaterTest(fn: WaterTest | null) {
  waterTest = fn
}

export function setElevationFn(fn: ElevationFn | null) {
  elevationFn = fn
}

export function hasWaterTest(): boolean {
  return waterTest !== null
}

export function isWater(lng: number, lat: number): boolean {
  if (!waterTest) return true
  try {
    return waterTest(lng, lat)
  } catch {
    return true
  }
}

// Terrain elevation in (exaggerated) meters at a coordinate. 0 when unknown.
export function elevationAt(lng: number, lat: number): number {
  if (!elevationFn) return 0
  try {
    return elevationFn(lng, lat) || 0
  } catch {
    return 0
  }
}
