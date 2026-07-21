'use client';

import { useEffect, useMemo, useRef } from 'react';
import ForceGraph3D, { ForceGraphMethods, NodeObject, LinkObject } from 'react-force-graph-3d';
import SpriteText from 'three-spritetext';
import { GraphData, GraphNode, Severity } from './types';
import { SEVERITY_COLORS, NODE_COLORS } from './config/colors';
import { cveNodeRadius, packageNodeRadius, FILE_NODE_SIZE, CWE_NODE_SIZE, FIX_NODE_SIZE } from './config/sizes';
import { GRAPH_CONFIG, CAMERA_DISTANCE } from './config/graph';

interface Props {
  graph: GraphData;
  onNodeClick?: (node: GraphNode) => void;
  height?: number;
}

// Minimal local typings for the force-graph runtime objects (the library's
// own types are loose; we only use a handful of fields).
interface FGNode {
  id: string;
  type?: string;
  severity?: Severity | null;
  cvss_score?: number | null;
  cve_count?: number | null;
  label?: string;
  __raw?: GraphNode;
  x?: number;
  y?: number;
  z?: number;
}
interface FGLink {
  source: string;
  target: string;
  label: string;
}

const MAX_NODES_3D = 250;

/**
 * The actual 3D force graph. Only ever loaded client-side (the parent wraps it
 * in next/dynamic with ssr:false) so Three.js never runs during SSR.
 */
export default function VulnGraph3DInner({ graph, onNodeClick, height = 460 }: Props) {
  const fgRef = useRef<ForceGraphMethods<NodeObject<FGNode>, LinkObject<FGNode, FGLink>> | undefined>(undefined);

  const data = useMemo(() => prepareData(graph), [graph]);

  useEffect(() => {
    const fg = fgRef.current;
    if (fg) {
      // frame the graph
      fg.cameraPosition({ z: CAMERA_DISTANCE });
      const t = setTimeout(() => fg.zoomToFit(200, 60), 600);
      return () => clearTimeout(t);
    }
    return undefined;
  }, [data]);

  if (!data.nodes.length) {
    return (
      <div className="flex items-center justify-center text-[var(--muted)] text-sm"
           style={{ height }}>
        No vulnerable dependencies to graph.
      </div>
    );
  }

  return (
    <div style={{ height }} className="rounded-md border border-[var(--border-color)] bg-[var(--background)]/40 overflow-hidden">
      <ForceGraph3D
        ref={fgRef}
        graphData={data}
        nodeRelSize={GRAPH_CONFIG.nodeRelSize}
        cooldownTicks={GRAPH_CONFIG.cooldownTicks}
        d3AlphaDecay={GRAPH_CONFIG.d3AlphaDecay}
        d3VelocityDecay={GRAPH_CONFIG.d3VelocityDecay}
        linkDirectionalArrowLength={4}
        linkDirectionalArrowRelPos={1}
        linkLabel={(l: FGLink) => l.label}
        linkColor={() => 'rgba(148,163,184,0.5)'}
        linkWidth={0.6}
        nodeColor={nodeColor}
        nodeVal={nodeVal}
        nodeLabel={nodeLabel}
        nodeThreeObject={nodeThreeObject}
        nodeThreeObjectExtend
        onNodeClick={(n: FGNode) => {
          if (n.__raw) onNodeClick?.(n.__raw);
        }}
        showNavInfo={false}
        backgroundColor="rgba(0,0,0,0)"
      />
    </div>
  );
}

function prepareData(graph: GraphData) {
  // Keep worst CVEs + their neighbours; cap total for perf.
  const cveNodes = graph.nodes.filter((n) => n.type === 'cve');
  cveNodes.sort(sevCompare);
  const keep = new Set<string>();
  for (const n of cveNodes.slice(0, MAX_NODES_3D)) keep.add(n.id);
  const keepLinks = graph.links.filter((l) => keep.has(l.source) || keep.has(l.target));
  for (const l of keepLinks) { keep.add(l.source); keep.add(l.target); }
  const keepNodes = graph.nodes.filter((n) => keep.has(n.id));

  return {
    nodes: keepNodes.map((n) => ({ ...n, __raw: n })) as FGNode[],
    links: keepLinks.map((l) => ({ source: l.source, target: l.target, label: l.label })) as FGLink[],
  };
}

function sevCompare(a: GraphNode, b: GraphNode) {
  const r: Record<Severity, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, UNKNOWN: 4 };
  return r[a.severity || 'UNKNOWN'] - r[b.severity || 'UNKNOWN'];
}

function nodeColor(node: FGNode): string {
  const n = node.__raw ?? (node as unknown as GraphNode);
  if (n.type === 'cve') return SEVERITY_COLORS[(n.severity as Severity) || 'UNKNOWN'] || SEVERITY_COLORS.UNKNOWN;
  return NODE_COLORS[n.type] || '#94a3b8';
}

function nodeVal(node: FGNode): number {
  const n = node.__raw ?? (node as unknown as GraphNode);
  switch (n.type) {
    case 'cve': return cveNodeRadius(n.cvss_score, n.severity ?? 'UNKNOWN');
    case 'package': return packageNodeRadius(n.cve_count);
    case 'cwe': return CWE_NODE_SIZE;
    case 'fix': return FIX_NODE_SIZE;
    case 'file': return FILE_NODE_SIZE;
    default: return FILE_NODE_SIZE;
  }
}

function nodeLabel(node: FGNode): string {
  const n = node.__raw ?? (node as unknown as GraphNode);
  if (n.type === 'cve') {
    return `${n.label} — ${n.severity || 'UNKNOWN'}` +
      (n.cvss_score != null ? ` (CVSS ${n.cvss_score.toFixed(1)})` : '');
  }
  return n.label || '';
}

function nodeThreeObject(node: FGNode): SpriteText | null {
  const n = node.__raw ?? (node as unknown as GraphNode);
  // Only label the meaningful nodes; files are too numerous and clutter 3D.
  if (n.type === 'file') return null;
  const sprite = new SpriteText(n.label || '');
  sprite.color = '#e2e8f0';
  sprite.backgroundColor = n.type === 'cwe'
    ? SEVERITY_COLORS[(n.severity as Severity) || 'UNKNOWN']
    : NODE_COLORS[n.type] || '#334155';
  sprite.padding = 2;
  sprite.textHeight = 4;
  // three ships untyped in this build, so the inherited Object3D.position isn't
  // visible on the SpriteText type — cast through unknown to nudge the label
  // above the node sphere. (Runtime: SpriteText is a THREE.Sprite, has position.)
  (sprite as unknown as { position: { y: number } }).position.y = 8;
  return sprite;
}