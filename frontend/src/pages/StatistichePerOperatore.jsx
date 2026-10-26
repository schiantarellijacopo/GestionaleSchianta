import { useEffect, useState } from "react";
import { api, fmtEur } from "@/lib/api";
import { Loading } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { CUR, ALL_COLS, FSel, MeseRange, YearPicker, RamoMulti } from "@/pages/statsShared";

export default function StatistichePerOperatore() {
    const [sel, setSel] = useState([CUR, CUR - 1]);
    const [dataField, setDataField] = useState("incasso");
    const [meseDa, setMeseDa] = useState(1);
    const [meseA, setMeseA] = useState(12);
    const [metriche, setMetriche] = useState(["netto", "provvigioni", "lordo"]);
    const [compagniaId, setCompagniaId] = useState("all");
    const [tipo, setTipo] = useState("all");
    const [compagnie, setCompagnie] = useState([]);
    const [rami, setRami] = useState([]);
    const [ramoSel, setRamoSel] = useState([]);
    const [tipiTitolo, setTipiTitolo] = useState([]);
    const [data, setData] = useState(null);

    useEffect(() => {
        api.get("/compagnie").then((r) => setCompagnie(r.data || []));
        api.get("/librerie/tipi-titolo", { params: { solo_attivi: true } })
            .then((r) => setTipiTitolo(r.data || [])).catch(() => setTipiTitolo([]));
        api.get("/librerie/rami", { params: { dedup: 1, con_polizze: 1 } })
            .then((r) => setRami((r.data || []).map((x) => x.nome).filter(Boolean)))
            .catch(() => setRami([]));
    }, []);

    useEffect(() => {
        if (!sel.length) { setData({ anni: [], operatori: [] }); return; }
        setData(null);
        const p = { anni: sel.join(","), data_field: dataField, mese_da: meseDa, mese_a: meseA };
        if (compagniaId !== "all") p.compagnia_id = compagniaId;
        if (tipo !== "all") p.tipo = tipo;
        if (ramoSel.length) p.ramo = ramoSel.join(",");
        api.get("/statistiche/per-operatore", { params: p }).then((r) => setData(r.data));
        // eslint-disable-next-line
    }, [sel, dataField, meseDa, meseA, compagniaId, tipo, ramoSel]);

    const toggleMetrica = (k) => setMetriche((m) => m.includes(k) ? (m.length > 1 ? m.filter((x) => x !== k) : m) : [...m, k]);
    const cols = ALL_COLS.filter((c) => metriche.includes(c.key));
    const anni = (data?.anni || []).map(String);
    const operatori = data?.operatori || [];

    // Totali per colonna (per riga TOTALE)
    const totale = {};
    anni.forEach((y) => { totale[y] = { netto: 0, provvigioni: 0, lordo: 0 }; });
    operatori.forEach((o) => anni.forEach((y) => cols.forEach((c) => { totale[y][c.key] += o.per_anno[y]?.[c.key] || 0; })));

    return (
        <div className="space-y-4" data-testid="stat-operatore-page">
            <p className="text-xs text-slate-500">Premi e provvigioni per operatore, con confronto tra anni. Le provvigioni sono la quota effettiva di ciascun operatore.</p>

            <Card className="p-3 flex flex-wrap items-end gap-3">
                <YearPicker sel={sel} setSel={setSel} />
                <MeseRange meseDa={meseDa} setMeseDa={setMeseDa} meseA={meseA} setMeseA={setMeseA} />
                <div>
                    <div className="text-[10px] uppercase text-slate-500 mb-1">Metriche</div>
                    <div className="flex gap-1">
                        {ALL_COLS.map((c) => (
                            <button key={c.key} onClick={() => toggleMetrica(c.key)} data-testid={`stat-op-metrica-${c.key}`}
                                className={`text-xs px-2 py-1 rounded border ${metriche.includes(c.key) ? "bg-slate-800 text-white border-slate-800" : "bg-white border-slate-200 text-slate-500"}`}>{c.label}</button>
                        ))}
                    </div>
                </div>
                <FSel label="Filtra per data" value={dataField} onChange={setDataField} opts={[["incasso", "Data incasso"], ["rata", "Rata / decorrenza"], ["copertura", "Data copertura"]]} tid="stat-op-datafield" />
                <FSel label="Tipo titolo" value={tipo} onChange={setTipo} opts={[["all", "Tutti"], ...tipiTitolo.map((t) => [t.chiave, t.nome])]} tid="stat-op-tipo" />
                <FSel label="Compagnia" value={compagniaId} onChange={setCompagniaId} opts={[["all", "Tutte"], ...compagnie.map((c) => [c.id, c.ragione_sociale])]} tid="stat-op-compagnia" />
                <RamoMulti rami={rami} sel={ramoSel} setSel={setRamoSel} tid="stat-op-ramo" />
            </Card>

            {!data ? <Loading /> : anni.length === 0 ? (
                <Card className="p-6 text-center text-sm text-slate-500">Seleziona almeno un anno.</Card>
            ) : cols.length === 0 ? (
                <Card className="p-6 text-center text-sm text-slate-500">Seleziona almeno una metrica.</Card>
            ) : operatori.length === 0 ? (
                <Card className="p-6 text-center text-sm text-slate-500">Nessun dato per gli operatori nel periodo selezionato.</Card>
            ) : (
                <Card className="p-0 overflow-x-auto">
                    <table className="w-full text-xs border-collapse" data-testid="stat-op-table">
                        <thead>
                            <tr className="bg-slate-50 border-b text-slate-600">
                                <th className="text-left px-3 py-2" rowSpan={cols.length > 1 ? 2 : 1}>Operatore</th>
                                {anni.map((y) => (
                                    <th key={y} className="text-center px-3 py-2 border-l font-bold" colSpan={cols.length}>{y}</th>
                                ))}
                            </tr>
                            {cols.length > 1 && (
                                <tr className="bg-slate-50 border-b text-slate-500 text-[10px] uppercase">
                                    {anni.map((y) => cols.map((c, ci) => (
                                        <th key={`${y}-${c.key}`} className={`text-right px-3 py-1.5 ${ci === 0 ? "border-l" : ""} ${c.cls}`}>{c.label}</th>
                                    )))}
                                </tr>
                            )}
                        </thead>
                        <tbody>
                            {operatori.map((o) => (
                                <tr key={o.operatore_id} className="border-b border-slate-100 hover:bg-slate-50">
                                    <td className="px-3 py-1.5 font-medium">{o.nome}</td>
                                    {anni.map((y) => cols.map((c, ci) => (
                                        <td key={`${y}-${c.key}`} className={`text-right px-3 py-1.5 font-mono ${ci === 0 ? "border-l border-slate-100" : ""}`}>{fmtEur(o.per_anno[y]?.[c.key] || 0)}</td>
                                    )))}
                                </tr>
                            ))}
                            <tr className="bg-fuchsia-50 font-bold border-t-2 border-fuchsia-200">
                                <td className="px-3 py-2">TOTALE</td>
                                {anni.map((y) => cols.map((c, ci) => (
                                    <td key={`${y}-${c.key}`} className={`text-right px-3 py-2 font-mono ${ci === 0 ? "border-l border-fuchsia-200" : ""}`}>{fmtEur(totale[y][c.key])}</td>
                                )))}
                            </tr>
                        </tbody>
                    </table>
                </Card>
            )}
        </div>
    );
}
