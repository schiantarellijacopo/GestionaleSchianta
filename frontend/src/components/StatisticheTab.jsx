import { useEffect, useState } from "react";
import { api, fmtEur } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Loading } from "@/components/Shared";
import { TrendingUp, TrendingDown, Wallet, Building2, RotateCcw } from "lucide-react";

export default function StatisticheTab() {
    const [dal, setDal] = useState("");
    const [al, setAl] = useState("");
    const [d, setD] = useState(null);

    const load = () => {
        const params = {};
        if (dal) params.dal = dal;
        if (al) params.al = al;
        api.get("/contabilita/statistiche", { params }).then((r) => setD(r.data));
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [dal, al]);

    if (!d) return <div className="mt-4"><Loading /></div>;

    return (
        <div className="mt-4 space-y-4" data-testid="statistiche-tab">
            {/* Filtri periodo */}
            <Card className="p-4 border-slate-200">
                <div className="flex items-end gap-3 flex-wrap">
                    <div className="text-sm font-semibold text-slate-700 mr-2">Statistiche del periodo</div>
                    <div>
                        <Label className="text-[10px]">Dal</Label>
                        <Input type="date" value={dal} onChange={(e) => setDal(e.target.value)} className="w-40" data-testid="stat-dal" />
                    </div>
                    <div>
                        <Label className="text-[10px]">Al</Label>
                        <Input type="date" value={al} onChange={(e) => setAl(e.target.value)} className="w-40" data-testid="stat-al" />
                    </div>
                    <Button variant="outline" size="sm" onClick={() => { setDal(""); setAl(""); }} data-testid="stat-reset">
                        <RotateCcw size={13} className="mr-1" /> Tutto il periodo
                    </Button>
                </div>
            </Card>

            {/* 7 KPI cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2" data-testid="stat-kpi">
                <KPI label="Entrate" v={d.kpi.entrate} accent="emerald" icon={<TrendingUp size={14} />} />
                <KPI label="Provvigioni" v={d.kpi.provvigioni} accent="sky" />
                <KPI label="Crediti" v={d.kpi.crediti} accent="amber" />
                <KPI label="Rimesse" v={d.kpi.rimesse} accent="violet" />
                <KPI label="Sconti" v={d.kpi.sconti} accent="orange" />
                <KPI label="Spese" v={d.kpi.spese} accent="rose" icon={<TrendingDown size={14} />} />
                <KPI label="Saldo Cassa Cmp." v={d.kpi.saldo_cassa_compagnie} accent="slate" bold />
            </div>

            {/* Liquidità: 2 card grandi */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3" data-testid="stat-liquidita">
                <Card className="p-5 border-emerald-200 border-l-4 border-l-emerald-500 bg-emerald-50/30">
                    <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-emerald-800 mb-1">
                        <Wallet size={14} /> Liquidità Disponibile
                    </div>
                    <div className="text-3xl font-bold text-emerald-700 num">{fmtEur(d.liquidita_disponibile)}</div>
                    <div className="text-[11px] text-slate-500 mt-2">
                        {fmtEur(d.sum_conti)} (conti) − {fmtEur(d.crediti_attivi)} (sospesi/anticipi) − {fmtEur(d.kpi.saldo_cassa_compagnie)} (debito vs. compagnie)
                    </div>
                </Card>
                <Card className="p-5 border-sky-200 border-l-4 border-l-sky-500 bg-sky-50/30">
                    <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-sky-800 mb-1">
                        <Wallet size={14} /> Liquidità Postera
                    </div>
                    <div className="text-3xl font-bold text-sky-700 num">{fmtEur(d.liquidita_postera)}</div>
                    <div className="text-[11px] text-slate-500 mt-2">
                        {fmtEur(d.sum_conti)} (conti) − {fmtEur(d.kpi.saldo_cassa_compagnie)} (debito vs. compagnie)
                    </div>
                </Card>
            </div>

            {/* Saldi per conto cassa */}
            <Card className="border-slate-200">
                <div className="px-4 py-2 bg-slate-50 border-b border-slate-200">
                    <div className="text-sm font-semibold uppercase tracking-wider text-slate-700">
                        Saldo per Conto / Metodo di Pagamento
                    </div>
                </div>
                <table className="tbl w-full text-xs">
                    <thead>
                        <tr className="bg-slate-900 text-white">
                            <th className="text-left px-3 py-2">Conto</th>
                            <th className="text-right px-3 py-2">Saldo iniziale</th>
                            <th className="text-right px-3 py-2">Entrate cumulative</th>
                            <th className="text-right px-3 py-2">Uscite cumulative</th>
                            <th className="text-right px-3 py-2">Saldo attuale</th>
                        </tr>
                    </thead>
                    <tbody>
                        {d.saldi_conti.map((c) => (
                            <tr key={c.id} data-testid={`stat-conto-${c.id}`}>
                                <td className="px-3 py-1.5 font-medium">{c.nome}</td>
                                <td className="num text-right px-3 text-slate-500">{fmtEur(c.saldo_iniziale)}</td>
                                <td className="num text-right px-3 text-emerald-700">{fmtEur(c.entrate)}</td>
                                <td className="num text-right px-3 text-rose-600">{fmtEur(c.uscite)}</td>
                                <td className={`num text-right px-3 font-bold ${c.saldo_attuale >= 0 ? "text-slate-900" : "text-rose-700"}`}>
                                    {fmtEur(c.saldo_attuale)}
                                </td>
                            </tr>
                        ))}
                        <tr className="bg-slate-100 font-bold">
                            <td className="px-3 py-2">TOTALE CONTI</td>
                            <td colSpan={3}></td>
                            <td className="num text-right px-3">{fmtEur(d.sum_conti)}</td>
                        </tr>
                    </tbody>
                </table>
            </Card>

            {/* Saldi per compagnia */}
            {(d.saldi_compagnie || []).length > 0 && (
                <Card className="border-slate-200">
                    <div className="px-4 py-2 bg-slate-50 border-b border-slate-200">
                        <div className="text-sm font-semibold uppercase tracking-wider text-slate-700 flex items-center gap-2">
                            <Building2 size={14} /> Saldo per Compagnia (cumulativo)
                        </div>
                    </div>
                    <table className="tbl w-full text-xs">
                        <thead>
                            <tr className="bg-slate-900 text-white">
                                <th className="text-left px-3 py-2">Compagnia</th>
                                <th className="text-right px-3 py-2">Incassi lordi</th>
                                <th className="text-right px-3 py-2">Provvigioni</th>
                                <th className="text-right px-3 py-2">Saldo dovuto</th>
                                <th className="text-right px-3 py-2">Rimesse pagate</th>
                                <th className="text-right px-3 py-2">Saldo attuale</th>
                            </tr>
                        </thead>
                        <tbody>
                            {d.saldi_compagnie.map((s) => (
                                <tr key={s.compagnia_id}>
                                    <td className="px-3 py-1.5 font-medium">{s.compagnia}</td>
                                    <td className="num text-right px-3">{fmtEur(s.incassi_lordi)}</td>
                                    <td className="num text-right px-3 text-sky-700">{fmtEur(s.provvigioni)}</td>
                                    <td className="num text-right px-3">{fmtEur(s.saldo_dovuto)}</td>
                                    <td className="num text-right px-3 text-violet-700">{fmtEur(s.rimesse_pagate)}</td>
                                    <td className={`num text-right px-3 font-bold ${s.saldo_cassa > 0 ? "text-rose-700" : s.saldo_cassa < 0 ? "text-emerald-700" : "text-slate-500"}`}>
                                        {fmtEur(s.saldo_cassa)}
                                    </td>
                                </tr>
                            ))}
                            <tr className="bg-slate-100 font-bold">
                                <td className="px-3 py-2">TOTALE DEBITO COMPAGNIE</td>
                                <td colSpan={4}></td>
                                <td className="num text-right px-3">{fmtEur(d.kpi.saldo_cassa_compagnie)}</td>
                            </tr>
                        </tbody>
                    </table>
                </Card>
            )}
        </div>
    );
}

function KPI({ label, v, accent = "slate", bold, icon }) {
    const colors = {
        emerald: "border-l-emerald-500",
        sky: "border-l-sky-500",
        amber: "border-l-amber-500",
        violet: "border-l-violet-500",
        orange: "border-l-orange-500",
        rose: "border-l-rose-500",
        slate: "border-l-slate-700",
    };
    return (
        <Card className={`p-3 border-slate-200 border-l-4 ${colors[accent]}`}>
            <div className="text-[10px] uppercase tracking-wider text-slate-500 flex items-center gap-1">
                {icon} {label}
            </div>
            <div className={`num ${bold ? "text-xl font-bold text-slate-900" : "text-base font-semibold text-slate-800"} mt-1`}>
                {fmtEur(v || 0)}
            </div>
        </Card>
    );
}
