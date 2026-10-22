import { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";

const BG_URL = "https://images.unsplash.com/photo-1742148186848-8b257455009b?crop=entropy&cs=srgb&fm=jpg&q=85&w=1920";

export default function Login() {
    const { login, user } = useAuth();
    const nav = useNavigate();
    const loc = useLocation();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [err, setErr] = useState("");
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (user && user !== false) {
            // Se super_admin arriva sulla login normale, dirotta subito al pannello dedicato
            if (user.is_super_admin) {
                nav("/super-admin", { replace: true });
                return;
            }
            const from = loc.state?.from || "/";
            nav(from, { replace: true });
        }
    }, [user, nav, loc.state]);

    const submit = async (e) => {
        e.preventDefault();
        setErr("");
        setLoading(true);
        const res = await login(email, password);
        setLoading(false);
        if (!res.ok) setErr(res.error);
    };

    return (
        <div className="min-h-screen flex">
            <div
                className="hidden lg:flex flex-1 relative items-end p-12 bg-cover bg-center"
                style={{ backgroundImage: `linear-gradient(rgba(15,23,42,0.85),rgba(15,23,42,0.92)), url(${BG_URL})` }}
            >
                <div className="text-slate-100 max-w-md">
                    <h1 className="text-4xl font-semibold tracking-tight leading-tight mb-4">
                        La piattaforma assicurativa<br />per chi lavora con i dati.
                    </h1>
                    <p className="text-slate-300 text-sm leading-relaxed">
                        Anagrafiche, polizze, titoli, sinistri, contabilità e calcolo pensioni INPS.
                        Importazione giornaliera dei tracciati ANIA, multi-compagnia e log completo
                        delle attività.
                    </p>
                </div>
            </div>

            <div className="flex-1 flex items-center justify-center px-6 py-10 bg-slate-50">
                <Card className="w-full max-w-md p-8 shadow-sm border-slate-200">
                    <h2 className="text-2xl font-semibold tracking-tight text-slate-900 mb-1">
                        Accedi al gestionale
                    </h2>
                    <p className="text-sm text-slate-500 mb-6">
                        Inserisci le tue credenziali per continuare.
                    </p>

                    <form onSubmit={submit} className="space-y-4">
                        <div>
                            <Label htmlFor="email" className="text-xs uppercase tracking-wider text-slate-500">
                                Email
                            </Label>
                            <Input
                                id="email"
                                data-testid="login-email-input"
                                type="email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                required
                                className="mt-1"
                            />
                        </div>
                        <div>
                            <Label htmlFor="password" className="text-xs uppercase tracking-wider text-slate-500">
                                Password
                            </Label>
                            <Input
                                id="password"
                                data-testid="login-password-input"
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                required
                                className="mt-1"
                            />
                        </div>
                        {err && (
                            <div data-testid="login-error" className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-md px-3 py-2">
                                {err}
                            </div>
                        )}
                        <Button
                            type="submit"
                            data-testid="login-submit-button"
                            disabled={loading}
                            className="w-full bg-sky-700 hover:bg-sky-800 text-white"
                        >
                            {loading ? "Accesso..." : "Accedi"}
                        </Button>
                        <div className="text-center pt-1">
                            <a
                                href="/forgot-password"
                                data-testid="forgot-password-link"
                                className="text-sm text-sky-700 hover:text-sky-800"
                            >
                                Password dimenticata?
                            </a>
                        </div>
                    </form>
                </Card>
            </div>
        </div>
    );
}
