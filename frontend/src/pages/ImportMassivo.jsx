/**
 * Import Massivo Intelligente — multi-file Excel/CSV con mapping AI (Claude Sonnet).
 * Migra Anagrafiche + Polizze + Titoli/Quietanze + Sinistri (con metodi di pagamento).
 * Deduplica per CF/P.IVA / numero polizza (+ fuzzy nome). Duplicati → aggiorna campi vuoti.
 */
import { useState, useRef, useEffect } from "react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
    UploadCloud, FileSpreadsheet, Sparkles, Wand2, CheckCircle2,
    AlertTriangle, X, ArrowRight, Loader2, Users, FileText, Receipt, ShieldAlert, Download,
} from "lucide-react";
import { toast } from "sonner";

const ENTITY_FIELDS = {
    anagrafica: { tipo: "Tipo", ragione_sociale: "Ragione sociale/Nome", nome: "Nome", cognome: "Cognome", codice_fiscale: "Codice fiscale", partita_iva: "Partita IVA", data_nascita: "Data nascita", sesso: "Sesso", indirizzo: "Indirizzo", comune: "Comune", provincia: "Provincia", cap: "CAP", telefono: "Telefono", cellulare: "Cellulare", email: "Email", iban: "IBAN", professione: "Professione", note: "Note", preferenza_pagamento: "Metodo pagamento" },
    polizza: { numero_polizza: "Numero polizza", compagnia_nome: "Compagnia", contraente_cf: "CF/P.IVA contraente", contraente_nome: "Nome contraente", ramo: "Ramo", prodotto: "Prodotto", stato: "Stato", effetto: "Effetto", scadenza: "Scadenza", frazionamento: "Frazionamento", premio_lordo: "Premio lordo", premio_netto: "Premio netto", premio_tasse: "Imposte", premio_ssn: "SSN", provvigioni: "Provvigioni", targa: "Targa", mezzo_pagamento_preferito: "Metodo pagamento", note: "Note" },
    titolo: { numero_polizza: "Numero polizza", numero_titolo: "Numero titolo", tipo: "Tipo", effetto: "Effetto", scadenza: "Scadenza", stato: "Stato", importo_lordo: "Importo lordo", importo_netto: "Importo netto", imposte: "Imposte", provvigioni: "Provvigioni", data_incasso: "Data incasso", mezzo_pagamento: "Metodo pagamento", note: "Note" },
    sinistro: { numero_sinistro: "Numero sinistro", numero_polizza: "Numero polizza", contraente_cf: "CF/P.IVA contraente", contraente_nome: "Nome contraente", compagnia_nome: "Compagnia", data_avvenimento: "Data avvenimento", data_denuncia: "Data denuncia", ramo: "Ramo", stato: "Stato", descrizione: "Descrizione", riserva: "Riserva", liquidazione: "Liquidazione", note: "Note" },
};
const ENTITY_META = {
    anagrafica: { label: "Anagrafica", Icon: Users, tone: "bg-sky-100 text-sky-700" },
    polizza: { label: "Polizza", Icon: FileText, tone: "bg-violet-100 text-violet-700" },
    titolo: { label: "Titolo/Quietanza", Icon: Receipt, tone: "bg-emerald-100 text-emerald-700" },
    sinistro: { label: "Sinistro", Icon: ShieldAlert, tone: "bg-rose-100 text-rose-700" },
};
const NONE = "__none__";

export default function ImportMassivo() {
    const [session, setSession] = useState(null);
    const [uploading, setUploading] = useState(false);
    const [committing, setCommitting] = useState(false);
    const [progress, setProgress] = useState(null);
    const [result, setResult] = useState(null);
    const fileRef = useRef(null);
    const pollRef = useRef(null);

    useEffect(() => () => clearInterval(pollRef.current), []);

    const onFiles = async (fileList) => {
        const files = Array.from(fileList || []);
        if (!files.length) return;
        const fd = new FormData();
        files.forEach((f) => fd.append("files", f));
        setUploading(true);
        setResult(null); setProgress(null);
        try {
            const r = await api.post("/import-massivo/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
            setSession(r.data);
            toast.success(`${(r.data.files || []).length} file analizzati con l'AI`);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore durante l'analisi dei file");
        } finally {
            setUploading(false);
        }
    };

    const updateFile = (fi, patch) => {
        setSession((s) => ({
            ...s,
            files: s.files.map((f) => (f.file_index === fi ? { ...f, ...patch } : f)),
        }));
    };
    const setEntity = (fi, entity) => {
        // reset mapping non compatibile con la nuova entità
        const valid = new Set(Object.keys(ENTITY_FIELDS[entity] || {}));
        updateFile(fi, {
            entity,
            mapping: Object.fromEntries((session.files.find((f) => f.file_index === fi)?.headers || []).map((h) => {
                const cur = session.files.find((f) => f.file_index === fi)?.mapping?.[h];
                return [h, valid.has(cur) ? cur : null];
            })),
        });
    };
    const setMap = (fi, header, field) => {
        const f = session.files.find((x) => x.file_index === fi);
        updateFile(fi, { mapping: { ...f.mapping, [header]: field === NONE ? null : field } });
    };

    const commit = async () => {
        if (!session) return;
        const plan = session.files
            .filter((f) => !f.error && f.entity)
            .map((f) => ({ file_index: f.file_index, entity: f.entity, mapping: f.mapping }));
        if (!plan.length) { toast.error("Nessun file valido da importare"); return; }
        setCommitting(true);
        try {
            const r = await api.post(`/import-massivo/${session.id}/commit`, { plan });
            setProgress({ fase: "avvio", totale: r.data.totale_righe, elaborate: 0, creati: 0, aggiornati: 0, saltati: 0, errori: 0 });
            let fails = 0;
            pollRef.current = setInterval(async () => {
                try {
                    const st = await api.get(`/import-massivo/${session.id}/status`);
                    fails = 0;
                    setProgress(st.data.progress);
                    if (st.data.status === "completato") {
                        clearInterval(pollRef.current);
                        setResult(st.data.result);
                        setCommitting(false);
                        {
                            const rr = st.data.result || {};
                            toast.success(
                                `Importazione completata · ${rr.creati || 0} creati, ${rr.aggiornati || 0} aggiornati, ${rr.saltati || 0} saltati, ${rr.errori || 0} errori`,
                                { duration: 8000 });
                        }
                    } else if (st.data.status === "errore") {
                        clearInterval(pollRef.current);
                        setResult(st.data.result || { errore: "Errore sconosciuto" });
                        setCommitting(false);
                        toast.error("Importazione interrotta da un errore");
                    }
                } catch {
                    if (++fails >= 5) {
                        clearInterval(pollRef.current);
                        setCommitting(false);
                        toast.error("Interrotto: impossibile leggere lo stato dell'importazione");
                    }
                }
            }, 1200);
        } catch (e) {
            setCommitting(false);
            toast.error(e.response?.data?.detail || "Errore avvio importazione");
        }
    };

    const reset = () => { setSession(null); setResult(null); setProgress(null); clearInterval(pollRef.current); };

    // ---- RISULTATO ----
    if (result) {
        const errs = result.errori_dettaglio || [];
        const errTot = result.errori_dettaglio_totali ?? errs.length;
        const scaricaCsv = () => {
            const head = "riga;entita;motivo\n";
            const body = errs.map((e) => `${e.row};${e.entity};"${String(e.reason || "").replace(/"/g, "'")}"`).join("\n");
            const blob = new Blob(["\ufeff" + head + body], { type: "text/csv;charset=utf-8" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `righe_non_importate_${new Date().toISOString().slice(0, 10)}.csv`;
            a.click();
            URL.revokeObjectURL(url);
        };
        return (
            <Card className="p-6" data-testid="import-massivo-result">
                {result.errore ? (
                    <div className="flex items-center gap-2 mb-4">
                        <AlertTriangle className="text-rose-600" size={22} />
                        <h3 className="text-lg font-semibold text-rose-700">Importazione interrotta</h3>
                    </div>
                ) : (
                    <div className="flex items-center gap-2 mb-4">
                        <CheckCircle2 className="text-emerald-600" size={22} />
                        <h3 className="text-lg font-semibold">Importazione completata</h3>
                    </div>
                )}
                {result.errore && (
                    <div className="bg-rose-50 border border-rose-200 rounded-lg px-3 py-2 text-sm text-rose-700 mb-4" data-testid="import-massivo-errore">
                        {result.errore}
                    </div>
                )}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                    <StatBox label="Creati" value={result.creati} tone="text-emerald-700" />
                    <StatBox label="Aggiornati" value={result.aggiornati} tone="text-sky-700" />
                    <StatBox label="Saltati" value={result.saltati} tone="text-slate-500" />
                    <StatBox label="Errori" value={result.errori} tone="text-rose-700" />
                </div>
                {result.auto_creati && Object.values(result.auto_creati_totali || {}).some((n) => n > 0) && (
                    <div className="border border-emerald-200 rounded-lg overflow-hidden mb-4" data-testid="import-massivo-autocreati">
                        <div className="bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700">
                            Creati automaticamente
                        </div>
                        <div className="p-3 space-y-2 text-xs">
                            {[
                                ["polizze_da_titolo", "Polizze create dai titoli"],
                                ["compagnie", "Compagnie"],
                                ["mezzi_pagamento", "Metodi di pagamento"],
                                ["banche", "Banche"],
                                ["collaboratori", "Collaboratori/Operatori (da completare in Librerie)"],
                            ].filter(([k]) => (result.auto_creati_totali?.[k] || 0) > 0).map(([k, label]) => (
                                <div key={k} data-testid={`autocreati-${k}`}>
                                    <span className="font-medium text-slate-700">{label} ({result.auto_creati_totali[k]}):</span>{" "}
                                    <span className="text-slate-500">{(result.auto_creati[k] || []).slice(0, 30).join(", ")}{(result.auto_creati_totali[k] > 30) ? "…" : ""}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
                {errs.length > 0 && (
                    <div className="border border-rose-200 rounded-lg overflow-hidden mb-4" data-testid="import-massivo-errori-report">
                        <div className="bg-rose-50 px-3 py-2 flex items-center justify-between">
                            <span className="text-xs font-semibold text-rose-700">
                                Righe non importate — motivo{" "}
                                {errTot > errs.length ? `(mostrate ${errs.length} di ${errTot})` : `(${errs.length})`}
                            </span>
                            <Button size="sm" variant="outline" onClick={scaricaCsv} className="h-7 text-xs gap-1" data-testid="import-massivo-scarica-csv">
                                <Download size={13} /> Scarica CSV
                            </Button>
                        </div>
                        <div className="max-h-60 overflow-y-auto divide-y divide-slate-100 text-xs">
                            {errs.map((e, i) => (
                                <div key={i} className="px-3 py-1.5 flex gap-3" data-testid={`import-err-${i}`}>
                                    <span className="text-slate-400 shrink-0">riga {e.row}</span>
                                    <Badge variant="outline" className="text-[10px] shrink-0">{e.entity}</Badge>
                                    <span className="text-rose-600">{e.reason}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
                <Button onClick={reset} data-testid="import-massivo-new">Nuova importazione</Button>
            </Card>
        );
    }

    // ---- PROGRESSO ----
    if (committing || progress) {
        const pct = progress?.totale ? Math.round((progress.elaborate / progress.totale) * 100) : 0;
        return (
            <Card className="p-6" data-testid="import-massivo-progress">
                <div className="flex items-center gap-2 mb-4">
                    <Loader2 className="animate-spin text-sky-600" size={20} />
                    <h3 className="text-lg font-semibold">Importazione in corso — {progress?.fase}</h3>
                </div>
                <Progress value={pct} className="mb-2" />
                <div className="text-sm text-slate-500 mb-4">{progress?.elaborate || 0} / {progress?.totale || 0} righe ({pct}%)</div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <StatBox label="Creati" value={progress?.creati || 0} tone="text-emerald-700" />
                    <StatBox label="Aggiornati" value={progress?.aggiornati || 0} tone="text-sky-700" />
                    <StatBox label="Saltati" value={progress?.saltati || 0} tone="text-slate-500" />
                    <StatBox label="Errori" value={progress?.errori || 0} tone="text-rose-700" />
                </div>
            </Card>
        );
    }

    // ---- UPLOAD + MAPPING ----
    return (
        <div className="space-y-4" data-testid="import-massivo-page">
            <Card className="p-5 bg-gradient-to-br from-slate-50 to-white border-dashed border-2">
                <div className="flex items-start gap-3">
                    <div className="p-2.5 rounded-xl bg-violet-100"><Sparkles className="text-violet-600" size={20} /></div>
                    <div className="flex-1">
                        <h3 className="font-semibold text-slate-800">Import Massivo Intelligente</h3>
                        <p className="text-sm text-slate-500 mt-0.5">
                            Carica più file Excel/CSV insieme (clienti, polizze, titoli, sinistri). L'AI riconosce
                            automaticamente il tipo di dato e mappa le colonne. I duplicati aggiornano i campi mancanti.
                        </p>
                    </div>
                </div>
                <div
                    className="mt-4 border-2 border-dashed border-slate-300 rounded-xl p-8 text-center cursor-pointer hover:border-violet-400 hover:bg-violet-50/40 transition-colors"
                    onClick={() => fileRef.current?.click()}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => { e.preventDefault(); onFiles(e.dataTransfer.files); }}
                    data-testid="import-massivo-dropzone"
                >
                    {uploading ? (
                        <div className="flex flex-col items-center gap-2 text-slate-500">
                            <Loader2 className="animate-spin" size={28} />
                            <span className="text-sm">Analisi AI dei file in corso…</span>
                        </div>
                    ) : (
                        <div className="flex flex-col items-center gap-2 text-slate-500">
                            <UploadCloud size={32} className="text-violet-500" />
                            <span className="text-sm font-medium">Trascina qui i file o clicca per selezionarli</span>
                            <span className="text-xs text-slate-400">.xlsx · .xls · .csv — anche più file insieme</span>
                        </div>
                    )}
                    <input
                        ref={fileRef} type="file" multiple accept=".xlsx,.xls,.xlsm,.csv" className="hidden"
                        onChange={(e) => onFiles(e.target.files)} data-testid="import-massivo-file-input"
                    />
                </div>
            </Card>

            {session && (session.files || []).map((f) => (
                <FileCard key={f.file_index} f={f} onEntity={setEntity} onMap={setMap} />
            ))}

            {session && (session.files || []).some((f) => !f.error) && (
                <div className="flex items-center justify-between sticky bottom-0 bg-white/90 backdrop-blur border-t py-3">
                    <Button variant="ghost" onClick={reset}><X size={14} className="mr-1" /> Annulla</Button>
                    <Button className="bg-violet-700 hover:bg-violet-800" onClick={commit} data-testid="import-massivo-commit">
                        Avvia importazione <ArrowRight size={14} className="ml-1.5" />
                    </Button>
                </div>
            )}
        </div>
    );
}

function FileCard({ f, onEntity, onMap }) {
    const [open, setOpen] = useState(true);
    if (f.error) {
        return (
            <Card className="p-4 border-rose-200" data-testid={`file-card-${f.file_index}`}>
                <div className="flex items-center gap-2 text-rose-600 text-sm">
                    <AlertTriangle size={16} /> <strong>{f.filename}</strong> — {f.error}
                </div>
            </Card>
        );
    }
    const meta = ENTITY_META[f.entity] || ENTITY_META.anagrafica;
    const fields = ENTITY_FIELDS[f.entity] || {};
    const mappedCount = Object.values(f.mapping || {}).filter(Boolean).length;
    return (
        <Card className="p-4" data-testid={`file-card-${f.file_index}`}>
            <div className="flex items-center gap-3 flex-wrap">
                <FileSpreadsheet className="text-slate-400" size={20} />
                <div className="flex-1 min-w-[180px]">
                    <div className="font-medium text-slate-800 text-sm">{f.filename}</div>
                    <div className="text-xs text-slate-400">{f.total_rows} righe · {mappedCount}/{(f.headers || []).length} colonne mappate</div>
                </div>
                <Badge className={meta.tone}><meta.Icon size={12} className="mr-1" />{meta.label}</Badge>
                {f.mapping_source === "ai"
                    ? <Badge variant="outline" className="text-[10px] text-violet-700 border-violet-300"><Sparkles size={10} className="mr-1" />AI {Math.round((f.entity_confidence || 0) * 100)}%</Badge>
                    : <Badge variant="outline" className="text-[10px]"><Wand2 size={10} className="mr-1" />Euristica</Badge>}
                <Select value={f.entity} onValueChange={(v) => onEntity(f.file_index, v)}>
                    <SelectTrigger className="w-44 h-8 text-xs" data-testid={`file-entity-${f.file_index}`}><SelectValue /></SelectTrigger>
                    <SelectContent>
                        {Object.entries(ENTITY_META).map(([k, m]) => <SelectItem key={k} value={k}>{m.label}</SelectItem>)}
                    </SelectContent>
                </Select>
                <Button variant="ghost" size="sm" onClick={() => setOpen((o) => !o)}>{open ? "Nascondi" : "Mostra"} mapping</Button>
            </div>

            {open && (
                <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-2">
                    {(f.headers || []).map((h) => (
                        <div key={h} className="flex items-center gap-2">
                            <span className="text-xs text-slate-600 truncate flex-1" title={h}>{h}</span>
                            <ArrowRight size={12} className="text-slate-300 shrink-0" />
                            <Select value={f.mapping?.[h] || NONE} onValueChange={(v) => onMap(f.file_index, h, v)}>
                                <SelectTrigger className="w-44 h-7 text-xs shrink-0" data-testid={`map-${f.file_index}-${h}`}>
                                    <SelectValue placeholder="—" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value={NONE}>— Ignora —</SelectItem>
                                    {Object.entries(fields).map(([fk, fl]) => <SelectItem key={fk} value={fk}>{fl}</SelectItem>)}
                                </SelectContent>
                            </Select>
                        </div>
                    ))}
                </div>
            )}
        </Card>
    );
}

function StatBox({ label, value, tone = "text-slate-800" }) {
    return (
        <div className="bg-slate-50 border border-slate-200 rounded-lg px-3 py-2">
            <div className="text-[10px] uppercase tracking-wide text-slate-400">{label}</div>
            <div className={`text-2xl font-bold ${tone}`}>{value}</div>
        </div>
    );
}
