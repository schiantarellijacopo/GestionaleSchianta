import { useEffect, useState, useCallback } from "react";
import { api, fmtEur } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Loading } from "@/components/Shared";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from "recharts";
import { TrendingUp, TrendingDown, Filter } from "lucide-react";

const COLORS = ["#60a5fa", "#334155", "#86efac", "#f59e0b", "#c026d3", "#0ea5e9", "#ef4444", "#14b8a6", "#a78bfa", "#fb923c"];
const annoCorr = new Date().getFullYear();
const ANNI = [annoCorr, annoCorr - 1, annoCorr - 2, annoCorr - 3];

function Donut({ title, rows }) {
    const data = (rows || []).slice(0, 10).map((r) => ({ name: r.label, value: r.premio, num: r.num }));
    return (
        <Card className="p-4">
            <div className="text-sm font-semibold text-slate-700 text-center mb-2">{title}</div>
            <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                    <Pie data={data} dataKey="value" nameKey="name" innerRadius={55} outerRadius={95} paddingAngle={1}>
                        {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                    </Pie>
                    <Tooltip formatter={(v, n, p) => [`${fmtEur(v)} · ${p.payload.num} contr.`, p.payload.name]} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                </PieChart>
            </ResponsiveContainer>
        </Card>
    );
}

function KpiRow({ label, val, conf, nv, nc }) {
    const hasConf = conf != null;
    const a = Number(nv ?? val ?? 0), b = nc == null ? null : Number(nc || 0);
    const varpct = (b != null && b !== 0) ? ((a - b) / b) * 100 : null;
    return (
        <tr className="border-b border-slate-100">
            <td className="py-2 text-slate-700">{label}</td>
            <td className="py-2 text-right font-semibold">{val}</td>
            {hasConf && <td className="py-2 text-right text-slate-500">{conf}</td>}
            {hasConf && (
                <td className="py-2 text-right">
                    {varpct == null ? "—" : (
                        <span className={`inline-flex items-center gap-1 ${varpct >= 0 ? "text-emerald-600" : "text-rose-600"}`}>
                            {varpct >= 0 ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
                            {varpct.toFixed(2)}%
                        </span>
                    )}
                </td>
            )}
        </tr>
    );
}

export default function StatistichePortafoglio() {
    const [collaboratori, setCollaboratori] = useState([]);
    const [f, setF] = useState({
        anno: String(annoCorr), anno_confronto: "none", collaboratore_id: "all",
        incasso_da: "", incasso_a: "", copertura_da: "", copertura_a: "", effetto_da: "", effetto_a: "",
    });
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        api.get("/collaboratori?tutti=true").then((r) => setCollaboratori(r.data || [])).catch(() => {});
    }, []);

    const load = useCallback(() => {
        setLoading(true);
        const p = new URLSearchParams();
        if (f.anno) p.set("anno", f.anno);
        if (f.anno_confronto && f.anno_confronto !== "none") p.set("anno_confronto", f.anno_confronto);
        if (f.collaboratore_id && f.collaboratore_id !== "all") p.set("collaboratore_id", f.collaboratore_id);
        ["incasso_da", "incasso_a", "copertura_da", "copertura_a", "effetto_da", "effetto_a"].forEach((k) => { if (f[k]) p.set(k, f[k]); });
        api.get(`/statistiche/portafoglio?${p.toString()}`).then((r) => setData(r.data)).catch(() => setData({})).finally(() => setLoading(false));
    }, [f]);
    useEffect(() => { load(); }, []); // eslint-disable-line

    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
    const hasConf = data?.kpi_confronto != null;
    const k = data?.kpi || {};
    const kc = data?.kpi_confronto || {};

    return (
        <div className="space-y-4">
            {/* Barra filtri */}
            <Card className="p-4 bg-slate-50 border-slate-200">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div>
                        <Label className="text-xs">Anno</Label>
                        <Select value={f.anno} onValueChange={(v) => set("anno", v)}>
                            <SelectTrigger data-testid="port-anno"><SelectValue /></SelectTrigger>
                            <SelectContent>{ANNI.map((a) => <SelectItem key={a} value={String(a)}>{a}</SelectItem>)}</SelectContent>
                        </Select>
                    </div>
                    <div>
                        <Label className="text-xs">Anno confronto</Label>
                        <Select value={f.anno_confronto} onValueChange={(v) => set("anno_confronto", v)}>
                            <SelectTrigger data-testid="port-anno-confronto"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="none">—</SelectItem>
                                {ANNI.map((a) => <SelectItem key={a} value={String(a)}>{a}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="col-span-2">
                        <Label className="text-xs">Collaboratore</Label>
                        <Select value={f.collaboratore_id} onValueChange={(v) => set("collaboratore_id", v)}>
                            <SelectTrigger data-testid="port-collaboratore"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Tutti</SelectItem>
                                {collaboratori.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div><Label className="text-xs">Rata/Effetto da</Label><Input type="date" value={f.effetto_da} onChange={(e) => set("effetto_da", e.target.value)} data-testid="port-effetto-da" /></div>
                    <div><Label className="text-xs">Rata/Effetto a</Label><Input type="date" value={f.effetto_a} onChange={(e) => set("effetto_a", e.target.value)} /></div>
                    <div><Label className="text-xs">Data incasso da</Label><Input type="date" value={f.incasso_da} onChange={(e) => set("incasso_da", e.target.value)} data-testid="port-incasso-da" /></div>
                    <div><Label className="text-xs">Data incasso a</Label><Input type="date" value={f.incasso_a} onChange={(e) => set("incasso_a", e.target.value)} /></div>
                    <div><Label className="text-xs">Data copertura da</Label><Input type="date" value={f.copertura_da} onChange={(e) => set("copertura_da", e.target.value)} data-testid="port-copertura-da" /></div>
                    <div><Label className="text-xs">Data copertura a</Label><Input type="date" value={f.copertura_a} onChange={(e) => set("copertura_a", e.target.value)} /></div>
                </div>
                <div className="flex justify-end mt-3">
                    <Button onClick={load} className="bg-sky-700 hover:bg-sky-800" data-testid="port-estrai"><Filter size={14} className="mr-1" /> Estrai</Button>
                </div>
            </Card>

            {loading ? <Loading /> : (
                <>
                    <Card className="p-4">
                        <div className="text-lg font-semibold text-slate-800 mb-3">Portafoglio: consistenza e distribuzione</div>
                        <table className="w-full text-sm">
                            <thead><tr className="text-xs text-slate-500 border-b">
                                <th className="text-left py-1"></th>
                                <th className="text-right py-1">{f.anno}</th>
                                {hasConf && <th className="text-right py-1">{f.anno_confronto}</th>}
                                {hasConf && <th className="text-right py-1">Var. %</th>}
                            </tr></thead>
                            <tbody data-testid="port-kpi">
                                <KpiRow label="Contratti attivi" val={k.contratti_attivi} conf={hasConf ? kc.contratti_attivi : null} nv={k.contratti_attivi} nc={hasConf ? kc.contratti_attivi : null} />
                                <KpiRow label="Premio medio per contratto" val={fmtEur(k.premio_medio)} conf={hasConf ? fmtEur(kc.premio_medio) : null} nv={k.premio_medio} nc={hasConf ? kc.premio_medio : null} />
                                <KpiRow label="Portafoglio per operatore" val={fmtEur(k.portafoglio_per_operatore)} conf={hasConf ? fmtEur(kc.portafoglio_per_operatore) : null} nv={k.portafoglio_per_operatore} nc={hasConf ? kc.portafoglio_per_operatore : null} />
                            </tbody>
                        </table>
                        <div className="text-xs text-slate-400 mt-2">Premio totale portafoglio: <b>{fmtEur(k.premio_totale)}</b></div>
                    </Card>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <Donut title="per compagnia" rows={data?.per_compagnia} />
                        <Donut title="per macro-ramo" rows={data?.per_ramo} />
                        <Donut title="per operatore" rows={data?.per_operatore} />
                    </div>
                </>
            )}
        </div>
    );
}
