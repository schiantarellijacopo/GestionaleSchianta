/**
 * ImpostazioniFirme — Pannello admin per configurare Namirial eSignAnyWhere.
 *
 * I campi sono salvati in db.azienda_config (endpoint POST /librerie/azienda):
 * - firma_provider     (namirial)
 * - firma_base_url     (sandbox: https://demo.esignanywhere.net/Api/v6)
 * - firma_api_token    (64ch — Settings → API Tokens su eSAW)
 * - firma_environment  (sandbox | production)
 * - firma_webhook_secret (opzionale, se il tenant lo attiva)
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { PenLine, Save, ExternalLink, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export default function ImpostazioniFirme() {
    const [cfg, setCfg] = useState(null);
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        api.get("/librerie/azienda").then((r) => setCfg(r.data)).catch(() => setCfg({}));
    }, []);

    if (!cfg) return <div className="text-slate-400 p-8">Caricamento…</div>;

    const set = (k, v) => setCfg((c) => ({ ...c, [k]: v }));

    const salva = async () => {
        setBusy(true);
        try {
            await api.put("/librerie/azienda", cfg);
            toast.success("Configurazione firma salvata");
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore salvataggio");
        } finally { setBusy(false); }
    };

    const configurato = !!(cfg.firma_base_url && cfg.firma_api_token);

    return (
        <div className="space-y-6">
            {/* Hero */}
            <div className="rounded-2xl bg-gradient-to-br from-indigo-600 via-blue-700 to-slate-900 p-6 text-white shadow-lg relative overflow-hidden">
                <div className="absolute -right-16 -top-16 w-64 h-64 rounded-full bg-white/10 blur-3xl" />
                <div className="relative flex items-start gap-4">
                    <div className="w-14 h-14 rounded-2xl bg-white/20 backdrop-blur flex items-center justify-center">
                        <PenLine size={28} />
                    </div>
                    <div className="flex-1">
                        <h1 className="text-2xl font-bold">Firma Elettronica — Namirial</h1>
                        <p className="text-sm text-white/80 mt-1">
                            Configura eSignAnyWhere v6 per supportare firma OTP SMS/Email, grafometrica tablet e link remoto
                        </p>
                    </div>
                    <div className={`text-xs px-3 py-1 rounded-full font-semibold shrink-0 ${
                        configurato ? "bg-emerald-500/30 text-emerald-100" : "bg-amber-500/30 text-amber-100"
                    }`}>
                        {configurato ? "✓ Configurato" : "⚠ Da configurare"}
                    </div>
                </div>
            </div>

            <Card className="p-6 rounded-2xl shadow-sm border border-slate-100">
                <div className="mb-5">
                    <div className="text-xs font-bold text-indigo-700 uppercase tracking-wider mb-1">Credenziali eSignAnyWhere</div>
                    <div className="text-xs text-slate-500">
                        Le trovi sul tuo tenant Namirial: <b>Settings → API Tokens and Apps → New Token</b>
                    </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                        <Label>Ambiente</Label>
                        <Select value={cfg.firma_environment || "sandbox"}
                                onValueChange={(v) => set("firma_environment", v)}>
                            <SelectTrigger data-testid="firma-env"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="sandbox">Sandbox (demo)</SelectItem>
                                <SelectItem value="production">Produzione</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>

                    <div>
                        <Label>URL API Base</Label>
                        <Input value={cfg.firma_base_url || ""}
                               onChange={(e) => set("firma_base_url", e.target.value)}
                               placeholder="https://demo.esignanywhere.net/Api/v6"
                               data-testid="firma-base-url" />
                    </div>

                    <div className="md:col-span-2">
                        <Label>API Token (64ch)</Label>
                        <Input type="password" value={cfg.firma_api_token || ""}
                               onChange={(e) => set("firma_api_token", e.target.value)}
                               placeholder="Bearer token generato in eSAW → Settings → API Tokens"
                               data-testid="firma-api-token" />
                        <div className="text-[11px] text-slate-500 mt-1">
                            Salvato solo lato server. Non compare mai nel browser dopo il primo salvataggio.
                        </div>
                    </div>

                    <div className="md:col-span-2">
                        <Label>Webhook Secret (opzionale)</Label>
                        <Input type="password" value={cfg.firma_webhook_secret || ""}
                               onChange={(e) => set("firma_webhook_secret", e.target.value)}
                               placeholder="Se il tuo tenant Namirial ha attivato la firma HMAC sui webhook"
                               data-testid="firma-webhook-secret" />
                    </div>
                </div>

                <div className="mt-6 flex flex-wrap items-center justify-between gap-3 pt-4 border-t border-slate-100">
                    <a href="https://namirial.atlassian.net/wiki/spaces/eSign/pages/91982330/Tutorial+Hello+World"
                       target="_blank" rel="noreferrer"
                       className="text-xs text-indigo-600 hover:underline inline-flex items-center gap-1">
                        <ExternalLink size={12} /> Documentazione Namirial v6
                    </a>
                    <Button onClick={salva} disabled={busy}
                            data-testid="firma-save"
                            className="bg-gradient-to-br from-indigo-600 to-blue-700 hover:from-indigo-700 hover:to-blue-800 rounded-xl shadow-md">
                        <Save size={14} className="mr-1.5" /> {busy ? "Salvataggio…" : "Salva configurazione"}
                    </Button>
                </div>
            </Card>

            {/* Feature summary */}
            <Card className="p-6 rounded-2xl shadow-sm border border-slate-100">
                <div className="text-xs font-bold text-emerald-700 uppercase tracking-wider mb-3">Modalità di firma supportate</div>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
                    <FeatCard icon={ShieldCheck} title="OTP SMS" descr="Cliente riceve un codice via SMS e firma da smartphone/PC" gradient="from-emerald-500 to-teal-600" />
                    <FeatCard icon={ShieldCheck} title="OTP Email" descr="Codice OTP via email, ideale per clienti senza cellulare" gradient="from-sky-500 to-blue-600" />
                    <FeatCard icon={ShieldCheck} title="Grafometrica" descr="FEA biometrica su tablet in agenzia (SDK SIGNificant)" gradient="from-violet-500 to-purple-600" />
                    <FeatCard icon={ShieldCheck} title="Link remoto" descr="Link firma via WhatsApp / SMS / Email" gradient="from-amber-500 to-orange-600" />
                </div>
            </Card>
        </div>
    );
}

function FeatCard({ icon: Icon, title, descr, gradient }) {
    return (
        <div className="p-4 rounded-xl border border-slate-100 bg-white hover:shadow-md transition-shadow">
            <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${gradient} flex items-center justify-center mb-2 shadow`}>
                <Icon className="text-white" size={18} />
            </div>
            <div className="font-semibold text-sm text-slate-800">{title}</div>
            <div className="text-[11px] text-slate-500 mt-0.5">{descr}</div>
        </div>
    );
}
