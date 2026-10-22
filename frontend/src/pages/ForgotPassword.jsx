import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";

const BG_URL = "https://images.unsplash.com/photo-1742148186848-8b257455009b?crop=entropy&cs=srgb&fm=jpg&q=85&w=1920";

export default function ForgotPassword() {
    const [email, setEmail] = useState("");
    const [sent, setSent] = useState(false);
    const [loading, setLoading] = useState(false);

    const submit = async (e) => {
        e.preventDefault();
        setLoading(true);
        try {
            await api.post("/auth/password-reset/request", { email });
        } catch {
            /* risposta identica anche in caso di errore: non riveliamo nulla */
        }
        setLoading(false);
        setSent(true);
    };

    return (
        <div className="min-h-screen flex">
            <div
                className="hidden lg:flex flex-1 relative items-end p-12 bg-cover bg-center"
                style={{ backgroundImage: `linear-gradient(rgba(15,23,42,0.85),rgba(15,23,42,0.92)), url(${BG_URL})` }}
            >
                <div className="text-slate-100 max-w-md">
                    <h1 className="text-4xl font-semibold tracking-tight leading-tight mb-4">
                        Recupera l&apos;accesso<br />al tuo gestionale.
                    </h1>
                    <p className="text-slate-300 text-sm leading-relaxed">
                        Ti invieremo un link sicuro per reimpostare la password. Il link è valido per 45 minuti.
                    </p>
                </div>
            </div>

            <div className="flex-1 flex items-center justify-center px-6 py-10 bg-slate-50">
                <Card className="w-full max-w-md p-8 shadow-sm border-slate-200" data-testid="forgot-password-card">
                    <h2 className="text-2xl font-semibold tracking-tight text-slate-900 mb-1">
                        Password dimenticata
                    </h2>
                    <p className="text-sm text-slate-500 mb-6">
                        Inserisci la tua email: se è associata a un account riceverai le istruzioni.
                    </p>

                    {sent ? (
                        <div data-testid="forgot-password-success" className="text-sm text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-md px-4 py-3">
                            Se l&apos;indirizzo è associato a un account, riceverai a breve un&apos;email con il link
                            per reimpostare la password. Controlla anche la cartella spam.
                        </div>
                    ) : (
                        <form onSubmit={submit} className="space-y-4">
                            <div>
                                <Label htmlFor="email" className="text-xs uppercase tracking-wider text-slate-500">
                                    Email
                                </Label>
                                <Input
                                    id="email"
                                    data-testid="forgot-email-input"
                                    type="email"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    required
                                    className="mt-1"
                                />
                            </div>
                            <Button
                                type="submit"
                                data-testid="forgot-submit-button"
                                disabled={loading}
                                className="w-full bg-sky-700 hover:bg-sky-800 text-white"
                            >
                                {loading ? "Invio..." : "Invia istruzioni"}
                            </Button>
                        </form>
                    )}

                    <div className="mt-6 text-center">
                        <Link to="/login" data-testid="back-to-login-link" className="text-sm text-sky-700 hover:text-sky-800">
                            ← Torna all&apos;accesso
                        </Link>
                    </div>
                </Card>
            </div>
        </div>
    );
}
