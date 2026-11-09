"use client";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import type { AuthResponse, User } from "@health/contracts";

type Api = <T>(path: string, options?: { method?: string; body?: unknown }) => Promise<T>;
async function request<T>(path: string, csrf: string | null, options?: { method?: string; body?: unknown }): Promise<T> {
  const response = await fetch(`/backend/api/v1${path}`, { method: options?.method ?? "GET", credentials: "same-origin", cache: "no-store",
    headers: { ...(csrf ? { "X-CSRF-Token": csrf } : {}), ...(options?.body ? { "Content-Type": "application/json" } : {}) },
    body: options?.body ? JSON.stringify(options.body) : undefined });
  if (!response.ok) {
    const result = await response.json().catch(() => ({}));
    const detail = result.detail;
    const error = new Error(Array.isArray(detail) ? detail.map((row: { loc: string[]; msg: string }) => `${row.loc.slice(1).join(".")}: ${row.msg}`).join("; ") : detail ?? `Lỗi ${response.status}`);
    if (response.status === 401) Object.assign(error, { unauthorized: true });
    throw error;
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}
type Session = { user: User | null; ready: boolean; api: Api; login: (email: string, password: string) => Promise<void>; logout: () => Promise<void> };
const Context = createContext<Session | null>(null);
export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null); const [csrf, setCsrf] = useState<string | null>(null); const [ready, setReady] = useState(false);
  useEffect(() => { let live = true; request<AuthResponse>("/auth/session", null).then(result => { if (live) { setUser(result.user); setCsrf(result.csrf_token); } }).catch(() => {}).finally(() => { if (live) setReady(true); }); return () => { live = false; }; }, []);
  const api = useCallback<Api>(async (path, options) => {
    try { return await request(path, csrf, options); }
    catch (error) { if (error instanceof Error && "unauthorized" in error) { setUser(null); setCsrf(null); } throw error; }
  }, [csrf]);
  async function login(email: string, password: string) {
    const result = await request<AuthResponse>("/auth/login", null, { method: "POST", body: { email, password, client: "web" } });
    if (result.user.role !== "admin") {
      await request("/auth/logout", result.csrf_token, { method: "POST" });
      throw new Error("Web này dành cho quản trị viên. Tài khoản cá nhân sử dụng ứng dụng di động.");
    }
    setCsrf(result.csrf_token); setUser(result.user);
  }
  async function logout() { await api("/auth/logout", { method: "POST" }); setUser(null); setCsrf(null); }
  return <Context.Provider value={{ user, ready, api, login, logout }}>{children}</Context.Provider>;
}
export function useSession() { const result = useContext(Context); if (!result) throw new Error("Session provider missing"); return result; }
