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
import { Upload, Activity, TrendingUp, AlertTriangle, Sparkles, FileText, Printer } from "lucide-react";
import { BarChart, Bar, Cell, XAxis, YAxis, ResponsiveContainer, Tooltip, ReferenceLine } from "recharts";
import { toast } from "sonner";
import AnalisiAziendaTab from "@/components/AnalisiAziendaTab";
import { PiramideCopertureNuova } from "@/components/AnalisiClienteTab";
import ImmobiliSection from "@/components/ImmobiliSection";

// ── Anteprima stampabile del bilancio riclassificato (3 / 5 anni) ──
function buildRiclassHTML(allYears, nAnni, fonte, azienda) {
    const _HAS = ["ricavi", "valore_produzione", "totale_attivo", "patrimonio_netto", "utile_netto", "costi_personale", "ebitda", "totale_debiti"];
    const hasData = (y) => _HAS.some((k) => y[k] != null && y[k] !== "");
    const years = [...(allYears || [])]
        .filter((y) => y && y.anno != null && hasData(y))
        .sort((a, b) => (b.anno || 0) - (a.anno || 0))
        .slice(0, nAnni);
    if (!years.length) return null;

    const num = (v) => (v == null || v === "" || isNaN(Number(v))) ? null : Number(v);
    const fmt = (v) => { const x = num(v); return x == null ? "n.d." : x.toLocaleString("it-IT", { maximumFractionDigits: 0 }) + " €"; };
    const va = (y) => {
        if (!y.completo) return null;
        const vp = num(y.valore_produzione);
        if (vp == null) return null;
        return vp - ((num(y.costi_materie) || 0) + (num(y.costi_servizi) || 0) + (num(y.costi_godimento_beni) || 0) + (num(y.oneri_diversi_gestione) || 0));
    };
    const cellVal = (y, key) => key === "__va" ? va(y) : y[key];

    const ceRows = [
        ["Ricavi delle vendite e prestazioni", "ricavi", 0],
        ["Variazione rimanenze prodotti", "rimanenze_variazione", 0],
        ["VALORE DELLA PRODUZIONE", "valore_produzione", 1],
        ["Costi per materie prime", "costi_materie", 0],
        ["Costi per servizi", "costi_servizi", 0],
        ["Godimento beni di terzi", "costi_godimento_beni", 0],
        ["Oneri diversi di gestione", "oneri_diversi_gestione", 0],
        ["VALORE AGGIUNTO", "__va", 1],
        ["Costo del personale", "costi_personale", 0],
        ["MARGINE OPERATIVO LORDO (EBITDA)", "ebitda", 1],
        ["Ammortamenti e svalutazioni", "ammortamenti", 0],
        ["RISULTATO OPERATIVO (EBIT)", "ebit", 1],
        ["Proventi finanziari", "proventi_finanziari", 0],
        ["Oneri finanziari", "oneri_finanziari", 0],
        ["RISULTATO ANTE IMPOSTE", "utile_lordo", 1],
        ["Imposte sul reddito", "imposte", 0],
        ["UTILE / (PERDITA) D'ESERCIZIO", "utile_netto", 1],
    ];
    const spRows = [
        ["ATTIVO", null, 2],
        ["Immobilizzazioni", "immobilizzazioni", 0],
        ["Attivo circolante", "attivo_circolante", 0],
        ["\u2014 di cui Rimanenze", "rimanenze_totali", 0],
        ["\u2014 di cui Crediti verso clienti", "crediti_clienti", 0],
        ["TOTALE ATTIVO", "totale_attivo", 1],
        ["PASSIVO E PATRIMONIO NETTO", null, 2],
        ["Patrimonio netto", "patrimonio_netto", 1],
        ["\u2014 di cui Capitale sociale", "capitale_sociale", 0],
        ["Totale debiti", "totale_debiti", 0],
        ["\u2014 di cui Debiti a breve termine", "debiti_breve", 0],
        ["\u2014 di cui Debiti verso fornitori", "debiti_fornitori", 0],
    ];

    const multi = years.length > 1;
    const varPct = (key) => {
        if (!multi) return "";
        const recente = cellVal(years[0], key);
        const vecchio = cellVal(years[years.length - 1], key);
        const a = num(recente), b = num(vecchio);
        if (a == null || b == null || b === 0) return "";
        const p = ((a - b) / Math.abs(b)) * 100;
        const cls = p >= 0 ? "pos" : "neg";
        return `<td class="var ${cls}">${p >= 0 ? "+" : ""}${p.toFixed(1)}%</td>`;
    };

    const headCols = years.map((y) => `<th class="num">${y.anno}</th>`).join("");
    const varHead = multi ? `<th class="num">Var. ${years[years.length - 1].anno}\u2192${years[0].anno}</th>` : "";
    const renderRows = (rows) => rows.map(([label, key, kind]) => {
        if (kind === 2) return `<tr class="sez"><td colspan="${years.length + (multi ? 2 : 1)}">${label}</td></tr>`;
        const cells = years.map((y) => `<td class="num">${fmt(cellVal(y, key))}</td>`).join("");
        return `<tr class="${kind === 1 ? "tot" : ""}"><td class="lbl">${label}</td>${cells}${varPct(key)}</tr>`;
    }).join("");

    const titolo = azienda || "Azienda";
    const annoMin = years[years.length - 1].anno, annoMax = years[0].anno;
    return `<!doctype html><html lang="it"><head><meta charset="utf-8">
<title>Bilancio riclassificato \u2014 ${titolo}</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; color: #1e293b; margin: 0; padding: 28px 34px; }
  .bar { display:flex; justify-content:space-between; align-items:center; gap:16px; margin-bottom:18px; }
  h1 { font-size: 19px; margin: 0; }
  .sub { font-size: 12px; color:#64748b; margin-top:3px; }
  .btn { background:#0f766e; color:#fff; border:0; border-radius:6px; padding:9px 16px; font-size:13px; cursor:pointer; }
  h2 { font-size:14px; margin: 22px 0 8px; padding-bottom:5px; border-bottom:2px solid #0f766e; color:#0f766e; }
  table { width:100%; border-collapse:collapse; font-size:12px; }
  th, td { padding:5px 9px; border-bottom:1px solid #e2e8f0; }
  th { background:#f1f5f9; text-align:left; font-size:11px; text-transform:uppercase; letter-spacing:.03em; color:#475569; }
  th.num, td.num { text-align:right; font-variant-numeric: tabular-nums; }
  td.lbl { text-align:left; }
  tr.tot td { font-weight:700; background:#f8fafc; }
  tr.sez td { font-weight:700; background:#0f766e; color:#fff; text-transform:uppercase; font-size:11px; letter-spacing:.04em; }
  td.var { text-align:right; font-weight:600; }
  td.var.pos { color:#047857; } td.var.neg { color:#be123c; }
  .foot { margin-top:22px; font-size:10px; color:#94a3b8; }
  @media print { .btn { display:none; } body { padding:0; } }
</style></head>
<body>
  <div class="bar">
    <div>
      <h1>Bilancio riclassificato \u2014 comparazione ${years.length} ${years.length === 1 ? "anno" : "anni"}</h1>
      <div class="sub">${titolo} \u00b7 esercizi ${annoMin}\u2013${annoMax}${fonte ? " \u00b7 fonte: " + fonte : ""}</div>
    </div>
    <button class="btn" onclick="window.print()">\ud83d\udda8\ufe0f Stampa / Salva PDF</button>
  </div>
  <h2>Conto economico riclassificato (a valore aggiunto)</h2>
  <table><thead><tr><th>Voce</th>${headCols}${varHead}</tr></thead>
  <tbody>${renderRows(ceRows)}</tbody></table>
  <h2>Stato patrimoniale riclassificato</h2>
  <table><thead><tr><th>Voce</th>${headCols}${varHead}</tr></thead>
  <tbody>${renderRows(spRows)}</tbody></table>
  <div class="foot">Le voci non disponibili per gli esercizi precedenti all'ultimo bilancio depositato sono indicate con "n.d.". Documento generato automaticamente dal gestionale.</div>
</body></html>`;
}


export default function SaluteFiscaleTab({ anagrafica_id, ana, canEdit, onReload }) {
    const [dati, setDati] = useState(null);
    const [aggIl, setAggIl] = useState(null);
    const [busy, setBusy] = useState(false);
    const [visuraBusy, setVisuraBusy] = useState(false);
    const [showPir, setShowPir] = useState(false);
    const [pirBusy, setPirBusy] = useState(false);

    const uploadVisura = async (e) => {
        const f = e.target.files?.[0]; if (!f) return;
        setVisuraBusy(true);
        try {
            const fd = new FormData();
            fd.append("file", f);
            fd.append("anagrafica_id", anagrafica_id);
            const r = await api.post(`/utility/ocr-visura-camerale`, fd,
                { headers: { "Content-Type": "multipart/form-data" } });
            const res = (await api.post(`/anagrafiche/${anagrafica_id}/applica-visura`, { dati: r.data })).data;
            const nAmm = (res.amministratori || []).length;
            toast.success(`Visura elaborata · dati societari aggiornati${nAmm ? ` · ${nAmm} amministratori rilevati` : ""}`);
            onReload?.();
        } catch (err) { toast.error(err.response?.data?.detail || "Errore OCR visura camerale"); }
        finally { setVisuraBusy(false); e.target.value = ""; }
    };

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

    const scaricaReport = async (fmt) => {
        try {
            const collegate = (ana?.parente_di || []).length;
            let gruppo = false;
            if (collegate > 0) {
                gruppo = window.confirm(`Questa azienda ha ${collegate} società collegate. Vuoi generare il REPORT DI GRUPPO (capogruppo + collegate con totali consolidati)?\n\nOK = report di gruppo · Annulla = solo questa azienda`);
            }
            const r = await api.get(`/anagrafiche/${anagrafica_id}/report-azienda/${fmt}`, { params: { gruppo }, responseType: "blob" });
            const type = fmt === "pdf" ? "application/pdf" : "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
            const url = URL.createObjectURL(new Blob([r.data], { type }));
            if (fmt === "pdf") {
                const w = window.open(url, "_blank");
                if (!w) { const a = document.createElement("a"); a.href = url; a.download = "report_azienda.pdf"; a.click(); }
            } else {
                const a = document.createElement("a"); a.href = url; a.download = "report_azienda.docx"; a.click();
            }
            setTimeout(() => URL.revokeObjectURL(url), 60000);
        } catch (e) { toast.error(e.response?.data?.detail || "Errore generazione report"); }
    };

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
    const riclass = dati?.bilanci_riclassificati || [];
    const rischio = dati?.score_rischio_default ?? null;
    const crossSell = dati?.cross_sell_suggerito || [];
    const ramoColor = (s) => s == null ? "slate" : s <= 3 ? "emerald" : s <= 6 ? "amber" : "rose";

    // Riclassificato effettivo: usa i bilanci multi-anno se presenti, altrimenti
    // ricostruisce l'ultimo anno dal bilancio estratto (OCR o OpenAPI) così
    // "ultimo anno" è SEMPRE disponibile anche senza lo storico OpenAPI.
    const bilHasData = bil && Object.keys(bil).some(
        (k) => !["anno", "confidenza", "dimensione_impresa"].includes(k) && bil[k] != null);
    const riclassEff = riclass.length > 0
        ? riclass
        : (bilHasData ? [{ ...bil, anno: bil.anno, completo: true }] : []);

    const stampaRiclassificato = (nAnni) => {
        const html = buildRiclassHTML(riclassEff, nAnni, dati?.fonte, ana?.ragione_sociale);
        if (!html) { toast.error("Nessun bilancio disponibile. Premi prima \u26a1 Compila da OpenAPI o carica un bilancio."); return; }
        const w = window.open("", "_blank");
        if (!w) { toast.error("Abilita i popup per aprire l'anteprima di stampa"); return; }
        w.document.write(html);
        w.document.close();
    };

    const scaricaRiclassPdf = async (nAnni) => {
        try {
            const r = await api.get(`/anagrafiche/${anagrafica_id}/report-azienda/riclassificato`, {
                params: { anni: nAnni }, responseType: "blob",
            });
            const url = URL.createObjectURL(new Blob([r.data], { type: "application/pdf" }));
            const w = window.open(url, "_blank");
            if (!w) { const a = document.createElement("a"); a.href = url; a.download = `bilancio_riclassificato_${nAnni}anni.pdf`; a.click(); }
            setTimeout(() => URL.revokeObjectURL(url), 60000);
        } catch (e) { toast.error(e.response?.data?.detail || "Errore generazione PDF riclassificato"); }
    };

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
                        <label className="inline-flex items-center gap-2 px-3 py-2 bg-teal-700 text-white rounded text-sm cursor-pointer hover:bg-teal-800" data-testid="sf-visura-btn">
                            <FileText size={14} />
                            {visuraBusy ? "Leggo visura…" : "Carica visura camerale"}
                            <input type="file" hidden accept="application/pdf,image/*" onChange={uploadVisura} />
                        </label>
                        {riclassEff.length > 0 && (
                            <div className="flex flex-col gap-1.5 items-end border-t border-emerald-200 pt-2 mt-1">
                                <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">Bilancio riclassificato</div>
                                <div className="flex gap-2 flex-wrap justify-end">
                                    <button onClick={() => stampaRiclassificato(1)}
                                        className="inline-flex items-center gap-1.5 px-2.5 py-1.5 bg-amber-500 text-white rounded text-xs hover:bg-amber-600"
                                        data-testid="sf-riclass-1-btn"><Printer size={13} /> Ultimo anno</button>
                                    <button onClick={() => stampaRiclassificato(3)}
                                        className="inline-flex items-center gap-1.5 px-2.5 py-1.5 bg-amber-600 text-white rounded text-xs hover:bg-amber-700"
                                        data-testid="sf-riclass-3-btn"><Printer size={13} /> 3 anni</button>
                                    <button onClick={() => stampaRiclassificato(5)}
                                        className="inline-flex items-center gap-1.5 px-2.5 py-1.5 bg-amber-700 text-white rounded text-xs hover:bg-amber-800"
                                        data-testid="sf-riclass-5-btn"><Printer size={13} /> 5 anni</button>
                                </div>
                                <div className="flex gap-2 flex-wrap justify-end">
                                    <button onClick={() => scaricaRiclassPdf(1)}
                                        className="inline-flex items-center gap-1.5 px-2.5 py-1.5 bg-rose-600 text-white rounded text-xs hover:bg-rose-700"
                                        data-testid="sf-riclass-pdf-1-btn"><FileText size={13} /> PDF ultimo anno</button>
                                    <button onClick={() => scaricaRiclassPdf(3)}
                                        className="inline-flex items-center gap-1.5 px-2.5 py-1.5 bg-rose-700 text-white rounded text-xs hover:bg-rose-800"
                                        data-testid="sf-riclass-pdf-3-btn"><FileText size={13} /> PDF 3 anni</button>
                                    <button onClick={() => scaricaRiclassPdf(5)}
                                        className="inline-flex items-center gap-1.5 px-2.5 py-1.5 bg-rose-800 text-white rounded text-xs hover:bg-rose-900"
                                        data-testid="sf-riclass-pdf-5-btn"><FileText size={13} /> PDF 5 anni</button>
                                </div>
                            </div>
                        )}
                        {tipoCliente && (
                            <button onClick={apriPiramide} disabled={pirBusy}
                                className="inline-flex items-center gap-2 px-3 py-2 bg-indigo-600 text-white rounded text-sm hover:bg-indigo-700 disabled:opacity-50"
                                data-testid="sf-piramide-btn">
                                🔺 {pirBusy ? "Precompilo…" : "Piramide Azienda"}
                            </button>
                        )}
                        <div className="flex gap-2">
                            <button onClick={() => scaricaReport("pdf")} disabled={busy}
                                className="inline-flex items-center gap-2 px-3 py-2 bg-slate-700 text-white rounded text-sm hover:bg-slate-800 disabled:opacity-50"
                                data-testid="sf-report-pdf-btn">📄 Report PDF</button>
                            <button onClick={() => scaricaReport("docx")} disabled={busy}
                                className="inline-flex items-center gap-2 px-3 py-2 bg-sky-800 text-white rounded text-sm hover:bg-sky-900 disabled:opacity-50"
                                data-testid="sf-report-word-btn">📝 Report Word</button>
                        </div>
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

                    <MargineContribuzione bil={bil} anagrafica_id={anagrafica_id} saved={ana?.salute_fiscale_scenari} savedList={ana?.salute_fiscale_scenari_list} ragione={ana?.ragione_sociale} onReload={onReload} />
                    <StudioBilancio bil={bil} />
                </>
            )}

            <ImmobiliSection anagrafica_id={anagrafica_id} canEdit={canEdit} />
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
const eur0 = (v) => (v == null ? "—" : Number(v).toLocaleString("it-IT", { maximumFractionDigits: 0, useGrouping: "always" }) + " €");

// ── Margine di Contribuzione + Metriche di impatto (fermo attività) ──
function MargineContribuzione({ bil, anagrafica_id, saved, savedList, ragione, onReload }) {
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
    // Gestione multi-scenario: lista salvata per cliente (ognuno con nome + anno)
    const [scenari, setScenari] = useState(() => (Array.isArray(savedList) ? savedList : []));
    const [curId, setCurId] = useState(null);
    const [nome, setNome] = useState("Scenario 1");
    const [anno, setAnno] = useState(bil.anno || new Date().getFullYear() - 1);
    // se non ci sono scenari salvati, ri-inizializza le righe quando cambiano i dati di bilancio
    useEffect(() => {
        if (!saved?.rows?.length && !scenari.length) setRows(initRows());
        /* eslint-disable-next-line */
    }, [bil.valore_produzione, bil.rimanenze_totali, bil.costi_servizi]);

    const snapshot = () => ({ rows, giorni, gScen, riskTol, riskApp });
    const loadScenario = (s) => {
        if (!s) return;
        setCurId(s.id); setNome(s.nome || "Scenario"); setAnno(s.anno || anno);
        if (s.rows?.length) setRows(s.rows);
        if (s.giorni != null) setGiorni(s.giorni);
        if (s.gScen?.length === 4) setGScen(s.gScen);
        if (s.riskTol != null) setRiskTol(s.riskTol);
        if (s.riskApp != null) setRiskApp(s.riskApp);
    };
    const persistList = async (list, msg) => {
        setSaving(true);
        try {
            await api.put(`/anagrafiche/${anagrafica_id}`, { salute_fiscale_scenari_list: list });
            setScenari(list);
            toast.success(msg || "Scenari salvati");
            onReload?.();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore salvataggio scenari"); }
        finally { setSaving(false); }
    };
    const salvaScenari = async () => {
        const id = curId || (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()));
        const entry = { id, nome: nome || `Scenario ${scenari.length + 1}`, anno, ...snapshot(), updated_at: new Date().toISOString() };
        const exists = scenari.some((s) => s.id === id);
        const list = exists ? scenari.map((s) => (s.id === id ? entry : s)) : [...scenari, entry];
        setCurId(id);
        await persistList(list, exists ? "Scenario aggiornato" : "Scenario salvato");
    };
    const nuovoScenario = () => {
        setCurId(null); setNome(`Scenario ${scenari.length + 1}`);
        setAnno(bil.anno || new Date().getFullYear() - 1); setRows(initRows());
    };
    const copiaScenario = async () => {
        const id = crypto.randomUUID ? crypto.randomUUID() : String(Date.now());
        const entry = { id, nome: `${nome} (copia)`, anno, ...snapshot(), updated_at: new Date().toISOString() };
        setCurId(id); setNome(entry.nome);
        await persistList([...scenari, entry], "Scenario copiato");
    };
    const eliminaScenario = async () => {
        if (!curId) { nuovoScenario(); return; }
        if (!window.confirm("Eliminare questo scenario?")) return;
        const list = scenari.filter((s) => s.id !== curId);
        nuovoScenario();
        await persistList(list, "Scenario eliminato");
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

    const stampaScenario = () => {
        const righe = rows.map((r) => `<tr><td>${r.l}</td><td class="r">${eur0(r.imp)}</td><td class="r">${r.pct}%</td><td class="r">${r.seg === "+" ? eur0(pesato(r)) : "-"}</td><td class="r">${r.seg === "-" ? eur0(pesato(r)) : "-"}</td></tr>`).join("");
        const html = `<!doctype html><html lang="it"><head><meta charset="utf-8"><title>MDC ${nome} ${anno}</title>
<style>body{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1e293b;padding:28px 34px}h1{font-size:18px;margin:0}.sub{color:#64748b;font-size:12px;margin:2px 0 14px}table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:5px 9px;border-bottom:1px solid #e2e8f0}th{background:#f1f5f9;text-align:left;text-transform:uppercase;font-size:10px;color:#475569}td.r,th.r{text-align:right}.tot td{font-weight:700;border-top:2px solid #cbd5e1}.kpi{display:flex;gap:16px;margin-top:16px}.kpi div{background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:10px 14px}.kpi b{display:block;font-size:16px;color:#0369a1}.btn{background:#0f172a;color:#fff;border:0;border-radius:6px;padding:9px 16px;font-size:13px;cursor:pointer;margin-top:16px}@media print{.btn{display:none}body{padding:0}}</style></head><body>
<h1>Margine di Contribuzione — perdita in caso di fermo</h1>
<div class="sub">${ragione || "Azienda"} · ${nome} · esercizio ${anno}</div>
<table><thead><tr><th>Voci di bilancio</th><th class="r">Importo</th><th class="r">% non assic.</th><th class="r">Importo +</th><th class="r">Importo −</th></tr></thead>
<tbody>${righe}<tr class="tot"><td>Totale importi</td><td></td><td></td><td class="r">${eur0(totPiu)}</td><td class="r">${eur0(totMeno)}</td></tr></tbody></table>
<div class="kpi"><div>Margine di contribuzione<b>${eur0(mdc)}</b></div><div>% su ricavi<b>${pctRicavi.toFixed(1)} %</b></div><div>MDC giornaliero<b>${eur0(mdcGiorno)}</b></div><div>Giorni lavorativi/anno<b>${giorni}</b></div></div>
<button class="btn" onclick="window.print()">🖨️ Stampa / Salva PDF</button></body></html>`;
        const w = window.open("", "_blank");
        if (!w) { toast.error("Abilita i popup per la stampa"); return; }
        w.document.write(html); w.document.close();
    };

    return (
        <>
        <Card className="p-4" data-testid="sf-mdc-card">
            <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                <h4 className="font-semibold text-slate-800 text-sm">🧮 Margine di Contribuzione (perdita in caso di fermo)</h4>
                <div className="flex items-center gap-1.5 flex-wrap">
                    <select value={curId || ""} onChange={(e) => e.target.value ? loadScenario(scenari.find((s) => s.id === e.target.value)) : nuovoScenario()}
                        className="h-7 text-xs border border-slate-300 rounded px-2 bg-white" data-testid="mdc-scenario-select">
                        <option value="">➕ Nuovo scenario</option>
                        {scenari.map((s) => <option key={s.id} value={s.id}>{s.nome} · {s.anno}</option>)}
                    </select>
                    <Input value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Nome scenario" className="h-7 w-32 text-xs" data-testid="mdc-scenario-nome" />
                    <Input type="number" value={anno} onChange={(e) => setAnno(n(e.target.value))} className="h-7 w-20 text-xs" data-testid="mdc-scenario-anno" />
                    <button onClick={salvaScenari} disabled={saving} className="text-xs px-2.5 py-1.5 rounded bg-slate-800 text-white hover:bg-slate-900 disabled:opacity-50" data-testid="sf-salva-scenari">{saving ? "Salvo…" : "💾 Salva"}</button>
                    <button onClick={copiaScenario} disabled={saving} className="text-xs px-2.5 py-1.5 rounded border border-slate-300 text-slate-700 hover:bg-slate-100" data-testid="mdc-copia">📋 Copia</button>
                    <button onClick={eliminaScenario} disabled={saving} className="text-xs px-2.5 py-1.5 rounded border border-rose-300 text-rose-700 hover:bg-rose-50" data-testid="mdc-elimina">🗑️ Elimina</button>
                    <button onClick={stampaScenario} className="text-xs px-2.5 py-1.5 rounded border border-sky-300 text-sky-700 hover:bg-sky-50" data-testid="mdc-stampa">🖨️ Stampa</button>
                </div>
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
