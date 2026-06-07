import { createContext, useContext, useState, ReactNode } from "react";
import { api, setToken, clearToken, getToken } from "../api/client";

interface AuthState {
  username: string | null;
  isAuthed: boolean;
  login: (u: string, p: string) => Promise<void>;
  logout: () => void;
}

const AuthCtx = createContext<AuthState>(null as unknown as AuthState);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [username, setUsername] = useState<string | null>(
    localStorage.getItem("azureredops_user")
  );

  async function login(u: string, p: string) {
    const res = await api.login(u, p);
    setToken(res.access_token);
    localStorage.setItem("azureredops_user", res.username);
    setUsername(res.username);
  }

  function logout() {
    clearToken();
    localStorage.removeItem("azureredops_user");
    setUsername(null);
  }

  return (
    <AuthCtx.Provider value={{ username, isAuthed: !!getToken(), login, logout }}>
      {children}
    </AuthCtx.Provider>
  );
}

export const useAuth = () => useContext(AuthCtx);
