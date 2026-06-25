import { useEffect, useRef, useState } from "react";
import { api, API_BASE, fmtDate } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Upload, FileText, Eye, Trash2, Loader2, ScanLine, Sparkles, Car, FileSearch } from "lucide-react";
import { toast } from "sonner";

const fmtBytes = (n) => {
    if (!n) return "—";
    const k = 1024;
    if (n < k) return `${n} B`;
    if (n < k * k) return `${(n / k).toFixed(1)} KB`;
    return `${(n / k / k).toFixed(1)} MB`;
};

const ICON_FOR_EXT = (name = "") => {
    const ext = name.split(".").pop()?.toLowerCase();
    if (["pdf"].includes(ext)) return <FileText size={16} className="text-rose-600" />;
    if (["jpg", "jpeg", "png", "heic", "webp"].includes(ext)) return <FileText size={16} className="text-emerald-600" />;
    return <FileText size={16} className="text-slate-500" />;
};

/**
 * Tab "Documenti" per PolizzaDetail.
 * Mostra tutti gli allegati legati a polizza_id, con upload manuale e azioni speciali OCR.
 *
 * Props:
 *  - polizzaId: id polizza
 *  - canEdit: bool
 *  - onAfterOCR: callback per ricaricare la polizza dopo OCR libretto (campi veicolo aggiornati)
 */
export default function DocumentiPolizzaTab({ polizzaId, canEdit = true, onAfterOCR }) {
    const [items, setItems] = useState(null);
    const [uploading, setUploading] = useState(false);
    const [ocrLibrettoOpen, setOcrLibrettoOpen] = useState(false);
    const inputRef = useRef(null);

    const load = async () => {
        const r = await api.get("/allegati", { params: { entita_tipo: "polizza", entita_id: polizzaId } });
        setItems(r.data || []);
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [polizzaId]);

    const upload = async (file) => {
        if (!file) return;
        setUploading(true);
        try {
            const fd = new FormData();
            fd.append("file", file);
            await api.post(
                `/allegati?entita_tipo=polizza&entita_id=${polizzaId}`,
                fd, { headers: { "Content-Type": "multipart/form-data" } },
            );
            toast.success("Documento caricato");
            await load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore upload");
        } finally {
            setUploading(false);
            if (inputRef.current) inputRef.current.value = "";
        }
    };

    const rimuovi = async (aid) => {
        if (!window.confirm("Eliminare definitivamente il documento?")) return;
        try {
            await api.delete(`/allegati/${aid}`);
            toast.success("Documento eliminato");
            await load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        }
    };

    return (
        <Card className="border-slate-200 mt-4 p-5" data-testid="documenti-tab">
            {/* Header / Azioni */}
            <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
                <div>
                    <h3 className="font-semibold text-slate-900">Documenti</h3>
                    <p className="text-xs text-slate-500">PDF, immagini, ricevute, libretto veicolo — {items?.length || 0} elementi</p>
                </div>
                {canEdit && (
                    <div className="flex gap-2 flex-wrap">
                        <input
                            ref={inputRef} type="file" className="hidden"
                            accept=".pdf,.jpg,.jpeg,.png,.heic,.webp,.doc,.docx"
                            onChange={(e) => upload(e.target.files?.[0])}
                            data-testid="doc-upload-input"
                        />
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => inputRef.current?.click()}
                            disabled={uploading}
                            data-testid="doc-upload-btn"
                        >
                            {uploading
                                ? <><Loader2 size={14} className="animate-spin mr-1" /> Carico…</>
                                : <><Upload size={14} className="mr-1" /> Carica documento</>
                            }
                        </Button>
                        <Button
                            size="sm"
                            className="bg-violet-600 hover:bg-violet-700"
                            onClick={() => setOcrLibrettoOpen(true)}
                            data-testid="ocr-libretto-btn"
                        >
                            <Sparkles size={14} className="mr-1" /> OCR Libretto veicolo
                        </Button>
                    </div>
                )}
            </div>

            {/* Tabella documenti */}
            {items === null ? (
                <div className="py-12 text-center text-sm text-slate-400">
                    <Loader2 size={18} className="inline animate-spin mr-1" /> Caricamento…
                </div>
            ) : items.length === 0 ? (
                <div className="py-12 text-center text-sm text-slate-500 border border-dashed border-slate-200 rounded-md">
                    <FileSearch size={28} className="mx-auto text-slate-300 mb-1" />
                    Nessun documento caricato per questa polizza.<br />
                    {canEdit && <span className="text-xs">Usa &quot;Carica documento&quot; o &quot;OCR Libretto&quot; per iniziare.</span>}
                </div>
            ) : (
                <table className="tbl w-full" data-testid="doc-table">
                    <thead>
                        <tr>
                            <th className="w-[40px]"></th>
                            <th>Nome file</th>
                            <th className="w-[110px]">Descrizione</th>
                            <th className="w-[80px] text-right">Dimensione</th>
                            <th className="w-[110px]">Caricato il</th>
                            <th className="w-[120px] text-center">Azioni</th>
                        </tr>
                    </thead>
                    <tbody>
                        {items.map((it) => (
                            <tr key={it.id} className="hover:bg-slate-50" data-testid={`doc-row-${it.id}`}>
                                <td className="text-center">{ICON_FOR_EXT(it.nome_file)}</td>
                                <td className="truncate max-w-[280px]" title={it.nome_file}>{it.nome_file}</td>
                                <td className="text-xs text-slate-600">
                                    {it.descrizione || "—"}
                                    {it.descrizione?.includes("OCR") && (
                                        <span className="ml-1 inline-flex items-center text-violet-600 text-[10px]">
                                            <Sparkles size={9} />
                                        </span>
                                    )}
                                </td>
                                <td className="num text-right text-xs">{fmtBytes(it.size_bytes)}</td>
                                <td className="num text-xs">{fmtDate(it.uploaded_at)}</td>
                                <td className="text-center">
                                    <div className="flex justify-center gap-1">
                                        <a
                                            href={`${API_BASE}/allegati/${it.id}/download`}
                                            target="_blank" rel="noreferrer"
                                            className="text-sky-700 hover:text-sky-900"
                                            data-testid={`doc-view-${it.id}`}
                                            title="Apri"
                                        >
                                            <Eye size={15} />
                                        </a>
                                        {canEdit && (
                                            <button
                                                onClick={() => rimuovi(it.id)}
                                                className="text-rose-500 hover:text-rose-700"
                                                data-testid={`doc-del-${it.id}`}
                                                title="Elimina"
                                            >
                                                <Trash2 size={15} />
                                            </button>
                                        )}
                                    </div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}

            {ocrLibrettoOpen && (
                <OcrLibrettoDialog
                    polizzaId={polizzaId}
                    onClose={(refreshPolizza) => {
                        setOcrLibrettoOpen(false);
                        load();
                        if (refreshPolizza && onAfterOCR) onAfterOCR();
                    }}
                />
            )}
        </Card>
    );
}

function OcrLibrettoDialog({ polizzaId, onClose }) {
    const [file, setFile] = useState(null);
    const [loading, setLoading] = useState(false);
    const [estratto, setEstratto] = useState(null);
    const [applica, setApplica] = useState({
        targa: true, marca: true, modello: true, data_immatricolazione: true,
        tipo_veicolo: true, alimentazione: true, kw: true, cv: true, telaio: true,
    });

    const analizza = async () => {
        if (!file) return;
        setLoading(true);
        setEstratto(null);
        try {
            const fd = new FormData();
            fd.append("file", file);
            fd.append("polizza_id", polizzaId);
            const r = await api.post(`/ocr/libretto`, fd, {
                headers: { "Content-Type": "multipart/form-data" },
            });
            setEstratto(r.data);
            toast.success("Libretto analizzato");
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore OCR");
        } finally {
            setLoading(false);
        }
    };

    const applicaAllaPolizza = async () => {
        if (!estratto?.dati) return;
        const fields = Object.entries(applica).filter(([, v]) => v).map(([k]) => k);
        try {
            await api.post(`/ocr/libretto/apply`, {
                polizza_id: polizzaId,
                dati: estratto.dati,
                allegato_id: estratto.allegato_id,
                campi: fields,
            });
            toast.success("Dati applicati alla polizza");
            onClose(true);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose(false)}>
            <DialogContent className="max-w-2xl" data-testid="ocr-libretto-dialog">
                <DialogHeader>
                    <DialogTitle><Car className="inline mr-2 -mt-1" size={18} />OCR Libretto veicolo</DialogTitle>
                </DialogHeader>

                {!estratto && (
                    <div className="py-2 space-y-3">
                        <div className="text-xs text-slate-500">
                            Carica il PDF o l&apos;immagine del libretto. I dati vengono estratti automaticamente con AI
                            (Gemini 3 Flash) e il file salvato come allegato della polizza.
                        </div>
                        <div>
                            <Label>File libretto (PDF / JPG / PNG / HEIC)</Label>
                            <Input
                                type="file"
                                accept=".pdf,.jpg,.jpeg,.png,.heic,.webp"
                                onChange={(e) => setFile(e.target.files?.[0] || null)}
                                data-testid="ocr-libretto-file"
                            />
                            {file && (
                                <div className="text-[11px] text-slate-500 mt-1">{file.name} · {fmtBytes(file.size)}</div>
                            )}
                        </div>
                    </div>
                )}

                {estratto && (
                    <div className="py-2 space-y-3" data-testid="ocr-result">
                        <div className="text-xs bg-violet-50 border border-violet-200 rounded p-2 text-violet-900">
                            <Sparkles size={12} className="inline mr-1" />
                            Dati estratti dal libretto. Seleziona quali applicare alla polizza.
                        </div>
                        <table className="tbl w-full text-sm">
                            <tbody>
                                {Object.entries(estratto.dati || {}).map(([k, v]) => (
                                    <tr key={k}>
                                        <td className="w-8 text-center">
                                            <input
                                                type="checkbox"
                                                checked={!!applica[k]}
                                                onChange={(e) => setApplica((p) => ({ ...p, [k]: e.target.checked }))}
                                                disabled={v === null || v === ""}
                                                data-testid={`apply-${k}`}
                                            />
                                        </td>
                                        <td className="text-xs uppercase tracking-wider text-slate-500 w-40">{k.replace(/_/g, " ")}</td>
                                        <td className="font-medium">{v ?? <span className="text-slate-300">—</span>}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                        {estratto.confidence != null && (
                            <div className="text-[11px] text-slate-500">Confidence: {Math.round((estratto.confidence || 0) * 100)}%</div>
                        )}
                    </div>
                )}

                <DialogFooter>
                    <Button variant="outline" onClick={() => onClose(false)}>Annulla</Button>
                    {!estratto ? (
                        <Button
                            onClick={analizza}
                            disabled={!file || loading}
                            className="bg-violet-600 hover:bg-violet-700"
                            data-testid="ocr-analizza-btn"
                        >
                            {loading
                                ? <><Loader2 size={14} className="animate-spin mr-1" /> Analizzo…</>
                                : <><ScanLine size={14} className="mr-1" /> Analizza libretto</>
                            }
                        </Button>
                    ) : (
                        <Button
                            onClick={applicaAllaPolizza}
                            className="bg-emerald-600 hover:bg-emerald-700"
                            data-testid="ocr-applica-btn"
                        >
                            Applica alla polizza
                        </Button>
                    )}
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
