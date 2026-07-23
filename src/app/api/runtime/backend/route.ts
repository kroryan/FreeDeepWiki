import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

export async function GET() {
  // SERVER_BASE_URL is injected by the standalone launcher after it chooses
  // a free backend port. Returning it from a server route avoids baking
  // localhost:8001 into browser bundles at `next build` time.
  return NextResponse.json({
    baseUrl: process.env.SERVER_BASE_URL || 'http://localhost:8001',
  });
}
