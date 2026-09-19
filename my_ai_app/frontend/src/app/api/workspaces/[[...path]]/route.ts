import { NextRequest, NextResponse } from "next/server";

const backend = process.env.BACKEND_URL || "http://localhost:8000";

async function proxy(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  const token = request.cookies.get("access_token")?.value;
  if (!token) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  const { path = [] } = await context.params;
  if (path.some((part) => !/^[a-zA-Z0-9-]+$/.test(part))) {
    return NextResponse.json({ detail: "Invalid path" }, { status: 400 });
  }
  if (!["GET", "HEAD"].includes(request.method)) {
    const origin = request.headers.get("origin");
    if (origin && origin !== request.nextUrl.origin) {
      return NextResponse.json({ detail: "Invalid origin" }, { status: 403 });
    }
  }
  if (Number(request.headers.get("content-length")) > 11 * 1024 * 1024) {
    return NextResponse.json({ detail: "Upload too large" }, { status: 413 });
  }
  try {
    const body = ["GET", "HEAD"].includes(request.method) ? undefined : await request.arrayBuffer();
    if (body && body.byteLength > 11 * 1024 * 1024) {
      return NextResponse.json({ detail: "Upload too large" }, { status: 413 });
    }
    const response = await fetch(
      `${backend}/api/v1/workspaces${path.length ? "/" + path.join("/") : ""}${request.nextUrl.search}`,
      {
        method: request.method,
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": request.headers.get("content-type") || "application/json",
        },
        body,
        cache: "no-store",
        signal: AbortSignal.timeout(45000),
      },
    );
    return new NextResponse(await response.arrayBuffer(), {
      status: response.status,
      headers: { "Content-Type": "application/json", "Cache-Control": "private, no-store" },
    });
  } catch {
    return NextResponse.json(
      { detail: "Support service unavailable. Please retry." },
      { status: 502 },
    );
  }
}

export { proxy as GET, proxy as POST, proxy as PATCH, proxy as DELETE };
