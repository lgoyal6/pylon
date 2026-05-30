import type { Relay, Connection } from './mesh'

export function findPath(
  fromId: string,
  toId: string,
  relays: Relay[],
  connections: Connection[]
): string[] | null {
  const adjacency = new Map<string, string[]>()
  relays.forEach(r => adjacency.set(r.id, []))

  connections
    .filter(c => c.status === 'active' || c.status === 'rerouted')
    .forEach(c => {
      adjacency.get(c.from)?.push(c.to)
      adjacency.get(c.to)?.push(c.from)
    })

  const queue: string[][] = [[fromId]]
  const visited = new Set<string>([fromId])

  while (queue.length > 0) {
    const path = queue.shift()!
    const current = path[path.length - 1]
    if (current === toId) return path
    for (const neighbor of adjacency.get(current) || []) {
      if (!visited.has(neighbor)) {
        visited.add(neighbor)
        queue.push([...path, neighbor])
      }
    }
  }
  return null
}
