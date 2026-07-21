'use client';

import React from 'react';
import { CVEFinding } from './types';
import { severityColor } from './config/colors';

interface Props {
  finding: CVEFinding;
  onClick: (finding: CVEFinding) => void;
}

export default function VulnFindingCard({ finding, onClick }: Props) {
  const color = severityColor(finding.severity);
  const priority = finding.ai_priority || 0;

  return (
    <button
      type="button"
      onClick={() => onClick(finding)}
      className="w-full text-left rounded-md border bg-[var(--card-bg)] hover:border-[var(--accent-primary)] transition-colors overflow-hidden focus:outline-none focus:border-[var(--accent-primary)]"
      style={{ borderLeftWidth: 4, borderLeftColor: color, borderColor: 'var(--border-color)' }}
    >
      <div className="p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span
                className="inline-flex items-center text-[10px] font-bold uppercase px-1.5 py-0.5 rounded text-white"
                style={{ backgroundColor: color }}
              >
                {finding.severity}
              </span>
              {finding.cvss_score != null && (
                <span className="text-[10px] text-[var(--muted)]">
                  CVSS {finding.cvss_score.toFixed(1)}
                </span>
              )}
              {finding.dev && (
                <span className="text-[10px] text-[var(--muted)] border border-[var(--border-color)] rounded px-1">
                  dev
                </span>
              )}
              {priority > 0 && (
                <span className="text-[10px] text-[var(--muted)]">
                  priority {priority}/5
                </span>
              )}
            </div>
            <div className="mt-1 font-mono text-sm text-[var(--foreground)] truncate">
              {finding.id}
            </div>
            <div className="text-xs text-[var(--muted)] truncate">
              {finding.package_name}@{finding.installed_version}
              {finding.fixed_version
                ? ` → fix ${finding.fixed_version}`
                : ' · no fix yet'}
            </div>
          </div>
        </div>
        {(finding.summary || finding.ai_impact_analysis) && (
          <p className="mt-2 text-xs text-[var(--foreground)]/80 line-clamp-2">
            {finding.ai_impact_analysis || finding.summary}
          </p>
        )}
        {finding.cwe_ids.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {finding.cwe_ids.slice(0, 3).map((cwe) => (
              <span
                key={cwe}
                className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--background)]/60 text-[var(--muted)]"
              >
                {cwe}
              </span>
            ))}
          </div>
        )}
      </div>
    </button>
  );
}