"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { API_URL, ApiError, apiFetch } from "./api";
import type { AuthResponse, User } from "./types";

const STORAGE_KEY = "tixgh.auth";

type Tokens = { access: string; refresh: string };
type RequestOpts = { method?: string; body?: unknown };

type AuthState = {
  user: User | null;
  ready: boolean;
  signIn: (res: AuthResponse) => void;
  signOut: () => Promise<void>;
  setUser: (u: User) => void;
  /** Authenticated API call; refreshes the access token once on 401. */
  request: <T>(path: string, opts?: RequestOpts) => Promise<T>;
  download: (path: string, filename: string) => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

function loadTokens(): Tokens | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Tokens) : null;
  } catch {
    return null;
  }
}

function saveTokens(t: Tokens | null) {
  try {
    if (t) localStorage.setItem(STORAGE_KEY, JSON.stringify(t));
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* storage unavailable (private mode); session-only login */
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const tokens = useRef<Tokens | null>(null);
  const refreshing = useRef<Promise<boolean> | null>(null);

  const refresh = useCallback(async (): Promise<boolean> => {
    if (!tokens.current) return false;
    refreshing.current ??= (async () => {
      try {
        const t = await apiFetch<Tokens>("/auth/token/refresh/", { body: { refresh: tokens.current!.refresh } });
        tokens.current = { access: t.access, refresh: t.refresh ?? tokens.current!.refresh };
        saveTokens(tokens.current);
        return true;
      } catch {
        tokens.current = null;
        saveTokens(null);
        setUser(null);
        return false;
      } finally {
        refreshing.current = null;
      }
    })();
    return refreshing.current;
  }, []);

  const request = useCallback(
    async <T,>(path: string, opts: RequestOpts = {}): Promise<T> => {
      try {
        return await apiFetch<T>(path, { ...opts, token: tokens.current?.access });
      } catch (e) {
        if (e instanceof ApiError && e.status === 401 && (await refresh())) {
          return apiFetch<T>(path, { ...opts, token: tokens.current?.access });
        }
        throw e;
      }
    },
    [refresh],
  );

  /** Download a file (PDF/CSV) that needs auth, and save it with `filename`. */
  const download = useCallback(
    async (path: string, filename: string) => {
      const go = () => fetch(`${API_URL}/api/v1${path}`, {
        headers: tokens.current ? { Authorization: `Bearer ${tokens.current.access}` } : {},
      });
      let res = await go();
      if (res.status === 401 && (await refresh())) res = await go();
      if (!res.ok) throw new ApiError(res.status, null);
      const url = URL.createObjectURL(await res.blob());
      const a = Object.assign(document.createElement("a"), { href: url, download: filename });
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    },
    [refresh],
  );

  useEffect(() => {
    tokens.current = loadTokens();
    if (!tokens.current) {
      setReady(true);
      return;
    }
    request<User>("/auth/me/")
      .then(setUser)
      .catch(() => {
        tokens.current = null;
        saveTokens(null);
      })
      .finally(() => setReady(true));
  }, [request]);

  const signIn = useCallback((res: AuthResponse) => {
    tokens.current = { access: res.access, refresh: res.refresh };
    saveTokens(tokens.current);
    setUser(res.user);
  }, []);

  const signOut = useCallback(async () => {
    const t = tokens.current;
    tokens.current = null;
    saveTokens(null);
    setUser(null);
    if (t) await apiFetch("/auth/logout/", { body: { refresh: t.refresh }, token: t.access }).catch(() => {});
  }, []);

  const value = useMemo(
    () => ({ user, ready, signIn, signOut, setUser, request, download }),
    [user, ready, signIn, signOut, request, download],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

/** Remember guest orders on this device so the payment-return page can find them. */
const ORDERS_KEY = "tixgh.orders";
export function rememberOrder(reference: string, token: string) {
  try {
    const all = JSON.parse(localStorage.getItem(ORDERS_KEY) ?? "{}");
    all[reference] = token;
    localStorage.setItem(ORDERS_KEY, JSON.stringify(all));
  } catch {
    /* ignore */
  }
}
export function orderToken(reference: string): string | null {
  try {
    return JSON.parse(localStorage.getItem(ORDERS_KEY) ?? "{}")[reference] ?? null;
  } catch {
    return null;
  }
}
