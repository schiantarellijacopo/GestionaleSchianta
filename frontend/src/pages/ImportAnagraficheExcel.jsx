/**
 * ImportAnagraficheExcel — wizard Excel/CSV import per Anagrafiche.
 *
 * Step:
 *  1. Upload file (.xlsx / .csv)
 *  2. Preview + mapping auto-detected (utente può correggere ogni colonna)
 *  3. Scelta policy duplicati (skip / overwrite / create_only)
 *  4. Execute → report
 */
import { useRef, useState, useMemo } from "react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Upload, FileSpreadsheet, ArrowRight, CheckCircle2, AlertCircle, Sparkles, RefreshCw } from "lucide-react";
import { toast } from "sonner";

const POLICY_LABEL = {
    skip: "Salta duplicati (default)",
    overwrite: "Sovrascrivi duplicati esistenti",
    create_only: "Crea sempre (anche duplicati) — SCONSIGLIATO",
};

export default function ImportAnagraficheExcel() {
    const [file, setFile] = useState(null);
    const [step, setStep] = useState("upload"); // "upload" | "preview" | "done"
    const [preview, setPreview] = useState(null); // dati dal /preview
    const [mapping, setMapping] = useState({}); // { header: canonical | "__ignore__" }
    const [policy, setPolicy] = useState("skip");
    const [busy, setBusy] = useState(false);
    const [report, setReport] = useState(null);
    const inputRef = useRef(null);

    const availableFields = preview?.available_fields || [];

    const doPreview = async () => {
        if (!file) { toast.error("Seleziona un file .xlsx o .csv"); return; }
        setBusy(true);
        const fd = new FormData();
        fd.append("file", file);
        try {
            const r = await api.post("/import/anagrafiche/preview", fd, {
                headers: { "Content-Type": "multipart/form-data" },
                timeout: 60000,
            });
            setPreview(r.data);
            // Inizializza mapping con auto-detection
            const init = {};
            (r.data.detected || []).forEach((d) => {
                init[d.header] = d.canonical || "__ignore__";
            });
            setMapping(init);
            setStep("preview");
        } catch (e) {
            toast.error("Errore anteprima: " + (e.response?.data?.detail || e.message));
        } finally {
            setBusy(false);
        }
    };

    const doExecute = async () => {
        setBusy(true);
        // Filtra mapping: rimuovi campi "__ignore__"
        const clean = {};
        Object.entries(mapping).forEach(([h, c]) => {
            if (c && c !== "__ignore__") clean[h] = c;
        });
        if (Object.keys(clean).length === 0) {
            toast.error("Devi mappare almeno una colonna");
            setBusy(false);
            return;
        }
        const fd = new FormData();
        fd.append("file", file);
        fd.append("mapping_json", JSON.stringify(clean));
        fd.append("policy", policy);
        try {
            const r = await api.post("/import/anagrafiche/execute", fd, {
                headers: { "Content-Type": "multipart/form-data" },
                timeout: 180000,
            });
            setReport(r.data);
            setStep("done");
            toast.success(`Import completato: ${r.data.created} nuove, ${r.data.updated} aggiornate, ${r.data.skipped} saltate`);
        } catch (e) {
            toast.error("Errore import: " + (e.response?.data?.detail || e.message));
        } finally {
            setBusy(false);
        }
    };

    const reset = () => {
        setFile(null); setPreview(null); setMapping({}); setPolicy("skip");
        setReport(null); setStep("upload");
        if (inputRef.current) inputRef.current.value = "";
    };

    // Campi già mappati (per evitare duplicati nel select)
    const usedFields = useMemo(() => {
        const s = new Set();
        Object.values(mapping).forEach((v) => { if (v && v !== "__ignore__") s.add(v); });
        return s;
    }, [mapping]);

    return (
        <div data-testid="import-anag-excel">
            {step === "upload" && (
                <Card className="p-6" data-testid="excel-dropzone">
                    <FileSpreadsheet size={36} className="mx-auto text-emerald-700 mb-3" />
                    <div className="text-center text-slate-800 font-medium mb-1">
                        Anagrafiche da Excel / CSV
                    </div>
                    <div className="text-center text-xs text-slate-500 mb-4">
                        <Sparkles size={11} className="inline text-violet-600" /> Riconoscimento intelligente automatico delle colonne
                        (CF, P.IVA, Nome, Cognome, Email, Indirizzo, IBAN, ecc.)
                    </div>
                    <div className="flex items-center justify-center gap-2">
                        <input
                            ref={inputRef}
                            type="file"
                            accept=".xlsx,.xls,.csv"
                            className="hidden"
                            onChange={(e) => setFile(e.target.files?.[0] || null)}
                            data-testid="excel-file-input"
                        />
                        <Button
                            type="button" variant="outline"
                            onClick={() => inputRef.current?.click()}
                            data-testid="excel-select-btn"
                        >
                            <Upload size={14} className="mr-1" />
                            {file ? file.name : "Seleziona file Excel/CSV"}
                        </Button>
                        <Button
                            type="button" onClick={doPreview}
                            disabled={!file || busy}
                            className="bg-emerald-700 hover:bg-emerald-800"
                            data-testid="excel-preview-btn"
                        >
                            {busy ? "Analisi in corso..." : "Analizza & Mappa"}
                            <ArrowRight size={14} className="ml-1" />
                        </Button>
                    </div>
                </Card>
            )}

            {step === "preview" && preview && (
                <div className="space-y-4">
                    <Card className="p-4 bg-sky-50 border-sky-200">
                        <div className="flex items-center justify-between flex-wrap gap-2">
                            <div className="text-sm">
                                <b>{preview.filename}</b> · {preview.total_rows} righe totali ·
                                {" "}<span className="text-slate-600">colonne rilevate: {preview.headers.length}</span>
                                {preview.duplicates_stimati > 0 && (
                                    <span className="ml-2 text-amber-800 bg-amber-100 border border-amber-300 rounded px-2 py-0.5 text-xs">
                                        ⚠ {preview.duplicates_stimati} duplicati stimati (CF/P.IVA già in archivio)
                                    </span>
                                )}
                            </div>
                            <Button size="sm" variant="ghost" onClick={reset} data-testid="excel-reset-btn">
                                <RefreshCw size={12} className="mr-1" /> Cambia file
                            </Button>
                        </div>
                    </Card>

                    <Card className="p-4">
                        <div className="text-sm font-medium mb-2 flex items-center gap-1">
                            <Sparkles size={14} className="text-violet-600" /> Mappatura colonne (auto-rilevate)
                        </div>
                        <div className="text-xs text-slate-500 mb-3">
                            Per ogni colonna del file, seleziona il campo di destinazione. Le colonne non mappate saranno ignorate.
                        </div>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead className="text-[10px] uppercase tracking-wider text-slate-500 border-b border-slate-200">
                                    <tr>
                                        <th className="text-left py-2">Colonna nel file</th>
                                        <th className="text-left py-2">Auto-rilevato</th>
                                        <th className="text-left py-2 w-64">Mappa a campo →</th>
                                        <th className="text-left py-2">Esempio (riga 1)</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {preview.detected.map((d) => {
                                        const currentMap = mapping[d.header] || "__ignore__";
                                        const sample = preview.rows?.[0]?.raw?.[d.header] || "—";
                                        return (
                                            <tr key={d.header} className="border-b border-slate-100" data-testid={`excel-map-row-${d.index}`}>
                                                <td className="py-2 pr-3 font-medium text-slate-800">{d.header}</td>
                                                <td className="py-2 pr-3 text-xs">
                                                    {d.canonical
                                                        ? <span className="bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded text-[10px]" data-testid={`excel-auto-${d.index}`}>
                                                            ✓ {d.canonical} ({Math.round(d.confidence * 100)}%)
                                                          </span>
                                                        : <span className="text-slate-400 italic text-[10px]">— non riconosciuta</span>
                                                    }
                                                </td>
                                                <td className="py-2 pr-3">
                                                    <Select
                                                        value={currentMap}
                                                        onValueChange={(v) => setMapping((p) => ({ ...p, [d.header]: v }))}
                                                    >
                                                        <SelectTrigger className="h-8 text-xs" data-testid={`excel-select-${d.index}`}>
                                                            <SelectValue />
                                                        </SelectTrigger>
                                                        <SelectContent>
                                                            <SelectItem value="__ignore__">— Ignora questa colonna —</SelectItem>
                                                            {availableFields.map((f) => (
                                                                <SelectItem key={f} value={f} disabled={usedFields.has(f) && currentMap !== f}>
                                                                    {f}
                                                                </SelectItem>
                                                            ))}
                                                        </SelectContent>
                                                    </Select>
                                                </td>
                                                <td className="py-2 pr-3 text-xs text-slate-600 font-mono truncate max-w-[280px]">
                                                    {sample}
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </Card>

                    {/* Anteprima righe normalizzate */}
                    <Card className="p-4">
                        <div className="text-sm font-medium mb-2">Anteprima righe normalizzate (prime {preview.rows.length})</div>
                        <div className="overflow-x-auto">
                            <table className="w-full text-xs">
                                <thead className="text-[10px] uppercase text-slate-500 border-b">
                                    <tr>
                                        <th className="text-left py-1">Ragione sociale</th>
                                        <th className="text-left py-1">Tipo</th>
                                        <th className="text-left py-1">CF</th>
                                        <th className="text-left py-1">P.IVA</th>
                                        <th className="text-left py-1">Email</th>
                                        <th className="text-left py-1">Comune</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {preview.rows.map((r, i) => (
                                        <tr key={i} className="border-b border-slate-100" data-testid={`excel-preview-row-${i}`}>
                                            <td className="py-1 pr-2 font-medium">{r.normalized?.ragione_sociale || "—"}</td>
                                            <td className="py-1 pr-2 text-[10px]">
                                                <span className={`px-1.5 py-0.5 rounded ${r.normalized?.tipo === "persona_giuridica" ? "bg-emerald-100 text-emerald-800" : "bg-sky-100 text-sky-800"}`}>
                                                    {r.normalized?.tipo === "persona_giuridica" ? "PG" : "PF"}
                                                </span>
                                            </td>
                                            <td className="py-1 pr-2 font-mono">{r.normalized?.codice_fiscale || "—"}</td>
                                            <td className="py-1 pr-2 font-mono">{r.normalized?.partita_iva || "—"}</td>
                                            <td className="py-1 pr-2">{r.normalized?.email || "—"}</td>
                                            <td className="py-1 pr-2">{r.normalized?.comune || "—"}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </Card>

                    <Card className="p-4">
                        <Label className="text-xs uppercase tracking-wider text-slate-500 mb-2 block">Politica sui duplicati</Label>
                        <Select value={policy} onValueChange={setPolicy}>
                            <SelectTrigger className="w-full max-w-md" data-testid="excel-policy-select">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                {Object.entries(POLICY_LABEL).map(([v, l]) => (
                                    <SelectItem key={v} value={v}>{l}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                        <div className="text-xs text-slate-500 mt-2">
                            {policy === "skip" && "Le righe con CF/P.IVA già presenti vengono ignorate."}
                            {policy === "overwrite" && "Le righe con CF/P.IVA esistente aggiornano l'anagrafica esistente (append IBAN, no duplicati)."}
                            {policy === "create_only" && "⚠ Crea sempre nuove anagrafiche, anche se ne esistono già con lo stesso CF/P.IVA."}
                        </div>
                    </Card>

                    <div className="flex justify-between">
                        <Button variant="outline" onClick={reset} data-testid="excel-back-btn">← Annulla</Button>
                        <Button
                            onClick={doExecute} disabled={busy}
                            className="bg-emerald-700 hover:bg-emerald-800"
                            data-testid="excel-execute-btn"
                        >
                            {busy ? "Importazione in corso..." : `Importa ${preview.total_rows} righe →`}
                        </Button>
                    </div>
                </div>
            )}

            {step === "done" && report && (
                <Card className={`p-5 border-l-4 ${report.errors.length === 0 ? "border-l-emerald-500" : "border-l-amber-500"}`} data-testid="excel-report">
                    <div className="flex items-center gap-2 mb-3">
                        {report.errors.length === 0
                            ? <CheckCircle2 size={20} className="text-emerald-600" />
                            : <AlertCircle size={20} className="text-amber-600" />}
                        <h3 className="font-medium">Report import: {report.filename}</h3>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm mb-3">
                        <Stat label="Righe totali" value={report.total_rows} />
                        <Stat label="Nuove create" value={report.created} color="emerald" testid="excel-report-created" />
                        <Stat label="Aggiornate" value={report.updated} color="sky" testid="excel-report-updated" />
                        <Stat label="Saltate/errori" value={report.skipped} color="amber" testid="excel-report-skipped" />
                    </div>
                    <div className="text-xs text-slate-500 mb-3">Policy applicata: <b>{POLICY_LABEL[report.policy]}</b></div>
                    {report.errors.length > 0 && (
                        <details className="mt-3">
                            <summary className="text-xs text-amber-800 cursor-pointer">Vedi righe con errori ({report.errors.length})</summary>
                            <div className="mt-2 max-h-48 overflow-auto text-xs">
                                {report.errors.map((e, i) => (
                                    <div key={i} className="border-b border-slate-100 py-1">
                                        <b>Riga {e.row}:</b> {e.reason}
                                    </div>
                                ))}
                            </div>
                        </details>
                    )}
                    <div className="mt-4 flex gap-2">
                        <Button variant="outline" onClick={reset} data-testid="excel-new-import-btn">
                            <Upload size={14} className="mr-1" /> Nuovo import
                        </Button>
                    </div>
                </Card>
            )}
        </div>
    );
}

function Stat({ label, value, color = "slate", testid }) {
    const colors = {
        emerald: "text-emerald-700",
        sky: "text-sky-700",
        amber: "text-amber-700",
        slate: "text-slate-800",
    };
    return (
        <div className="bg-white border border-slate-200 rounded p-2 text-center" data-testid={testid}>
            <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
            <div className={`text-xl font-bold ${colors[color]} num`}>{value ?? 0}</div>
        </div>
    );
}
