import { useEffect, useState, useRef } from "react";
import { api, fmtDate } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Upload, FileArchive, CheckCircle2, AlertCircle, Clock } from "lucide-react";
import { toast } from "sonner";

export default function Importazione() {
    const [storico, setStorico] = useState(null);
    const [dragActive, setDragActive] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [lastLog, setLastLog] = useState(null);
    const inputRef = useRef(null);

    const load = () => api.get("/import/storico").then((r) => setStorico(r.data));
    useEffect(() => { load(); }, []);

    const handleFile = async (file) => {
        if (!file) return;
        setUploading(true);
        const fd = new FormData();
        fd.append("file", file);
        try {
            const res = await api.post("/import/ania", fd, {
                headers: { "Content-Type": "multipart/form-data" },
            });
            setLastLog(res.data);
            toast.success(`Import completato in ${(res.data.durata_ms / 1000).toFixed(1)}s`);
            load();
        } catch (e) {
            toast.error("Errore durante l'import: " + (e.response?.data?.detail || e.message));
        } finally {
            setUploading(false);
        }
    };

    const onDrop = (e) => {
        e.preventDefault(); setDragActive(false);
        const f = e.dataTransfer.files?.[0]; if (f) handleFile(f);
    };

    return (
        <div data-testid="importazione-page">
            <PageHeader
                title="Importazione ANIA"
                subtitle="Carica giornalmente il pacchetto ZIP con i tracciati ANIA (rec00 / rec10 / rec20 / rec40 / rec50...)"
            />

            <Card
                className={`dropzone mb-6 ${dragActive ? "active" : ""}`}
                onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
                onDragLeave={() => setDragActive(false)}
                onDrop={onDrop}
                data-testid="import-dropzone"
            >
                <input
                    ref={inputRef}
                    type="file"
                    accept=".zip,.csv"
                    className="hidden"
                    onChange={(e) => handleFile(e.target.files?.[0])}
                    data-testid="import-file-input"
                />
                <FileArchive size={36} className="mx-auto text-sky-700 mb-3" />
                <div className="text-slate-800 font-medium mb-1">
                    Trascina qui il file ZIP del giorno
                </div>
                <div className="text-xs text-slate-500 mb-4">
                    Formato ANIA · Compagnia · Polizze · Titoli · Sinistri · Anagrafiche
                </div>
                <Button
                    type="button"
                    onClick={() => inputRef.current?.click()}
                    disabled={uploading}
                    data-testid="import-select-button"
                    className="bg-sky-700 hover:bg-sky-800"
                >
                    <Upload size={14} className="mr-1" />
                    {uploading ? "Importazione in corso..." : "Seleziona file"}
                </Button>
            </Card>

            {lastLog && (
                <Card className="p-6 border-slate-200 mb-6 border-l-4 border-l-emerald-500" data-testid="import-last-result">
                    <div className="flex items-center gap-2 mb-3">
                        <CheckCircle2 size={18} className="text-emerald-600" />
                        <div className="font-medium text-slate-900">Import completato: {lastLog.nome_file}</div>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                        <div><span className="text-slate-500">Anagrafiche create:</span> <span className="font-medium num">{lastLog.anagrafiche_create}</span></div>
                        <div><span className="text-slate-500">Anagrafiche aggiornate:</span> <span className="font-medium num">{lastLog.anagrafiche_aggiornate}</span></div>
                        <div><span className="text-slate-500">Polizze create:</span> <span className="font-medium num">{lastLog.polizze_create}</span></div>
                        <div><span className="text-slate-500">Polizze aggiornate:</span> <span className="font-medium num">{lastLog.polizze_aggiornate}</span></div>
                        <div><span className="text-slate-500">Titoli creati:</span> <span className="font-medium num">{lastLog.titoli_creati}</span></div>
                        <div><span className="text-slate-500">Sinistri creati:</span> <span className="font-medium num">{lastLog.sinistri_creati}</span></div>
                        <div><span className="text-slate-500">Durata:</span> <span className="font-medium num">{(lastLog.durata_ms / 1000).toFixed(2)}s</span></div>
                    </div>
                    <div className="mt-3 text-xs text-slate-600">
                        <div className="font-medium text-slate-700 mb-1">Record types processati:</div>
                        <div className="flex flex-wrap gap-2">
                            {Object.entries(lastLog.record_types_processati || {}).map(([k, v]) => (
                                <span key={k} className="badge badge-info">{k}: {v}</span>
                            ))}
                        </div>
                    </div>
                </Card>
            )}

            <h3 className="text-lg font-medium text-slate-900 mb-3">Storico importazioni</h3>
            <div className="bg-white border border-slate-200 rounded-md overflow-hidden">
                {storico === null ? <Loading /> : storico.length === 0 ? <Empty message="Nessuna importazione effettuata" /> : (
                    <table className="tbl w-full">
                        <thead>
                            <tr>
                                <th>Data</th>
                                <th>File</th>
                                <th>Stato</th>
                                <th className="text-right">Anag.</th>
                                <th className="text-right">Polizze</th>
                                <th className="text-right">Titoli</th>
                                <th className="text-right">Sinistri</th>
                                <th className="text-right">Durata</th>
                            </tr>
                        </thead>
                        <tbody>
                            {storico.map((l) => (
                                <tr key={l.id}>
                                    <td className="num">{fmtDate(l.created_at)}</td>
                                    <td className="text-xs">{l.nome_file}</td>
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
                                    <td className="num text-right">{((l.durata_ms || 0) / 1000).toFixed(2)}s</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
}
