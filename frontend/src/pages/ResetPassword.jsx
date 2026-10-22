import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, formatError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";

const BG_URL = "https://images.unsplash.com/photo-1742148186848-8b257455009b?crop=entropy&cs=srgb&fm=jpg&q=85&w=1920";

export default function ResetPassword() {
    const nav = useNavigate();
    const token = new URLSearchParams(window.location.search).get("token") || "";
    const [password, setPassword] = useState("");
    const [confirm, setConfirm] = useState("");
    const [err, setErr] = useState("");
    const [done, setDone] = useState(false);
    const [loading, setLoading] = useState(false);

    const submit = async (e) => {
        e.preventDefault();
        setErr("");
        if (password.length < 8) { setErr("La password deve avere almeno 8 caratteri."); return; }
        if (password !== confirm) { setErr("Le due password non coincidono."); return; }
        if (!token) { setErr("Link non valido o scaduto."); return; }
        setLoading(true);
        try {
            await api.post("/auth/password-reset/confirm", { token, new_password: password });
            window.history.replaceState({}, document.title, "/login");
            setDone(true);
            setTimeout(() => nav("/login", { replace: true }), 2500);
        } catch (e2) {
            setErr(formatError(e2));
        }
        setLoading(false);
    };

    return (
        <div className="min-h-screen flex">
            <div
                className="hidden lg:flex flex-1 relative items-end p-12 bg-cover bg-center"
                style={{ backgroundImage: `linear-gradient(rgba(15,23,42,0.85),rgba(15,23,42,0.92)), url(${BG_URL})` }}
            >
                <div className="text-slate-100 max-w-md">
                    <h1 className="text-4xl font-semibold tracking-tight leading-tight mb-4">
                        Imposta una<br />nuova password.
                    </h1>
                    <p className="text-slate-300 text-sm leading-relaxed">
                        Per sicurezza, al salvataggio tutte le sessioni aperte verranno disconnesse.
                    </p>
                </div>
            </div>

            <div className="flex-1 flex items-center justify-center px-6 py-10 bg-slate-50">
                <Card className="w-full max-w-md p-8 shadow-sm border-slate-200" data-testid="reset-password-card">
                    <h2 className="text-2xl font-semibold tracking-tight text-slate-900 mb-1">
                        Nuova password
                    </h2>
                    <p className="text-sm text-slate-500 mb-6">
                        Scegli una nuova password per il tuo account.
                    </p>

                    {done ? (
                        <div data-testid="reset-success" className="text-sm text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-md px-4 py-3">
                            Password aggiornata correttamente. Verrai reindirizzato all&apos;accesso…
                        </div>
                    ) : (
                        <form onSubmit={submit} className="space-y-4">
                            <div>
                                <Label htmlFor="pwd" className="text-xs uppercase tracking-wider text-slate-500">
                                    Nuova password
                                </Label>
                                <Input
                                    id="pwd"
                                    data-testid="reset-password-input"
                                    type="password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    required
                                    minLength={8}
                                    className="mt-1"
                                />
                            </div>
                            <div>
                                <Label htmlFor="pwd2" className="text-xs uppercase tracking-wider text-slate-500">
                                    Ripeti password
                                </Label>
                                <Input
                                    id="pwd2"
                                    data-testid="reset-password-confirm-input"
                                    type="password"
                                    value={confirm}
                                    onChange={(e) => setConfirm(e.target.value)}
                                    required
                                    minLength={8}
                                    className="mt-1"
                                />
                            </div>
                            {err && (
                                <div data-testid="reset-error" className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-md px-3 py-2">
                                    {err}
                                </div>
                            )}
                            <Button
                                type="submit"
                                data-testid="reset-submit-button"
                                disabled={loading}
                                className="w-full bg-sky-700 hover:bg-sky-800 text-white"
                            >
                                {loading ? "Salvataggio..." : "Salva nuova password"}
                            </Button>
                        </form>
                    )}

                    <div className="mt-6 text-center">
                        <Link to="/login" data-testid="reset-back-to-login" className="text-sm text-sky-700 hover:text-sky-800">
                            ← Torna all&apos;accesso
                        </Link>
                    </div>
                </Card>
            </div>
        </div>
    );
}
