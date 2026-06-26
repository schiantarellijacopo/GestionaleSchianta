/**
 * Pagina "Importazioni Flussi" — gestione di tutti i flussi di importazione.
 *
 * Tab:
 *  - OMNIA: ZIP ANIA giornaliero (anagrafiche, polizze, titoli, sinistri, garanzie)
 *  - Targhe / Libri Matricola: CSV con mapping manuale delle colonne
 *
 * UX changes (iter23):
 *  - Pulsante "Importa" esplicito (no auto-start dopo selezione file)
 *  - Report dettagliato post-import: cosa è entrato + cosa è stato saltato
 *  - Avviso entità non mappate (compagnia/ramo/collaboratore nuove)
 */
import { useEffect, useState, useRef } from "react";
import { api, fmtDate } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
    Upload, FileArchive, CheckCircle2, AlertCircle, Clock,
    AlertTriangle, FileText, Car,
} from "lucide-react";
import { toast } from "sonner";


export default function Importazioni() {
    const [tab, setTab] = useState("omnia");
    return (
        <div data-testid="importazioni-page">
            <PageHeader
                title="Importazioni Flussi"
                subtitle="Carica i tracciati delle compagnie. Più flussi supportati: OMNIA (ZIP ANIA) + Targhe/Libri matricola (CSV con mapping)."
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
            {tab === "omnia" && <ImportOmnia />}
            {tab === "targhe" && <ImportTargheStub />}
            {tab === "storico" && <Storico />}
        </div>
    );
}


// ============================================================
// OMNIA — ZIP ANIA
// ============================================================
function ImportOmnia() {
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
            {lastLog && <ImportReport log={lastLog} />}
        </div>
    );
}


// ============================================================
// REPORT DETTAGLIATO POST-IMPORT
// ============================================================
function ImportReport({ log }) {
    const skipped = log.record_skipped || [];
    const non_mappate = log.entita_non_mappate || {};
    const ha_non_mappate = Object.keys(non_mappate).some((k) => (non_mappate[k] || []).length > 0);

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

            {ha_non_mappate && (
                <Card className="p-5 border-l-4 border-l-amber-500 bg-amber-50/40" data-testid="non-mappate-card">
                    <div className="flex items-center gap-2 mb-2">
                        <AlertTriangle size={18} className="text-amber-600" />
                        <div className="font-medium text-amber-900">Entità non mappate ({sumLen(non_mappate)})</div>
                    </div>
                    <p className="text-sm text-amber-800 mb-3">
                        Le seguenti entità sono apparse nel flusso ma non sono ancora collegate
                        a un'entità del programma. Mappa ciascuna alla corrispondente per averle
                        gestite automaticamente al prossimo import.
                    </p>
                    {["compagnie", "rami", "collaboratori", "prodotti"].map((tipo) => {
                        const items = non_mappate[tipo] || [];
                        if (!items.length) return null;
                        return (
                            <div key={tipo} className="mb-3" data-testid={`non-mappate-${tipo}`}>
                                <div className="text-xs uppercase font-semibold text-amber-700 mb-1.5">{tipo}</div>
                                <div className="flex flex-wrap gap-1.5">
                                    {items.map((v) => (
                                        <span key={v} className="text-xs bg-white border border-amber-300 text-amber-900 px-2 py-1 rounded">
                                            {v}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        );
                    })}
                    <p className="text-[11px] text-amber-700 mt-2">
                        💡 Wizard mapping interattivo in arrivo — per ora puoi creare manualmente le entità mancanti in Compagnie / Anagrafiche / Librerie.
                    </p>
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

function sumLen(obj) {
    return Object.values(obj || {}).reduce((s, arr) => s + (arr?.length || 0), 0);
}


// ============================================================
// STORICO
// ============================================================
function Storico() {
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
                    <ImportReport log={details} />
                    <Button variant="outline" onClick={() => setDetails(null)} className="mt-3">Chiudi dettaglio</Button>
                </div>
            )}
        </div>
    );
}


// ============================================================
// IMPORT TARGHE / LIBRI MATRICOLA (skeleton fase 2)
// ============================================================
function ImportTargheStub() {
    return (
        <Card className="p-6 text-center" data-testid="targhe-stub">
            <Car size={36} className="mx-auto text-slate-400 mb-3" />
            <h3 className="font-medium text-slate-800 mb-2">Importazione Targhe / Libri Matricola</h3>
            <p className="text-sm text-slate-600 max-w-lg mx-auto">
                In arrivo — carica un CSV con qualsiasi struttura colonne (targa, libro matricola, polizza, scadenze, ecc.)
                e mappa manualmente ciascuna colonna alle corrispondenti del programma.
            </p>
            <div className="mt-4 inline-flex items-center gap-1 text-[11px] text-slate-500 bg-slate-100 px-2 py-1 rounded">
                <Clock size={11} /> Disponibile prossima release
            </div>
        </Card>
    );
}
