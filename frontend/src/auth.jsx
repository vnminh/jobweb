import { createContext, useContext, useEffect, useState } from "react";
import { api, getToken, setToken } from "./api";

const Ctx = createContext(null);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (!getToken()) { setReady(true); return; }
    api("/auth/me").then(setUser).catch(() => setToken(null)).finally(() => setReady(true));
  }, []);
  const login = async (email, password) => {
    const r = await api("/auth/login", { method: "POST", body: { email, password } });
    setToken(r.token); setUser(r.account); return r.account;
  };
  const register = async (body) => {
    const r = await api("/auth/register", { method: "POST", body });
    setToken(r.token); setUser(r.account); return r.account;
  };
  const logout = () => { setToken(null); setUser(null); };
  return <Ctx.Provider value={{ user, ready, login, register, logout }}>{children}</Ctx.Provider>;
}
