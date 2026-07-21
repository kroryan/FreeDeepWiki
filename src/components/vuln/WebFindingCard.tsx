'use client';

import React from 'react';
import { WebFinding } from './webTypes';
import { SEVERITY_COLORS } from './config/colors';

const INFO_COLOR = '#64748b';

function webSeverityColor(sev: string): string {
  return (SEVERITY_COLORS as Record<string, string>)[sev] ?? INFO_COLOR;
}

interface Props {
  finding: WebFinding;
  onClick: (finding: WebFinding) => void;
}

export default function WebFindingCard({ finding, onClick }: Props) {
  const color = webSeverityColor(finding.severity);

  return (
    <button
      type="button"
      onClick={() => onClick(finding)}
      className="text-left p-3 rounded-md border border-[var(--border-color)] bg-[var(--card-bg)] hover:border-[var(--accent-primary)] transition-colors"
    >
      <div className="flex items-start justify-between gap-2 mb-1">
        <span
          className="px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold shrink-0"
          style={{ backgroundColor: `${color}22`, color }}
        >
          {finding.severity}
        </span>
        {finding.ai_proposed && (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-[var(--accent-primary)]/15 text-[var(--accent-primary)] shrink-0">
            AI-proposed
          </span>
        )}
        {finding.ai_dismissed && (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-[var(--muted)]/15 text-[var(--muted)] shrink-0">
            likely false positive
          </span>
        )}
      </div>
      <p className="text-sm text-[var(--foreground)] font-medium line-clamp-2">{finding.title}</p>
      {finding.url && (
        <p className="text-xs text-[var(--muted)] mt-1 truncate">{finding.url}</p>
      )}
      {finding.cve_id && (
        <p className="text-xs text-[var(--muted)] mt-0.5 font-mono">{finding.cve_id}</p>
      )}
    </button>
  );
}
