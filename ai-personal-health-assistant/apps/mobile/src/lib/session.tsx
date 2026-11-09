import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";
import { fetch } from "expo/fetch";
import type { AuthResponse, User } from "@health/contracts";

export const baseUrl = process.env.EXPO_PUBLIC_API_URL ?? (Platform.OS === "android" ? "http://10.0.2.2:8000" : "http://localhost:8000");
const key = "health-session-v1";
export type Api = <T>(path: string, options?: { method?: string; body?: unknown; binary?: Blob }) => Promise<T>;

function createApi(token: string | null, unauthorized: () => void): Api {
  return async <T,>(path: string, options?: { method?: string; body?: unknown; binary?: Blob }) => {
    let response: Response;
    try {
      response = await fetch(`${baseUrl}/api/v1${path}`, {
        method: options?.method ?? "GET", credentials: "omit",
        headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...(options?.binary ? { "Content-Type": "application/octet-stream" } : options?.body ? { "Content-Type": "application/json" } : {}) },
        body: options?.binary ?? (options?.body ? JSON.stringify(options.body) : undefined),
      });
    } catch { throw new Error("Không kết nối được API. Kiểm tra địa chỉ máy chủ và mạng."); }
    if (response.status === 401 && token) unauthorized();
    if (!response.ok) {
      const result = await response.json().catch(() => ({}));
      const detail = result.detail;
      throw new Error(Array.isArray(detail) ? detail.map((x: { loc: string[]; msg: string }) => `${x.loc.slice(1).join(".")}: ${x.msg}`).join("\n") : detail ?? `Lỗi ${response.status}`);
    }
    return (response.status === 204 ? undefined : await response.json()) as T;
  };
}

type Session = { user: User | null; ready: boolean; api: Api; login: (email: string, password: string) => Promise<void>; logout: () => Promise<void>; forget: () => void };
const Context = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const forget = useCallback(() => {
    setToken(null); setUser(null);
    if (Platform.OS !== "web") void SecureStore.deleteItemAsync(key);
  }, []);
  const api = useMemo(() => createApi(token, forget), [token, forget]);
  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const saved = Platform.OS === "web" ? null : await SecureStore.getItemAsync(key);
        if (saved) {
          const result = await createApi(saved, forget)<AuthResponse>("/auth/session");
          if (live) { setToken(saved); setUser(result.user); }
        }
      } catch { forget(); }
      finally { if (live) setReady(true); }
    })();
    return () => { live = false; };
  }, [forget]);
  const login = async (email: string, password: string) => {
    const result = await createApi(null, forget)<AuthResponse>("/auth/login", { method: "POST", body: { email, password, client: "mobile" } });
    if (!result.access_token) throw new Error("Máy chủ không trả phiên đăng nhập");
    if (Platform.OS !== "web") await SecureStore.setItemAsync(key, result.access_token);
    setToken(result.access_token); setUser(result.user);
  };
  const logout = async () => { await api("/auth/logout", { method: "POST" }); forget(); };
  return <Context.Provider value={{ user, ready, api, login, logout, forget }}>{children}</Context.Provider>;
}

export function useSession() {
  const session = useContext(Context);
  if (!session) throw new Error("Session provider missing");
  return session;
}
