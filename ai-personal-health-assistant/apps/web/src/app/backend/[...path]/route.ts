import type { NextRequest } from "next/server";
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  if (!(path[0] === "api" && path[1] === "v1")) return Response.json({ detail: "Not found" }, { status: 404 });
  const headers = new Headers();
  for (const name of ["cookie", "content-type", "origin", "x-csrf-token"]) { const value = request.headers.get(name); if (value) headers.set(name, value); }
  let body: Uint8Array<ArrayBuffer> | undefined;
  if (request.body) {
    const reader = request.body.getReader(); const chunks: Uint8Array[] = []; let total = 0;
    while (true) { const item = await reader.read(); if (item.done) break; total += item.value.byteLength; if (total > 11*1024*1024) { await reader.cancel(); return Response.json({ detail: "Body too large" }, { status: 413 }); } chunks.push(item.value); }
    body = new Uint8Array(total); let offset = 0; for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.length; }
  }
  try {
    const base = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
    const response = await fetch(`${base}/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`, { method: request.method, headers, body, redirect: "manual", cache: "no-store", signal: AbortSignal.timeout(30000) });
    const outgoing = new Headers({ "Cache-Control": "no-store" });
    for (const name of ["content-type", "content-disposition", "x-request-id"]) { const value = response.headers.get(name); if (value) outgoing.set(name, value); }
    for (const cookie of response.headers.getSetCookie()) outgoing.append("Set-Cookie", cookie);
    return new Response(response.body, { status: response.status, headers: outgoing });
  } catch { return Response.json({ detail: "Không kết nối được máy chủ API" }, { status: 503 }); }
}
export { proxy as GET, proxy as POST, proxy as PUT, proxy as DELETE };
