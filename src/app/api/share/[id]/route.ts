import { NextRequest, NextResponse } from 'next/server';

// Proxy to the backend share resolver. The backend holds the share->wiki
// pointer in profile.db (api.storage.wiki_shares); this route just forwards
// so the browser can call a same-origin /api/share/<id> (avoids CORS and
// keeps the backend host internal, same pattern as /api/zim/[id]).
const getBackendBaseUrl = () => process.env.SERVER_BASE_URL || 'http://localhost:8001';

type RouteContext = {
  params: Promise<{ id: string }>;
};

export async function GET(_req: NextRequest, context: RouteContext) {
  const { id } = await context.params;
  try {
    const response = await fetch(`${getBackendBaseUrl()}/api/share/${encodeURIComponent(id)}`, {
      cache: 'no-store',
    });
    const data = await response.text();
    return new NextResponse(data, {
      status: response.status,
      headers: { 'Content-Type': response.headers.get('Content-Type') || 'application/json' },
    });
  } catch (error) {
    console.error(`Error proxying GET /api/share/${id}:`, error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
