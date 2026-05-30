// RF signal ingestion layer.
//
// The dashboard is built to take in real RF telemetry. Everything downstream
// (Selection panel, bottom signal chart, roster) reads from a single stream of
// `RFSample`s pushed into the store via `ingestRf`. Today a SimulatedRFSource
// synthesizes plausible samples; swap in WebSocketRFSource (point it at your
// SDR / receiver backend) and the same UI renders live data with no other
// changes.

export type RFMode = 'SIMULATED' | 'LIVE'

export interface RFSample {
  nodeId: string   // asset this sample belongs to (relay/FOB id)
  t: number        // epoch ms
  rssiDbm: number  // received signal strength, dBm (~ -100 weak .. -40 strong)
  snrDb: number    // signal-to-noise ratio, dB
  freqMhz: number  // carrier frequency, MHz
}

export interface RFSource {
  start(onSample: (s: RFSample) => void): void
  stop(): void
}

// Per-node ring-buffer length and default band (UHF, matches captured signal).
export const RF_BUFFER = 256
export const RF_BASE_FREQ_MHZ = 349.7

export interface RFNodeHint {
  id: string
  linkCount: number
  alert?: boolean
}

// Synthesizes RF telemetry for the current online nodes. Used until a real
// source is connected. rssi improves with link count, degrades on alert; snr
// drops when a node is under threat; frequency drifts slightly around the band.
export class SimulatedRFSource implements RFSource {
  private timer: ReturnType<typeof setInterval> | null = null
  private phase = 0
  constructor(
    private getNodes: () => RFNodeHint[],
    private intervalMs = 250,
  ) {}

  start(onSample: (s: RFSample) => void) {
    this.stop()
    this.timer = setInterval(() => {
      this.phase += 0.3
      const now = Date.now()
      for (const n of this.getNodes()) {
        const linkBoost = Math.min(n.linkCount, 4) * 4
        const wob = Math.sin(this.phase + n.id.charCodeAt(n.id.length - 1)) * 3
        const noise = (Math.random() - 0.5) * 4
        const rssiDbm = Math.round(-78 + linkBoost + wob + noise - (n.alert ? 6 : 0))
        const snrDb = Math.round(18 + (Math.random() - 0.5) * 4 - (n.alert ? 8 : 0))
        const freqMhz = Math.round((RF_BASE_FREQ_MHZ + (Math.random() - 0.5) * 6) * 10) / 10
        onSample({ nodeId: n.id, t: now, rssiDbm, snrDb, freqMhz })
      }
    }, this.intervalMs)
  }

  stop() {
    if (this.timer) clearInterval(this.timer)
    this.timer = null
  }
}

// Real RF over a WebSocket. Expects JSON messages shaped like RFSample (also
// tolerates {nodeId, rssi, snr, freq}). Point `url` at your receiver bridge.
export class WebSocketRFSource implements RFSource {
  private ws: WebSocket | null = null
  constructor(private url: string) {}

  start(onSample: (s: RFSample) => void) {
    this.ws = new WebSocket(this.url)
    this.ws.onmessage = (e: MessageEvent) => {
      try {
        const d = JSON.parse(e.data)
        if (!d || !d.nodeId) return
        onSample({
          nodeId: String(d.nodeId),
          t: typeof d.t === 'number' ? d.t : Date.now(),
          rssiDbm: d.rssiDbm ?? d.rssi ?? -70,
          snrDb: d.snrDb ?? d.snr ?? 10,
          freqMhz: d.freqMhz ?? d.freq ?? RF_BASE_FREQ_MHZ,
        })
      } catch {
        /* ignore malformed frames */
      }
    }
  }

  stop() {
    this.ws?.close()
    this.ws = null
  }
}
