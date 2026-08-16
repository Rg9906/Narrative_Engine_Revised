import { useEffect, useRef, useState } from 'react'
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type SimulationNodeDatum,
} from 'd3-force'
import type { GraphData, GraphEdge, GraphNode, GraphNodeType } from '@/types/state'

export const NODE_TYPE_ORDER: GraphNodeType[] = ['character', 'world', 'theme', 'event', 'chapter']

export const NODE_TYPE_LABELS: Record<GraphNodeType, string> = {
  character: 'Characters',
  world: 'World',
  theme: 'Themes',
  event: 'Events',
  chapter: 'Chapters',
}

const NODE_TYPE_COLOR_VAR: Record<string, string> = {
  character: '--color-primary',
  world: '--color-success',
  theme: '--color-accent',
  event: '--color-warning',
  chapter: '--color-muted-foreground',
}

// Edges are tinted to match the color of the node type they connect a
// character to (world -> success green, theme -> accent purple), so the
// graph reads as "edges glow with the color of what they connect" instead
// of every non-relationship edge type looking identical. Falls back to the
// neutral border color for any type not listed here.
const EDGE_TYPE_COLOR_VAR: Record<string, string> = {
  relationship: '--color-primary',
  character_world: '--color-success',
  character_theme: '--color-accent',
  event_chapter: '--color-warning',
}

type SimNode = SimulationNodeDatum & GraphNode & { degree: number; fx?: number | null; fy?: number | null }
type SimLink = { id: string; type: string; source: SimNode | string; target: SimNode | string }

interface Transform {
  x: number
  y: number
  k: number
}

interface GraphCanvasProps {
  data: GraphData
  hiddenTypes: Set<string>
  searchQuery: string
  onNodeClick?: (node: GraphNode) => void
  className?: string
}

function readColor(varName: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(varName).trim() || '#999'
}

export function GraphCanvas({ data, hiddenTypes, searchQuery, onNodeClick, className }: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const nodesRef = useRef<SimNode[]>([])
  const linksRef = useRef<SimLink[]>([])
  const transformRef = useRef<Transform>({ x: 0, y: 0, k: 1 })
  const hiddenTypesRef = useRef(hiddenTypes)
  const searchRef = useRef(searchQuery.trim().toLowerCase())
  const hoveredRef = useRef<SimNode | null>(null)
  const draggingRef = useRef<SimNode | null>(null)
  const panRef = useRef<{ startX: number; startY: number; origin: Transform } | null>(null)
  const pointerMovedRef = useRef(0)
  const sizeRef = useRef({ width: 0, height: 0 })
  const [hoverInfo, setHoverInfo] = useState<{ node: SimNode; x: number; y: number } | null>(null)

  hiddenTypesRef.current = hiddenTypes
  searchRef.current = searchQuery.trim().toLowerCase()

  // Build / rebuild the simulation whenever the underlying graph data changes.
  useEffect(() => {
    const width = containerRef.current?.clientWidth ?? 800
    const height = containerRef.current?.clientHeight ?? 600

    const degree = new Map<string, number>()
    for (const e of data.edges) {
      degree.set(e.source, (degree.get(e.source) ?? 0) + 1)
      degree.set(e.target, (degree.get(e.target) ?? 0) + 1)
    }

    const nodes: SimNode[] = data.nodes.map((n) => ({
      ...n,
      degree: degree.get(n.id) ?? 0,
      x: width / 2 + (Math.random() - 0.5) * 200,
      y: height / 2 + (Math.random() - 0.5) * 200,
    }))
    const nodeById = new Map(nodes.map((n) => [n.id, n]))
    const links: SimLink[] = data.edges
      .filter((e) => nodeById.has(e.source) && nodeById.has(e.target))
      .map((e) => ({ id: e.id, type: e.type, source: e.source, target: e.target }))

    nodesRef.current = nodes
    linksRef.current = links
    transformRef.current = { x: 0, y: 0, k: 1 }

    const simulation = forceSimulation(nodes)
      .force(
        'link',
        forceLink<SimNode, SimLink>(links)
          .id((d) => d.id)
          .distance((l) => (l.type === 'relationship' ? 90 : 55))
          .strength(0.35),
      )
      .force('charge', forceManyBody().strength(-140).distanceMax(500))
      .force('center', forceCenter(width / 2, height / 2))
      .force(
        'collide',
        forceCollide<SimNode>().radius((d) => 6 + Math.sqrt(d.degree) * 3),
      )
      .alpha(1)
      .alphaDecay(0.02)

    return () => {
      simulation.stop()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data])

  // Resize handling.
  useEffect(() => {
    const container = containerRef.current
    const canvas = canvasRef.current
    if (!container || !canvas) return

    const observer = new ResizeObserver(() => {
      const dpr = window.devicePixelRatio || 1
      const { clientWidth, clientHeight } = container
      sizeRef.current = { width: clientWidth, height: clientHeight }
      canvas.width = clientWidth * dpr
      canvas.height = clientHeight * dpr
      canvas.style.width = `${clientWidth}px`
      canvas.style.height = `${clientHeight}px`
      const ctx = canvas.getContext('2d')
      ctx?.setTransform(dpr, 0, 0, dpr, 0, 0)
    })
    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  // Persistent render loop — independent of simulation ticking so pan/zoom stays smooth
  // even after the layout has settled and the simulation has stopped emitting ticks.
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    let raf = 0

    const draw = () => {
      raf = requestAnimationFrame(draw)
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      const { width, height } = sizeRef.current
      if (!width || !height) return

      ctx.clearRect(0, 0, width, height)
      const t = transformRef.current
      ctx.save()
      ctx.translate(t.x, t.y)
      ctx.scale(t.k, t.k)

      const hidden = hiddenTypesRef.current
      const query = searchRef.current
      const edgeColor = readColor('--color-border-strong')
      // Precomputed once per frame (not per edge) -- getComputedStyle is a real
      // DOM read and this loop runs for hundreds of edges at up to 60fps.
      const edgeColorByType: Record<string, string> = {}
      for (const [type, cssVar] of Object.entries(EDGE_TYPE_COLOR_VAR)) {
        edgeColorByType[type] = readColor(cssVar)
      }

      // Edges
      for (const link of linksRef.current) {
        const s = link.source as SimNode
        const tg = link.target as SimNode
        if (typeof s !== 'object' || typeof tg !== 'object') continue
        if (hidden.has(s.type) || hidden.has(tg.type)) continue
        ctx.beginPath()
        ctx.moveTo(s.x ?? 0, s.y ?? 0)
        ctx.lineTo(tg.x ?? 0, tg.y ?? 0)
        ctx.strokeStyle = edgeColorByType[link.type] ?? edgeColor
        ctx.globalAlpha = link.type === 'relationship' ? 0.28 : 0.14
        ctx.lineWidth = 1 / t.k
        ctx.stroke()
      }
      ctx.globalAlpha = 1

      // Nodes
      for (const node of nodesRef.current) {
        if (hidden.has(node.type)) continue
        const matches = query.length > 0 && node.label.toLowerCase().includes(query)
        const dimmed = query.length > 0 && !matches
        const radius = 4 + Math.sqrt(node.degree) * 3
        const color = readColor(NODE_TYPE_COLOR_VAR[node.type] ?? '--color-muted-foreground')

        ctx.beginPath()
        ctx.arc(node.x ?? 0, node.y ?? 0, radius, 0, Math.PI * 2)
        ctx.fillStyle = color
        ctx.globalAlpha = dimmed ? 0.12 : hoveredRef.current === node ? 1 : 0.88
        if (matches) {
          ctx.shadowColor = color
          ctx.shadowBlur = 16
        } else {
          ctx.shadowBlur = 0
        }
        ctx.fill()
        ctx.shadowBlur = 0

        if (matches || hoveredRef.current === node) {
          ctx.lineWidth = 1.5 / t.k
          ctx.strokeStyle = color
          ctx.globalAlpha = 1
          ctx.stroke()
        }

        if (t.k > 1.3 && !dimmed) {
          ctx.globalAlpha = 0.85
          ctx.fillStyle = readColor('--color-foreground')
          ctx.font = `${11 / t.k}px Inter, sans-serif`
          ctx.fillText(node.label, (node.x ?? 0) + radius + 4, (node.y ?? 0) + 4)
        }
      }
      ctx.globalAlpha = 1
      ctx.restore()
    }

    raf = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(raf)
  }, [])

  function toGraphSpace(clientX: number, clientY: number): { x: number; y: number } {
    const rect = canvasRef.current!.getBoundingClientRect()
    const t = transformRef.current
    return { x: (clientX - rect.left - t.x) / t.k, y: (clientY - rect.top - t.y) / t.k }
  }

  function findNodeAt(x: number, y: number): SimNode | null {
    let best: SimNode | null = null
    let bestDist = Infinity
    for (const node of nodesRef.current) {
      if (hiddenTypesRef.current.has(node.type)) continue
      const radius = 4 + Math.sqrt(node.degree) * 3 + 3
      const dx = (node.x ?? 0) - x
      const dy = (node.y ?? 0) - y
      const dist = Math.hypot(dx, dy)
      if (dist <= radius && dist < bestDist) {
        best = node
        bestDist = dist
      }
    }
    return best
  }

  function handlePointerDown(e: React.PointerEvent<HTMLCanvasElement>) {
    ;(e.target as HTMLCanvasElement).setPointerCapture(e.pointerId)
    pointerMovedRef.current = 0
    const pos = toGraphSpace(e.clientX, e.clientY)
    const node = findNodeAt(pos.x, pos.y)
    if (node) {
      draggingRef.current = node
      node.fx = node.x
      node.fy = node.y
    } else {
      panRef.current = { startX: e.clientX, startY: e.clientY, origin: { ...transformRef.current } }
    }
  }

  function handlePointerMove(e: React.PointerEvent<HTMLCanvasElement>) {
    if (draggingRef.current) {
      pointerMovedRef.current += 1
      const pos = toGraphSpace(e.clientX, e.clientY)
      draggingRef.current.fx = pos.x
      draggingRef.current.fy = pos.y
      draggingRef.current.x = pos.x
      draggingRef.current.y = pos.y
      return
    }
    if (panRef.current) {
      pointerMovedRef.current += 1
      const { startX, startY, origin } = panRef.current
      transformRef.current = { ...origin, x: origin.x + (e.clientX - startX), y: origin.y + (e.clientY - startY) }
      return
    }
    const pos = toGraphSpace(e.clientX, e.clientY)
    const node = findNodeAt(pos.x, pos.y)
    hoveredRef.current = node
    if (node) {
      const rect = canvasRef.current!.getBoundingClientRect()
      setHoverInfo({ node, x: e.clientX - rect.left, y: e.clientY - rect.top })
    } else {
      setHoverInfo(null)
    }
  }

  function handlePointerUp() {
    const moved = pointerMovedRef.current
    const node = draggingRef.current
    if (node) {
      node.fx = null
      node.fy = null
      if (moved < 4) onNodeClick?.(node)
    }
    draggingRef.current = null
    panRef.current = null
  }

  // Registered as a native, non-passive listener: React's JSX onWheel is passive by
  // default, which silently swallows preventDefault and lets the page scroll instead of
  // zooming the canvas.
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const rect = canvas.getBoundingClientRect()
      const cx = e.clientX - rect.left
      const cy = e.clientY - rect.top
      const t = transformRef.current
      const factor = Math.exp(-e.deltaY * 0.001)
      const nextK = Math.min(4, Math.max(0.15, t.k * factor))
      const scaleRatio = nextK / t.k
      transformRef.current = {
        k: nextK,
        x: cx - (cx - t.x) * scaleRatio,
        y: cy - (cy - t.y) * scaleRatio,
      }
    }

    canvas.addEventListener('wheel', onWheel, { passive: false })
    return () => canvas.removeEventListener('wheel', onWheel)
  }, [])

  return (
    <div ref={containerRef} className={className} style={{ position: 'relative', overflow: 'hidden' }}>
      <canvas
        ref={canvasRef}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={() => {
          hoveredRef.current = null
          setHoverInfo(null)
        }}
        style={{ cursor: draggingRef.current ? 'grabbing' : 'grab', touchAction: 'none', display: 'block' }}
      />
      {hoverInfo ? (
        <div
          className="pointer-events-none absolute z-10 max-w-[220px] rounded-lg border border-border bg-surface-raised px-2.5 py-1.5 text-xs shadow-elevated"
          style={{ left: hoverInfo.x + 14, top: hoverInfo.y + 14 }}
        >
          <p className="font-medium text-foreground">{hoverInfo.node.label}</p>
          <p className="capitalize text-muted-foreground">
            {hoverInfo.node.type} · {hoverInfo.node.degree} connection{hoverInfo.node.degree === 1 ? '' : 's'}
          </p>
        </div>
      ) : null}
    </div>
  )
}

export type { GraphNode, GraphEdge }
