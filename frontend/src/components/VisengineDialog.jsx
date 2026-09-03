/**
 * VisengineDialog — selettore documenti Camerali / Patronato / INPS.
 * Flusso: 1) scelta documenti (tutti o alcuni) → 2) compilazione campi
 * (precompilati dai dati anagrafica + upload file richiesti) → 3) invio richieste.
 * Mostra anche lo storico delle richieste con stato e ricarica PDF.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { FileSearch, Loader2, Upload, RefreshCw, CheckCircle2, Clock, ChevronLeft } from "lucide-react";
import { toast } from "sonner";

const fileToVisengine = (file) =>
    new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(`${file.name}|${reader.result}`); // name|data:mime;base64,...
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });

export default function VisengineDialog({ ana, aid, onClose, onReload }) {
    const [step, setStep] = useState("select"); // select | compile | done
    const [gruppi, setGruppi] = useState({});
    const [selected, setSelected] = useState([]);       // [{hash, nome, categoria}]
    const [schemas, setSchemas] = useState({});         // hash → schema+campi
    const [values, setValues] = useState({});           // hash → {key: value}
    const [files, setFiles] = useState({});             // hash → {key: File}
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [results, setResults] = useState([]);

    const richieste = (ana.openapi_data?.visengine_richieste || []).slice().reverse();

    useEffect(() => {
        api.get("/openapi-it/visengine/catalog")
            .then((r) => setGruppi(r.data.gruppi || {}))
            .catch(() => toast.error("Errore caricamento catalogo"))
            .finally(() => setLoading(false));
    }, []);

    const isSelected = (hash) => selected.some((s) => s.hash === hash);
    const toggle = (doc) =>
        setSelected((p) => (isSelected(doc.hash) ? p.filter((s) => s.hash !== doc.hash) : [...p, doc]));

    const allDocs = Object.values(gruppi).flat();
    const allChecked = selected.length === allDocs.length && allDocs.length > 0;
    const toggleAll = () => setSelected(allChecked ? [] : [...allDocs]);

    const goCompile = async () => {
        if (selected.length === 0) { toast.error("Seleziona almeno un documento"); return; }
        setBusy(true);
        try {
            const newSchemas = { ...schemas };
            const newValues = { ...values };
            for (const doc of selected) {
                if (!newSchemas[doc.hash]) {
                    const r = await api.get(`/openapi-it/visengine/schema/${doc.hash}`, { params: { aid } });
                    newSchemas[doc.hash] = r.data;
                    newValues[doc.hash] = {};
                    (r.data.campi || []).forEach((c) => { newValues[doc.hash][c.key] = c.value || ""; });
                }
            }
            setSchemas(newSchemas);
            setValues(newValues);
            setStep("compile");
        } catch (e) {
            toast.error("Errore lettura struttura documenti");
        } finally { setBusy(false); }
    };

    const setVal = (hash, key, v) =>
        setValues((p) => ({ ...p, [hash]: { ...p[hash], [key]: v } }));
    const setFile = (hash, key, f) =>
        setFiles((p) => ({ ...p, [hash]: { ...p[hash], [key]: f } }));

    const totalePrezzo = selected.reduce((s, d) => s + (schemas[d.hash]?.prezzo_visura || 0), 0);

    const invia = async () => {
        setBusy(true);
        const out = [];
        try {
            for (const doc of selected) {
                const schema = schemas[doc.hash];
                const jv = {};
                let missing = false;
                for (const c of schema.campi || []) {
                    if (c.is_file) {
                        const f = files[doc.hash]?.[c.key];
                        if (f) jv[c.key] = await fileToVisengine(f);
                        else if (c.required) missing = true;
                    } else {
                        const v = (values[doc.hash]?.[c.key] || "").trim();
                        if (v) jv[c.key] = v;
                        else if (c.required) missing = true;
                    }
                }
                if (missing) {
                    out.push({ nome: doc.nome, ok: false, msg: "Campi/allegati obbligatori mancanti" });
                    continue;
                }
                try {
                    const r = await api.post(`/openapi-it/visengine/request/${aid}`, {
                        hash_visura: doc.hash, nome_visura: doc.nome, json_visura: jv,
                    });
                    out.push({ nome: doc.nome, ok: true, stato: r.data.stato, saved: !!r.data.allegato_id });
                } catch (e) {
                    out.push({ nome: doc.nome, ok: false, msg: e.response?.data?.detail || "Errore" });
                }
            }
            setResults(out);
            setStep("done");
            onReload?.();
        } finally { setBusy(false); }
    };

    const refresh = async (rid) => {
        try {
            const r = await api.post(`/openapi-it/visengine/refresh/${aid}/${rid}`);
            if (r.data.allegato_id) toast.success("PDF pronto e salvato negli Allegati");
            else toast.info(`Stato: ${r.data.stato}`);
            onReload?.();
        } catch (e) { toast.error("Errore aggiornamento"); }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-3xl max-h-[88vh] overflow-y-auto" data-testid="visengine-dialog">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <FileSearch size={18} className="text-sky-700" />
                        Visure & Documenti (Camerali / Patronato)
                    </DialogTitle>
                    <DialogDescription>
                        Scegli e richiedi documenti ufficiali (Camera di Commercio, INPS/Patronato) per questa anagrafica.
                    </DialogDescription>
                </DialogHeader>

                {loading ? (
                    <div className="py-10 text-center text-slate-400"><Loader2 className="animate-spin inline" /> Caricamento…</div>
                ) : step === "select" ? (
                    <div className="space-y-3">
                        <div className="text-xs text-slate-600 bg-sky-50 border border-sky-200 rounded p-2">
                            Scegli <b>tutti</b> i documenti o <b>solo alcuni</b>. Ogni documento ha un costo indicato nella schermata successiva.
                        </div>
                        <label className="flex items-center gap-2 text-sm font-medium cursor-pointer border-b pb-2">
                            <Checkbox checked={allChecked} onCheckedChange={toggleAll} data-testid="visengine-select-all" />
                            Seleziona tutti
                        </label>
                        {Object.entries(gruppi).map(([cat, docs]) => (
                            <div key={cat}>
                                <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-1">{cat}</div>
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                                    {docs.map((doc) => (
                                        <label key={doc.hash}
                                            className={`flex items-center gap-2 border rounded px-2.5 py-2 text-sm cursor-pointer transition-colors ${isSelected(doc.hash) ? "border-sky-400 bg-sky-50/60" : "border-slate-200 hover:bg-slate-50"}`}
                                            data-testid={`visengine-doc-${doc.hash}`}>
                                            <Checkbox checked={isSelected(doc.hash)} onCheckedChange={() => toggle(doc)} />
                                            {doc.nome}
                                        </label>
                                    ))}
                                </div>
                            </div>
                        ))}
                    </div>
                ) : step === "compile" ? (
                    <div className="space-y-4">
                        <button onClick={() => setStep("select")} className="text-xs text-sky-700 flex items-center gap-1">
                            <ChevronLeft size={13} /> Torna alla selezione
                        </button>
                        {selected.map((doc) => {
                            const schema = schemas[doc.hash];
                            return (
                                <div key={doc.hash} className="border border-slate-200 rounded p-3">
                                    <div className="flex items-center justify-between mb-2">
                                        <div className="font-medium text-sm">{doc.nome}</div>
                                        {schema.prezzo_visura != null && (
                                            <span className="text-xs text-emerald-700 font-medium">€ {Number(schema.prezzo_visura).toFixed(2)}</span>
                                        )}
                                    </div>
                                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                        {(schema.campi || []).map((c) => (
                                            <div key={c.key} className={c.is_file ? "sm:col-span-2" : ""}>
                                                <Label className="text-xs flex items-center gap-1">
                                                    {c.nome}{c.required && <span className="text-rose-500">*</span>}
                                                </Label>
                                                {c.is_file ? (
                                                    <div className="flex items-center gap-2">
                                                        <Input type="file" className="text-xs"
                                                            onChange={(e) => setFile(doc.hash, c.key, e.target.files?.[0])}
                                                            data-testid={`visengine-file-${doc.hash}-${c.key}`} />
                                                        {files[doc.hash]?.[c.key] && <CheckCircle2 size={14} className="text-emerald-600" />}
                                                    </div>
                                                ) : (
                                                    <Input value={values[doc.hash]?.[c.key] || ""}
                                                        onChange={(e) => setVal(doc.hash, c.key, e.target.value)}
                                                        placeholder={c.istruzioni}
                                                        data-testid={`visengine-field-${doc.hash}-${c.key}`} />
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                    {(schema.campi || []).some((c) => c.is_file) && (
                                        <div className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded p-1.5 mt-2 flex items-center gap-1">
                                            <Upload size={11} /> Questo documento richiede allegati (documento identità / tessera sanitaria / mandato).
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                        <div className="text-sm text-right font-medium">Totale stimato: <span className="text-emerald-700">€ {totalePrezzo.toFixed(2)}</span></div>
                    </div>
                ) : (
                    <div className="space-y-2">
                        <div className="text-sm font-medium">Esito richieste</div>
                        {results.map((r, i) => (
                            <div key={i} className={`text-sm border rounded p-2 flex items-center gap-2 ${r.ok ? "border-emerald-200 bg-emerald-50" : "border-rose-200 bg-rose-50"}`}>
                                {r.ok ? <CheckCircle2 size={15} className="text-emerald-600" /> : <span className="text-rose-600">✕</span>}
                                <span className="font-medium">{r.nome}</span>
                                <span className="text-xs text-slate-600 ml-auto">
                                    {r.ok ? (r.saved ? "PDF salvato ✓" : `Inviata (${r.stato})`) : r.msg}
                                </span>
                            </div>
                        ))}
                    </div>
                )}

                {/* Storico richieste */}
                {richieste.length > 0 && step !== "compile" && (
                    <div className="border-t pt-3 mt-2">
                        <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-1">Richieste inviate</div>
                        <div className="space-y-1 max-h-40 overflow-y-auto">
                            {richieste.map((r) => (
                                <div key={r.id} className="flex items-center gap-2 text-xs border border-slate-200 rounded px-2 py-1.5">
                                    {r.allegato_id ? <CheckCircle2 size={13} className="text-emerald-600" /> : <Clock size={13} className="text-amber-600" />}
                                    <span className="font-medium truncate flex-1">{r.nome_visura}</span>
                                    <span className="text-slate-500">{r.allegato_id ? "PDF salvato" : r.stato}</span>
                                    {!r.allegato_id && (
                                        <Button size="sm" variant="ghost" className="h-6 px-1.5" onClick={() => refresh(r.id)} data-testid={`visengine-refresh-${r.id}`}>
                                            <RefreshCw size={11} />
                                        </Button>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                <DialogFooter>
                    {step === "select" && (
                        <>
                            <Button variant="outline" onClick={onClose}>Chiudi</Button>
                            <Button onClick={goCompile} disabled={busy || selected.length === 0}
                                className="bg-sky-700 hover:bg-sky-800" data-testid="visengine-next-btn">
                                {busy ? <Loader2 size={14} className="animate-spin mr-1" /> : null}
                                Avanti ({selected.length})
                            </Button>
                        </>
                    )}
                    {step === "compile" && (
                        <>
                            <Button variant="outline" onClick={() => setStep("select")}>Indietro</Button>
                            <Button onClick={invia} disabled={busy} className="bg-emerald-600 hover:bg-emerald-700" data-testid="visengine-submit-btn">
                                {busy ? <Loader2 size={14} className="animate-spin mr-1" /> : null}
                                Richiedi documenti
                            </Button>
                        </>
                    )}
                    {step === "done" && (
                        <Button onClick={onClose} className="bg-sky-700 hover:bg-sky-800">Chiudi</Button>
                    )}
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
