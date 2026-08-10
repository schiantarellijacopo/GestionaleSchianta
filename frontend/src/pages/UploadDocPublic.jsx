/**
 * UploadDocPublic — Landing page pubblica per caricare un documento veicolo
 * (Atto Vendita, Certificato Demolizione, Doc. Esportazione) dal link ricevuto
 * via email/WhatsApp/SMS di sollecito.
 *
 * URL: /upload-doc?token=<jwt>
 * Backend: /api/public/upload-doc/info + /api/public/upload-doc/veicolo
 */
import { useEffect, useState } from "react";
import axios from "axios";
import { Toaster, toast } from "sonner";
import { Upload, CheckCircle2, AlertTriangle, Car, FileText } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api/public/upload-doc`;

export default function UploadDocPublic() {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token") || "";
    const [info, setInfo] = useState(null);
    const [error, setError] = useState("");
    const [file, setFile] = useState(null);
    const [uploading, setUploading] = useState(false);
    const [done, setDone] = useState(false);

    useEffect(() => {
        if (!token) { setError("Link non valido: token mancante"); return; }
        axios.get(`${API}/info`, { params: { token } })
            .then((r) => setInfo(r.data))
            .catch((e) => setError(e.response?.data?.detail || "Link non valido o scaduto"));
    }, [token]);

    const submit = async () => {
        if (!file) { toast.error("Seleziona prima un file"); return; }
        setUploading(true);
        try {
            const fd = new FormData();
            fd.append("token", token);
            fd.append("file", file);
            await axios.post(`${API}/veicolo`, fd, { headers: { "Content-Type": "multipart/form-data" } });
            setDone(true);
            toast.success("Documento caricato correttamente!");
        } catch (e) { toast.error(e.response?.data?.detail || "Errore upload"); }
        finally { setUploading(false); }
    };

    return (
        <div className="min-h-screen bg-gradient-to-br from-sky-50 via-white to-blue-100 flex items-center justify-center p-4">
            <Toaster position="top-center" richColors />
            <div className="w-full max-w-md bg-white rounded-2xl shadow-xl p-6 sm:p-8">
                <div className="text-center mb-6">
                    <div className="inline-flex w-16 h-16 rounded-full bg-sky-100 items-center justify-center mb-3">
                        <Upload className="text-sky-700" size={30} />
                    </div>
                    <h1 className="text-xl sm:text-2xl font-bold text-slate-800">Carica il tuo documento</h1>
                </div>
                {error && (
                    <div className="bg-rose-50 border border-rose-200 rounded p-4 text-sm text-rose-800">
                        <AlertTriangle className="inline mr-1" size={16} /> {error}
                    </div>
                )}
                {done && (
                    <div className="text-center py-8">
                        <CheckCircle2 className="mx-auto text-emerald-500 mb-3" size={48} />
                        <div className="font-semibold text-slate-800">Documento ricevuto!</div>
                        <div className="text-sm text-slate-500 mt-2">Grazie, l&apos;agenzia lo ha già in carico.</div>
                    </div>
                )}
                {info && !done && (
                    <>
                        <div className="bg-sky-50 border border-sky-200 rounded-lg p-3 mb-4 text-sm">
                            {info.gia_caricato && (
                                <div className="bg-emerald-50 border border-emerald-200 rounded p-2 mb-2 text-emerald-800 text-xs">
                                    ✓ Un documento è già stato caricato per questa pratica. Puoi comunque inviarne uno aggiornato.
                                </div>
                            )}
                            <div className="flex items-center gap-2 mb-1">
                                <Car className="text-sky-600" size={16} />
                                <span className="font-mono font-bold text-sky-800">{info.targa}</span>
                            </div>
                            <div className="text-xs text-slate-600">Intestatario: {info.intestatario || "—"}</div>
                            {info.polizza_numero && <div className="text-xs text-slate-600">Polizza: {info.polizza_numero}</div>}
                            <div className="text-xs mt-2">
                                Documento richiesto: <b className="text-slate-800 uppercase">{(info.categoria_richiesta || "").replace(/_/g, " ")}</b>
                            </div>
                        </div>

                        <label className="block cursor-pointer">
                            <input type="file" accept="application/pdf,image/*" capture="environment"
                                onChange={(e) => setFile(e.target.files?.[0] || null)}
                                className="hidden" data-testid="public-upload-file" />
                            <div className={`border-2 border-dashed rounded-lg p-6 text-center transition ${
                                file ? "border-sky-400 bg-sky-50" : "border-slate-300 hover:border-sky-400 hover:bg-sky-50"
                            }`}>
                                <FileText className="mx-auto mb-2 text-slate-400" size={32} />
                                {file ? (
                                    <div>
                                        <div className="font-semibold text-slate-800">{file.name}</div>
                                        <div className="text-xs text-slate-500">{(file.size / 1024).toFixed(0)} KB</div>
                                    </div>
                                ) : (
                                    <div>
                                        <div className="text-sm font-semibold text-slate-700">Tocca per scegliere un file</div>
                                        <div className="text-xs text-slate-500 mt-1">o scatta una foto</div>
                                    </div>
                                )}
                            </div>
                        </label>

                        <button onClick={submit} disabled={!file || uploading}
                            className="w-full mt-4 py-3 rounded-lg bg-sky-600 hover:bg-sky-700 text-white font-semibold disabled:opacity-50"
                            data-testid="public-upload-submit">
                            {uploading ? "Invio in corso…" : "Invia documento"}
                        </button>
                        <div className="text-[10px] text-slate-400 text-center mt-3">
                            Link protetto e cifrato. Il documento verrà ricevuto dall&apos;agenzia.
                        </div>
                    </>
                )}
                {!info && !error && <div className="text-center text-slate-400">Caricamento…</div>}
            </div>
        </div>
    );
}
