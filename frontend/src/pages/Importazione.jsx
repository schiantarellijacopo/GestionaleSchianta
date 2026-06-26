/**
 * Pagina "Importazioni Flussi" — gestione di tutti i flussi di importazione.
 *
 * Tab:
 *  - OMNIA: ZIP ANIA giornaliero (anagrafiche, polizze, titoli, sinistri, garanzie)
 *  - Targhe / Libri Matricola: CSV con mapping manuale delle colonne
 *
 * UX (iter23):
 *  - Pulsante "Importa" esplicito
 *  - Report dettagliato post-import: cosa è entrato + cosa è stato saltato
 *  - Wizard interattivo mapping delle entità non mappate (compagnie/rami/operatori/prodotti/garanzie)
 */
import { useEffect, useState, useRef, useCallback } from "react";
import { api, fmtDate } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
    Upload, FileArchive, CheckCircle2, AlertCircle, Clock,
    AlertTriangle, FileText, Car, Wand2, X, Save,
} from "lucide-react";
import { toast } from "sonner";


const TIPO_LABEL = {
    compagnia: "Compagnia",
    collaboratore: "Operatore / Collaboratore",
    prodotto: "Prodotto",
    garanzia: "Garanzia",
};
const TIPO_PLURAL = {
    compagnie: "compagnia",
    collaboratori: "collaboratore",
    prodotti: "prodotto",
    garanzie: "garanzia",
};


export default function Importazioni() {
    const [tab, setTab] = useState("omnia");
    const [showWizard, setShowWizard] = useState(false);

    return (
        <div data-testid="importazioni-page">
            <PageHeader
                title="Importazioni Flussi"
                subtitle="Carica i tracciati delle compagnie. OMNIA (ZIP ANIA) + Targhe/Libri matricola (CSV con mapping)."
                actions={
                    <Button
                        variant="outline"
                        onClick={() => setShowWizard(true)}
                        data-testid="wizard-mapping-btn"
                    >
                        <Wand2 size={14} className="mr-1.5" /> Wizard Mapping
                    </Button>
                }
            />
            <div className="flex gap-2 mb-4 border-b">
                {[
                    { v: "omnia", label: "Importazione OMNIA", Icon: FileArchive },
                    { v: "targhe", label: "Targhe / Libri Matricola", Icon: Car },
                    { v: "storico", label: "Storico", Icon: Clock },
                ].map(({ v, label, Icon }) => (
                    <button
                        key={v}
                        onClick={() => setTab(v)}
                        className={`inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 transition-colors ${tab === v ? "border-sky-600 text-sky-700" : "border-transparent text-slate-500 hover:text-slate-700"}`}
                        data-testid={`tab-${v}`}
                    >
                        <Icon size={14} /> {label}
                    </button>
                ))}
            </div>
            {tab === "omnia" && <ImportOmnia onOpenWizard={() => setShowWizard(true)} />}
            {tab === "targhe" && <ImportTargheStub />}
            {tab === "storico" && <Storico onOpenWizard={() => setShowWizard(true)} />}

            <MappingWizardDialog
                open={showWizard}
                onClose={() => setShowWizard(false)}
            />
        </div>
    );
}


// ============================================================
// OMNIA — ZIP ANIA
// ============================================================
function ImportOmnia({ onOpenWizard }) {
    const [file, setFile] = useState(null);
    const [uploading, setUploading] = useState(false);
    const [lastLog, setLastLog] = useState(null);
    const inputRef = useRef(null);

    const startImport = async () => {
        if (!file) { toast.error("Seleziona prima un file ZIP"); return; }
        setUploading(true);
        const fd = new FormData();
        fd.append("file", file);
        try {
            const res = await api.post("/import/omnia", fd, {
                headers: { "Content-Type": "multipart/form-data" },
            });
            setLastLog(res.data);
            toast.success(`Import completato in ${(res.data.durata_ms / 1000).toFixed(1)}s`);
            setFile(null);
            if (inputRef.current) inputRef.current.value = "";
        } catch (e) {
            toast.error("Errore import: " + (e.response?.data?.detail || e.message));
        } finally {
            setUploading(false);
        }
    };

    return (
        <div>
            <Card className="p-6 mb-4" data-testid="omnia-dropzone">
                <FileArchive size={36} className="mx-auto text-sky-700 mb-3" />
                <div className="text-center text-slate-800 font-medium mb-1">
                    File ZIP OMNIA (tracciati ANIA)
                </div>
                <div className="text-center text-xs text-slate-500 mb-4">
                    Anagrafiche · Polizze · Titoli · Sinistri · Garanzie · Operatori
                </div>
                <div className="flex items-center justify-center gap-2">
                    <input
                        ref={inputRef}
                        type="file"
                        accept=".zip,.csv"
                        className="hidden"
                        onChange={(e) => setFile(e.target.files?.[0] || null)}
                        data-testid="omnia-file-input"
                    />
                    <Button
                        type="button"
                        variant="outline"
                        onClick={() => inputRef.current?.click()}
                        data-testid="omnia-select-button"
                    >
                        <Upload size={14} className="mr-1" />
                        {file ? file.name : "Seleziona ZIP"}
                    </Button>
                    <Button
                        type="button"
                        onClick={startImport}
                        disabled={!file || uploading}
                        className="bg-sky-700 hover:bg-sky-800"
                        data-testid="omnia-importa-btn"
                    >
                        {uploading ? "Importazione in corso..." : "Importa"}
                    </Button>
                </div>
            </Card>
            {lastLog && <ImportReport log={lastLog} onOpenWizard={onOpenWizard} />}
        </div>
    );
}


// ============================================================
// REPORT DETTAGLIATO POST-IMPORT
// ============================================================
function ImportReport({ log, onOpenWizard }) {
    const skipped = log.record_skipped || [];
    const non_mappate = log.entita_non_mappate || {};
    const total_unmapped = Object.values(non_mappate).reduce((s, arr) => s + (arr?.length || 0), 0);

    return (
        <div className="space-y-4">
            <Card className={`p-5 border-l-4 ${log.stato === "completato" ? "border-l-emerald-500" : "border-l-amber-500"}`} data-testid="omnia-report">
                <div className="flex items-center gap-2 mb-3">
                    {log.stato === "completato"
                        ? <CheckCircle2 size={18} className="text-emerald-600" />
                        : <AlertCircle size={18} className="text-amber-600" />
                    }
                    <div className="font-medium text-slate-900">Report import: {log.nome_file}</div>
                    <span className="text-xs text-slate-500">{(log.durata_ms / 1000).toFixed(2)}s</span>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-6 gap-3 text-sm">
                    <Stat label="Anag. nuove" value={log.anagrafiche_create} />
                    <Stat label="Anag. agg." value={log.anagrafiche_aggiornate} />
                    <Stat label="Polizze nuove" value={log.polizze_create} />
                    <Stat label="Polizze agg." value={log.polizze_aggiornate} />
                    <Stat label="Titoli" value={log.titoli_creati} />
                    <Stat label="Sinistri" value={log.sinistri_creati} />
                </div>
                <div className="mt-3 text-xs text-slate-600">
                    <span className="font-medium text-slate-700">Record types:</span>{" "}
                    {Object.entries(log.record_types_processati || {}).map(([k, v]) => (
                        <span key={k} className="inline-block ml-2 text-[10px] bg-slate-100 px-1.5 py-0.5 rounded">
                            {k}: {v}
                        </span>
                    ))}
                </div>
            </Card>

            {total_unmapped > 0 && (
                <Card className="p-5 border-l-4 border-l-amber-500 bg-amber-50/40" data-testid="non-mappate-card">
                    <div className="flex items-center gap-2 mb-2">
                        <AlertTriangle size={18} className="text-amber-600" />
                        <div className="font-medium text-amber-900">Entità non mappate ({total_unmapped})</div>
                        <Button
                            size="sm"
                            className="ml-auto bg-amber-600 hover:bg-amber-700"
                            onClick={onOpenWizard}
                            data-testid="apri-wizard-da-report-btn"
                        >
                            <Wand2 size={13} className="mr-1" /> Apri Wizard
                        </Button>
                    </div>
                    <p className="text-sm text-amber-800 mb-3">
                        Le seguenti entità sono apparse nel flusso ma non sono ancora collegate
                        a un&apos;entità del programma. Mappa ciascuna per averle gestite automaticamente
                        al prossimo import e applica il back-fill ai record già caricati.
                    </p>
                    {["compagnie", "collaboratori", "prodotti", "garanzie"].map((tipoP) => {
                        const items = non_mappate[tipoP] || [];
                        if (!items.length) return null;
                        return (
                            <div key={tipoP} className="mb-3" data-testid={`non-mappate-${tipoP}`}>
                                <div className="text-xs uppercase font-semibold text-amber-700 mb-1.5">
                                    {tipoP} ({items.length})
                                </div>
                                <div className="flex flex-wrap gap-1.5">
                                    {items.slice(0, 50).map((v, i) => {
                                        const label = typeof v === "string" ? v : (v.label || v.valore);
                                        const count = typeof v === "object" ? v.count : null;
                                        return (
                                            <span key={i} className="text-xs bg-white border border-amber-300 text-amber-900 px-2 py-1 rounded">
                                                {label}{count ? ` ×${count}` : ""}
                                            </span>
                                        );
                                    })}
                                    {items.length > 50 && (
                                        <span className="text-[11px] text-amber-700">… e altri {items.length - 50}</span>
                                    )}
                                </div>
                            </div>
                        );
                    })}
                </Card>
            )}

            {(skipped.length > 0 || (log.errori || []).length > 0) && (
                <Card className="p-5 border-l-4 border-l-rose-400" data-testid="skipped-card">
                    <div className="flex items-center gap-2 mb-3">
                        <AlertCircle size={16} className="text-rose-600" />
                        <div className="font-medium text-rose-900">Record non importati ({skipped.length + (log.errori || []).length})</div>
                    </div>
                    {(log.errori || []).length > 0 && (
                        <div className="mb-3">
                            <div className="text-xs font-semibold text-rose-700 mb-1">Errori globali</div>
                            <ul className="text-xs text-rose-800 list-disc pl-5">
                                {(log.errori || []).slice(0, 20).map((e, i) => <li key={i}>{e}</li>)}
                            </ul>
                        </div>
                    )}
                    {skipped.length > 0 && (
                        <div className="overflow-x-auto">
                            <table className="data-table text-xs w-full">
                                <thead><tr>
                                    <th>Tipo</th><th>Riga</th><th>Motivo</th><th>Identificativo</th>
                                </tr></thead>
                                <tbody>
                                    {skipped.slice(0, 100).map((s, i) => (
                                        <tr key={i}>
                                            <td>{s.tipo || "—"}</td>
                                            <td className="num">{s.riga ?? "—"}</td>
                                            <td className="text-rose-700">{s.motivo}</td>
                                            <td>{s.id || s.codice || s.label || "—"}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                            {skipped.length > 100 && <p className="text-[11px] text-slate-500 mt-2">…e altri {skipped.length - 100} record</p>}
                        </div>
                    )}
                </Card>
            )}
        </div>
    );
}

function Stat({ label, value }) {
    return (
        <div className="bg-slate-50 rounded p-2">
            <div className="text-[10px] uppercase text-slate-500">{label}</div>
            <div className="text-xl font-semibold num">{value || 0}</div>
        </div>
    );
}


// ============================================================
// WIZARD MAPPING — Dialog interattivo
// ============================================================
function MappingWizardDialog({ open, onClose }) {
    const [data, setData] = useState(null);          // { compagnia: [...], prodotto: [...], candidates: {...} }
    const [edits, setEdits] = useState({});          // {mapping_id: entita_id | "" }
    const [active, setActive] = useState("compagnia");
    const [showAll, setShowAll] = useState(true);   // default ON: mostra TUTTE per permettere sempre modifica
    const [saving, setSaving] = useState(false);
    const [applying, setApplying] = useState(false);

    const load = useCallback(async () => {
        try {
            const res = await api.get(`/import/unmapped${showAll ? "?include_mapped=true" : ""}`);
            setData(res.data);
            const first = ["compagnia", "collaboratore", "prodotto", "garanzia"]
                .find((t) => (res.data[t] || []).length > 0);
            if (first) setActive(first);
        } catch (e) {
            toast.error("Errore caricamento mapping: " + (e.response?.data?.detail || e.message));
        }
    }, [showAll]);

    useEffect(() => {
        if (open) { setEdits({}); load(); }
    }, [open, load]);

    const saveAll = async (applyAfter = false) => {
        const items = data ? Object.values(data).flat().filter((x) => x?.id) : [];
        const byId = Object.fromEntries(items.map((it) => [it.id, it]));
        // Considera "modificato" se edits[id] è diverso dal current entita_id (o "" per scollegare)
        const updates = Object.entries(edits).filter(([mid, v]) => {
            const cur = byId[mid]?.entita_id || "";
            return v !== cur;  // ogni valore esplicitamente diverso (anche "" per scollegare)
        });
        if (!updates.length) {
            toast.info("Nessuna modifica da salvare");
            return;
        }
        setSaving(true);
        try {
            for (const [mid, entita_id] of updates) {
                const it = byId[mid];
                if (!it) continue;
                const tipo = ["compagnia", "collaboratore", "prodotto", "garanzia"]
                    .find((t) => (data[t] || []).some((x) => x.id === mid));
                await api.post("/import/mappings", {
                    tipo,
                    flusso: "omnia",
                    valore_flusso: it.valore_flusso,
                    entita_id: entita_id || null,
                    label_programma: entita_id
                        ? ((data.candidates[tipo] || []).find((c) => c.id === entita_id)?.label || null)
                        : null,
                });
            }
            toast.success(`Salvate ${updates.length} modifiche`);
            if (applyAfter) {
                await applyMappings(false);
            }
            await load();
        } catch (e) {
            toast.error("Errore salvataggio: " + (e.response?.data?.detail || e.message));
        } finally {
            setSaving(false);
        }
    };

    const removeMapping = async (mid) => {
        if (!window.confirm("Vuoi rimuovere completamente questa associazione?\nIl valore tornerà tra le entità da mappare.")) return;
        try {
            await api.delete(`/import/mappings/${mid}`);
            toast.success("Associazione rimossa");
            await load();
        } catch (e) {
            toast.error("Errore: " + (e.response?.data?.detail || e.message));
        }
    };

    const applyMappings = async (showToast = true) => {
        setApplying(true);
        try {
            const res = await api.post("/import/mappings/apply");
            const s = res.data;
            const total = (s.polizze_collaboratore || 0)
                + (s.polizze_prodotto || 0)
                + (s.polizze_garanzia || 0)
                + (s.polizze_compagnia || 0);
            if (showToast) {
                toast.success(`Back-fill completato: ${total} polizze aggiornate`);
            }
        } catch (e) {
            toast.error("Errore back-fill: " + (e.response?.data?.detail || e.message));
        } finally {
            setApplying(false);
        }
    };

    if (!open) return null;

    const tipi = ["compagnia", "collaboratore", "prodotto", "garanzia"];
    const counts = data ? Object.fromEntries(tipi.map((t) => [t, (data[t] || []).length])) : {};
    const totalCount = Object.values(counts).reduce((s, n) => s + n, 0);

    return (
        <Dialog open={open} onOpenChange={onClose}>
            <DialogContent className="max-w-3xl max-h-[85vh] overflow-hidden flex flex-col" data-testid="wizard-mapping-dialog">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Wand2 size={18} className="text-sky-700" />
                        Wizard Mapping Entità Importazione
                    </DialogTitle>
                    <DialogDescription>
                        Collega le entità apparse nei flussi alle librerie del programma. Puoi anche
                        modificare o rimuovere associazioni già effettuate.
                    </DialogDescription>
                </DialogHeader>

                {/* Toggle filtro */}
                <div className="flex items-center gap-3 text-xs border-b pb-2">
                    <label className="flex items-center gap-1.5 cursor-pointer" data-testid="wizard-toggle-showall">
                        <input
                            type="checkbox"
                            checked={!showAll}
                            onChange={(e) => setShowAll(!e.target.checked)}
                            className="rounded"
                        />
                        <span className="text-slate-700">Mostra solo entità ancora da mappare</span>
                    </label>
                    {showAll && (
                        <span className="text-[10px] text-slate-500">
                            (le righe in verde sono già associate — modifica/rimuovi cliccando sul dropdown o la X)
                        </span>
                    )}
                </div>

                {!data ? <Loading /> : totalCount === 0 ? (
                    <div className="py-12 text-center" data-testid="wizard-no-unmapped">
                        <CheckCircle2 size={42} className="mx-auto text-emerald-500 mb-3" />
                        <p className="text-sm text-slate-600">
                            {showAll
                                ? "Nessuna entità presente. Importa prima un flusso OMNIA."
                                : "Tutte le entità sono mappate."}
                        </p>
                        <p className="text-xs text-slate-500 mt-1">Puoi comunque eseguire il back-fill sui record esistenti.</p>
                        <Button
                            className="mt-4"
                            variant="outline"
                            disabled={applying}
                            onClick={() => applyMappings(true)}
                            data-testid="wizard-apply-only-btn"
                        >
                            {applying ? "Applicazione..." : "Applica back-fill ai record esistenti"}
                        </Button>
                    </div>
                ) : (
                    <>
                        <div className="flex gap-1 border-b">
                            {tipi.map((t) => (
                                <button
                                    key={t}
                                    onClick={() => setActive(t)}
                                    disabled={counts[t] === 0}
                                    className={`px-3 py-1.5 text-xs font-medium border-b-2 transition-colors ${active === t ? "border-sky-600 text-sky-700" : "border-transparent text-slate-500 hover:text-slate-700"} ${counts[t] === 0 ? "opacity-40 cursor-not-allowed" : ""}`}
                                    data-testid={`wizard-tab-${t}`}
                                >
                                    {TIPO_LABEL[t]} {counts[t] > 0 && <span className="ml-1 text-amber-700">({counts[t]})</span>}
                                </button>
                            ))}
                        </div>

                        <div className="overflow-y-auto flex-1 -mx-1 px-1 py-2" data-testid={`wizard-list-${active}`}>
                            <MappingRows
                                items={data[active] || []}
                                candidates={data.candidates?.[active] || []}
                                edits={edits}
                                onChange={(id, v) => setEdits((s) => ({ ...s, [id]: v }))}
                                onRemove={removeMapping}
                                tipo={active}
                            />
                        </div>
                    </>
                )}

                <DialogFooter className="border-t pt-3 gap-2">
                    <Button variant="ghost" onClick={onClose} data-testid="wizard-close-btn">
                        <X size={14} className="mr-1" /> Chiudi
                    </Button>
                    {data && totalCount > 0 && (
                        <>
                            <Button
                                variant="outline"
                                disabled={saving}
                                onClick={() => saveAll(false)}
                                data-testid="wizard-save-btn"
                            >
                                <Save size={14} className="mr-1" /> {saving ? "Salvataggio..." : "Salva modifiche"}
                            </Button>
                            <Button
                                className="bg-sky-700 hover:bg-sky-800"
                                disabled={saving || applying}
                                onClick={() => saveAll(true)}
                                data-testid="wizard-save-apply-btn"
                            >
                                <Wand2 size={14} className="mr-1" />
                                {saving || applying ? "Elaborazione..." : "Salva e applica"}
                            </Button>
                        </>
                    )}
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}


function MappingRows({ items, candidates, edits, onChange, onRemove, tipo }) {
    if (!items.length) {
        return <p className="text-sm text-slate-500 py-4 text-center">Nessuna entità in questa categoria.</p>;
    }
    return (
        <table className="data-table w-full text-sm">
            <thead>
                <tr>
                    <th>Valore nel flusso</th>
                    <th className="num">Occ.</th>
                    <th>Associazione → {TIPO_LABEL[tipo]} programma</th>
                    <th></th>
                </tr>
            </thead>
            <tbody>
                {items.map((it) => {
                    // Se l'utente ha modificato il valore, usa quello; altrimenti il valore corrente
                    const currentVal = edits[it.id] !== undefined ? edits[it.id] : (it.entita_id || "");
                    const isMapped = !!it.entita_id;
                    const hasLabel = it.label_flusso && it.label_flusso !== it.valore_flusso;
                    return (
                        <tr key={it.id} data-testid={`wizard-row-${it.id}`} className={isMapped ? "bg-emerald-50/40" : ""}>
                            <td>
                                {/* Il nome leggibile (descrizione) va in primo piano; il codice tecnico sotto */}
                                <div className="font-medium text-slate-800">
                                    {hasLabel ? it.label_flusso : it.valore_flusso}
                                </div>
                                {hasLabel && (
                                    <div className="text-[11px] text-slate-500 font-mono">cod: {it.valore_flusso}</div>
                                )}
                                {isMapped && (
                                    <div className="text-[10px] text-emerald-700 mt-0.5">
                                        ✓ Attualmente: {it.label_programma || it.entita_id}
                                    </div>
                                )}
                            </td>
                            <td className="num">{it.occorrenze || 0}</td>
                            <td>
                                <select
                                    value={currentVal}
                                    onChange={(e) => onChange(it.id, e.target.value)}
                                    className={`w-full text-xs border rounded px-2 py-1.5 bg-white ${isMapped && currentVal === (it.entita_id || "") ? "border-emerald-400" : ""}`}
                                    data-testid={`wizard-select-${it.id}`}
                                >
                                    <option value="">— Non associato —</option>
                                    {candidates.map((c) => (
                                        <option key={c.id} value={c.id}>{c.label}</option>
                                    ))}
                                </select>
                            </td>
                            <td>
                                {isMapped && (
                                    <button
                                        onClick={() => onRemove(it.id)}
                                        className="text-rose-600 hover:text-rose-800 p-1"
                                        title="Elimina mapping"
                                        data-testid={`wizard-remove-${it.id}`}
                                    >
                                        <X size={14} />
                                    </button>
                                )}
                            </td>
                        </tr>
                    );
                })}
            </tbody>
        </table>
    );
}


// ============================================================
// STORICO
// ============================================================
function Storico({ onOpenWizard }) {
    const [storico, setStorico] = useState(null);
    const [details, setDetails] = useState(null);

    useEffect(() => { api.get("/import/storico").then((r) => setStorico(r.data)); }, []);

    const openDetail = async (lid) => {
        const r = await api.get(`/import/log/${lid}`);
        setDetails(r.data);
    };

    if (storico === null) return <Loading />;
    if (storico.length === 0) return <Empty label="Nessuna importazione effettuata" />;

    return (
        <div>
            <Card className="overflow-hidden">
                <table className="data-table w-full">
                    <thead><tr>
                        <th>Data</th><th>File</th><th>Flusso</th><th>Stato</th>
                        <th className="text-right">Anag.</th><th className="text-right">Polizze</th>
                        <th className="text-right">Titoli</th><th className="text-right">Sinistri</th>
                        <th className="text-right">Durata</th><th></th>
                    </tr></thead>
                    <tbody>
                        {storico.map((l) => (
                            <tr key={l.id} className="cursor-pointer hover:bg-slate-50" onClick={() => openDetail(l.id)}>
                                <td className="num text-xs">{fmtDate(l.created_at)}</td>
                                <td className="text-xs">{l.nome_file}</td>
                                <td className="text-xs uppercase">{l.flusso || "omnia"}</td>
                                <td>
                                    <span className={`badge ${l.stato === "completato" ? "badge-success" : l.stato === "errore" ? "badge-danger" : "badge-warning"} inline-flex items-center gap-1`}>
                                        {l.stato === "completato" ? <CheckCircle2 size={11} /> : l.stato === "errore" ? <AlertCircle size={11} /> : <Clock size={11} />}
                                        {l.stato}
                                    </span>
                                </td>
                                <td className="num text-right">{(l.anagrafiche_create || 0) + (l.anagrafiche_aggiornate || 0)}</td>
                                <td className="num text-right">{(l.polizze_create || 0) + (l.polizze_aggiornate || 0)}</td>
                                <td className="num text-right">{l.titoli_creati || 0}</td>
                                <td className="num text-right">{l.sinistri_creati || 0}</td>
                                <td className="num text-right">{((l.durata_ms || 0) / 1000).toFixed(1)}s</td>
                                <td><FileText size={13} className="text-slate-400" /></td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </Card>
            {details && (
                <div className="mt-4">
                    <ImportReport log={details} onOpenWizard={onOpenWizard} />
                    <Button variant="outline" onClick={() => setDetails(null)} className="mt-3">Chiudi dettaglio</Button>
                </div>
            )}
        </div>
    );
}


// ============================================================
// IMPORT TARGHE / LIBRI MATRICOLA
// ============================================================
export function ImportTargheStub({ polizzaPreselezionata = null, onImportComplete = null }) {
    const [file, setFile] = useState(null);
    const [preview, setPreview] = useState(null);
    const [mapping, setMapping] = useState({});
    const [importing, setImporting] = useState(false);
    const [result, setResult] = useState(null);
    const [polizzaId, setPolizzaId] = useState(polizzaPreselezionata?.id || "");
    const [polizzaQuery, setPolizzaQuery] = useState(polizzaPreselezionata?.numero_polizza || "");
    const [polizzeMatch, setPolizzeMatch] = useState([]);
    const [polizzaSel, setPolizzaSel] = useState(polizzaPreselezionata || null);
    const inputRef = useRef(null);

    const onSelectFile = (f) => {
        setFile(f);
        setPreview(null);
        setResult(null);
        setMapping({});
    };

    // Live search polizze per numero/contraente (debounce semplice via lunghezza min)
    useEffect(() => {
        if (polizzaPreselezionata || !polizzaQuery || polizzaQuery.length < 2 || polizzaSel) {
            setPolizzeMatch([]);
            return;
        }
        const tid = setTimeout(async () => {
            try {
                const r = await api.get("/polizze", { params: { q: polizzaQuery, limit: 8 } });
                const items = Array.isArray(r.data) ? r.data : (r.data?.items || []);
                setPolizzeMatch(items);
            } catch { setPolizzeMatch([]); }
        }, 250);
        return () => clearTimeout(tid);
    }, [polizzaQuery, polizzaSel, polizzaPreselezionata]);

    const doPreview = async () => {
        if (!file) { toast.error("Seleziona prima un file"); return; }
        const fd = new FormData();
        fd.append("file", file);
        try {
            const res = await api.post("/import/libro-matricola/preview", fd, {
                headers: { "Content-Type": "multipart/form-data" },
            });
            setPreview(res.data);
            setMapping(res.data.suggested_mapping || {});
            toast.success(`Letto file: ${res.data.total_rows} righe, ${res.data.headers.length} colonne`);
        } catch (e) {
            toast.error("Errore preview: " + (e.response?.data?.detail || e.message));
        }
    };

    const doCommit = async () => {
        if (!file || !preview) return;
        const requiredFields = (preview.campi_target || []).filter((c) => c.required).map((c) => c.field);
        const mappedFields = new Set(Object.values(mapping).filter(Boolean));
        const missingReq = requiredFields.filter((f) => !mappedFields.has(f));
        if (missingReq.length) {
            toast.error("Mappa i campi obbligatori: " + missingReq.join(", "));
            return;
        }
        setImporting(true);
        try {
            const fd = new FormData();
            fd.append("file", file);
            fd.append("mapping", JSON.stringify(mapping));
            if (polizzaId) fd.append("polizza_id", polizzaId);
            const res = await api.post("/import/libro-matricola/commit", fd, {
                headers: { "Content-Type": "multipart/form-data" },
            });
            setResult(res.data);
            const s = res.data;
            const linkInfo = polizzaSel ? ` e collegati a polizza ${polizzaSel.numero_polizza}` : "";
            toast.success(`Importati ${s.creati + s.aggiornati} veicoli${linkInfo}`);
            if (onImportComplete) onImportComplete(res.data);
        } catch (e) {
            toast.error("Errore import: " + (e.response?.data?.detail || e.message));
        } finally {
            setImporting(false);
        }
    };

    const setHeaderMapping = (header, field) => setMapping((m) => ({ ...m, [header]: field }));

    const requiredFields = (preview?.campi_target || []).filter((c) => c.required).map((c) => c.field);
    const mappedFields = new Set(Object.values(mapping).filter(Boolean));
    const missingRequired = requiredFields.filter((f) => !mappedFields.has(f));

    return (
        <div className="space-y-4" data-testid="targhe-importer">
            {/* Step 1: upload + selettore polizza */}
            <Card className="p-6" data-testid="lm-upload-card">
                <div className="flex items-center gap-3 mb-3">
                    <Car size={22} className="text-sky-700" />
                    <div>
                        <h3 className="font-medium text-slate-800">Import Libro Matricola / Stato di Rischio</h3>
                        <p className="text-xs text-slate-500">
                            Carica Excel/CSV. <strong>Targa</strong>, <strong>Data Inizio</strong> e <strong>Proprietario</strong> obbligatori. Gli altri campi sono opzionali.
                        </p>
                    </div>
                </div>

                {/* Selettore polizza */}
                {polizzaPreselezionata ? (
                    <div className="mb-3 p-2 bg-emerald-50 border border-emerald-200 rounded text-xs flex items-center gap-2" data-testid="lm-polizza-locked">
                        <CheckCircle2 size={14} className="text-emerald-600" />
                        <span className="text-emerald-900">
                            I veicoli verranno collegati alla polizza <strong>{polizzaPreselezionata.numero_polizza}</strong>
                        </span>
                    </div>
                ) : (
                    <div className="mb-3 relative">
                        <label className="text-xs text-slate-600 mb-1 block">
                            Collega a polizza esistente <span className="text-slate-400">(opzionale)</span>
                        </label>
                        {polizzaSel ? (
                            <div className="flex items-center gap-2 text-sm bg-sky-50 border border-sky-200 rounded px-2 py-1.5" data-testid="lm-polizza-selected">
                                <Car size={13} className="text-sky-700" />
                                <span className="font-mono text-sky-900">{polizzaSel.numero_polizza}</span>
                                <span className="text-slate-600 text-xs">{polizzaSel.ramo}</span>
                                <button
                                    type="button"
                                    onClick={() => { setPolizzaSel(null); setPolizzaId(""); setPolizzaQuery(""); }}
                                    className="ml-auto text-rose-600 hover:text-rose-800"
                                    data-testid="lm-polizza-clear"
                                >
                                    <X size={14} />
                                </button>
                            </div>
                        ) : (
                            <>
                                <input
                                    type="text"
                                    value={polizzaQuery}
                                    onChange={(e) => setPolizzaQuery(e.target.value)}
                                    placeholder="Cerca per numero polizza o contraente…"
                                    className="w-full border rounded px-3 py-1.5 text-sm bg-white"
                                    data-testid="lm-polizza-search"
                                />
                                {polizzeMatch.length > 0 && (
                                    <div className="absolute z-10 mt-1 w-full bg-white border rounded shadow-lg max-h-60 overflow-y-auto">
                                        {polizzeMatch.map((p) => (
                                            <button
                                                key={p.id}
                                                type="button"
                                                onClick={() => {
                                                    setPolizzaSel(p);
                                                    setPolizzaId(p.id);
                                                    setPolizzaQuery(p.numero_polizza || "");
                                                    setPolizzeMatch([]);
                                                }}
                                                className="block w-full text-left px-3 py-2 hover:bg-sky-50 text-xs border-b last:border-0"
                                                data-testid={`lm-polizza-opt-${p.id}`}
                                            >
                                                <div className="font-mono text-slate-800">{p.numero_polizza}</div>
                                                <div className="text-slate-500">
                                                    {p.ramo} · {p.contraente?.ragione_sociale || p.contraente?.nome || ""}
                                                </div>
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </>
                        )}
                    </div>
                )}

                <div className="flex items-center gap-2 flex-wrap">
                    <input
                        ref={inputRef}
                        type="file"
                        accept=".xlsx,.xlsm,.csv"
                        className="hidden"
                        onChange={(e) => onSelectFile(e.target.files?.[0] || null)}
                        data-testid="lm-file-input"
                    />
                    <Button variant="outline" onClick={() => inputRef.current?.click()} data-testid="lm-select-btn">
                        <Upload size={14} className="mr-1" />
                        {file ? file.name : "Seleziona Excel/CSV"}
                    </Button>
                    <Button onClick={doPreview} disabled={!file} className="bg-sky-700 hover:bg-sky-800" data-testid="lm-preview-btn">
                        Anteprima & Mapping
                    </Button>
                </div>
            </Card>

            {/* Step 2: mapping */}
            {preview && (
                <Card className="p-5" data-testid="lm-mapping-card">
                    <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                        <div>
                            <h3 className="font-medium text-slate-800">Mappa le colonne del file</h3>
                            <p className="text-xs text-slate-500">
                                {preview.total_rows} righe · {preview.headers.length} colonne
                                {polizzaSel && <> · veicoli collegati a <strong>{polizzaSel.numero_polizza}</strong></>}
                            </p>
                        </div>
                        {missingRequired.length > 0 ? (
                            <div className="text-xs text-rose-700 bg-rose-50 border border-rose-200 px-2 py-1 rounded">
                                Mancano obbligatori: {missingRequired.join(", ")}
                            </div>
                        ) : (
                            <div className="text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-1 rounded">
                                ✓ Tutti gli obbligatori mappati
                            </div>
                        )}
                    </div>
                    <div className="max-h-[420px] overflow-y-auto border rounded">
                        <table className="data-table w-full text-xs">
                            <thead className="sticky top-0 bg-slate-50">
                                <tr><th>Colonna file</th><th>Esempio valore</th><th>Mappa a → campo</th></tr>
                            </thead>
                            <tbody>
                                {preview.headers.map((h, i) => {
                                    const example = (preview.preview_rows?.[0]?.[i] ?? "").toString().slice(0, 40);
                                    return (
                                        <tr key={h + i} data-testid={`lm-row-${i}`}>
                                            <td className="font-medium text-slate-800">{h || `(col ${i + 1})`}</td>
                                            <td className="text-slate-500">{example || "—"}</td>
                                            <td>
                                                <select
                                                    value={mapping[h] || ""}
                                                    onChange={(e) => setHeaderMapping(h, e.target.value)}
                                                    className="w-full border rounded px-2 py-1 bg-white text-xs"
                                                    data-testid={`lm-select-${i}`}
                                                >
                                                    <option value="">— Ignora colonna —</option>
                                                    {(preview.campi_target || []).map((c) => (
                                                        <option key={c.field} value={c.field}>
                                                            {c.label}{c.required ? " *" : ""}
                                                        </option>
                                                    ))}
                                                </select>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                    <div className="flex items-center justify-end gap-2 mt-3">
                        <Button variant="ghost" onClick={() => { setPreview(null); setFile(null); }}>Annulla</Button>
                        <Button
                            onClick={doCommit}
                            disabled={importing || missingRequired.length > 0}
                            className="bg-sky-700 hover:bg-sky-800"
                            data-testid="lm-commit-btn"
                        >
                            {importing
                                ? "Importazione..."
                                : `Importa ${preview.total_rows} veicoli${polizzaSel ? " su polizza" : ""}`}
                        </Button>
                    </div>
                </Card>
            )}

            {/* Step 3: result */}
            {result && (
                <Card className="p-5 border-l-4 border-l-emerald-500" data-testid="lm-result-card">
                    <div className="flex items-center gap-2 mb-3">
                        <CheckCircle2 size={18} className="text-emerald-600" />
                        <div className="font-medium text-slate-900">Import completato</div>
                        {polizzaSel && (
                            <div className="text-xs text-emerald-700 ml-auto">
                                Collegati a polizza <strong>{polizzaSel.numero_polizza}</strong>
                            </div>
                        )}
                    </div>
                    <div className="grid grid-cols-4 gap-3 text-sm">
                        <Stat label="Totale" value={result.totale} />
                        <Stat label="Creati" value={result.creati} />
                        <Stat label="Aggiornati" value={result.aggiornati} />
                        <Stat label="Scartati" value={result.scartati} />
                    </div>
                    {result.errori?.length > 0 && (
                        <div className="mt-3">
                            <div className="text-xs font-semibold text-rose-700 mb-1">Errori:</div>
                            <ul className="text-xs text-rose-800 list-disc pl-5 max-h-32 overflow-y-auto">
                                {result.errori.slice(0, 20).map((e, i) => <li key={i}>{e}</li>)}
                            </ul>
                        </div>
                    )}
                    <p className="text-xs text-slate-500 mt-3">
                        Digitando la <strong>targa</strong> nelle nuove polizze si potranno richiamare automaticamente i dati.
                    </p>
                </Card>
            )}
        </div>
    );
}
