import { useEffect, useState } from "react";
import { api, fmtEur } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Loading } from "@/components/Shared";
import { Label } from "@/components/ui/label";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import { BarChart3, HelpCircle, ArrowUp, ArrowDown } from "lucide-react";
import { MESI } from "@/pages/statsShared";

const CUR = new Date().getFullYear();
const MESI_FULL = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
    "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"];
const DONUT = {
    verde: ["#4f9d4f", "#6cb86c", "#8fcf8f", "#b3e0b3", "#2f7a2f", "#a7d8a7"],
    rosso: ["#9f2b4c", "#b83b5e", "#d16b85", "#e39db0", "#7a1f3a", "#c85a77"],
    teal: ["#5aa0a0", "#79b5b5", "#99c9c9", "#bcdcdc", "#3f8585", "#aad3d3"],
};

function Donut({ data, palette, subtitle, tid }) {
    const items = data || [];
    const totale = items.reduce((s, x) => s + (x.valore || 0), 0);
    return (
        <div className="flex flex-col items-center" data-testid={tid}>
            <BarChart3 size={18} className="text-sky-500 mb-2" />
            <div className="w-full" style={{ height: 230 }}>
                {items.length === 0 ? (
                    <div className="h-full flex items-center justify-center text-xs text-slate-400">Nessun dato</div>
                ) : (
                    <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                            <Pie data={items} dataKey="valore" nameKey="nome" cx="50%" cy="50%"
                                innerRadius={58} outerRadius={92} paddingAngle={1} stroke="#fff" strokeWidth={2}
                                label={({ nome, percent }) => percent > 0.06 ? nome : ""}
                                labelLine={false} style={{ fontSize: 11, fontWeight: 600 }}>
                                {items.map((_, i) => <Cell key={i} fill={palette[i % palette.length]} />)}
                            </Pie>
                            <Tooltip formatter={(v, n) => [fmtEur(v), n]} contentStyle={{ fontSize: 12 }} />
                        </PieChart>
                    </ResponsiveContainer>
                )}
            </div>
            <div className="text-sm font-semibold text-slate-600 mt-1">{subtitle}</div>
            <div className="text-[11px] text-slate-400 font-mono">{fmtEur(totale)}</div>
        </div>
    );
}

function Hint({ text }) {
    return (
        <span className="inline-flex items-center align-middle ml-1 text-slate-400" title={text}>
            <HelpCircle size={13} />
        </span>
    );
}

export default function StatisticheIncassi() {
    const now = new Date();
    const [anno, setAnno] = useState(CUR);
    const [mese, setMese] = useState(now.getMonth() + 1);
    const [d, setD] = useState(null);

    useEffect(() => {
        setD(null);
        api.get("/statistiche/incassi-situazione", { params: { anno, mese } })
            .then((r) => setD(r.data)).catch(() => setD(null));
    }, [anno, mese]);

    const anni = []; for (let a = CUR; a >= CUR - 5; a--) anni.push(a);
    const meseLabel = MESI_FULL[(mese - 1) % 12];
    const abbr = (m, y) => `${MESI[(m - 1) % 12].slice(0, 3).toLowerCase()} '${String(y).slice(2)}`;

    return (
        <div className="space-y-5" data-testid="stat-incassi-page">
            <Card className="p-3 flex flex-wrap items-end gap-3">
                <div>
                    <Label className="text-xs">Mese</Label>
                    <Select value={String(mese)} onValueChange={(v) => setMese(parseInt(v))}>
                        <SelectTrigger className="w-36" data-testid="incassi-mese"><SelectValue /></SelectTrigger>
                        <SelectContent>{MESI.map((m, i) => <SelectItem key={i} value={String(i + 1)}>{m}</SelectItem>)}</SelectContent>
                    </Select>
                </div>
                <div>
                    <Label className="text-xs">Anno</Label>
                    <Select value={String(anno)} onValueChange={(v) => setAnno(parseInt(v))}>
                        <SelectTrigger className="w-28" data-testid="incassi-anno"><SelectValue /></SelectTrigger>
                        <SelectContent>{anni.map((a) => <SelectItem key={a} value={String(a)}>{a}</SelectItem>)}</SelectContent>
                    </Select>
                </div>
            </Card>

            {!d ? <Loading /> : (
                <>
                    {/* Snapshot + KPI */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <table className="w-full text-sm" data-testid="incassi-snapshot">
                            <thead>
                                <tr>
                                    <th></th>
                                    <th className="text-right px-4 py-2 bg-amber-400/90 text-white font-bold rounded-sm w-44">{abbr(mese, anno)}</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr className="border-b border-dotted border-slate-200">
                                    <td className="py-2 text-slate-700">Titoli arretrati (scaduto)</td>
                                    <td className="py-2 text-right font-mono">{fmtEur(d.snapshot.arretrati_scaduto)}</td>
                                </tr>
                                <tr className="border-b border-dotted border-slate-200">
                                    <td className="py-2 text-slate-700">Sospesi della Rete Vendita</td>
                                    <td className="py-2 text-right font-mono">{fmtEur(d.snapshot.sospesi_rete_vendita)}</td>
                                </tr>
                                <tr className="border-b border-dotted border-slate-200">
                                    <td className="py-2 text-slate-700">Sospesi cliente</td>
                                    <td className="py-2 text-right font-mono">{fmtEur(d.snapshot.sospesi_cliente)}</td>
                                </tr>
                            </tbody>
                        </table>

                        <table className="w-full text-sm" data-testid="incassi-kpi">
                            <thead>
                                <tr>
                                    <th></th>
                                    <th className="text-right px-4 py-2 bg-amber-400/90 text-white font-bold rounded-sm w-44">{d.finestra_12 ? `${abbr(d.finestra_12.mese_start, d.finestra_12.anno_start)} - ${abbr(mese, anno)}` : ""}</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr className="border-b border-dotted border-slate-200">
                                    <td className="py-2 text-slate-700">Velocità di incasso
                                        <Hint text="Premi incassati / premi dovuti negli ultimi 12 mesi (base scadenza)." /></td>
                                    <td className="py-2 text-right font-mono">{(d.kpi.velocita_incasso ?? 0).toLocaleString("it-IT", { maximumFractionDigits: 2 })}</td>
                                </tr>
                                <tr className="border-b border-dotted border-slate-200">
                                    <td className="py-2 text-slate-700">Velocità di recupero sul cliente
                                        <Hint text="Quota di premi dovuti non rimasti insoluti negli ultimi 12 mesi." /></td>
                                    <td className="py-2 text-right font-mono">{(d.kpi.velocita_recupero_cliente ?? 0).toLocaleString("it-IT", { maximumFractionDigits: 2 })}</td>
                                </tr>
                                <tr className="border-b border-dotted border-slate-200">
                                    <td className="py-2 text-slate-700">Velocità di recupero sulla Rete Vendita
                                        <Hint text="Quota di premi recuperati rispetto agli insoluti a carico rete negli ultimi 12 mesi." /></td>
                                    <td className="py-2 text-right font-mono">{(d.kpi.velocita_recupero_rete ?? 0).toLocaleString("it-IT", { maximumFractionDigits: 2 })}</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>

                    {/* Donut */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
                        <Donut data={d.donut_provv_compagnia} palette={DONUT.verde} subtitle="per compagnia (provv.)" tid="donut-provv-compagnia" />
                        <Donut data={d.donut_provv_ramo} palette={DONUT.rosso} subtitle="per ramo (provv.)" tid="donut-provv-ramo" />
                        <Donut data={d.donut_premi_modalita} palette={DONUT.teal} subtitle="per mod. incasso (premi)" tid="donut-premi-modalita" />
                    </div>

                    {/* Situazione del mese */}
                    <div>
                        <h2 className="text-2xl font-light text-slate-700 border-b pb-2 mb-3">Incassi: situazione di {meseLabel}</h2>
                        <table className="w-full text-sm" data-testid="incassi-situazione">
                            <thead>
                                <tr>
                                    <th></th>
                                    <th className="text-right px-4 py-2 bg-orange-300 text-slate-800 font-bold w-40">{anno}</th>
                                    <th className="text-right px-4 py-2 bg-orange-300 text-slate-800 font-bold w-40">{anno - 1}</th>
                                    <th className="text-right px-4 py-2 bg-orange-300 text-slate-800 font-bold w-32">Var. %</th>
                                </tr>
                            </thead>
                            <tbody>
                                {d.situazione.map((r) => {
                                    const up = r.var_perc >= 0;
                                    return (
                                        <tr key={r.label} className="border-b border-slate-100" data-testid={`riga-${r.label.replace(/\s+/g, "-").toLowerCase()}`}>
                                            <td className="py-3 text-slate-700">{r.label}</td>
                                            <td className="py-3 text-right font-mono">{fmtEur(r.corrente)}</td>
                                            <td className="py-3 text-right font-mono text-slate-500">{fmtEur(r.precedente)}</td>
                                            <td className={`py-3 text-right font-mono font-semibold ${up ? "text-emerald-600" : "text-rose-600"}`}>
                                                <span className="inline-flex items-center justify-end gap-1">
                                                    {(up ? "" : "") + r.var_perc.toLocaleString("it-IT", { maximumFractionDigits: 2 })}%
                                                    {up ? <ArrowUp size={14} /> : <ArrowDown size={14} />}
                                                </span>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                        {d.scoped_operatore && (
                            <p className="text-[11px] text-slate-400 mt-2">Dati limitati alle tue provvigioni/incassi.</p>
                        )}
                    </div>
                </>
            )}
        </div>
    );
}
