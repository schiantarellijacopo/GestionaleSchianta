/**
 * Statistiche — overview aggregata: KPI globali, top 5 compagnie, top 5 rami,
 * in scadenza, nuovi clienti. Read-only, accessibile a tutti i ruoli ≥ collaboratore.
 */
import { useEffect, useState } from "react";
import { api, fmtEur } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { PageHeader, Loading } from "@/components/Shared";
import {
    TrendingUp, Users, Building, FileText, AlertTriangle, Wallet,
    Calendar, Trophy, PieChart,
} from "lucide-react";

export default function Statistiche() {
    const [s, setS] = useState(null);
    useEffect(() => {
        api.get("/statistiche/overview").then((r) => setS(r.data)).catch(() => setS({}));
    }, []);
    if (!s) return <Loading />;
    return (
        <div data-testid="statistiche-page" className="space-y-5">
            <PageHeader title="Statistiche" subtitle="Indicatori aggregati globali dell'agenzia" />

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <KCard color="sky" icon={Users} label="Clienti privati" value={s.clienti_privati} />
                <KCard color="indigo" icon={Building} label="Clienti aziende" value={s.clienti_aziende} />
                <KCard color="emerald" icon={TrendingUp} label="Nuovi clienti (30g)" value={s.nuovi_clienti_30g} />
                <KCard color="violet" icon={FileText} label="Polizze attive" value={s.polizze_attive} />
                <KCard color="amber" icon={Calendar} label="In scadenza (30g)" value={s.polizze_in_scadenza_30g} />
                <KCard color="rose" icon={AlertTriangle} label="Sinistri aperti" value={s.sinistri_aperti} />
                <KCard color="slate" icon={AlertTriangle} label="Sinistri ultimo anno" value={s.sinistri_ultimo_anno} />
                <KCard color="emerald" icon={Wallet} label="Premio attivo totale" value={fmtEur(s.premio_attivo_totale)} mono />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                <Card className="p-4">
                    <div className="flex items-center gap-2 mb-3">
                        <Trophy size={16} className="text-amber-600" />
                        <h2 className="font-semibold text-slate-800">Top 5 Compagnie per Premio</h2>
                    </div>
                    {(s.top_compagnie || []).length === 0 ? (
                        <div className="text-sm text-slate-500">Nessun dato</div>
                    ) : (
                        <table className="w-full text-sm">
                            <thead><tr className="text-xs text-slate-500 border-b">
                                <th className="text-left py-1.5">Compagnia</th>
                                <th className="text-right">Polizze</th>
                                <th className="text-right">Premio</th>
                            </tr></thead>
                            <tbody>
                                {s.top_compagnie.map((c) => (
                                    <tr key={c.id} className="border-b border-slate-100">
                                        <td className="py-1.5 font-medium">{c.nome}</td>
                                        <td className="text-right">{c.n_polizze}</td>
                                        <td className="text-right font-mono">{fmtEur(c.premio_totale)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </Card>

                <Card className="p-4">
                    <div className="flex items-center gap-2 mb-3">
                        <PieChart size={16} className="text-sky-600" />
                        <h2 className="font-semibold text-slate-800">Top 5 Rami per Premio</h2>
                    </div>
                    {(s.top_rami || []).length === 0 ? (
                        <div className="text-sm text-slate-500">Nessun dato</div>
                    ) : (
                        <table className="w-full text-sm">
                            <thead><tr className="text-xs text-slate-500 border-b">
                                <th className="text-left py-1.5">Ramo</th>
                                <th className="text-right">Polizze</th>
                                <th className="text-right">Premio</th>
                            </tr></thead>
                            <tbody>
                                {s.top_rami.map((r, i) => (
                                    <tr key={i} className="border-b border-slate-100">
                                        <td className="py-1.5 font-medium">{r.ramo}</td>
                                        <td className="text-right">{r.n_polizze}</td>
                                        <td className="text-right font-mono">{fmtEur(r.premio_totale)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </Card>
            </div>
        </div>
    );
}

const COLOR = {
    sky: "border-sky-400 text-sky-700",
    indigo: "border-indigo-400 text-indigo-700",
    emerald: "border-emerald-400 text-emerald-700",
    violet: "border-violet-400 text-violet-700",
    amber: "border-amber-400 text-amber-700",
    rose: "border-rose-400 text-rose-700",
    slate: "border-slate-400 text-slate-700",
};
const KCard = ({ icon: Ic, label, value, color, mono }) => (
    <Card className={`p-3 border-l-4 bg-white ${COLOR[color] || COLOR.sky}`} data-testid={`stat-${label}`}>
        <div className="flex items-start justify-between">
            <div>
                <div className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">{label}</div>
                <div className={`text-2xl font-bold mt-0.5 ${mono ? "font-mono" : ""}`}>{value ?? "—"}</div>
            </div>
            <Ic size={20} className={`opacity-40 ${(COLOR[color] || "").split(" ")[1]}`} />
        </div>
    </Card>
);
