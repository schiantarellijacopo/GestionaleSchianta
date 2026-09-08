/**
 * SaluteFiscaleTab — per clienti corporate. OCR bilancio con Gemini →
 * calcolo indicatori (ROE, leva, oneri finanziari) + score rischio default +
 * cross-sell suggerito.
 */
import { useEffect, useState } from "react";
import { api, fmtEur } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Upload, Activity, TrendingUp, AlertTriangle, Sparkles } from "lucide-react";
import { toast } from "sonner";

export default function SaluteFiscaleTab({ anagrafica_id, ana, canEdit }) {
    const [dati, setDati] = useState(null);
    const [aggIl, setAggIl] = useState(null);
    const [busy, setBusy] = useState(false);

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
                        </div>
                    )}
                </div>
            </Card>

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
                            <h4 className="font-semibold text-slate-800 mb-3 text-sm">📈 Storico bilanci</h4>
                            <table className="w-full text-xs">
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
