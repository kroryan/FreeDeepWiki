'use client';

import React, { useMemo, useState } from 'react';
import { FaChevronRight, FaChevronDown } from 'react-icons/fa';

// The wiki-structure-planning LLM decides section nesting purely via
// section_ref (see determineWikiStructure's prompt in page.tsx) with
// nothing on this end validating the result. For a large/comprehensive
// wiki the model can chain sections arbitrarily deep (section -> subsection
// -> subsection -> ...) instead of the intended shallow grouping, and
// nothing stopped it: no depth cap and no cycle detection, so a long chain
// rendered as a long chain (unusable, easy to lose pages in), and an actual
// cycle would have infinite-looped/crashed the render entirely. Sections
// beyond this depth are "promoted" to render as their own top-level entry
// instead of nesting further, so every page stays visible and reachable
// from the sidebar no matter how the model organized the section graph.
// The prompt asks the model to aim for 3 levels normally and only reach a
// 4th if the wiki genuinely needs it -- this is the hard structural ceiling
// backing that up (counting the root section itself as level 1).
const MAX_SECTION_DEPTH = 4;

interface DisplayTree {
  // sectionId -> the subsection ids to actually render nested under it
  // (a subset of section.subsections, with anything past MAX_SECTION_DEPTH
  // or already placed elsewhere removed).
  effectiveSubsections: Map<string, string[]>;
  // Section ids to render as additional top-level entries: either promoted
  // for exceeding the depth cap, or otherwise unreachable from
  // wikiStructure.rootSections (e.g. only referenced by a cycle).
  promotedRootIds: string[];
}

function buildDisplayTree(sections: WikiSection[], rootSections: string[]): DisplayTree {
  const sectionById = new Map(sections.map(s => [s.id, s]));
  const visited = new Set<string>();
  const promotedRootIds: string[] = [];
  const effectiveSubsections = new Map<string, string[]>();

  const walk = (id: string, depth: number) => {
    if (visited.has(id) || !sectionById.has(id)) return;
    visited.add(id);
    const section = sectionById.get(id)!;
    const keep: string[] = [];
    for (const childId of section.subsections || []) {
      if (!sectionById.has(childId)) continue;
      if (visited.has(childId)) {
        // Already placed elsewhere in the tree -- either a cycle (childId is
        // an ancestor of id) or the same section referenced from more than
        // one parent. Either way, rendering it again here would duplicate
        // it at best or infinite-loop at worst, so it's shown only in the
        // first place it was actually found.
        console.warn(
          `WikiTreeView: section "${childId}" forms a cycle or is referenced by more than one parent section; showing it only where it first appeared.`
        );
        continue;
      }
      if (depth + 1 >= MAX_SECTION_DEPTH) {
        promotedRootIds.push(childId);
        walk(childId, 0);
      } else {
        keep.push(childId);
        walk(childId, depth + 1);
      }
    }
    effectiveSubsections.set(id, keep);
  };

  for (const rootId of rootSections) {
    walk(rootId, 0);
  }
  // Anything not reachable at all from rootSections (shouldn't normally
  // happen given how rootSections is computed, but guarantees every
  // section -- and therefore every page -- stays reachable regardless of
  // how malformed the model's section graph turned out to be).
  for (const section of sections) {
    if (!visited.has(section.id)) {
      promotedRootIds.push(section.id);
      walk(section.id, 0);
    }
  }

  return { effectiveSubsections, promotedRootIds };
}

// Import interfaces from the page component
interface WikiPage {
  id: string;
  title: string;
  content: string;
  filePaths: string[];
  importance: 'high' | 'medium' | 'low';
  relatedPages: string[];
  parentId?: string;
  isSection?: boolean;
  children?: string[];
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

interface WikiTreeViewProps {
  wikiStructure: WikiStructure;
  currentPageId: string | undefined;
  onPageSelect: (pageId: string) => void;
  messages?: {
    pages?: string;
    [key: string]: string | undefined;
  };
}

const WikiTreeView: React.FC<WikiTreeViewProps> = ({
  wikiStructure,
  currentPageId,
  onPageSelect,
}) => {
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(wikiStructure.rootSections)
  );

  const { effectiveSubsections, promotedRootIds } = useMemo(
    () => buildDisplayTree(wikiStructure.sections, wikiStructure.rootSections),
    [wikiStructure.sections, wikiStructure.rootSections]
  );

  const toggleSection = (sectionId: string, event: React.MouseEvent) => {
    event.stopPropagation();
    setExpandedSections(prev => {
      const newSet = new Set(prev);
      if (newSet.has(sectionId)) {
        newSet.delete(sectionId);
      } else {
        newSet.add(sectionId);
      }
      return newSet;
    });
  };

  const renderSection = (sectionId: string, level = 0) => {
    const section = wikiStructure.sections.find(s => s.id === sectionId);
    if (!section) return null;

    const isExpanded = expandedSections.has(sectionId);

    return (
      <div key={sectionId} className="mb-2">
        <button
          className={`flex items-center w-full text-left px-2 py-1.5 rounded-md text-sm font-medium text-[var(--foreground)] hover:bg-[var(--background)]/70 transition-colors ${
            level === 0 ? 'bg-[var(--background)]/50' : ''
          }`}
          onClick={(e) => toggleSection(sectionId, e)}
        >
          {isExpanded ? (
            <FaChevronDown className="mr-2 text-xs" />
          ) : (
            <FaChevronRight className="mr-2 text-xs" />
          )}
          <span className="truncate">{section.title}</span>
        </button>

        {isExpanded && (
          <div className={`ml-4 mt-1 space-y-1 ${level > 0 ? 'pl-2 border-l border-[var(--border-color)]/30' : ''}`}>
            {/* Render pages in this section */}
            {section.pages.map(pageId => {
              const page = wikiStructure.pages.find(p => p.id === pageId);
              if (!page) return null;

              return (
                <button
                  key={pageId}
                  className={`w-full text-left px-3 py-1.5 rounded-md text-sm transition-colors ${
                    currentPageId === pageId
                      ? 'bg-[var(--accent-primary)]/20 text-[var(--accent-primary)] border border-[var(--accent-primary)]/30'
                      : 'text-[var(--foreground)] hover:bg-[var(--background)] border border-transparent'
                  }`}
                  onClick={() => onPageSelect(pageId)}
                >
                  <div className="flex items-center">
                    <div
                      className={`w-2 h-2 rounded-full mr-2 flex-shrink-0 ${
                        page.importance === 'high'
                          ? 'bg-[#9b7cb9]'
                          : page.importance === 'medium'
                          ? 'bg-[#d7c4bb]'
                          : 'bg-[#e8927c]'
                      }`}
                    ></div>
                    <span className="truncate">{page.title}</span>
                  </div>
                </button>
              );
            })}

            {/* Render subsections recursively, capped to MAX_SECTION_DEPTH --
                anything deeper was already promoted to a top-level entry by
                buildDisplayTree, so it's rendered in the root loop below
                instead of nested arbitrarily deep here. */}
            {effectiveSubsections.get(sectionId)?.map(subsectionId =>
              renderSection(subsectionId, level + 1)
            )}
          </div>
        )}
      </div>
    );
  };

  // If there are no sections defined yet, or if sections/rootSections are empty arrays, fall back to the flat list view
  if (!wikiStructure.sections || wikiStructure.sections.length === 0 || !wikiStructure.rootSections || wikiStructure.rootSections.length === 0) {
    console.log("WikiTreeView: Falling back to flat list view due to missing or empty sections/rootSections");
    return (
      <ul className="space-y-2">
        {wikiStructure.pages.map(page => (
          <li key={page.id}>
            <button
              className={`w-full text-left px-3 py-2 rounded-md text-sm transition-colors ${
                currentPageId === page.id
                  ? 'bg-[var(--accent-primary)]/20 text-[var(--accent-primary)] border border-[var(--accent-primary)]/30'
                  : 'text-[var(--foreground)] hover:bg-[var(--background)] border border-transparent'
              }`}
              onClick={() => onPageSelect(page.id)}
            >
              <div className="flex items-center">
                <div
                  className={`w-2 h-2 rounded-full mr-2 flex-shrink-0 ${
                    page.importance === 'high'
                      ? 'bg-[#9b7cb9]'
                      : page.importance === 'medium'
                      ? 'bg-[#d7c4bb]'
                      : 'bg-[#e8927c]'
                  }`}
                ></div>
                <span className="truncate">{page.title}</span>
              </div>
            </button>
          </li>
        ))}
      </ul>
    );
  }

  // Log information about the sections for debugging
  console.log("WikiTreeView: Rendering tree view with sections:", wikiStructure.sections);
  console.log("WikiTreeView: Root sections:", wikiStructure.rootSections);

  return (
    <div className="space-y-1">
      {/* promotedRootIds: sections buildDisplayTree pulled out of a chain
          that would otherwise have exceeded MAX_SECTION_DEPTH (or that
          were unreachable from rootSections entirely) -- rendered here as
          additional top-level entries so their pages stay reachable. */}
      {[...wikiStructure.rootSections, ...promotedRootIds].map(sectionId => {
        const section = wikiStructure.sections.find(s => s.id === sectionId);
        if (!section) {
          console.warn(`WikiTreeView: Could not find section with id ${sectionId}`);
          return null;
        }
        return renderSection(sectionId);
      })}
    </div>
  );
};

export default WikiTreeView;