import * as SecureStore from "expo-secure-store";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, apiFetch, type FetchOpts } from "./api";
import type { AuthResponse, User } from "./types";

const KEY = "tixgh.auth";
type Tokens = { access: string; refresh: string };

type AuthState = {
  user: User | null;
  ready: boolean;
  signIn: (res: AuthResponse) => Promise<void>;
  signOut: () => Promise<void>;
  /** Authenticated call; refreshes the access token once on 401. */
  request: <T>(path: string, opts?: Omit<FetchOpts, "token">) => Promise<T>;
};

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const tokens = useRef<Tokens | null>(null);
  const refreshing = useRef<Promise<boolean> | null>(null);

  const save = async (t: Tokens | null) => {
    tokens.current = t;
    if (t) await SecureStore.setItemAsync(KEY, JSON.stringify(t));
    else await SecureStore.deleteItemAsync(KEY);
  };

  const refresh = useCallback(async () => {
    if (!tokens.current) return false;
    refreshing.current ??= (async () => {
      try {
        const t = await apiFetch<Tokens>("/auth/token/refresh/", { body: { refresh: tokens.current!.refresh } });
        await save({ access: t.access, refresh: t.refresh ?? tokens.current!.refresh });
        return true;
      } catch (e) {
        // Only sign out if the server rejected the token, not when offline.
        if (e instanceof ApiError) {
          await save(null);
          setUser(null);
        }
        return false;
      } finally {
        refreshing.current = null;
      }
    })();
    return refreshing.current;
  }, []);

  const request = useCallback(
    async <T,>(path: string, opts: Omit<FetchOpts, "token"> = {}) => {
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

  useEffect(() => {
    (async () => {
      try {
        const raw = await SecureStore.getItemAsync(KEY);
        if (raw) {
          tokens.current = JSON.parse(raw);
          const cached = await SecureStore.getItemAsync(`${KEY}.user`);
          if (cached) setUser(JSON.parse(cached)); // works offline
          request<User>("/auth/me/").then((u) => {
            setUser(u);
            SecureStore.setItemAsync(`${KEY}.user`, JSON.stringify(u));
          }).catch(() => {});
        }
      } finally {
        setReady(true);
      }
    })();
  }, [request]);

  const signIn = useCallback(async (res: AuthResponse) => {
    await save({ access: res.access, refresh: res.refresh });
    await SecureStore.setItemAsync(`${KEY}.user`, JSON.stringify(res.user));
    setUser(res.user);
  }, []);

  const signOut = useCallback(async () => {
    const t = tokens.current;
    await save(null);
    await SecureStore.deleteItemAsync(`${KEY}.user`);
    setUser(null);
    if (t) apiFetch("/auth/logout/", { body: { refresh: t.refresh }, token: t.access }).catch(() => {});
  }, []);

  const value = useMemo(() => ({ user, ready, signIn, signOut, request }), [user, ready, signIn, signOut, request]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth outside AuthProvider");
  return c;
}
