import { NextRequest, NextResponse } from 'next/server';

// Read at request time (not at `next build` time) so this works correctly
// with the portable app's dynamically-chosen backend port.
const getBackendBaseUrl = () => process.env.SERVER_BASE_URL || 'http://localhost:8001';

export async function POST(req: NextRequest) {
  try {
    const body = await req.text();
    const backendResponse = await fetch(`${getBackendBaseUrl()}/export/wiki`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
    });

    if (!backendResponse.ok) {
      const errorText = await backendResponse.text();
      return new NextResponse(errorText, { status: backendResponse.status });
    }

    const fileContent = await backendResponse.arrayBuffer();
    const headers = new Headers();
    const contentType = backendResponse.headers.get('Content-Type');
    const contentDisposition = backendResponse.headers.get('Content-Disposition');
    if (contentType) headers.set('Content-Type', contentType);
    if (contentDisposition) headers.set('Content-Disposition', contentDisposition);

    return new NextResponse(fileContent, { status: backendResponse.status, headers });
  } catch (error) {
    console.error('Error proxying POST /export/wiki:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
