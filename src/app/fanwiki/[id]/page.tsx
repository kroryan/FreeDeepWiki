'use client';

import ChatWidget from '@/components/ChatWidget';
import Markdown from '@/components/Markdown';
import ThemeToggle from '@/components/theme-toggle';
import { useLanguage } from '@/contexts/LanguageContext';
import RepoInfo from '@/types/repoinfo';
import Link from 'next/link';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { FaExternalLinkAlt, FaHome, FaMagic, FaSearch } from 'react-icons/fa';

interface FanwikiMetadata {
  id: string;
  owner: string;
  repo: string;
  name: string;
  repo_type: 'fanwiki';
  submittedAt: number;
  start_url: string;
  page_count: number;
  description: string;
  main_page_path: string | null;
}

interface FanwikiIndexEntry {
  path: string;
  title: string;
  url: string;
  categories: string[];
}

interface FanwikiIndexResponse {
  entries: FanwikiIndexEntry[];
  truncated: boolean;
  totalArticles: number;
}

interface FanwikiPage extends FanwikiIndexEntry {
  content: string;
}

function resolveRelativePath(currentPath: string, value: string): string | null {
  const withoutFragment = value.split('#', 1)[0].split('?', 1)[0].trim();
  if (
    !withoutFragment ||
    withoutFragment.startsWith('#') ||
    /^(?:[a-z][a-z0-9+.-]*:|\/\/)/i.test(withoutFragment)
  ) {
    return null;
  }

  // Keep percent-encoded MediaWiki title characters intact: they are also
  // present in the imported filename (`Category%3AFoo.md`).
  const base = withoutFragment.startsWith('/')
    ? []
    : currentPath.split('/').slice(0, -1);
  const parts = [...base, ...withoutFragment.replace(/^\/+/, '').split('/')];
  const normalized: string[] = [];
  for (const part of parts) {
    if (!part || part === '.') continue;
    if (part === '..') {
      normalized.pop();
    } else {
      normalized.push(part);
    }
  }
  return normalized.join('/');
}

export default function FanwikiReaderPage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const fanwikiId = params.id as string;
  const pageParam = searchParams.get('page');
  const { language, messages } = useLanguage();

  const [metadata, setMetadata] = useState<FanwikiMetadata | null>(null);
  const [indexEntries, setIndexEntries] = useState<FanwikiIndexEntry[]>([]);
  const [indexTruncated, setIndexTruncated] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<FanwikiIndexEntry[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [currentPath, setCurrentPath] = useState<string | null>(pageParam);
  const [currentPage, setCurrentPage] = useState<FanwikiPage | null>(null);
  const [isPageLoading, setIsPageLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const repoInfo: RepoInfo | null = useMemo(() => {
    if (!metadata) return null;
    return {
      owner: metadata.owner,
      repo: metadata.repo,
      type: 'fanwiki',
      token: null,
      localPath: null,
      repoUrl: metadata.start_url,
    };
  }, [metadata]);

  useEffect(() => {
    if (!fanwikiId) return;
    setError(null);
    fetch(`/api/fanwiki/${encodeURIComponent(fanwikiId)}`, { cache: 'no-store' })
      .then(async (response) => {
        const body = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(body.detail || body.error || 'No se pudo abrir la wiki importada.');
        }
        return body as FanwikiMetadata;
      })
      .then((data) => {
        setMetadata(data);
        setCurrentPath((existing) => existing || data.main_page_path);
      })
      .catch((reason) => {
        setError(reason instanceof Error ? reason.message : 'No se pudo abrir la wiki importada.');
      });
  }, [fanwikiId]);

  useEffect(() => {
    if (!fanwikiId) return;
    fetch(`/api/fanwiki/${encodeURIComponent(fanwikiId)}/index?limit=500`, { cache: 'no-store' })
      .then((response) => response.json())
      .then((data: FanwikiIndexResponse) => {
        setIndexEntries(Array.isArray(data.entries) ? data.entries : []);
        setIndexTruncated(Boolean(data.truncated));
      })
      .catch(() => setIndexEntries([]));
  }, [fanwikiId]);

  useEffect(() => {
    if (!pageParam) return;
    setCurrentPath(pageParam);
  }, [pageParam]);

  useEffect(() => {
    if (!fanwikiId || !currentPath) return;
    setIsPageLoading(true);
    setError(null);
    fetch(
      `/api/fanwiki/${encodeURIComponent(fanwikiId)}/page?path=${encodeURIComponent(currentPath)}`,
      { cache: 'no-store' },
    )
      .then(async (response) => {
        const body = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(body.detail || body.error || 'No se pudo cargar el artículo.');
        }
        return body as FanwikiPage;
      })
      .then(setCurrentPage)
      .catch((reason) => {
        setCurrentPage(null);
        setError(reason instanceof Error ? reason.message : 'No se pudo cargar el artículo.');
      })
      .finally(() => setIsPageLoading(false));
  }, [fanwikiId, currentPath]);

  useEffect(() => {
    const normalized = query.trim();
    if (!normalized) {
      setResults([]);
      setIsSearching(false);
      return;
    }
    setIsSearching(true);
    const timer = window.setTimeout(() => {
      fetch(
        `/api/fanwiki/${encodeURIComponent(fanwikiId)}/search?q=${encodeURIComponent(normalized)}&limit=50`,
        { cache: 'no-store' },
      )
        .then((response) => response.json())
        .then((data) => setResults(Array.isArray(data) ? data : []))
        .catch(() => setResults([]))
        .finally(() => setIsSearching(false));
    }, 180);
    return () => window.clearTimeout(timer);
  }, [fanwikiId, query]);

  const openPage = useCallback((path: string) => {
    setCurrentPath(path);
    setCurrentPage(null);
    router.push(`/fanwiki/${encodeURIComponent(fanwikiId)}?page=${encodeURIComponent(path)}`);
  }, [fanwikiId, router]);

  const resolveInternalLink = useCallback((href: string) => {
    if (!currentPath) return null;
    const resolved = resolveRelativePath(currentPath, href);
    return resolved?.toLowerCase().endsWith('.md') ? resolved : null;
  }, [currentPath]);

  const resolveImageUrl = useCallback((src: string) => {
    if (!currentPath || /^(?:data:|https?:|\/\/)/i.test(src)) return src;
    const resolved = resolveRelativePath(currentPath, src);
    return resolved
      ? `/api/fanwiki/${encodeURIComponent(fanwikiId)}/asset?path=${encodeURIComponent(resolved)}`
      : src;
  }, [currentPath, fanwikiId]);

  const visibleEntries = query ? results : indexEntries;

  return (
    <div
      className="h-screen overflow-hidden flex flex-col bg-[var(--background)]"
      data-testid="fanwiki-reader"
    >
      <header className="border-b border-[var(--border-color)] px-4 py-3 flex items-center justify-between gap-4 shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <Link href="/" className="text-[var(--muted)] hover:text-[var(--accent-primary)]" title="Inicio">
            <FaHome className="h-4 w-4" />
          </Link>
          <div className="min-w-0">
            <h1 className="font-medium text-[var(--foreground)] truncate" data-testid="fanwiki-title">
              {metadata?.name || 'Cargando…'}
            </h1>
            {metadata && (
              <p className="text-xs text-[var(--muted)]">
                {metadata.page_count.toLocaleString()} artículos · XML de MediaWiki
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {metadata && (
            <Link
              href={`/?resume_fanwiki=${encodeURIComponent(metadata.start_url)}`}
              className="hidden sm:flex items-center gap-2 px-3 py-2 text-xs rounded-md border border-[var(--accent-primary)]/40 text-[var(--accent-primary)] hover:bg-[var(--accent-primary)]/10 transition-colors"
              title="Crear una wiki resumida y estructurada mediante el LLM"
            >
              <FaMagic />
              Generar con IA
            </Link>
          )}
          <ThemeToggle />
        </div>
      </header>

      {error && (
        <div className="px-4 py-2 border-b border-[var(--highlight)]/30 bg-[var(--highlight)]/10 text-[var(--highlight)] text-sm">
          {error}
        </div>
      )}

      <div className="flex-1 flex min-h-0">
        <aside className="w-72 md:w-80 shrink-0 border-r border-[var(--border-color)] flex flex-col min-h-0">
          <div className="p-3 border-b border-[var(--border-color)]">
            <div className="relative">
              <FaSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted)] h-3.5 w-3.5" />
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Buscar artículos…"
                aria-label="Buscar artículos"
                className="input-japanese w-full pl-9 pr-3 py-2 rounded-lg border-[var(--border-color)] bg-transparent text-sm text-[var(--foreground)] focus:outline-none focus:border-[var(--accent-primary)]"
              />
            </div>
          </div>
          <div className="flex-1 overflow-y-auto" data-testid="fanwiki-index">
            {isSearching && (
              <p className="p-3 text-xs text-[var(--muted)]">Buscando…</p>
            )}
            {!isSearching && query && visibleEntries.length === 0 && (
              <p className="p-3 text-xs text-[var(--muted)]">No hay resultados.</p>
            )}
            {visibleEntries.map((entry) => (
              <button
                key={entry.path}
                type="button"
                onClick={() => openPage(entry.path)}
                className={`block w-full text-left px-3 py-2 text-sm border-b border-[var(--border-color)]/50 hover:bg-[var(--card-bg)] transition-colors ${
                  currentPath === entry.path
                    ? 'bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]'
                    : 'text-[var(--foreground)]'
                }`}
              >
                {entry.title}
              </button>
            ))}
            {!query && indexTruncated && (
              <p className="p-3 text-xs text-[var(--muted)]">
                Mostrando los primeros {indexEntries.length.toLocaleString()} artículos. Usa la búsqueda para acceder al resto.
              </p>
            )}
          </div>
        </aside>

        <main id="fanwiki-content" className="flex-1 min-w-0 overflow-y-auto">
          {isPageLoading && (
            <div className="h-full flex items-center justify-center text-sm text-[var(--muted)]">
              Cargando artículo…
            </div>
          )}
          {!isPageLoading && currentPage && (
            <article className="max-w-5xl mx-auto px-6 py-8" data-testid="fanwiki-article">
              <div className="mb-6 border-b border-[var(--border-color)] pb-4 min-w-0">
                <div className="flex items-start justify-between gap-4">
                  <h2 className="text-2xl md:text-3xl font-bold font-serif text-[var(--foreground)]">
                    {currentPage.title}
                  </h2>
                  {currentPage.url && (
                    <a
                      href={currentPage.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="shrink-0 text-xs text-[var(--muted)] hover:text-[var(--accent-primary)] flex items-center gap-1.5"
                    >
                      Fuente <FaExternalLinkAlt className="h-3 w-3" />
                    </a>
                  )}
                </div>
                {currentPage.categories.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {currentPage.categories.slice(0, 12).map((category) => (
                      <span
                        key={category}
                        title={category}
                        className="px-2 py-0.5 rounded-full text-[11px] border border-[var(--border-color)] text-[var(--muted)] max-w-full truncate"
                      >
                        {category}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <Markdown
                content={currentPage.content}
                repoInfo={repoInfo || undefined}
                resolveInternalLink={resolveInternalLink}
                onInternalLink={openPage}
                resolveImageUrl={resolveImageUrl}
              />
            </article>
          )}
          {!isPageLoading && !currentPage && !error && (
            <div className="h-full flex items-center justify-center text-sm text-[var(--muted)]">
              Selecciona un artículo para leerlo.
            </div>
          )}
        </main>
      </div>

      <ChatWidget
        repoInfo={repoInfo}
        language={language}
        currentPageId={currentPath || undefined}
        title={messages.ask?.title || 'Chat con la wiki'}
        fabAriaLabel={messages.ask?.title || 'Preguntar a esta wiki'}
      />
    </div>
  );
}
