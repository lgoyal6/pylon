'use client'
import React from 'react'
import { useSimStore } from '../sim/state'
import type { TourStep } from '../sim/state'

interface Slide {
  tag: string
  title: string
  body: string
  next: TourStep | 'done'
  cta: string
}

const SLIDES: Partial<Record<TourStep, Slide>> = {
  intro: {
    tag: '// SITUATION',
    title: 'Forward Operating Base — exposed perimeter.',
    body:
      'A FOB sits in contested terrain with no fixed surveillance grid. ' +
      'Conventional radar is line-of-sight, expensive, and a single point of ' +
      'failure. We need detection that scales with deployment, not budget.',
    next: 'deploy',
    cta: 'Deploy mesh',
  },
  meshed: {
    tag: '// MESH ONLINE',
    title: 'Self-organizing edge network.',
    body:
      'Each relay is an autonomous edge-compute node. On power-up they ' +
      'discover their neighbors over RF and form a self-healing mesh — no ' +
      'central server, no operator config. Knock one out and the topology ' +
      're-routes around the loss.',
    next: 'incoming',
    cta: 'Stage threat',
  },
  detected: {
    tag: '// CONTACT',
    title: 'Threat detected at perimeter.',
    body:
      'The nearest pylon picks up the unmanned system the moment it ' +
      'crosses into RF range. Classification and bearing are computed ' +
      'on-node — no cloud round-trip, no central correlator.',
    next: 'routing',
    cta: 'Route to FOB',
  },
  neutralized: {
    tag: '// NEUTRALIZED',
    title: 'Threat eliminated.',
    body:
      'Detection data hops through the mesh to the FOB, an interceptor is ' +
      'launched, and the target is neutralized at standoff range. End-to-end: ' +
      'detect → coordinate → engage, fully at the edge.',
    next: 'done',
    cta: 'Enter sandbox',
  },
}

const cardStyle: React.CSSProperties = {
  position: 'absolute',
  bottom: '36px',
  left: '50%',
  transform: 'translateX(-50%)',
  width: '460px',
  background: '#0c0d0fee',
  border: '1px solid #2a2b2e',
  padding: '18px 20px 16px',
  color: '#c5c7cb',
  fontFamily: 'inherit',
  fontSize: '13px',
  lineHeight: 1.55,
  letterSpacing: '0.01em',
  pointerEvents: 'auto',
  boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
  backdropFilter: 'blur(4px)',
  WebkitBackdropFilter: 'blur(4px)',
}

const tagStyle: React.CSSProperties = {
  fontSize: '10px',
  letterSpacing: '0.18em',
  color: '#9a9b9e',
  marginBottom: '8px',
  textTransform: 'uppercase',
}

const titleStyle: React.CSSProperties = {
  fontSize: '14px',
  color: '#e8eaee',
  marginBottom: '8px',
  letterSpacing: '0.02em',
}

const bodyStyle: React.CSSProperties = {
  color: '#9a9b9e',
  fontSize: '12px',
  marginBottom: '14px',
}

const buttonRow: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  gap: '8px',
}

const skipBtn: React.CSSProperties = {
  background: 'transparent',
  border: 'none',
  color: '#5a5b5e',
  cursor: 'pointer',
  padding: '4px 0',
  fontSize: '10px',
  letterSpacing: '0.15em',
  fontFamily: 'inherit',
  textTransform: 'uppercase',
}

const nextBtn: React.CSSProperties = {
  background: '#1a1b1e',
  border: '1px solid #3a3b3e',
  color: '#e8eaee',
  cursor: 'pointer',
  padding: '7px 14px',
  fontSize: '11px',
  letterSpacing: '0.12em',
  fontFamily: 'inherit',
  textTransform: 'uppercase',
}

const ghostCard: React.CSSProperties = {
  ...cardStyle,
  textAlign: 'center',
  width: 'auto',
  minWidth: '260px',
  padding: '10px 16px',
}

const ghostText: React.CSSProperties = {
  color: '#9a9b9e',
  fontSize: '11px',
  letterSpacing: '0.15em',
  textTransform: 'uppercase',
}

/**
 * Renders the scripted intro popups + the always-visible Skip control. Steps
 * with no popup ('deploy', 'incoming', 'routing') just show a thin "stage"
 * banner so the viewer knows something is happening; the camera and visuals
 * carry the story.
 */
export default function TourOverlay() {
  const active = useSimStore(s => s.tour.active)
  const step = useSimStore(s => s.tour.step)
  const setTourStep = useSimStore(s => s.setTourStep)
  const skipTour = useSimStore(s => s.skipTour)

  if (!active) return null

  const slide = SLIDES[step]

  const handleNext = () => {
    if (!slide) return
    if (slide.next === 'done') {
      skipTour()
      return
    }
    setTourStep(slide.next)
  }

  const stageLabels: Partial<Record<TourStep, string>> = {
    deploy: 'Relays deploying around FOB…',
    incoming: 'Hostile UAV inbound — watch the perimeter',
    routing: 'Detection data routing through mesh…',
  }

  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        pointerEvents: 'none',
        zIndex: 50,
      }}
    >
      {/* Always-on Skip in top right, doesn't block the map. */}
      <button
        onClick={skipTour}
        style={{
          position: 'absolute',
          top: '14px',
          right: '14px',
          pointerEvents: 'auto',
          background: '#0c0d0fcc',
          border: '1px solid #2a2b2e',
          color: '#9a9b9e',
          cursor: 'pointer',
          padding: '6px 12px',
          fontSize: '10px',
          letterSpacing: '0.15em',
          fontFamily: 'inherit',
          textTransform: 'uppercase',
        }}
      >
        Skip intro
      </button>

      {slide && (
        <div style={cardStyle}>
          <div style={tagStyle}>{slide.tag}</div>
          <div style={titleStyle}>{slide.title}</div>
          <div style={bodyStyle}>{slide.body}</div>
          <div style={buttonRow}>
            <button style={skipBtn} onClick={skipTour}>
              Skip
            </button>
            <button style={nextBtn} onClick={handleNext}>
              {slide.cta} →
            </button>
          </div>
        </div>
      )}

      {!slide && stageLabels[step] && (
        <div style={ghostCard}>
          <span style={ghostText}>{stageLabels[step]}</span>
        </div>
      )}
    </div>
  )
}
