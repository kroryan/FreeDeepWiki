import { NextRequest, NextResponse } from 'next/server';

const getBackendBaseUrl = () => process.env.SERVER_BASE_URL || 'http://localhost:8001';

type RouteContext = {
  params: Promise<{ id: string }>;
};

export async function GET(req: NextRequest, context: RouteContext) {
  const { id } = await context.params;
  try {
    const response = await fetch(`${getBackendBaseUrl()}/api/zim/${encodeURIComponent(id)}`, {
      cache: 'no-store',
    });
    const data = await response.text();
    return new NextResponse(data, {
      status: response.status,
      headers: { 'Content-Type': response.headers.get('Content-Type') || 'application/json' },
    });
  } catch (error) {
    console.error(`Error proxying GET /api/zim/${id}:`, error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}

export async function DELETE(req: NextRequest, context: RouteContext) {
  const { id } = await context.params;
  try {
    const response = await fetch(`${getBackendBaseUrl()}/api/zim/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    });
    const data = await response.text();
    return new NextResponse(data, {
      status: response.status,
      headers: { 'Content-Type': response.headers.get('Content-Type') || 'application/json' },
    });
  } catch (error) {
    console.error(`Error proxying DELETE /api/zim/${id}:`, error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
