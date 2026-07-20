import { NextRequest, NextResponse } from 'next/server';

const getBackendBaseUrl = () => process.env.SERVER_BASE_URL || 'http://localhost:8001';

type RouteContext = {
  params: Promise<{ id: string; path: string[] }>;
};

// Proxies raw bytes of an entry inside a .zim namespace (images, CSS, JS,
// linked articles) -- binary-safe, unlike the other zim routes which proxy
// JSON/HTML text.
export async function GET(req: NextRequest, context: RouteContext) {
  const { id, path } = await context.params;
  const entryPath = path.map(encodeURIComponent).join('/');
  try {
    const backendUrl = `${getBackendBaseUrl()}/api/zim/${encodeURIComponent(id)}/raw/${entryPath}`;
    const response = await fetch(backendUrl, { cache: 'no-store' });
    const data = await response.arrayBuffer();
    return new NextResponse(data, {
      status: response.status,
      headers: {
        'Content-Type': response.headers.get('Content-Type') || 'application/octet-stream',
        'X-Content-Type-Options': 'nosniff',
      },
    });
  } catch (error) {
    console.error(`Error proxying GET /api/zim/${id}/raw/${entryPath}:`, error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
