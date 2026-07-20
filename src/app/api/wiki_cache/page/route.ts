import { NextRequest, NextResponse } from 'next/server';

// Read at request time (not at `next build` time) so this works correctly
// with the portable app's dynamically-chosen backend port.
const getBackendBaseUrl = () => process.env.SERVER_BASE_URL || 'http://localhost:8001';

export async function PATCH(req: NextRequest) {
  try {
    const body = await req.text();
    const response = await fetch(`${getBackendBaseUrl()}/api/wiki_cache/page`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body,
    });
    const data = await response.text();
    return new NextResponse(data, {
      status: response.status,
      headers: { 'Content-Type': response.headers.get('Content-Type') || 'application/json' },
    });
  } catch (error) {
    console.error('Error proxying PATCH /api/wiki_cache/page:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
