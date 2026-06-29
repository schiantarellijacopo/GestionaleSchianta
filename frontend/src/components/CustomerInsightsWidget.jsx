/**
 * CustomerInsightsWidget — widget compatto da posizionare in AnagraficaDetail.
 * Mostra KPI rapide cliente + opportunità cross-selling + rischio score +
 * ultimo suggerimento AI.
 */
import { useEffect, useState } from "react";
import { api, fmtEur } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Sparkles, ShieldAlert, TrendingUp, FileText, AlertTriangle } from "lucide-react";

export default function CustomerInsightsWidget({ anagrafica_id }) {
    const [data, setData] = useState(null);
    useEffect(() => {
        api.get(`/anagrafiche/${anagrafica_id}/customer-insights-widget`)
            .then((r) => setData(r.data))
            .catch(() => setData({}));
    }, [anagrafica_id]);

    if (!data) return null;
    const kpi = data.kpi || {};
    const opp = data.cross_selling_opportunita || [];
    const rsk = data.rischio_score ?? 0;
    const ai = data.ultimo_suggerimento_ai;

    const rcol = rsk <= 3 ? "emerald" : rsk <= 6 ? "amber" : "rose";

    return (
        <Card className="p-4 mb-4 bg-gradient-to-br from-violet-50 via-white to-sky-50 border-violet-200" data-testid="customer-insights-widget">
            <div className="flex items-center gap-2 mb-3">
                <Sparkles className="text-violet-600" size={16} />
                <h3 className="font-semibold text-violet-900 text-sm">Customer Insights · AI Snapshot</h3>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-6 gap-2 text-center">
                <KpiMini icon={FileText} label="Polizze attive" value={kpi.n_polizze_attive} color="sky" />
                <KpiMini icon={FileText} label="Polizze scadute" value={kpi.n_polizze_scadute} color="amber" />
                <KpiMini icon={TrendingUp} label="Rami coperti" value={kpi.n_rami_coperti} color="emerald" />
                <KpiMini icon={AlertTriangle} label="Sinistri (anno)" value={kpi.n_sinistri_anno_corrente} color="rose" />
                <KpiMini icon={FileText} label="Premio attivo" value={fmtEur(kpi.premio_totale_attivo)} color="violet" mono />
                <KpiMini icon={ShieldAlert} label="Rischio" value={`${rsk}/10`} color={rcol} mono />
            </div>
            {opp.length > 0 && (
                <div className="mt-3 pt-3 border-t border-violet-100">
                    <div className="text-[10px] uppercase text-violet-700 font-semibold mb-1">Opportunità Cross-Selling</div>
                    <div className="flex flex-wrap gap-1.5">
                        {opp.map((r) => (
                            <span key={r} className="text-[11px] bg-violet-100 text-violet-800 px-2 py-0.5 rounded-full">
                                {r}
                            </span>
                        ))}
                    </div>
                </div>
            )}
            {ai && ai.testo && (
                <div className="mt-3 pt-3 border-t border-violet-100 text-xs text-slate-700 italic">
                    💡 <span className="font-medium">AI:</span> {ai.testo}
                </div>
            )}
        </Card>
    );
}

const COLOR_BG = {
    sky: "border-sky-200 text-sky-700",
    emerald: "border-emerald-200 text-emerald-700",
    amber: "border-amber-200 text-amber-700",
    rose: "border-rose-200 text-rose-700",
    violet: "border-violet-200 text-violet-700",
    slate: "border-slate-200 text-slate-700",
};

const KpiMini = ({ icon: Icon, label, value, color, mono }) => (
    <div className={`bg-white border ${COLOR_BG[color] || COLOR_BG.sky} rounded p-2`}>
        <div className="flex items-center justify-center gap-1 text-[10px] uppercase tracking-wider text-slate-500">
            <Icon size={10} /> {label}
        </div>
        <div className={`text-lg font-bold ${mono ? "font-mono" : ""} mt-0.5`}>{value ?? "—"}</div>
    </div>
);
