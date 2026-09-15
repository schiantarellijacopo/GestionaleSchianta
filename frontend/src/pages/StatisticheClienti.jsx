import { useEffect, useState } from "react";
import { api, fmtEur } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Loading } from "@/components/Shared";
import { Trophy, Users } from "lucide-react";

const COLOR_MAP = {
    sky: "border-sky-400 text-sky-700",
    emerald: "border-emerald-400 text-emerald-700",
    amber: "border-amber-400 text-amber-700",
    rose: "border-rose-400 text-rose-700",
    indigo: "border-indigo-400 text-indigo-700",
    violet: "border-violet-400 text-violet-700",
};
const SegCard = ({ label, value, hint, color }) => (
    <Card className={`p-3 border-l-4 bg-white ${COLOR_MAP[color] || COLOR_MAP.sky}`}>
        <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
        <div className="text-2xl font-bold mt-0.5">{value ?? "—"}</div>
        <div className="text-[10px] text-slate-500 italic">{hint}</div>
    </Card>
);

export function TopClientiModulo() {
    const currentYear = new Date().getFullYear();
    const [anno, setAnno] = useState(currentYear);
    const [tutti, setTutti] = useState(false);
    const [pctRegalo, setPctRegalo] = useState(5);
    const [data, setData] = useState(null);
    useEffect(() => {
        setData(null);
        api.get("/cervello/top-clienti", { params: { anno, limit: 100, tutti } }).then((r) => setData(r.data));
    }, [anno, tutti]);
    return (
        <div className="space-y-4">
            <Card className="p-3 flex flex-wrap items-end gap-4">
                <div>
                    <Label className="text-xs">Anno</Label>
                    <Select value={String(anno)} onValueChange={(v) => setAnno(parseInt(v))}>
                        <SelectTrigger className="w-32" data-testid="topcli-anno"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            {[0, -1, -2, -3, -4].map((d) => {
                                const y = currentYear + d;
                                return <SelectItem key={y} value={String(y)}>{y}</SelectItem>;
                            })}
                        </SelectContent>
                    </Select>
                </div>
                <div>
                    <Label className="text-xs">% Regalo su provvigioni</Label>
                    <div className="relative w-28">
                        <Input type="number" min="0" step="0.5" value={pctRegalo}
                            onChange={(e) => setPctRegalo(parseFloat(e.target.value) || 0)}
                            className="h-9" data-testid="topcli-pct-regalo" />
                        <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-slate-400">%</span>
                    </div>
                </div>
                <div>
                    <Label className="text-xs block mb-1">Clienti</Label>
                    <div className="flex rounded border border-slate-200 overflow-hidden">
                        <button onClick={() => setTutti(false)} data-testid="topcli-primi100"
                            className={`text-xs px-3 py-2 ${!tutti ? "bg-slate-800 text-white" : "bg-white text-slate-600"}`}>Primi 100</button>
                        <button onClick={() => setTutti(true)} data-testid="topcli-tutti"
                            className={`text-xs px-3 py-2 border-l border-slate-200 ${tutti ? "bg-slate-800 text-white" : "bg-white text-slate-600"}`}>Tutti gli attivi</button>
                    </div>
                </div>
            </Card>
            {!data ? <Loading /> : (
                <>
                    <Card className="p-3 bg-violet-50/40 border-violet-200">
                        <div className="flex items-center gap-3 text-sm">
                            <Trophy className="text-violet-600" />
                            <div>
                                <div className="font-semibold">Pareto 80/20</div>
                                <div className="text-xs text-slate-600">
                                    I primi <b>{data.pareto_80_idx}</b> clienti generano l&apos;80% delle provvigioni (totale: {fmtEur(data.totale_provvigioni)} su {data.n_clienti_top} clienti{data.tutti ? " attivi" : ""})
                                </div>
                            </div>
                        </div>
                    </Card>
                    <Card className="p-2 overflow-x-auto">
                        <table className="w-full text-xs" data-testid="topcli-table">
                            <thead><tr className="text-left border-b text-slate-500">
                                <th className="py-2 w-10">#</th>
                                <th>Cliente</th><th>Tipo</th>
                                <th className="text-right">Cliente da</th>
                                <th className="text-right">Polizze attive</th>
                                <th className="text-right">Premi netti</th>
                                <th className="text-right">Provvigioni</th>
                                <th className="text-right text-amber-700">Regalo ({pctRegalo}%)</th>
                                <th className="text-right">% sul totale</th>
                                <th className="text-right">% cumulata</th>
                            </tr></thead>
                            <tbody>
                                {data.items.map((r, i) => (
                                    <tr key={r.anagrafica_id} className={`border-b border-slate-100 ${i < data.pareto_80_idx ? "bg-amber-50/40 font-medium" : ""}`}>
                                        <td className="py-1.5 font-mono">{r.rank}</td>
                                        <td>{r.nome}</td>
                                        <td className="text-xs text-slate-500">{r.tipo === "persona_giuridica" ? "Azienda" : "Privato"}</td>
                                        <td className="text-right text-slate-600">{r.anni_cliente != null ? `${r.anni_cliente} ${r.anni_cliente === 1 ? "anno" : "anni"}` : "—"}</td>
                                        <td className="text-right">{r.n_polizze_attive}</td>
                                        <td className="text-right font-mono">{fmtEur(r.premi_netti_anno)}</td>
                                        <td className="text-right font-mono font-semibold">{fmtEur(r.provvigioni_anno)}</td>
                                        <td className="text-right font-mono text-amber-700">{fmtEur((r.provvigioni_anno || 0) * pctRegalo / 100)}</td>
                                        <td className="text-right text-slate-500">{r.incidenza_pct}%</td>
                                        <td className="text-right text-slate-500">{r.incidenza_cumulata_pct}%</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </Card>
                </>
            )}
        </div>
    );
}

export function SegmentazioneModulo() {
    const [data, setData] = useState(null);
    useEffect(() => { api.get("/cervello/segmentazione").then((r) => setData(r.data)); }, []);
    if (!data) return <Loading />;
    const b = data.breakdown;
    return (
        <div className="space-y-4">
            <Card className="p-4 bg-emerald-50/40 border-emerald-200">
                <div className="flex items-center gap-3">
                    <Users className="text-emerald-600" size={24} />
                    <div>
                        <div className="text-3xl font-bold text-slate-800">{data.tasso_multi_comparto_pct}%</div>
                        <div className="text-xs text-slate-600">
                            Tasso di multi-comparto · <b>{data.totale_clienti_con_polizze}</b> clienti con polizze attive
                        </div>
                    </div>
                </div>
                <div className="text-xs text-slate-500 mt-2">
                    Più comparti = più fidelizzazione. Target ideale: &gt;25% multi-comparto.
                </div>
            </Card>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <SegCard label="Mono Auto" value={b.mono_auto} hint="Massimo rischio churn" color="rose" />
                <SegCard label="Mono Persone" value={b.mono_persone} hint="Cross-selling target" color="amber" />
                <SegCard label="Mono Aziende" value={b.mono_aziende} hint="Up-selling target" color="indigo" />
                <SegCard label="Mono Vita" value={b.mono_vita} hint="Solo Vita: cross-sell" color="violet" />
                <SegCard label="2 Comparti" value={b.due_comparti} hint="Fidelizzati" color="sky" />
                <SegCard label="3 Comparti" value={b.tre_comparti} hint="Molto fidelizzati" color="emerald" />
                <SegCard label="4 Comparti" value={b.quattro_comparti} hint="Top fidelizzazione" color="emerald" />
            </div>
        </div>
    );
}
