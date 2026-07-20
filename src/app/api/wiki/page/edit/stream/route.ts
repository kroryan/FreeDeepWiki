import { NextRequest, NextResponse } from 'next/server';

// Read at request time (not at `next build` time) so this works correctly
// with the portable app's dynamically-chosen backend port.
const getBackendBaseUrl = () => process.env.SERVER_BASE_URL || 'http://localhost:8001';

// Proxies the AI-assisted page edit stream through to the backend, same
// streaming-passthrough shape as /api/chat/stream.
export async function POST(req: NextRequest) {
  try {
    const requestBody = await req.text();

    const backendResponse = await fetch(`${getBackendBaseUrl()}/api/wiki/page/edit/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
      },
      body: requestBody,
    });

    if (!backendResponse.ok) {
      const errorBody = await backendResponse.text();
      return new NextResponse(errorBody, {
        status: backendResponse.status,
        statusText: backendResponse.statusText,
      });
    }

    if (!backendResponse.body) {
      return new NextResponse('Stream body from backend is null', { status: 500 });
    }

    const stream = new ReadableStream({
      async start(controller) {
        const reader = backendResponse.body!.getReader();
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            controller.enqueue(value);
          }
        } catch (error) {
          console.error('Error reading from backend stream in proxy:', error);
          controller.error(error);
        } finally {
          controller.close();
          reader.releaseLock();
        }
      },
    });

    const responseHeaders = new Headers();
    const contentType = backendResponse.headers.get('Content-Type');
    if (contentType) responseHeaders.set('Content-Type', contentType);
    responseHeaders.set('Cache-Control', 'no-cache, no-transform');

    return new NextResponse(stream, {
      status: backendResponse.status,
      headers: responseHeaders,
    });
  } catch (error) {
    console.error('Error in API proxy route (/api/wiki/page/edit/stream):', error);
    const errorMessage = error instanceof Error ? error.message : 'Internal Server Error in proxy';
    return new NextResponse(JSON.stringify({ error: errorMessage }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
