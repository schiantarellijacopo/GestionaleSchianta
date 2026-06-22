import { createContext, useContext, useEffect, useState } from "react";
import { api, setToken, formatError } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    const [user, setUser] = useState(null); // null = checking
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let mounted = true;
        api.get("/auth/me")
            .then((res) => mounted && setUser(res.data))
            .catch(() => mounted && setUser(false))
            .finally(() => mounted && setLoading(false));
        return () => { mounted = false; };
    }, []);

    const login = async (email, password) => {
        try {
            const res = await api.post("/auth/login", { email, password });
            if (res.data?.access_token) setToken(res.data.access_token);
            setUser(res.data.user);
            return { ok: true };
        } catch (e) {
            return { ok: false, error: formatError(e) };
        }
    };

    const logout = async () => {
        try { await api.post("/auth/logout"); } catch { /* ignore */ }
        setToken(null);
        setUser(false);
    };

    return (
        <AuthContext.Provider value={{ user, loading, login, logout, setUser }}>
            {children}
        </AuthContext.Provider>
    );
}

export const useAuth = () => useContext(AuthContext);
