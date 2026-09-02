import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { UploadCloud, CheckCircle2, Loader2, FileText, AlertTriangle } from "lucide-react";

export default function CaricaDocumento() {
    const { token } = useParams();
    const [info, setInfo] = useState(null);
    const [error, setError] = useState(null);
    const [uploading, setUploading] = useState(false);
    const [done, setDone] = useState([]);
    const fileRef = useRef(null);

    useEffect(() => {
        api.get(`/public/upload/${token}`)
            .then((r) => setInfo(r.data))
            .catch((e) => setError(e.response?.data?.detail || "Link non valido"));
    }, [token]);

    const upload = async (file) => {
        if (!file) return;
        setUploading(true);
        try {
            const fd = new FormData();
            fd.append("file", file);
            const r = await api.post(`/public/upload/${token}`, fd, { headers: { "Content-Type": "multipart/form-data" } });
            setDone((d) => [...d, r.data.nome_file || file.name]);
        } catch (e) {
            setError(e.response?.data?.detail || "Errore durante il caricamento");
        } finally { setUploading(false); }
    };

    return (
        <div className="min-h-screen bg-slate-100 flex items-center justify-center p-4">
            <div className="w-full max-w-md bg-white rounded-2xl shadow-xl overflow-hidden">
                <div className="bg-sky-700 text-white px-6 py-5">
                    <div className="text-xs opacity-80">{info?.agenzia_nome || "Caricamento documento"}</div>
                    <div className="text-lg font-semibold mt-0.5">Carica documento</div>
                </div>
                <div className="p-6 space-y-4">
                    {error && (
                        <div className="flex items-start gap-2 text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-lg p-3">
                            <AlertTriangle size={16} className="mt-0.5 shrink-0" /> {error}
                        </div>
                    )}
                    {!info && !error && (
                        <div className="flex items-center gap-2 text-slate-500 text-sm"><Loader2 size={16} className="animate-spin" /> Caricamento…</div>
                    )}
                    {info && !info.scaduto && (
                        <>
                            <div className="text-sm text-slate-700">
                                Ciao{info.cliente_nome ? ` ${info.cliente_nome}` : ""}, carica qui: <strong>{info.descrizione}</strong>
                            </div>
                            {done.length > 0 && (
                                <div className="space-y-1">
                                    {done.map((n, i) => (
                                        <div key={i} className="flex items-center gap-2 text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">
                                            <CheckCircle2 size={15} /> {n} caricato
                                        </div>
                                    ))}
                                </div>
                            )}
                            <button
                                onClick={() => fileRef.current?.click()}
                                disabled={uploading}
                                className="w-full border-2 border-dashed border-sky-300 rounded-xl p-6 flex flex-col items-center gap-2 text-sky-700 hover:bg-sky-50 transition-colors disabled:opacity-60"
                                data-testid="public-upload-drop"
                            >
                                {uploading ? <Loader2 size={26} className="animate-spin" /> : <UploadCloud size={26} />}
                                <span className="text-sm font-medium">{uploading ? "Caricamento…" : "Tocca per scegliere il file"}</span>
                                <span className="text-[11px] text-slate-400">PDF, foto o documenti (max 20 MB)</span>
                            </button>
                            <input ref={fileRef} type="file" className="hidden"
                                onChange={(e) => { upload(e.target.files?.[0]); e.target.value = ""; }} />
                            {done.length > 0 && (
                                <div className="text-center text-xs text-slate-500 flex items-center justify-center gap-1">
                                    <FileText size={12} /> Puoi caricare altri file se necessario
                                </div>
                            )}
                        </>
                    )}
                    {info?.scaduto && (
                        <div className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-3">
                            Questo link è scaduto. Contatta la tua agenzia per riceverne uno nuovo.
                        </div>
                    )}
                </div>
                <div className="px-6 py-3 bg-slate-50 text-center text-[11px] text-slate-400">
                    Collegamento sicuro · i file arrivano direttamente alla tua agenzia
                </div>
            </div>
        </div>
    );
}
