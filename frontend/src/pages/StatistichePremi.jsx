import { useEffect, useState } from "react";
import { api, fmtEur } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Loading } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid } from "recharts";
import { MESI, CUR, ALL_COLS, YEAR_BARS, FSel, MeseRange, YearPicker, RamoMulti } from "@/pages/statsShared";

export default function StatistichePremi() {
    const { user } = useAuth();
    const isAdmin = user?.role === "admin";
    const [sel, setSel] = useState([CUR, CUR - 1]);
    const [dataField, setDataField] = useState("incasso");
    const [meseDa, setMeseDa] = useState(1);
    const [meseA, setMeseA] = useState(12);
    const [metriche, setMetriche] = useState(["netto", "provvigioni", "lordo"]);
    const [compagniaId, setCompagniaId] = useState("all");
    const [operatoreId, setOperatoreId] = useState("all");
    const [tipo, setTipo] = useState("all");
    const [compagnie, setCompagnie] = useState([]);
    const [operatori, setOperatori] = useState([]);
    const [rami, setRami] = useState([]);
    const [ramoSel, setRamoSel] = useState([]);
    const [data, setData] = useState(null);

    useEffect(() => {
        api.get("/compagnie").then((r) => setCompagnie(r.data || []));
        api.get("/librerie/rami", { params: { dedup: 1, con_polizze: 1 } })
            .then((r) => setRami((r.data || []).map((x) => x.nome).filter(Boolean)))
            .catch(() => setRami([]));
        if (isAdmin) api.get("/auth/users").then((r) => setOperatori((r.data || []).filter((u) => u.role !== "cliente")));
    }, [isAdmin]);

    useEffect(() => {
        if (!sel.length) { setData({ anni: [] }); return; }
        setData(null);
        const p = { anni: sel.join(","), data_field: dataField, mese_da: meseDa, mese_a: meseA };
        if (compagniaId !== "all") p.compagnia_id = compagniaId;
        if (isAdmin && operatoreId !== "all") p.operatore_id = operatoreId;
        if (tipo !== "all") p.tipo = tipo;
        if (ramoSel.length) p.ramo = ramoSel.join(",");
        api.get("/statistiche/premi-provvigioni", { params: p }).then((r) => setData(r.data));
        // eslint-disable-next-line
    }, [sel, dataField, meseDa, meseA, compagniaId, operatoreId, tipo, ramoSel, isAdmin]);

    const toggleMetrica = (k) => setMetriche((m) => m.includes(k) ? (m.length > 1 ? m.filter((x) => x !== k) : m) : [...m, k]);
    const cols = ALL_COLS.filter((c) => metriche.includes(c.key));
    const anni = data?.anni || [];
    const showDelta = anni.length === 2;
    const deltaPerc = (a, b) => (b ? ((a - b) / b) * 100 : (a ? 100 : 0));
    const mesiVisibili = MESI.map((mn, i) => ({ mn, i })).filter(({ i }) => i + 1 >= meseDa && i + 1 <= meseA);
    const totPeriodo = (a, key) => mesiVisibili.reduce((s, { i }) => s + (a[key][i] || 0), 0);

    const chartMetric = cols[0];
    const chartData = mesiVisibili.map(({ mn, i }) => {
        const row = { mese: mn };
        anni.forEach((a) => { row[String(a.anno)] = a[chartMetric.key][i]; });
        return row;
    });

    return (
        <div className="space-y-4" data-testid="stat-premi-page">
            <p className="text-xs text-slate-500">
                {data?.scoped_operatore
                    ? "I tuoi premi e le tue provvigioni · andamento per periodo, con confronto tra anni."
                    : "Andamento per periodo: scegli metriche, mesi e anni da confrontare."}
            </p>

            <Card className="p-3 flex flex-wrap items-end gap-3">
                <YearPicker sel={sel} setSel={setSel} />
                <MeseRange meseDa={meseDa} setMeseDa={setMeseDa} meseA={meseA} setMeseA={setMeseA} />
                <div>
                    <div className="text-[10px] uppercase text-slate-500 mb-1">Metriche</div>
                    <div className="flex gap-1">
                        {ALL_COLS.map((c) => (
                            <button key={c.key} onClick={() => toggleMetrica(c.key)} data-testid={`stat-metrica-${c.key}`}
                                className={`text-xs px-2 py-1 rounded border ${metriche.includes(c.key) ? "bg-slate-800 text-white border-slate-800" : "bg-white border-slate-200 text-slate-500"}`}>{c.label}</button>
                        ))}
                    </div>
                </div>
                <FSel label="Filtra per data" value={dataField} onChange={setDataField} opts={[["incasso", "Data incasso"], ["rata", "Rata / decorrenza"], ["copertura", "Data copertura"]]} tid="stat-datafield" />
                <FSel label="Tipo titolo" value={tipo} onChange={setTipo} opts={[["all", "Tutti"], ["nuova", "Nuove"], ["sostituzione", "Sostituite"], ["regolazione", "Regolazioni"], ["rinnovo", "Rinnovi"], ["quietanza", "Quietanze"]]} tid="stat-tipo" />
                <FSel label="Compagnia" value={compagniaId} onChange={setCompagniaId} opts={[["all", "Tutte"], ...compagnie.map((c) => [c.id, c.ragione_sociale])]} tid="stat-compagnia" />
                <RamoMulti rami={rami} sel={ramoSel} setSel={setRamoSel} tid="stat-ramo" />
                {isAdmin && (
                    <FSel label="Operatore" value={operatoreId} onChange={setOperatoreId} opts={[["all", "Tutti"], ...operatori.map((o) => [o.id, o.name])]} tid="stat-operatore" />
                )}
            </Card>

            {!data ? <Loading /> : anni.length === 0 ? (
                <Card className="p-6 text-center text-sm text-slate-500">Seleziona almeno un anno.</Card>
            ) : cols.length === 0 ? (
                <Card className="p-6 text-center text-sm text-slate-500">Seleziona almeno una metrica.</Card>
            ) : (
                <>
                    <Card className="p-4" data-testid="stat-chart">
                        <div className="text-xs font-semibold text-slate-700 mb-2">Andamento mensile · {chartMetric.label}</div>
                        <ResponsiveContainer width="100%" height={280}>
                            <BarChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eef2f7" />
                                <XAxis dataKey="mese" tick={{ fontSize: 11 }} />
                                <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => (v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v)} width={48} />
                                <Tooltip formatter={(v) => fmtEur(v)} contentStyle={{ fontSize: 12 }} />
                                <Legend wrapperStyle={{ fontSize: 11 }} />
                                {anni.map((a, i) => (
                                    <Bar key={a.anno} dataKey={String(a.anno)} fill={YEAR_BARS[i % YEAR_BARS.length]} radius={[3, 3, 0, 0]} />
                                ))}
                            </BarChart>
                        </ResponsiveContainer>
                    </Card>

                    <Card className="p-0 overflow-x-auto">
                        <table className="w-full text-xs border-collapse" data-testid="stat-table">
                            <thead>
                                <tr className="bg-slate-50 border-b text-slate-600">
                                    <th className="text-left px-3 py-2" rowSpan={cols.length > 1 ? 2 : 1}>Mese</th>
                                    {anni.map((a) => (
                                        <th key={a.anno} className="text-center px-3 py-2 border-l font-bold" colSpan={cols.length}>{a.anno}</th>
                                    ))}
                                </tr>
                                {cols.length > 1 && (
                                    <tr className="bg-slate-50 border-b text-slate-500 text-[10px] uppercase">
                                        {anni.map((a) => cols.map((c, ci) => (
                                            <th key={`${a.anno}-${c.key}`} className={`text-right px-3 py-1.5 ${ci === 0 ? "border-l" : ""} ${c.cls}`}>{c.label}</th>
                                        )))}
                                    </tr>
                                )}
                            </thead>
                            <tbody>
                                {mesiVisibili.map(({ mn, i }) => (
                                    <tr key={mn} className="border-b border-slate-100 hover:bg-slate-50">
                                        <td className="px-3 py-1.5 font-medium">{mn}</td>
                                        {anni.map((a) => cols.map((c, ci) => (
                                            <td key={`${a.anno}-${c.key}`} className={`text-right px-3 py-1.5 font-mono ${ci === 0 ? "border-l border-slate-100" : ""}`}>{fmtEur(a[c.key][i])}</td>
                                        )))}
                                    </tr>
                                ))}
                                <tr className="bg-fuchsia-50 font-bold border-t-2 border-fuchsia-200">
                                    <td className="px-3 py-2">TOTALE</td>
                                    {anni.map((a) => cols.map((c, ci) => (
                                        <td key={`${a.anno}-${c.key}`} className={`text-right px-3 py-2 font-mono ${ci === 0 ? "border-l border-fuchsia-200" : ""}`}>{fmtEur(totPeriodo(a, c.key))}</td>
                                    )))}
                                </tr>
                                {showDelta && (
                                    <tr className="bg-slate-50 border-t text-[11px]">
                                        <td className="px-3 py-2 font-semibold text-slate-600">Δ % ({anni[0].anno} vs {anni[1].anno})</td>
                                        {anni.map((a, ai) => cols.map((c, ci) => {
                                            if (ai !== 0) return <td key={`${a.anno}-${c.key}`} className={`px-3 py-2 ${ci === 0 ? "border-l" : ""}`}></td>;
                                            const d = deltaPerc(totPeriodo(anni[0], c.key), totPeriodo(anni[1], c.key));
                                            return <td key={`${a.anno}-${c.key}`} className={`text-right px-3 py-2 font-mono font-semibold ${ci === 0 ? "border-l" : ""} ${d >= 0 ? "text-emerald-700" : "text-rose-600"}`}>{d >= 0 ? "+" : ""}{d.toFixed(1)}%</td>;
                                        }))}
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </Card>
                </>
            )}
        </div>
    );
}
