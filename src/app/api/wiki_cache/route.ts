import { NextRequest, NextResponse } from 'next/server';

// Read at request time (not at `next build` time) so this works correctly
// with the portable app's dynamically-chosen backend port.
const getBackendBaseUrl = () => process.env.SERVER_BASE_URL || 'http://localhost:8001';

export async function GET(req: NextRequest) {
  try {
    const backendUrl = `${getBackendBaseUrl()}/api/wiki_cache${req.nextUrl.search}`;
    const response = await fetch(backendUrl);
    const data = await response.text();
    return new NextResponse(data, {
      status: response.status,
      headers: { 'Content-Type': response.headers.get('Content-Type') || 'application/json' },
    });
  } catch (error) {
    console.error('Error proxying GET /api/wiki_cache:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.text();
    const response = await fetch(`${getBackendBaseUrl()}/api/wiki_cache`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
    });
    const data = await response.text();
    return new NextResponse(data, {
      status: response.status,
      headers: { 'Content-Type': response.headers.get('Content-Type') || 'application/json' },
    });
  } catch (error) {
    console.error('Error proxying POST /api/wiki_cache:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}

export async function DELETE(req: NextRequest) {
  try {
    const backendUrl = `${getBackendBaseUrl()}/api/wiki_cache${req.nextUrl.search}`;
    const response = await fetch(backendUrl, { method: 'DELETE' });
    const data = await response.text();
    return new NextResponse(data, {
      status: response.status,
      headers: { 'Content-Type': response.headers.get('Content-Type') || 'application/json' },
    });
  } catch (error) {
    console.error('Error proxying DELETE /api/wiki_cache:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
