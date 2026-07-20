import { NextResponse } from 'next/server';

// Read at request time (not at `next build` time) so this works correctly
// with the portable app's dynamically-chosen backend port.
const getBackendBaseUrl = () => process.env.SERVER_BASE_URL || 'http://localhost:8001';

export async function GET() {
  try {
    const response = await fetch(`${getBackendBaseUrl()}/lang/config`);
    const data = await response.text();
    return new NextResponse(data, {
      status: response.status,
      headers: { 'Content-Type': response.headers.get('Content-Type') || 'application/json' },
    });
  } catch (error) {
    console.error('Error proxying GET /api/lang/config:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
