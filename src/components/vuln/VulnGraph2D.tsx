'use client';

import React, { useMemo } from 'react';
import Mermaid from '@/components/Mermaid';
import { GraphData, GraphNode, Severity } from './types';
import { SEVERITY_COLORS } from './config/colors';

interface Props {
  graph: GraphData;
  height?: number;
}

const MAX_CVE_NODES = 40; // keep the mermaid diagram readable

/**
 * Renders the vulnerability graph as a Mermaid flowchart (always available,
 * no extra deps). Used both as a standalone "2D" view and as the automatic
 * fallback when the 3D view can't load.
 */
export default function VulnGraph2D({ graph, height = 460 }: Props) {
  const chart = useMemo(() => buildMermaid(graph), [graph]);

  if (!graph.nodes.length) {
    return (
      <div className="flex items-center justify-center text-[var(--muted)] text-sm"
           style={{ height }}>
        No vulnerable dependencies to graph.
      </div>
    );
  }

  return (
    <div style={{ height }} className="overflow-auto rounded-md border border-[var(--border-color)] bg-[var(--card-bg)] p-2">
      <Mermaid chart={chart} zoomingEnabled />
    </div>
  );
}

function sanitizeId(id: string): string {
  return 'n' + id.replace(/[^A-Za-z0-9]/g, '_');
}

function buildMermaid(graph: GraphData): string {
  // Rank CVE nodes by severity, keep only the worst MAX_CVE_NODES to avoid
  // exploding mermaid on huge reports.
  const sevRank: Record<Severity, number> = {
    CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, UNKNOWN: 4,
  };
  const cveNodes = graph.nodes
    .filter((n) => n.type === 'cve')
    .sort((a, b) => (sevRank[a.severity || 'UNKNOWN'] - sevRank[b.severity || 'UNKNOWN']))
    .slice(0, MAX_CVE_NODES);
  const keepIds = new Set<string>(cveNodes.map((n) => n.id));

  // also keep package/cwe/fix/file nodes adjacent to kept CVEs
  const keepLinks = graph.links.filter(
    (l) => keepIds.has(l.source) || keepIds.has(l.target),
  );
  for (const l of keepLinks) {
    keepIds.add(l.source);
    keepIds.add(l.target);
  }
  const keepNodes = graph.nodes.filter((n) => keepIds.has(n.id));

  const lines: string[] = ['graph LR'];

  for (const node of keepNodes) {
    lines.push(`  ${nodeLine(node)}`);
  }
  for (const link of keepLinks) {
    lines.push(
      `  ${sanitizeId(link.source)} -->|${link.label}| ${sanitizeId(link.target)}`,
    );
  }

  // classDef colours
  lines.push(`  classDef crit fill:${SEVERITY_COLORS.CRITICAL},color:#fff,stroke:#7f1d1d;`);
  lines.push(`  classDef high fill:${SEVERITY_COLORS.HIGH},color:#fff,stroke:#7f1d1d;`);
  lines.push(`  classDef med fill:${SEVERITY_COLORS.MEDIUM},color:#000,stroke:#78350f;`);
  lines.push(`  classDef low fill:${SEVERITY_COLORS.LOW},color:#fff,stroke:#14532d;`);
  lines.push(`  classDef unk fill:${SEVERITY_COLORS.UNKNOWN},color:#fff,stroke:#334155;`);
  lines.push(`  classDef pkg fill:#3b82f6,color:#fff,stroke:#1e3a8a;`);
  lines.push(`  classDef cwe fill:#a855f7,color:#fff,stroke:#581c87;`);
  lines.push(`  classDef fix fill:#22c55e,color:#fff,stroke:#14532d;`);
  lines.push(`  classDef file fill:#94a3b8,color:#000,stroke:#334155;`);

  // assign classes
  const classAssign: string[] = [];
  for (const node of keepNodes) {
    const sid = sanitizeId(node.id);
    if (node.type === 'cve') {
      const cls = node.severity === 'CRITICAL' ? 'crit'
        : node.severity === 'HIGH' ? 'high'
        : node.severity === 'MEDIUM' ? 'med'
        : node.severity === 'LOW' ? 'low' : 'unk';
      classAssign.push(`class ${sid} ${cls};`);
    } else if (node.type === 'package') classAssign.push(`class ${sid} pkg;`);
    else if (node.type === 'cwe') classAssign.push(`class ${sid} cwe;`);
    else if (node.type === 'fix') classAssign.push(`class ${sid} fix;`);
    else if (node.type === 'file') classAssign.push(`class ${sid} file;`);
  }
  lines.push(...classAssign);

  return lines.join('\n');
}

function nodeLine(node: GraphNode): string {
  const sid = sanitizeId(node.id);
  const label = escapeMermaid(node.label);
  if (node.type === 'cve') {
    const sev = node.severity || 'UNKNOWN';
    const cvss = node.cvss_score != null ? ` ${node.cvss_score.toFixed(1)}` : '';
    return `${sid}["🔴 ${label}<br/>${sev}${cvss}"]`;
  }
  if (node.type === 'package') return `${sid}["📦 ${label}"]`;
  if (node.type === 'cwe') return `${sid}["🏷️ ${label}"]`;
  if (node.type === 'fix') return `${sid}["🛡️ ${label}"]`;
  return `${sid}["📁 ${label}"]`;
}

function escapeMermaid(s: string): string {
  // mermaid node text with htmlLabels: escape quotes and brackets
  return s.replace(/"/g, "'").replace(/[<>]/g, (c) => (c === '<' ? '&lt;' : '&gt;'));
}