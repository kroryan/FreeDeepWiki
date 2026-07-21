'use client';

import React from 'react';
import { VulnReport, SEVERITY_ORDER } from './types';
import { severityColor } from './config/colors';

interface Props {
  report: VulnReport;
}

export default function VulnOverview({ report }: Props) {
  return (
    <div className="mb-4">
      <h3 className="text-base font-semibold text-[var(--foreground)] mb-3">
        📊 Vulnerability Overview
      </h3>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
        {SEVERITY_ORDER.map((sev) => (
          <div
            key={sev}
            className="rounded-md border bg-[var(--card-bg)] p-3 text-center"
            style={{ borderColor: 'var(--border-color)' }}
          >
            <div className="text-2xl font-bold" style={{ color: severityColor(sev) }}>
              {report.counts[sev] ?? 0}
            </div>
            <div className="text-[10px] uppercase tracking-wide text-[var(--muted)] mt-0.5">
              {sev}
            </div>
          </div>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--muted)]">
        <span>Total findings: <strong className="text-[var(--foreground)]">{report.total_findings}</strong></span>
        <span>Dependencies scanned: <strong className="text-[var(--foreground)]">{report.total_dependencies_scanned}</strong></span>
        <span>AI analysis: <strong className="text-[var(--foreground)]">{report.ai_analyzed ? 'yes' : 'defaults'}</strong></span>
        {report.generated_at && (
          <span>Generated: <strong className="text-[var(--foreground)]">{new Date(report.generated_at).toLocaleString()}</strong></span>
        )}
      </div>
    </div>
  );
}