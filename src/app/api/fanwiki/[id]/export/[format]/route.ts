import { NextRequest, NextResponse } from 'next/server';

const getBackendBaseUrl = () => process.env.SERVER_BASE_URL || 'http://localhost:8001';

type RouteContext = {
  params: Promise<{ id: string; format: string }>;
};

export async function GET(_req: NextRequest, context: RouteContext) {
  const { id, format } = await context.params;
  try {
    const response = await fetch(
      `${getBackendBaseUrl()}/api/fanwiki/${encodeURIComponent(id)}/export/${encodeURIComponent(format)}`,
      { cache: 'no-store' },
    );
    if (!response.ok) {
      const body = await response.text();
      return new NextResponse(body, {
        status: response.status,
        headers: {
          'Content-Type': response.headers.get('Content-Type') || 'application/json',
        },
      });
    }

    // Forward the stream instead of buffering the complete archive in the
    // Next.js process; MediaWiki dumps and their image folders can be large.
    const headers = new Headers({
      'Content-Type': response.headers.get('Content-Type') || 'application/zip',
      'Content-Disposition': response.headers.get('Content-Disposition') || 'attachment',
      'X-HackDeepWiki-Page-Count': response.headers.get('X-HackDeepWiki-Page-Count') || '0',
      'X-HackDeepWiki-Asset-Count': response.headers.get('X-HackDeepWiki-Asset-Count') || '0',
    });
    const contentLength = response.headers.get('Content-Length');
    if (contentLength) headers.set('Content-Length', contentLength);

    return new NextResponse(response.body, {
      status: response.status,
      headers,
    });
  } catch (error) {
    console.error(`Error proxying fanwiki ${id} ${format} export:`, error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
