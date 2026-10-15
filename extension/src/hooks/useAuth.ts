import { useEffect, useState } from "react";
import { login, logout } from "../api/auth";

export function useAuth() {
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    const expired = () => setToken(null);
    chrome.storage.local.get("fieldnote_token").then(value => {
      if (active) setToken(value.fieldnote_token ?? null);
    }).catch(() => { if (active) setToken(null); }).finally(() => { if (active) setLoading(false); });
    window.addEventListener("fieldnote:session-expired", expired);
    return () => { active = false; window.removeEventListener("fieldnote:session-expired", expired); };
  }, []);
  return {
    token,
    loading,
    signIn: async (email: string, password: string) => { const result = await login(email, password); setToken(result.access_token); },
    signOut: async () => { setToken(null); await logout(); },
  };
}
