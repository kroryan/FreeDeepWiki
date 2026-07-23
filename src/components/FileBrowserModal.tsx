'use client';

import React, { useEffect, useState } from 'react';

interface FsEntry {
  name: string;
  is_dir: boolean;
  size: number | null;
}

interface FsListResponse {
  path: string;
  parent: string | null;
  entries: FsEntry[];
}

interface FileBrowserModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (path: string) => void;
  // 'file': clicking a file selects it immediately. 'directory': directories
  // are for navigation only, a "Select this folder" button confirms the
  // current directory itself.
  mode: 'file' | 'directory';
  // Comma-separated extensions (e.g. ".xml") to filter file entries by --
  // ignored (no files shown at all, only directories to navigate through)
  // when mode is 'directory'.
  extensions?: string;
  initialPath?: string;
  title?: string;
}

/**
 * Generic local-filesystem browser -- lets the user navigate directories and
 * pick a file or a folder, the same way a native "Open File"/"Open Folder"
 * dialog would, instead of requiring an absolute path typed from memory.
 * Not specific to any one feature (fanwiki XML import, images folder, ...):
 * backed by the generic GET /api/fs/list endpoint, so any picker in the app
 * can reuse this same component.
 */
export default function FileBrowserModal({
  isOpen, onClose, onSelect, mode, extensions, initialPath, title,
}: FileBrowserModalProps) {
  const [currentPath, setCurrentPath] = useState<string | null>(null);
  const [data, setData] = useState<FsListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Reset to the requested starting point every time the modal (re)opens,
  // rather than resuming wherever a previous session of it left off.
  useEffect(() => {
    if (isOpen) {
      setCurrentPath(initialPath || null);
      setData(null);
      setError(null);
    }
  }, [isOpen, initialPath]);

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    const params = new URLSearchParams();
    if (currentPath) params.set('path', currentPath);
    if (mode === 'file' && extensions) params.set('extensions', extensions);
    fetch(`/api/fs/list?${params.toString()}`)
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || `HTTP ${res.status}`);
        }
        return res.json();
      })
      .then((d: FsListResponse) => {
        if (cancelled) return;
        setData(d);
        setCurrentPath(d.path);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to list directory');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [isOpen, currentPath, mode, extensions]);

  if (!isOpen) return null;

  const joinPath = (dir: string, name: string) => `${dir}${dir.endsWith('/') ? '' : '/'}${name}`;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4">
      <div className="bg-[var(--card-bg)] border border-[var(--border-color)] rounded-lg shadow-custom w-full max-w-lg p-4 card-japanese max-h-[80vh] flex flex-col">
        <h3 className="text-base font-semibold text-[var(--foreground)] mb-2">
          {title || (mode === 'file' ? 'Select a file' : 'Select a folder')}
        </h3>
        <div className="text-xs text-[var(--muted)] mb-2 break-all font-mono">
          {data?.path || currentPath || '~'}
        </div>
        {error && <div className="text-[var(--highlight)] text-xs mb-2">{error}</div>}
        <div className="flex-1 overflow-y-auto rounded-md border border-[var(--border-color)] min-h-[200px]">
          {loading && <div className="p-3 text-xs text-[var(--muted)]">Loading…</div>}
          {!loading && data && (
            <>
              {data.parent !== null && (
                <button
                  type="button"
                  onClick={() => setCurrentPath(data.parent)}
                  className="w-full text-left px-3 py-1.5 text-sm hover:bg-[var(--background)] text-[var(--foreground)] border-b border-[var(--border-color)]/50"
                >
                  .. (up)
                </button>
              )}
              {data.entries.map((entry) => {
                const disabled = !entry.is_dir && mode === 'directory';
                return (
                  <button
                    key={entry.name}
                    type="button"
                    onClick={() => {
                      if (entry.is_dir) {
                        setCurrentPath(joinPath(data.path, entry.name));
                      } else if (mode === 'file') {
                        onSelect(joinPath(data.path, entry.name));
                        onClose();
                      }
                    }}
                    disabled={disabled}
                    className="w-full text-left px-3 py-1.5 text-sm hover:bg-[var(--background)] text-[var(--foreground)] flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <span>{entry.is_dir ? '📁' : '📄'}</span>
                    <span className="truncate">{entry.name}</span>
                  </button>
                );
              })}
              {data.entries.length === 0 && (
                <div className="p-3 text-xs text-[var(--muted)]">Empty folder</div>
              )}
            </>
          )}
        </div>
        <div className="flex justify-end gap-2 mt-3">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm text-[var(--foreground)] hover:bg-[var(--background)] transition-colors"
          >
            Cancel
          </button>
          {mode === 'directory' && (
            <button
              type="button"
              onClick={() => { if (data?.path) { onSelect(data.path); onClose(); } }}
              className="btn-japanese px-4 py-2 rounded-lg text-sm disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={!data?.path}
            >
              Select this folder
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
