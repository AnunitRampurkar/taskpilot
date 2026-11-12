import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "./api";

const AuthContext = createContext(null);
const STORAGE_KEY = "taskpilot_auth";

function loadSaved() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState(loadSaved);
  const [checking, setChecking] = useState(Boolean(loadSaved()));

  const save = useCallback((data) => {
    setAuth(data);
    try {
      if (data) localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
      else localStorage.removeItem(STORAGE_KEY);
    } catch {
      // private mode etc, login just won't survive a refresh
    }
  }, []);

  const logout = useCallback(() => save(null), [save]);

  // on first load make sure the saved token still works and the role is up to date
  useEffect(() => {
    const saved = loadSaved();
    if (!saved) return;
    api("/api/auth/me", { token: saved.token })
      .then((user) => save({ token: saved.token, user }))
      .catch((err) => {
        if (err.status === 401) save(null);
      })
      .finally(() => setChecking(false));
  }, [save]);

  const login = useCallback(
    async (email, password) => {
      const data = await api("/api/auth/login", { method: "POST", body: { email, password } });
      save({ token: data.access_token, user: data.user });
    },
    [save]
  );

  const signup = useCallback(
    async (name, email, password) => {
      const data = await api("/api/auth/signup", { method: "POST", body: { name, email, password } });
      save({ token: data.access_token, user: data.user });
    },
    [save]
  );

  // wrapper so every page gets the token added and gets logged out on 401
  const request = useCallback(
    async (path, options = {}) => {
      try {
        return await api(path, { ...options, token: auth?.token });
      } catch (err) {
        if (err.status === 401) save(null);
        throw err;
      }
    },
    [auth, save]
  );

  const value = useMemo(
    () => ({
      user: auth?.user || null,
      token: auth?.token || null,
      isAdmin: auth?.user?.role === "admin",
      checking,
      login,
      signup,
      logout,
      request,
    }),
    [auth, checking, login, signup, logout, request]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
