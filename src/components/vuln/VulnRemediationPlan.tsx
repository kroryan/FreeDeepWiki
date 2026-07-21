'use client';

import React from 'react';
import { RemediationPlan } from './types';
import { severityColor } from './config/colors';

interface Props {
  plan?: RemediationPlan;
}

const INFO_COLOR = '#64748b';

export default function VulnRemediationPlan({ plan }: Props) {
  if (!plan || plan.steps.length === 0) {
    return (
      <div className="p-6 rounded-md border border-[var(--border-color)] bg-[var(--card-bg)] text-sm text-[var(--muted)]">
        No actionable remediation steps for this scan. 🎉
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="p-4 rounded-md border border-[var(--border-color)] bg-[var(--background)]/40">
        <h3 className="text-sm font-semibold text-[var(--accent-primary)] mb-1">🛠️ Suggested Solutions</h3>
        <p className="text-sm text-[var(--foreground)]/80">{plan.summary}</p>
      </div>

      <ol className="space-y-2">
        {plan.steps.map((step, i) => {
          const color = step.severity === 'INFO' ? INFO_COLOR : severityColor(step.severity as never);
          return (
            <li
              key={`${step.action}-${i}`}
              className="p-4 rounded-md border border-[var(--border-color)] bg-[var(--card-bg)]"
            >
              <div className="flex items-start gap-3">
                <span
                  className="shrink-0 mt-0.5 h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: color }}
                  title={step.severity}
                />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-[var(--foreground)] font-medium">{step.action}</p>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-[var(--muted)]">
                    <span
                      className="px-1.5 py-0.5 rounded font-mono"
                      style={{ backgroundColor: `${color}22`, color }}
                    >
                      {step.severity}
                    </span>
                    <span>
                      resolves {step.affected_count} finding{step.affected_count === 1 ? '' : 's'}
                    </span>
                    {step.category && <span>· {step.category}</span>}
                  </div>
                  {step.finding_titles.length > 0 && (
                    <details className="mt-2 text-xs text-[var(--muted)]">
                      <summary className="cursor-pointer hover:text-[var(--foreground)]">
                        Affected: {step.finding_titles.slice(0, 3).join(', ')}
                        {step.finding_titles.length > 3 ? ` +${step.finding_titles.length - 3} more` : ''}
                      </summary>
                      <ul className="mt-1 ml-4 list-disc space-y-0.5">
                        {step.finding_titles.map((t) => (
                          <li key={t}>{t}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
