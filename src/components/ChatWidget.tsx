'use client';

import React, { useEffect, useRef, useState } from 'react';
import { FaComments, FaCompress, FaExpand, FaTimes } from 'react-icons/fa';
import Ask from './Ask';
import RepoInfo from '@/types/repoinfo';

interface ChatWidgetProps {
  // null means "not ready yet" (e.g. .zim metadata still loading) -- the
  // widget renders nothing rather than mounting Ask with an incomplete repoInfo.
  repoInfo: RepoInfo | null;
  provider?: string;
  model?: string;
  isCustomModel?: boolean;
  customModel?: string;
  language: string;
  currentPageId?: string;
  title: string;
  fabAriaLabel: string;
}

// Shared floating chat button + panel used by both the repo wiki page and the
// .zim reader page -- previously each duplicated this ~40 lines of JSX with
// its own open-state and Escape-key handling (only the repo page had the
// latter). Consolidated here so both get the same behavior, including the
// full-screen maximize toggle.
export default function ChatWidget({
  repoInfo,
  provider,
  model,
  isCustomModel,
  customModel,
  language,
  currentPageId,
  title,
  fabAriaLabel,
}: ChatWidgetProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isMaximized, setIsMaximized] = useState(false);
  const askComponentRef = useRef<{ clearConversation: () => void } | null>(null);

  // Escape closes the panel; if maximized, the first Escape just restores
  // it instead, matching how most apps handle a maximized window/modal.
  useEffect(() => {
    if (!isOpen) return;
    const handleEsc = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      if (isMaximized) {
        setIsMaximized(false);
      } else {
        setIsOpen(false);
      }
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [isOpen, isMaximized]);

  if (!repoInfo) return null;

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className={`fixed bottom-6 right-6 w-14 h-14 rounded-full bg-[var(--accent-primary)] text-black shadow-[0_0_20px_var(--shadow-color)] flex items-center justify-center hover:scale-105 transition-all z-50 ${isOpen ? 'opacity-0 pointer-events-none scale-90' : 'opacity-100'}`}
        aria-label={fabAriaLabel}
      >
        <FaComments className="text-xl" />
      </button>

      <div
        className={`fixed z-50 flex flex-col rounded-xl border border-[var(--border-color)] bg-[var(--card-bg)] shadow-[0_8px_40px_rgba(0,0,0,0.35),0_0_0_1px_var(--border-color)] backdrop-blur-xl overflow-hidden origin-bottom-right transition-all duration-250 ease-out ${
          isMaximized
            ? 'inset-4 sm:inset-8'
            : 'bottom-6 right-6 w-[calc(100vw-2rem)] sm:w-[420px] h-[min(680px,calc(100vh-6rem))] max-h-[calc(100vh-6rem)]'
        } ${
          isOpen
            ? 'opacity-100 scale-100 translate-y-0'
            : 'opacity-0 scale-95 translate-y-4 pointer-events-none'
        }`}
        aria-hidden={!isOpen}
      >
        {/* Neon top accent line, matching the sidebar/card treatment elsewhere */}
        <div className="h-[2px] w-full shrink-0 bg-gradient-to-r from-[var(--accent-primary)] via-[var(--accent-secondary)] to-transparent" />
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border-color)] shrink-0">
          <span className="text-sm font-semibold font-mono text-[var(--foreground)] flex items-center gap-2">
            <FaComments className="text-[var(--accent-primary)]" />
            {title}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setIsMaximized((v) => !v)}
              className="text-[var(--muted)] hover:text-[var(--accent-primary)] transition-colors rounded-full p-1.5 hover:bg-[var(--accent-primary)]/10"
              aria-label={isMaximized ? 'Restore' : 'Maximize'}
              title={isMaximized ? 'Restore' : 'Maximize'}
            >
              {isMaximized ? <FaCompress className="text-sm" /> : <FaExpand className="text-sm" />}
            </button>
            <button
              onClick={() => setIsOpen(false)}
              className="text-[var(--muted)] hover:text-[var(--accent-primary)] transition-colors rounded-full p-1.5 hover:bg-[var(--accent-primary)]/10"
              aria-label="Close"
            >
              <FaTimes className="text-base" />
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto min-h-0">
          <Ask
            repoInfo={repoInfo}
            provider={provider}
            model={model}
            isCustomModel={isCustomModel}
            customModel={customModel}
            language={language}
            currentPageId={currentPageId}
            onRef={(ref) => (askComponentRef.current = ref)}
          />
        </div>
      </div>
    </>
  );
}
