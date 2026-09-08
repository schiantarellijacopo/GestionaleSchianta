/**
 * SaluteFiscaleTab — per clienti corporate. OCR bilancio con Gemini →
 * calcolo indicatori (ROE, leva, oneri finanziari) + score rischio default +
 * cross-sell suggerito.
 */
import { useEffect, useState } from "react";
import { api, fmtEur } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Upload, Activity, TrendingUp, AlertTriangle, Sparkles } from "lucide-react";
import { BarChart, Bar, Cell, XAxis, YAxis, ResponsiveContainer, Tooltip, ReferenceLine } from "recharts";
import { toast } from "sonner";
import AnalisiAziendaTab from "@/components/AnalisiAziendaTab";
import { PiramideCopertureNuova } from "@/components/AnalisiClienteTab";

export default function SaluteFiscaleTab({ anagrafica_id, ana, canEdit, onReload }) {
    const [dati, setDati] = useState(null);
    const [aggIl, setAggIl] = useState(null);
    const [busy, setBusy] = useState(false);
    const [showPir, setShowPir] = useState(false);
    const [pirBusy, setPirBusy] = useState(false);

    const apriPiramide = async () => {
        setPirBusy(true);
        try {
            // precompila i dati_reddito con i dati di bilancio azienda, preservando eventuali personalizzazioni
            const cur = (await api.get(`/anagrafiche/${anagrafica_id}/analisi/piramide-v2`)).data || {};
            const pre = (await api.post(`/anagrafiche/${anagrafica_id}/analisi/piramide-v2/prepopola`)).data || {};
            await api.put(`/anagrafiche/${anagrafica_id}/analisi/piramide-v2`, {
                dati_reddito: { ...(cur.dati_reddito || {}), ...pre },
                testamento: cur.testamento || false,
                eredi_legittimi: cur.eredi_legittimi || [],
                override_voci: cur.override_voci || {},
                stato_voci: cur.stato_voci || {},
                voci_custom: cur.voci_custom || {},
            });
            toast.success("Piramide azienda precompilata dai dati di bilancio");
            setShowPir(true);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Impossibile precompilare la piramide");
            setShowPir(true); // mostra comunque la piramide (auto-popolata dalle polizze)
        } finally { setPirBusy(false); }
    };

    const load = () => api.get(`/anagrafiche/${anagrafica_id}/salute-fiscale`).then((r) => {
        setDati(r.data.dati || {});
        setAggIl(r.data.aggiornato_il);
    });
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [anagrafica_id]);

    const upload = async (e) => {
        const f = e.target.files?.[0]; if (!f) return;
        setBusy(true);
        try {
            const fd = new FormData(); fd.append("file", f);
            const r = await api.post(`/anagrafiche/${anagrafica_id}/salute-fiscale/ocr-bilancio`, fd,
                { headers: { "Content-Type": "multipart/form-data" } });
            toast.success("Bilancio elaborato");
            setDati(r.data);
            load();
        } catch (err) { toast.error(err.response?.data?.detail || "Errore OCR"); }
        finally { setBusy(false); e.target.value = ""; }
    };

    const ind = dati?.indicatori || {};
    const bil = dati?.bilancio_estratto || {};
    const storico = dati?.storico || [];
    const rischio = dati?.score_rischio_default ?? null;
    const crossSell = dati?.cross_sell_suggerito || [];
    const ramoColor = (s) => s == null ? "slate" : s <= 3 ? "emerald" : s <= 6 ? "amber" : "rose";

    const tipoCliente = ana?.tipo === "persona_giuridica";

    return (
        <div className="space-y-4 mt-4" data-testid="salute-fiscale-tab">
            {/* Panoramica azienda + Soci/Governance/Forza lavoro (fusa da Analisi Azienda) */}
            {tipoCliente && <AnalisiAziendaTab ana={ana} canEdit={canEdit} onReload={onReload} />}

            <Card className="p-4 bg-gradient-to-r from-emerald-50 to-sky-50 border-emerald-200">
                <div className="flex items-start justify-between flex-wrap gap-3">
                    <div>
                        <h3 className="font-semibold text-emerald-800 flex items-center gap-2">
                            <Activity size={18} /> Salute Fiscale Cliente
                        </h3>
                        <div className="text-xs text-slate-600 mt-1">
                            {tipoCliente
                                ? "OCR del bilancio d'esercizio → KPI economico-finanziari + score rischio + opportunità cross-sell."
                                : "Funzione ottimizzata per clienti azienda. Funziona anche su persone fisiche con bilancio personale."}
                        </div>
                        {aggIl && <div className="text-[10px] text-slate-500 mt-1">Ultimo bilancio elaborato: {new Date(aggIl).toLocaleDateString("it-IT")}</div>}
                    </div>
                    {canEdit && (
                        <div className="flex flex-col gap-2 items-end">
                        <button onClick={async () => {
                            try {
                                setBusy(true);
                                const r = await api.post(`/anagrafiche/${anagrafica_id}/salute-fiscale/da-openapi`);
                                setDati(r.data);
                                setAggIl(new Date().toISOString());
                                toast.success("Dati compilati da OpenAPI (company.openapi.com)");
                            } catch (e) { toast.error(e.response?.data?.detail || "Dati OpenAPI non disponibili"); }
                            finally { setBusy(false); }
                        }} disabled={busy} className="inline-flex items-center gap-2 px-3 py-2 bg-sky-700 text-white rounded text-sm hover:bg-sky-800 disabled:opacity-50" data-testid="sf-openapi-btn">
                            ⚡ Compila da OpenAPI
                        </button>
                        <label className="inline-flex items-center gap-2 px-3 py-2 bg-emerald-700 text-white rounded text-sm cursor-pointer hover:bg-emerald-800" data-testid="sf-upload-btn">
                            <Upload size={14} />
                            {busy ? "Elaborazione OCR…" : "Carica bilancio (PDF/JPG)"}
                            <input type="file" hidden accept="application/pdf,image/*" onChange={upload} />
                        </label>
                        {tipoCliente && (
                            <button onClick={apriPiramide} disabled={pirBusy}
                                className="inline-flex items-center gap-2 px-3 py-2 bg-indigo-600 text-white rounded text-sm hover:bg-indigo-700 disabled:opacity-50"
                                data-testid="sf-piramide-btn">
                                🔺 {pirBusy ? "Precompilo…" : "Piramide Azienda"}
                            </button>
                        )}
                        </div>
                    )}
                </div>
            </Card>

            {showPir && tipoCliente && (
                <Card className="p-4" data-testid="sf-piramide-card">
                    <div className="flex items-center justify-between mb-1">
                        <h4 className="font-semibold text-slate-800 text-sm flex items-center gap-2">🔺 Piramide delle Coperture — Azienda</h4>
                        <button onClick={() => setShowPir(false)} className="text-xs text-slate-500 hover:text-slate-700" data-testid="sf-piramide-close">Chiudi</button>
                    </div>
                    <PiramideCopertureNuova anagrafica_id={anagrafica_id} canEdit={canEdit} />
                </Card>
            )}

            {!dati || !Object.keys(bil).length ? (
                <Card className="p-8 text-center text-slate-500 text-sm">
                    Nessun bilancio caricato. Premi &quot;Carica bilancio&quot; per estrarre automaticamente i dati con l&apos;OCR Gemini.
                </Card>
            ) : (
                <>
                    {/* Score rischio */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <Card className={`p-4 border-l-4 border-${ramoColor(rischio)}-500 bg-white`} data-testid="sf-rischio-card">
                            <div className="text-[10px] uppercase tracking-wider text-slate-500">Score rischio default</div>
                            <div className="flex items-end gap-2 mt-1">
                                <div className={`text-4xl font-bold text-${ramoColor(rischio)}-600`}>{rischio ?? "—"}</div>
                                <div className="text-sm text-slate-500 mb-1">/ 10</div>
                            </div>
                            <div className={`text-xs text-${ramoColor(rischio)}-700 font-medium mt-1`}>
                                {rischio == null ? "—" : rischio <= 3 ? "BASSO · Cliente solido" : rischio <= 6 ? "MEDIO · Da monitorare" : "ALTO · Attenzione default"}
                            </div>
                        </Card>
                        <Card className="p-4 border-l-4 border-violet-400 bg-white" data-testid="sf-crosssell-card">
                            <div className="text-[10px] uppercase tracking-wider text-slate-500 flex items-center gap-1">
                                <Sparkles size={11} /> Cross-sell suggerito (AI)
                            </div>
                            {crossSell.length === 0 ? (
                                <div className="text-sm text-slate-400 mt-2">Nessuna opportunità specifica rilevata</div>
                            ) : (
                                <ul className="text-sm text-violet-700 mt-2 space-y-0.5">
                                    {crossSell.map((c, i) => <li key={i} className="flex gap-1.5"><TrendingUp size={12} className="mt-0.5 shrink-0" /> {c}</li>)}
                                </ul>
                            )}
                        </Card>
                    </div>

                    {/* Bilancio estratto */}
                    <Card className="p-4">
                        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                            <h4 className="font-semibold text-slate-800 text-sm">📄 Conto economico · Anno {bil.anno || "—"}</h4>
                            <div className="flex items-center gap-2 text-[11px]">
                                {bil.dimensione_impresa && <span className="px-2 py-0.5 rounded-full bg-sky-100 text-sky-800">{bil.dimensione_impresa}</span>}
                                {bil.dipendenti != null && <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700">{bil.dipendenti} dipendenti</span>}
                                {bil.trend_fatturato_pct != null && (
                                    <span className={`px-2 py-0.5 rounded-full ${bil.trend_fatturato_pct >= 0 ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800"}`}>
                                        Trend fatturato {bil.trend_fatturato_pct >= 0 ? "+" : ""}{bil.trend_fatturato_pct}%
                                    </span>
                                )}
                            </div>
                        </div>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                            <BilItem label="Ricavi vendite" value={bil.ricavi} />
                            <BilItem label="Valore produzione" value={bil.valore_produzione} />
                            <BilItem label="Costi produzione" value={bil.costi_produzione} />
                            <BilItem label="Costi materie prime" value={bil.costi_materie} />
                            <BilItem label="Costi servizi" value={bil.costi_servizi} />
                            <BilItem label="Godimento beni terzi" value={bil.costi_godimento_beni} />
                            <BilItem label="Costo del personale" value={bil.costi_personale} />
                            <BilItem label="Ammortamenti/svalut." value={bil.ammortamenti} />
                            <BilItem label="Oneri diversi gest." value={bil.oneri_diversi_gestione} />
                            <BilItem label="EBITDA" value={bil.ebitda} positivo />
                            <BilItem label="EBIT (risult. operativo)" value={bil.ebit} positivo />
                            <BilItem label="Cash flow" value={bil.cash_flow} positivo />
                            <BilItem label="Proventi finanziari" value={bil.proventi_finanziari} />
                            <BilItem label="Oneri finanziari" value={bil.oneri_finanziari} />
                            <BilItem label="Utile lordo (ante imposte)" value={bil.utile_lordo} positivo />
                            <BilItem label="Imposte" value={bil.imposte} />
                            <BilItem label="Utile/perdita d'esercizio" value={bil.utile_netto} positivo />
                        </div>
                        <h4 className="font-semibold text-slate-800 mt-4 mb-2 text-sm">🏛️ Stato patrimoniale</h4>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                            <BilItem label="Totale attivo" value={bil.totale_attivo} />
                            <BilItem label="Totale debiti" value={bil.totale_debiti} />
                            <BilItem label="Patrimonio netto" value={bil.patrimonio_netto} positivo />
                            <BilItem label="Capitale sociale" value={bil.capitale_sociale} />
                        </div>
                    </Card>

                    {/* Storico fatturato */}
                    {storico.length > 0 && (
                        <Card className="p-4" data-testid="sf-storico-card">
                            <h4 className="font-semibold text-slate-800 mb-3 text-sm">📈 Andamento fatturato</h4>
                            <ResponsiveContainer width="100%" height={200}>
                                <BarChart data={[...storico].filter((s) => s.fatturato != null).sort((a, b) => (a.anno || 0) - (b.anno || 0))} margin={{ top: 12, right: 10, left: 0, bottom: 0 }}>
                                    <XAxis dataKey="anno" tick={{ fontSize: 11 }} />
                                    <YAxis tickFormatter={(v) => `${(v / 1000000).toFixed(1)}M`} tick={{ fontSize: 11 }} width={40} />
                                    <Tooltip formatter={(v) => fmtEur(v)} labelFormatter={(l) => `Anno ${l}`} />
                                    <Bar dataKey="fatturato" fill="#0ea5e9" radius={[4, 4, 0, 0]} name="Fatturato" />
                                </BarChart>
                            </ResponsiveContainer>
                            <table className="w-full text-xs mt-3">
                                <thead className="text-[10px] uppercase text-slate-500 border-b border-slate-200">
                                    <tr><th className="text-left py-1">Anno</th><th className="text-right">Fatturato</th><th className="text-right">Patrimonio netto</th><th className="text-right">Dipendenti</th></tr>
                                </thead>
                                <tbody>
                                    {storico.map((s, i) => (
                                        <tr key={i} className="border-b border-slate-100">
                                            <td className="py-1 font-medium">{s.anno || "—"}</td>
                                            <td className="text-right font-mono">{s.fatturato == null ? "—" : fmtEur(s.fatturato)}</td>
                                            <td className="text-right font-mono">{s.patrimonio_netto == null ? "—" : fmtEur(s.patrimonio_netto)}</td>
                                            <td className="text-right font-mono">{s.dipendenti ?? "—"}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </Card>
                    )}

                    {/* Indicatori */}
                    <Card className="p-4">
                        <h4 className="font-semibold text-slate-800 mb-3 text-sm">📊 Indicatori economico-finanziari</h4>
                        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                            <IndItem label="ROE" value={ind.roe_pct} unit="%" good={(v) => v >= 8} bad={(v) => v < 3} />
                            <IndItem label="ROI" value={ind.roi_pct} unit="%" good={(v) => v >= 6} bad={(v) => v < 2} />
                            <IndItem label="ROS" value={ind.ros_pct} unit="%" good={(v) => v >= 10} bad={(v) => v < 2} />
                            <IndItem label="EBITDA margin" value={ind.ebitda_margin_pct} unit="%" good={(v) => v >= 10} bad={(v) => v < 4} />
                            <IndItem label="Leva fin. (Att/PN)" value={ind.leva_finanziaria} unit="x" good={(v) => v <= 2} bad={(v) => v > 3} />
                            <IndItem label="PFN/EBITDA" value={ind.pfn_ebitda} unit="x" good={(v) => v <= 3} bad={(v) => v > 4} />
                            <IndItem label="Oneri fin./Ricavi" value={ind.incidenza_oneri_fin_pct} unit="%" good={(v) => v < 2} bad={(v) => v > 5} />
                            <IndItem label="Press. fiscale" value={ind.pressione_fiscale_pct} unit="%" good={(v) => v < 30} bad={(v) => v > 50} />
                            <IndItem label="Inc. personale" value={ind.incidenza_personale_pct} unit="%" good={(v) => v < 25} bad={(v) => v > 45} />
                        </div>
                    </Card>

                    <MargineContribuzione bil={bil} anagrafica_id={anagrafica_id} saved={ana?.salute_fiscale_scenari} onReload={onReload} />
                    <StudioBilancio bil={bil} />
                </>
            )}
        </div>
    );
}

const BilItem = ({ label, value, positivo, text }) => (
    <div className="bg-slate-50 border border-slate-200 rounded p-2">
        <div className="text-[10px] uppercase text-slate-500">{label}</div>
        <div className={`text-base font-mono font-semibold mt-0.5 ${
            text ? "text-slate-700 capitalize" : positivo && value && value > 0 ? "text-emerald-700" :
            positivo && value && value < 0 ? "text-rose-700" : "text-slate-800"
        }`}>
            {value == null ? "—" : text ? value : fmtEur(value)}
        </div>
    </div>
);

const IndItem = ({ label, value, unit, good, bad }) => {
    const col = value == null ? "slate" : good && good(value) ? "emerald" : bad && bad(value) ? "rose" : "amber";
    return (
        <div className={`border-l-4 border-${col}-400 bg-white border border-slate-200 rounded p-2`}>
            <div className="text-[10px] uppercase text-slate-500">{label}</div>
            <div className={`text-xl font-mono font-bold text-${col}-700`}>
                {value == null ? "—" : `${value}${unit || ""}`}
            </div>
        </div>
    );
};

const n = (v) => { const x = parseFloat(v); return isNaN(x) ? 0 : x; };
const eur0 = (v) => (v == null ? "—" : Number(v).toLocaleString("it-IT", { maximumFractionDigits: 0 }) + " €");

// ── Margine di Contribuzione + Metriche di impatto (fermo attività) ──
function MargineContribuzione({ bil, anagrafica_id, saved, onReload }) {
    // righe: [chiave, label, segno(+/-), %nonAssicurataDefault, importoDaBilancio]
    const initRows = () => [
        { k: "ricavi", l: "Ricavi di vendita", seg: "+", pct: 100, imp: n(bil.valore_produzione) || n(bil.ricavi) },
        { k: "rimf", l: "Rimanenze finali", seg: "+", pct: 100, imp: n(bil.rimanenze_totali) },
        { k: "rimi", l: "Rimanenze iniziali", seg: "-", pct: 100, imp: 0 },
        { k: "materie", l: "Materie prime e sussidiarie", seg: "-", pct: 100, imp: n(bil.costi_materie) },
        { k: "godimento", l: "Godimento beni di terzi", seg: "-", pct: 0, imp: n(bil.costi_godimento_beni) },
        { k: "personale", l: "Personale", seg: "-", pct: 0, imp: n(bil.costi_personale) },
        { k: "servizi", l: "Costi tecnici (servizi)", seg: "-", pct: 70, imp: n(bil.costi_servizi) },
        { k: "amm", l: "Costi amministrativi (oneri diversi)", seg: "-", pct: 30, imp: n(bil.oneri_diversi_gestione) },
    ];
    const [rows, setRows] = useState(() => (saved?.rows?.length ? saved.rows : initRows()));
    const [giorni, setGiorni] = useState(saved?.giorni ?? 220);
    const [gScen, setGScen] = useState(saved?.gScen?.length === 4 ? saved.gScen : [20, 58, 115, 189]);
    const [riskTol, setRiskTol] = useState(saved?.riskTol ?? 8000000);
    const [riskApp, setRiskApp] = useState(saved?.riskApp ?? 12000000);
    const [saving, setSaving] = useState(false);
    // se non ci sono scenari salvati, ri-inizializza le righe quando cambiano i dati di bilancio
    useEffect(() => {
        if (!saved?.rows?.length) setRows(initRows());
        /* eslint-disable-next-line */
    }, [bil.valore_produzione, bil.rimanenze_totali, bil.costi_servizi]);

    const salvaScenari = async () => {
        setSaving(true);
        try {
            await api.put(`/anagrafiche/${anagrafica_id}`, {
                salute_fiscale_scenari: { rows, giorni, gScen, riskTol, riskApp },
            });
            toast.success("Scenari salvati per questo cliente");
            onReload?.();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore salvataggio scenari"); }
        finally { setSaving(false); }
    };

    const upd = (i, patch) => setRows((p) => p.map((r, j) => (j === i ? { ...r, ...patch } : r)));
    const pesato = (r) => r.imp * (r.pct / 100);
    const totPiu = rows.filter((r) => r.seg === "+").reduce((s, r) => s + pesato(r), 0);
    const totMeno = rows.filter((r) => r.seg === "-").reduce((s, r) => s + pesato(r), 0);
    const mdc = totPiu - totMeno;
    const baseRicavi = pesato(rows[0]); // % su ricavi (A1+A5) = MDC / valore produzione
    const pctRicavi = baseRicavi > 0 ? (mdc / baseRicavi) * 100 : 0;
    const mdcGiorno = giorni > 0 ? mdc / giorni : 0;
    const SCEN = ["Trascurabile", "Gestibile", "Grave", "Critico"];
    const SCEN_COL = ["#10b981", "#eab308", "#f59e0b", "#ef4444"];
    const chartData = SCEN.map((s, i) => ({ name: s, impatto: Math.round(mdcGiorno * gScen[i]), giorni: gScen[i], fill: SCEN_COL[i] }));

    return (
        <>
        <Card className="p-4" data-testid="sf-mdc-card">
            <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                <h4 className="font-semibold text-slate-800 text-sm">🧮 Margine di Contribuzione (perdita in caso di fermo)</h4>
                <button onClick={salvaScenari} disabled={saving} className="text-xs px-3 py-1.5 rounded bg-slate-800 text-white hover:bg-slate-900 disabled:opacity-50" data-testid="sf-salva-scenari">
                    {saving ? "Salvo…" : "💾 Salva scenari"}
                </button>
            </div>
            <div className="overflow-x-auto">
            <table className="w-full text-xs">
                <thead className="text-[10px] uppercase text-slate-500 border-b border-slate-200">
                    <tr><th className="text-left py-1">Voci di bilancio</th><th className="text-right">Importo</th><th className="text-right">% non assicurata</th><th className="text-right">Importo +</th><th className="text-right">Importo −</th></tr>
                </thead>
                <tbody>
                    {rows.map((r, i) => (
                        <tr key={r.k} className="border-b border-slate-100">
                            <td className="py-1.5">{r.l}</td>
                            <td className="text-right"><Input type="number" value={r.imp} onChange={(e) => upd(i, { imp: n(e.target.value) })} className="h-7 text-xs text-right w-32 inline-block" data-testid={`mdc-imp-${r.k}`} /></td>
                            <td className="text-right"><Input type="number" value={r.pct} onChange={(e) => upd(i, { pct: n(e.target.value) })} className="h-7 text-xs text-right w-20 inline-block" data-testid={`mdc-pct-${r.k}`} /> %</td>
                            <td className="text-right font-mono text-emerald-700">{r.seg === "+" ? eur0(pesato(r)) : "-"}</td>
                            <td className="text-right font-mono text-rose-600">{r.seg === "-" ? eur0(pesato(r)) : "-"}</td>
                        </tr>
                    ))}
                    <tr className="border-t-2 border-slate-300 font-semibold"><td className="py-1.5">Totale importi</td><td></td><td></td><td className="text-right font-mono">{eur0(totPiu)}</td><td className="text-right font-mono">{eur0(totMeno)}</td></tr>
                </tbody>
            </table>
            </div>
            <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="bg-sky-50 border border-sky-200 rounded p-3"><div className="text-[10px] uppercase text-slate-500">Margine di contribuzione</div><div className="text-lg font-bold text-sky-800 font-mono" data-testid="mdc-totale">{eur0(mdc)}</div></div>
                <div className="bg-slate-50 border border-slate-200 rounded p-3"><div className="text-[10px] uppercase text-slate-500">% su ricavi (A1+A5)</div><div className="text-lg font-bold text-slate-800 font-mono">{pctRicavi.toFixed(1)} %</div></div>
                <div className="bg-slate-50 border border-slate-200 rounded p-3"><div className="text-[10px] uppercase text-slate-500">MDC giornaliero</div><div className="text-lg font-bold text-slate-800 font-mono">{eur0(mdcGiorno)}</div></div>
                <div><div className="text-[10px] uppercase text-slate-500 mb-1">Giorni lavorativi/anno</div><Input type="number" value={giorni} onChange={(e) => setGiorni(n(e.target.value))} className="h-9" data-testid="mdc-giorni" /></div>
            </div>
        </Card>

        <Card className="p-4" data-testid="sf-impatto-card">
            <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                <h4 className="font-semibold text-slate-800 text-sm">📉 Metriche di impatto (fermo attività)</h4>
                <div className="flex items-center gap-2 text-[11px]">
                    <span className="text-slate-500">Risk Tolerance</span><Input type="number" value={riskTol} onChange={(e) => setRiskTol(n(e.target.value))} className="h-7 w-28 text-xs" data-testid="risk-tol" />
                    <span className="text-slate-500">Risk Appetite</span><Input type="number" value={riskApp} onChange={(e) => setRiskApp(n(e.target.value))} className="h-7 w-28 text-xs" data-testid="risk-app" />
                </div>
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <ResponsiveContainer width="100%" height={240}>
                    <BarChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                        <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                        <YAxis tickFormatter={(v) => `${(v / 1000000).toFixed(0)}M`} tick={{ fontSize: 11 }} />
                        <Tooltip formatter={(v) => eur0(v)} />
                        <ReferenceLine y={riskTol} stroke="#334155" strokeDasharray="4 4" label={{ value: "Risk Tolerance", fontSize: 10, position: "right" }} />
                        <ReferenceLine y={riskApp} stroke="#334155" strokeDasharray="4 4" label={{ value: "Risk Appetite", fontSize: 10, position: "right" }} />
                        <Bar dataKey="impatto" radius={[4, 4, 0, 0]}>
                            {chartData.map((d, i) => <Cell key={i} fill={d.fill} />)}
                        </Bar>
                    </BarChart>
                </ResponsiveContainer>
                <table className="w-full text-xs self-center">
                    <thead className="text-[10px] uppercase text-slate-500 border-b border-slate-200">
                        <tr><th className="text-left py-1">Scenario</th><th className="text-right">Impatto diretto</th><th className="text-right">Fermo attività</th></tr>
                    </thead>
                    <tbody>
                        {chartData.map((d, i) => (
                            <tr key={i} className="border-b border-slate-100">
                                <td className="py-1.5"><span className="inline-block w-2.5 h-2.5 rounded-full mr-1.5" style={{ background: d.fill }} />{d.name}</td>
                                <td className="text-right font-mono">{eur0(d.impatto)}</td>
                                <td className="text-right"><Input type="number" value={gScen[i]} onChange={(e) => setGScen((p) => p.map((g, j) => (j === i ? n(e.target.value) : g)))} className="h-7 w-20 text-xs text-right inline-block" data-testid={`scen-giorni-${i}`} /> gg</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </Card>
        </>
    );
}

// ── Studio di bilancio per fermo attività (indici + score) ──
function StudioBilancio({ bil }) {
    const ricavi = n(bil.ricavi) || n(bil.valore_produzione);
    const valAgg = n(bil.valore_produzione) - (n(bil.costi_materie) + n(bil.costi_servizi) + n(bil.costi_godimento_beni) + n(bil.oneri_diversi_gestione));
    const ciclo = ricavi > 0 ? ((n(bil.crediti_clienti) + n(bil.rimanenze_totali) - n(bil.debiti_fornitori)) / ricavi) * 365 : null;
    const molOf = n(bil.oneri_finanziari) > 0 ? n(bil.ebitda) / n(bil.oneri_finanziari) : null;
    const valImm = n(bil.immobilizzazioni) > 0 ? valAgg / n(bil.immobilizzazioni) : null;
    const ricCred = n(bil.crediti_clienti) > 0 ? ricavi / n(bil.crediti_clienti) : null;
    // Altri indici utili
    const attCirc = n(bil.attivo_circolante);
    const debBreve = n(bil.debiti_breve);
    const margTesoreria = attCirc && debBreve ? (attCirc - n(bil.rimanenze_totali)) - debBreve : null;
    const indiceDisp = debBreve > 0 ? attCirc / debBreve : null;

    const scores = {
        ciclo: ciclo == null ? null : Math.min(1, Math.max(0, ciclo / 180)),
        molOf: molOf == null ? null : Math.min(1, Math.max(0, 1 - molOf / 15)),
        valImm: valImm == null ? null : Math.min(1, Math.max(0, 1 - valImm / 3)),
        ricCred: ricCred == null ? null : Math.min(1, Math.max(0, 1 - ricCred / 6)),
    };

    const params = [
        { key: "ciclo", l: "Ciclo del circolante", sintesi: "Giorni medi tra pagamento fornitori e incasso clienti.", val: ciclo, unit: " gg" },
        { key: "molOf", l: "MOL / OF", sintesi: "Capacità del margine operativo di coprire gli oneri finanziari.", val: molOf, unit: "x" },
        { key: "valImm", l: "Val. agg / immobilizzi", sintesi: "Dipendenza del valore aggiunto dagli investimenti fissi.", val: valImm, unit: "x" },
        { key: "ricCred", l: "Ricavi / crediti vs Clienti", sintesi: "Facilità di incasso / potere contrattuale verso i clienti.", val: ricCred, unit: "x" },
    ];
    return (
        <Card className="p-4" data-testid="sf-studio-card">
            <h4 className="font-semibold text-slate-800 mb-3 text-sm">🔬 Studio di bilancio per fermo attività</h4>
            <div className="space-y-4">
                {params.map((p) => (
                    <div key={p.key} className="grid grid-cols-12 items-center gap-3 border-b border-slate-100 pb-3">
                        <div className="col-span-4">
                            <div className="text-sm font-medium text-slate-800">{p.l}</div>
                            <div className="text-[11px] text-slate-500">{p.sintesi}</div>
                        </div>
                        <div className="col-span-3 text-sm font-mono font-semibold">{p.val == null ? "Non calcolato" : `${p.val.toFixed(2)}${p.unit}`}</div>
                        <div className="col-span-5">
                            {scores[p.key] == null ? <span className="text-xs text-slate-400">dati insufficienti</span> : (
                                <div className="relative h-3 rounded-full" style={{ background: "linear-gradient(90deg,#10b981,#eab308,#f59e0b,#ef4444)" }} data-testid={`studio-score-${p.key}`}>
                                    <div className="absolute -top-1 w-4 h-4 rounded-full bg-white border-2 border-slate-700" style={{ left: `calc(${scores[p.key] * 100}% - 8px)` }} />
                                </div>
                            )}
                        </div>
                    </div>
                ))}
            </div>
            <div className="mt-4 pt-3 border-t border-slate-200">
                <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-2">Altri indici utili</div>
                <div className="grid grid-cols-2 gap-3">
                    <div className="bg-slate-50 border border-slate-200 rounded p-3">
                        <div className="text-[10px] uppercase text-slate-500">Margine di tesoreria</div>
                        <div className={`text-lg font-mono font-bold ${margTesoreria == null ? "text-slate-400" : margTesoreria < 0 ? "text-rose-600" : "text-emerald-700"}`} data-testid="idx-margine-tesoreria">{margTesoreria == null ? "—" : eur0(margTesoreria)}</div>
                    </div>
                    <div className="bg-slate-50 border border-slate-200 rounded p-3">
                        <div className="text-[10px] uppercase text-slate-500">Indice di disponibilità</div>
                        <div className={`text-lg font-mono font-bold ${indiceDisp == null ? "text-slate-400" : indiceDisp < 1 ? "text-amber-600" : "text-emerald-700"}`} data-testid="idx-disponibilita">{indiceDisp == null ? "—" : indiceDisp.toFixed(2)}</div>
                    </div>
                </div>
            </div>
            <div className="text-[10px] text-slate-400 mt-2">Score calcolati con soglie standard di bilancio.</div>
        </Card>
    );
}
