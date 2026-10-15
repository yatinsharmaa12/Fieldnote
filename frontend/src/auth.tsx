import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "./api";

type AuthContextValue = { token: string | null; login: (email: string, password: string) => Promise<void>; logout: () => Promise<void> };
const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState(() => sessionStorage.getItem("fieldnote_token"));
  useEffect(() => {
    const expired = () => setToken(null);
    window.addEventListener("fieldnote:session-expired", expired);
    return () => window.removeEventListener("fieldnote:session-expired", expired);
  }, []);
  async function login(email: string, password: string) {
    const result = await api.login(email, password);
    sessionStorage.setItem("fieldnote_token", result.access_token);
    setToken(result.access_token);
  }
  async function logout() {
    const revocation = sessionStorage.getItem("fieldnote_token") ? api.logout() : Promise.resolve();
    sessionStorage.removeItem("fieldnote_token");
    setToken(null);
    try {
      await revocation;
    } catch {
      // Best-effort revocation; always clear local state.
    }
  }
  return <AuthContext.Provider value={{ token, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
