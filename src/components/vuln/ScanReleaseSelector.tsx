'use client';

import React from 'react';
import { FaHistory, FaSync, FaTrash } from 'react-icons/fa';
import { ScanRelease } from './types';

interface Props {
  releases: ScanRelease[];
  selectedVersion: number | null;
  onSelectVersion: (version: number) => void;
  onDeleteVersion: (version: number) => void;
  onRerun?: () => void;
  disabled?: boolean;
}

/**
 * Version-history dropdown for a vulnerability/website-security scan --
 * mirrors the wiki's "Wiki Release" dropdown, but scoped to a scan's own
 * releases so past scans stay reachable instead of only ever showing the
 * latest one. Shown as soon as there's at least one saved release (matching
 * the wiki dropdown's `length > 0` threshold) -- it previously required 2+
 * releases before rendering at all, which hid it entirely for anyone who'd
 * only ever run one scan.
 */
export default function ScanReleaseSelector({
  releases, selectedVersion, onSelectVersion, onDeleteVersion, onRerun, disabled = false,
}: Props) {
  if (releases.length === 0) return null;

  return (
    <div className="mb-3">
      <label className="flex items-center text-xs text-[var(--muted)] mb-1.5 font-mono">
        <FaHistory className="mr-1.5" />
        Scan History
      </label>
      <div className="flex items-stretch gap-2">
        <select
          value={selectedVersion ?? ''}
          onChange={(e) => {
            const v = Number(e.target.value);
            if (!Number.isNaN(v) && v > 0) onSelectVersion(v);
          }}
          disabled={disabled}
          className="flex-1 min-w-0 text-xs px-3 py-2 bg-[var(--background)] text-[var(--foreground)] rounded-md border border-[var(--border-color)] disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:border-[var(--accent-primary)] transition-colors hover:cursor-pointer"
        >
          {releases.map((release) => {
            const date = new Date(release.created_at);
            const dateStr = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
            return (
              <option key={release.id} value={release.version}>
                v{release.version} — {dateStr} ({release.total_findings ?? '?'} findings)
              </option>
            );
          })}
        </select>
        {onRerun && (
          <button
            type="button"
            onClick={onRerun}
            disabled={disabled}
            title="Rerun scan"
            aria-label="Rerun scan"
            className="flex items-center gap-1.5 px-3 text-xs bg-[var(--background)] text-[var(--foreground)] rounded-md border border-[var(--border-color)] hover:border-[var(--accent-primary)] hover:text-[var(--accent-primary)] disabled:opacity-50 disabled:cursor-not-allowed transition-colors hover:cursor-pointer"
          >
            <FaSync />
            Rerun
          </button>
        )}
        <button
          type="button"
          onClick={() => { if (selectedVersion != null) onDeleteVersion(selectedVersion); }}
          disabled={disabled || selectedVersion == null}
          title="Delete selected release"
          aria-label="Delete selected release"
          className="flex items-center justify-center px-3 text-xs bg-[var(--background)] text-[var(--highlight)] rounded-md border border-[var(--border-color)] hover:bg-[var(--highlight)]/10 disabled:opacity-50 disabled:cursor-not-allowed transition-colors hover:cursor-pointer"
        >
          <FaTrash />
        </button>
      </div>
    </div>
  );
}
