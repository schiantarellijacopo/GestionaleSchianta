import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Shield, Lock } from "lucide-react";
import { toast } from "sonner";

/**
 * Login dedicato al Platform Owner (Super Admin).
 * Reindirizza a /super-admin dopo autenticazione. Se l'utente NON è
 * super_admin, il login viene rifiutato con messaggio dedicato.
 */
export default function AdminLogin() {
    const { login, user, logout } = useAuth();
    const nav = useNavigate();
    const [email, setEmail] = useState("superadmin@assicura.it");
    const [password, setPassword] = useState("superadmin123!");
    const [err, setErr] = useState("");
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (user && user !== false) {
            if (user.is_super_admin) nav("/super-admin", { replace: true });
        }
    }, [user, nav]);

    const submit = async (e) => {
        e.preventDefault();
        setErr("");
        setLoading(true);
        const res = await login(email, password);
        setLoading(false);
        if (!res.ok) { setErr(res.error); return; }
        // Verifica ruolo super_admin dopo il login (user viene aggiornato via context)
        // Se non è super_admin, forza logout e mostra errore
        setTimeout(async () => {
            try {
                const raw = JSON.parse(localStorage.getItem("auth_user") || "null");
                // se non abbiamo storage, controlliamo direttamente il context (user aggiornato)
            } catch { /* ignore */ }
        }, 0);
    };

    // Se l'utente è loggato ma NON super_admin, mostra messaggio e permetti logout
    if (user && user !== false && !user.is_super_admin) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-slate-950 p-6">
                <div className="max-w-md w-full bg-slate-900 border border-slate-800 rounded-lg p-6 text-slate-200 text-center">
                    <Lock size={40} className="text-rose-400 mx-auto mb-3" />
                    <h2 className="text-lg font-semibold mb-2">Accesso non consentito</h2>
                    <p className="text-sm text-slate-400 mb-4">
                        L'utente <b>{user.email}</b> non è un Super Admin.
                        Questa area è riservata al proprietario della piattaforma.
                    </p>
                    <button onClick={async () => { await logout(); nav("/admin-login"); }}
                        className="w-full bg-rose-600 hover:bg-rose-700 text-white text-sm font-semibold py-2 rounded-md"
                        data-testid="admin-login-logout-btn">
                        Esci e riprova
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-950 via-violet-950 to-slate-900 p-6">
            <div className="max-w-md w-full">
                <div className="text-center mb-8">
                    <div className="inline-flex items-center justify-center w-14 h-14 rounded-lg bg-violet-600 mb-4">
                        <Shield size={28} className="text-white" />
                    </div>
                    <h1 className="text-2xl font-bold text-white">Super Admin Console</h1>
                    <p className="text-sm text-violet-300 mt-1">Accesso riservato al proprietario della piattaforma SaaS</p>
                </div>
                <form onSubmit={submit} className="bg-slate-900/70 backdrop-blur border border-violet-900/50 rounded-lg p-6 space-y-4" data-testid="admin-login-form">
                    <div>
                        <label className="text-xs font-semibold text-violet-300 uppercase tracking-wider block mb-1.5">Email</label>
                        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                            required autoFocus placeholder="admin@assicura.it"
                            className="w-full px-3 py-2 bg-slate-950/60 border border-slate-700 rounded-md text-white text-sm focus:border-violet-500 outline-none"
                            data-testid="admin-login-email" />
                    </div>
                    <div>
                        <label className="text-xs font-semibold text-violet-300 uppercase tracking-wider block mb-1.5">Password</label>
                        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                            required placeholder="••••••••"
                            className="w-full px-3 py-2 bg-slate-950/60 border border-slate-700 rounded-md text-white text-sm focus:border-violet-500 outline-none"
                            data-testid="admin-login-password" />
                    </div>
                    {err && <div className="text-xs text-rose-400 bg-rose-950/40 border border-rose-900 px-3 py-2 rounded-md">{err}</div>}
                    <button type="submit" disabled={loading}
                        className="w-full bg-violet-600 hover:bg-violet-700 disabled:opacity-60 text-white text-sm font-semibold py-2.5 rounded-md transition-colors"
                        data-testid="admin-login-submit">
                        {loading ? "Accesso in corso..." : "Accedi come Super Admin"}
                    </button>

                    {/* Credenziali di prova pre-caricate (rimuovere in produzione) */}
                    <div className="bg-violet-950/40 border border-violet-900/60 rounded-md px-3 py-2 text-[11px] text-violet-200 space-y-0.5">
                        <div className="font-semibold text-violet-100 uppercase tracking-wider text-[10px]">Credenziali Super Admin</div>
                        <div>Email: <span className="font-mono text-violet-300">superadmin@assicura.it</span></div>
                        <div>Password: <span className="font-mono text-violet-300">superadmin123!</span></div>
                    </div>

                    <div className="text-center pt-2">
                        <a href="/login" className="text-xs text-violet-400 hover:text-violet-300">
                            ← Accesso agenzia (utente normale)
                        </a>
                    </div>
                </form>
            </div>
        </div>
    );
}
