'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import WikiTreeView from '@/components/WikiTreeView';
import Markdown from '@/components/Markdown';

// Local types matching WikiTreeView's own interface (which requires
// sections/rootSections as non-optional arrays). The backend cache may omit
// them (the canonical src/types/wiki types mark them optional), so we
// normalize at load time below.
interface WikiPage {
  id: string;
  title: string;
  content: string;
  filePaths: string[];
  importance: 'high' | 'medium' | 'low';
  relatedPages: string[];
}
interface WikiSection {
  id: string;
  title: string;
  pages: string[];
  subsections?: string[];
}
interface WikiStructure {
  id: string;
  title: string;
  description: string;
  pages: WikiPage[];
  sections: WikiSection[];
  rootSections: string[];
}
interface WikiCache {
  wiki_structure: Partial<WikiStructure>;
  generated_pages: Record<string, WikiPage>;
}

// A shared wiki is a READ-ONLY view of one generated wiki release, addressed
// by an opaque share ID instead of owner/repo. The flow:
//   1. GET /api/share/<id>  -> resolves to {owner, repo, repo_type, language, version}
//   2. GET /api/wiki_cache?... -> loads the actual wiki (the share stores
//      only a pointer, never the content, so sharing doesn't duplicate data
//      and a deleted wiki invalidates its share automatically).
//
// This intentionally does NOT replicate the 4700-line [owner]/[repo] page --
// a share is for reading, not regenerating/chatting. Tree + rendered page
// only, reusing the existing WikiTreeView and Markdown components.

type ShareResolution = {
  owner?: string | null;
  repo: string;
  repo_type: string;
  language: string;
  version?: string | null;
  title?: string | null;
};

function normalizeStructure(raw: Partial<WikiStructure>): WikiStructure {
  return {
    id: raw.id || 'shared',
    title: raw.title || '',
    description: raw.description || '',
    pages: raw.pages || [],
    sections: raw.sections || [],
    rootSections: raw.rootSections || [],
  };
}

export default function SharePage() {
  const params = useParams<{ id: string }>();
  const shareId = params?.id;

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [resolution, setResolution] = useState<ShareResolution | null>(null);
  const [wiki, setWiki] = useState<WikiCache | null>(null);
  const [currentPageId, setCurrentPageId] = useState<string | undefined>(undefined);

  useEffect(() => {
    if (!shareId) return;
    let cancelled = false;
    (async () => {
      try {
        // 1) resolve the share -> wiki pointer
        const resRes = await fetch(`/api/share/${encodeURIComponent(shareId)}`, { cache: 'no-store' });
        if (resRes.status === 404) {
          if (!cancelled) setError('This share link is invalid, expired, or its wiki has been deleted.');
          return;
        }
        if (!resRes.ok) throw new Error(`Failed to resolve share (${resRes.status})`);
        const res: ShareResolution = await resRes.json();
        if (cancelled) return;
        setResolution(res);

        // 2) load the wiki via the resolved pointer
        const qp = new URLSearchParams({
          owner: res.owner || '',
          repo: res.repo,
          repo_type: res.repo_type,
          language: res.language,
        });
        if (res.version) qp.set('version', res.version);
        const wikiRes = await fetch(`/api/wiki_cache?${qp.toString()}`, { cache: 'no-store' });
        if (!wikiRes.ok) throw new Error(`Failed to load wiki (${wikiRes.status})`);
        const data: WikiCache = await wikiRes.json();
        if (cancelled) return;
        setWiki(data);
        // land on the first page
        const firstPage = data.wiki_structure?.pages?.[0];
        if (firstPage) setCurrentPageId(firstPage.id);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load shared wiki.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [shareId]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-[var(--muted)]">
        Loading shared wiki…
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4 text-[var(--foreground)]">
        <h1 className="text-xl font-semibold">Share not available</h1>
        <p className="text-[var(--muted)]">{error}</p>
        <Link href="/" className="text-[var(--accent-primary)] hover:underline">
          Back to HackDeepWiki
        </Link>
      </div>
    );
  }

  if (!wiki) return null;

  const structure = normalizeStructure(wiki.wiki_structure);
  // Prefer the fully-generated page content (generated_pages) over the
  // structure stub, matching how the main page resolves a page to render.
  const currentPage =
    (currentPageId && wiki.generated_pages?.[currentPageId]) ||
    structure.pages.find(p => p.id === currentPageId);

  return (
    <div className="min-h-screen bg-[var(--background)] text-[var(--foreground)]">
      <header className="border-b border-[var(--border-color)] px-6 py-3 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">
            {structure.title || resolution?.repo || 'Shared Wiki'}
          </h1>
          {resolution?.owner && (
            <p className="text-xs text-[var(--muted)]">
              {resolution.owner}/{resolution.repo} · {resolution.language}
              {resolution.version ? ` · ${resolution.version}` : ''}
            </p>
          )}
        </div>
        <span className="text-xs text-[var(--muted)] border border-[var(--border-color)] rounded px-2 py-1">
          read-only share
        </span>
      </header>
      <div className="flex h-[calc(100vh-57px)]">
        <aside className="w-72 border-r border-[var(--border-color)] overflow-y-auto p-3 shrink-0">
          <WikiTreeView
            wikiStructure={structure}
            currentPageId={currentPageId}
            onPageSelect={(id) => setCurrentPageId(id)}
          />
        </aside>
        <main className="flex-1 overflow-y-auto p-6 max-w-4xl">
          {currentPage ? (
            <>
              <h2 className="text-2xl font-bold mb-4">{currentPage.title}</h2>
              <Markdown content={currentPage.content || ''} />
            </>
          ) : (
            <p className="text-[var(--muted)]">Select a page from the tree.</p>
          )}
        </main>
      </div>
    </div>
  );
}
