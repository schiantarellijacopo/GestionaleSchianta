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
                        <label className="inline-flex items-center gap-2 px-3 py-2 bg-emerald-700 text-white rounded text-sm cursor-pointer hover:bg-emerald-800" data-testid="sf-upload-btn">
                            <Upload size={14} />
                            {busy ? "Elaborazione OCR…" : "Carica bilancio (PDF/JPG)"}
                            <input type="file" hidden accept="application/pdf,image/*" onChange={upload} />
                        </label>
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
                        <h4 className="font-semibold text-slate-800 mb-3 text-sm">📄 Bilancio estratto · Anno {bil.anno || "—"}</h4>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                            <BilItem label="Ricavi" value={bil.ricavi} />
                            <BilItem label="Costi personale" value={bil.costi_personale} />
                            <BilItem label="Costi servizi" value={bil.costi_servizi} />
                            <BilItem label="Costi god. beni" value={bil.costi_godimento_beni} />
                            <BilItem label="Ammortamenti" value={bil.ammortamenti} />
                            <BilItem label="Oneri finanziari" value={bil.oneri_finanziari} />
                            <BilItem label="Utile lordo" value={bil.utile_lordo} positivo />
                            <BilItem label="Imposte" value={bil.imposte} />
                            <BilItem label="Utile netto" value={bil.utile_netto} positivo />
                            <BilItem label="Totale attivo" value={bil.totale_attivo} />
                            <BilItem label="Patrimonio netto" value={bil.patrimonio_netto} positivo />
                            <BilItem label="OCR confidenza" value={bil.confidenza} text />
                        </div>
                    </Card>

                    {/* Indicatori */}
                    <Card className="p-4">
                        <h4 className="font-semibold text-slate-800 mb-3 text-sm">📊 Indicatori economico-finanziari</h4>
                        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                            <IndItem label="ROE" value={ind.roe_pct} unit="%" good={(v) => v >= 8} bad={(v) => v < 3} />
                            <IndItem label="ROS" value={ind.ros_pct} unit="%" good={(v) => v >= 10} bad={(v) => v < 2} />
                            <IndItem label="Leva fin." value={ind.leva_finanziaria} unit="x" good={(v) => v <= 2} bad={(v) => v > 3} />
                            <IndItem label="Oneri/Ricavi" value={ind.incidenza_oneri_fin_pct} unit="%" good={(v) => v < 2} bad={(v) => v > 5} />
                            <IndItem label="Press. fiscale" value={ind.pressione_fiscale_pct} unit="%" good={(v) => v < 30} bad={(v) => v > 50} />
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
