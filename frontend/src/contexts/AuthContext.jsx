import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, setToken, formatError } from "@/lib/api";

const AuthContext = createContext(null);
const IDLE_MS = 10 * 60 * 1000; // 10 minuti di inattività → logout automatico

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

    const logout = useCallback(async (opts = {}) => {
        try { await api.post("/auth/logout"); } catch { /* ignore */ }
        setToken(null);
        setUser(false);
        if (opts.idle) {
            const { toast } = await import("sonner");
            toast.message("Sessione terminata", {
                description: "Sei stato disconnesso dopo 10 minuti di inattività.",
            });
        }
    }, []);

    // Auto-logout dopo 10 minuti di inattività (solo se autenticato)
    useEffect(() => {
        if (!user || user === false) return;
        let timer;
        const reset = () => {
            clearTimeout(timer);
            timer = setTimeout(() => logout({ idle: true }), IDLE_MS);
        };
        const events = ["mousemove", "mousedown", "keydown", "scroll", "touchstart", "click"];
        events.forEach((e) => window.addEventListener(e, reset, { passive: true }));
        reset();
        return () => {
            clearTimeout(timer);
            events.forEach((e) => window.removeEventListener(e, reset));
        };
    }, [user, logout]);

    return (
        <AuthContext.Provider value={{ user, loading, login, logout, setUser }}>
            {children}
        </AuthContext.Provider>
    );
}

export const useAuth = () => useContext(AuthContext);
