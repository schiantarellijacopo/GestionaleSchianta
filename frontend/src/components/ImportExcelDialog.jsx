/**
 * ImportExcelDialog — dialog riusabile per import Excel/CSV di qualsiasi entità.
 *
 * Props:
 *   - open           : bool
 *   - onClose        : function
 *   - onSuccess      : function(report)
 *   - entity         : "polizze" | "sinistri"  (determina l'endpoint /api/import/{entity}/...)
 *   - title          : label mostrata (es "Importa Polizze da Excel/CSV")
 *   - required       : lista campi CRM obbligatori (es ["numero_polizza"])
 *   - policyLabels   : override delle label delle policy (default: skip/overwrite/create_only)
 *
 * Flusso: 1) upload → 2) preview + mapping → 3) execute → 4) risultato
 */
import { useRef, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Upload, CheckCircle2, AlertCircle, Sparkles } from "lucide-react";
import { toast } from "sonner";

const DEFAULT_POLICY_LABEL = {
    skip: "Salta duplicati (default sicuro)",
    overwrite: "Sovrascrivi duplicati esistenti",
    create_only: "Crea sempre — anche duplicati (SCONSIGLIATO)",
};

export default function ImportExcelDialog({
    open, onClose, onSuccess, entity, title,
    required = [], policyLabels = DEFAULT_POLICY_LABEL,
}) {
    const [file, setFile] = useState(null);
    const [step, setStep] = useState("upload");   // upload | preview | done
    const [preview, setPreview] = useState(null);
    const [mapping, setMapping] = useState({});   // {header: canonical | "__ignore__"}
    const [policy, setPolicy] = useState("skip");
    const [busy, setBusy] = useState(false);
    const [report, setReport] = useState(null);
    const inputRef = useRef(null);

    const availableFields = preview?.available_fields || [];

    const reset = () => {
        setFile(null);
        setPreview(null);
        setMapping({});
        setReport(null);
        setStep("upload");
    };

    const closeDialog = () => {
        reset();
        onClose?.();
    };

    const doPreview = async () => {
        if (!file) { toast.error("Seleziona un file .xlsx o .csv"); return; }
        setBusy(true);
        const fd = new FormData();
        fd.append("file", file);
        try {
            const r = await api.post(`/import/${entity}/preview`, fd, {
                headers: { "Content-Type": "multipart/form-data" },
                timeout: 60000,
            });
            setPreview(r.data);
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
        // Verifica campi obbligatori mappati
        const mapped = Object.values(mapping).filter((v) => v && v !== "__ignore__");
        for (const req of required) {
            if (!mapped.includes(req)) {
                toast.error(`Devi mappare il campo obbligatorio "${req}"`);
                return;
            }
        }
        const clean = {};
        Object.entries(mapping).forEach(([h, c]) => {
            if (c && c !== "__ignore__") clean[h] = c;
        });
        setBusy(true);
        const fd = new FormData();
        fd.append("file", file);
        fd.append("mapping_json", JSON.stringify(clean));
        fd.append("policy", policy);
        try {
            const r = await api.post(`/import/${entity}/execute`, fd, {
                headers: { "Content-Type": "multipart/form-data" },
                timeout: 120000,
            });
            setReport(r.data);
            setStep("done");
            onSuccess?.(r.data);
            toast.success(`Import completato: ${r.data.created} creati, ${r.data.updated} aggiornati`);
        } catch (e) {
            toast.error("Errore import: " + (e.response?.data?.detail || e.message));
        } finally {
            setBusy(false);
        }
    };

    return (
        <Dialog open={!!open} onOpenChange={(o) => !o && closeDialog()}>
            <DialogContent className="max-w-4xl max-h-[92vh] overflow-y-auto"
                           data-testid={`dialog-import-${entity}`}>
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Upload size={18} /> {title || `Importa ${entity} da Excel/CSV`}
                        <span className="text-xs text-slate-500 font-normal ml-2">
                            Step {step === "upload" ? "1 · Carica file"
                                : step === "preview" ? "2 · Verifica mapping"
                                : "3 · Risultato"}
                        </span>
                    </DialogTitle>
                </DialogHeader>

                {step === "upload" && (
                    <div className="space-y-3">
                        <div className="bg-sky-50 border border-sky-200 rounded p-2.5 text-xs text-sky-900">
                            📄 Carica un file <strong>.xlsx</strong>, <strong>.xls</strong> o <strong>.csv</strong>.
                            Il sistema leggerà le intestazioni e ti proporrà un mapping automatico verso i campi CRM.
                            {required.length > 0 && (
                                <div className="mt-1">
                                    <strong>Campi obbligatori:</strong> {required.join(", ")}
                                </div>
                            )}
                        </div>
                        <Input
                            ref={inputRef}
                            type="file" accept=".xlsx,.xls,.csv,.xlsm"
                            onChange={(e) => setFile(e.target.files?.[0] || null)}
                            data-testid={`import-${entity}-file`}
                        />
                        {file && (
                            <div className="text-xs text-slate-600">
                                Selezionato: <strong>{file.name}</strong> ({(file.size / 1024).toFixed(1)} KB)
                            </div>
                        )}
                    </div>
                )}

                {step === "preview" && preview && (
                    <div className="space-y-3">
                        <div className="bg-emerald-50 border border-emerald-200 rounded p-2.5 text-xs text-emerald-900 flex items-center gap-2">
                            <Sparkles size={14} className="text-emerald-600" />
                            <div>
                                File letto: <strong>{preview.total_rows}</strong> righe · <strong>{preview.headers.length}</strong> colonne
                                {preview.duplicates_stimati > 0 && (
                                    <span className="ml-2 text-amber-700">
                                        · ~{preview.duplicates_stimati} duplicati stimati
                                    </span>
                                )}
                            </div>
                        </div>
                        <Card className="p-2 overflow-x-auto max-h-80">
                            <table className="w-full text-xs">
                                <thead className="bg-slate-100 sticky top-0">
                                    <tr>
                                        <th className="p-1.5 text-left font-semibold">Colonna nel file</th>
                                        <th className="p-1.5 text-left font-semibold">→ Campo CRM</th>
                                        <th className="p-1.5 text-left font-semibold text-slate-500">Esempio</th>
                                        <th className="p-1.5 text-center">Auto</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {preview.detected.map((d) => (
                                        <tr key={d.header} className="border-b border-slate-100">
                                            <td className="p-1.5 font-mono text-[11px]">{d.header}</td>
                                            <td className="p-1.5">
                                                <select
                                                    value={mapping[d.header] || "__ignore__"}
                                                    onChange={(e) => setMapping({ ...mapping, [d.header]: e.target.value })}
                                                    className="w-full text-xs border rounded h-7 px-1.5"
                                                    data-testid={`mapping-${d.header}`}
                                                >
                                                    <option value="__ignore__">— ignora colonna —</option>
                                                    {availableFields.map((f) => (
                                                        <option key={f} value={f}>
                                                            {f}{required.includes(f) ? " *" : ""}
                                                        </option>
                                                    ))}
                                                </select>
                                            </td>
                                            <td className="p-1.5 text-[10px] text-slate-500 max-w-[220px] truncate">
                                                {preview.rows[0]?.raw?.[d.header] ?? "-"}
                                            </td>
                                            <td className="p-1.5 text-center">
                                                {d.canonical && d.confidence >= 0.6 ? (
                                                    <span className="text-emerald-600 text-[10px] font-semibold">
                                                        ✓ {(d.confidence * 100).toFixed(0)}%
                                                    </span>
                                                ) : (
                                                    <span className="text-slate-300 text-[10px]">—</span>
                                                )}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </Card>
                        <div>
                            <Label className="text-xs font-semibold">Comportamento sui duplicati</Label>
                            <div className="grid grid-cols-1 gap-1 mt-1">
                                {Object.entries(policyLabels).map(([k, v]) => (
                                    <label key={k} className="flex items-center gap-2 text-xs cursor-pointer p-1.5 border rounded hover:bg-slate-50">
                                        <input
                                            type="radio" name="policy" value={k}
                                            checked={policy === k}
                                            onChange={() => setPolicy(k)}
                                            data-testid={`policy-${k}`}
                                        />
                                        {v}
                                    </label>
                                ))}
                            </div>
                        </div>
                    </div>
                )}

                {step === "done" && report && (
                    <div className="space-y-3">
                        <div className="bg-emerald-50 border border-emerald-300 rounded p-3">
                            <div className="flex items-center gap-2">
                                <CheckCircle2 className="text-emerald-600" size={20} />
                                <div className="text-lg font-bold text-emerald-900">Import completato</div>
                            </div>
                            <div className="grid grid-cols-4 gap-2 mt-3 text-sm">
                                <div><span className="text-slate-500">Letti:</span> <strong>{report.total_rows}</strong></div>
                                <div><span className="text-emerald-700">Creati:</span> <strong>{report.created}</strong></div>
                                <div><span className="text-sky-700">Aggiornati:</span> <strong>{report.updated}</strong></div>
                                <div><span className="text-amber-700">Saltati:</span> <strong>{report.skipped}</strong></div>
                            </div>
                        </div>
                        {(report.errors || []).length > 0 && (
                            <div className="bg-rose-50 border border-rose-200 rounded p-2 max-h-40 overflow-y-auto">
                                <div className="text-xs font-semibold text-rose-900 mb-1 flex items-center gap-1">
                                    <AlertCircle size={12} /> {report.errors.length} righe con problemi
                                </div>
                                {report.errors.slice(0, 20).map((e, i) => (
                                    <div key={i} className="text-[10px] text-rose-800">
                                        Riga {e.row}: {e.reason}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}

                <DialogFooter>
                    {step === "upload" && (
                        <>
                            <Button variant="outline" onClick={closeDialog}>Annulla</Button>
                            <Button onClick={doPreview} disabled={!file || busy}
                                    className="bg-sky-700 hover:bg-sky-800"
                                    data-testid={`btn-import-${entity}-preview`}>
                                {busy ? "Analisi…" : "Analizza file →"}
                            </Button>
                        </>
                    )}
                    {step === "preview" && (
                        <>
                            <Button variant="outline" onClick={() => setStep("upload")}>← Indietro</Button>
                            <Button onClick={doExecute} disabled={busy}
                                    className="bg-emerald-600 hover:bg-emerald-700"
                                    data-testid={`btn-import-${entity}-execute`}>
                                {busy ? "Import in corso…" : `Importa ${preview?.total_rows || 0} righe`}
                            </Button>
                        </>
                    )}
                    {step === "done" && (
                        <Button onClick={closeDialog} className="bg-sky-700 hover:bg-sky-800">
                            Chiudi
                        </Button>
                    )}
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
