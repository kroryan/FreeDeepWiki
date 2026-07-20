import { NextRequest, NextResponse } from 'next/server';

// Proxy to the backend's GET /api/wiki_cache/releases, which lists every saved
// release (version) of a repository's wiki for the "Wiki Release" dropdown.
// Read at request time so the portable app's dynamically-chosen backend port works.
const getBackendBaseUrl = () => process.env.SERVER_BASE_URL || 'http://localhost:8001';

export async function GET(req: NextRequest) {
  try {
    const backendUrl = `${getBackendBaseUrl()}/api/wiki_cache/releases${req.nextUrl.search}`;
    const response = await fetch(backendUrl);
    const data = await response.text();
    return new NextResponse(data, {
      status: response.status,
      headers: { 'Content-Type': response.headers.get('Content-Type') || 'application/json' },
    });
  } catch (error) {
    console.error('Error proxying GET /api/wiki_cache/releases:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}