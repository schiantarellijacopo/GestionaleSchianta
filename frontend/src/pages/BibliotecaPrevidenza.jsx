/**
 * Biblioteca Previdenza — archivio PDF normativi (PASS PREVIDENZA).
 * Cartelle + upload multiplo drag&drop + sync Google Drive + consulto AI.
 */
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { PageHeader, Loading } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
    FolderOpen, Folder, Upload, Trash2, Download, Plus, Cloud,
    Sparkles, FileText, Loader2,
} from "lucide-react";
import { toast } from "sonner";

export default function BibliotecaPrevidenza() {
    const [cartelle, setCartelle] = useState(null);
    const [sel, setSel] = useState(null);
    const [docs, setDocs] = useState([]);
    const [uploading, setUploading] = useState(false);
    const [syncing, setSyncing] = useState(false);
    const [dragOver, setDragOver] = useState(false);
    const [nuovaCartella, setNuovaCartella] = useState("");
    const fileRef = useRef(null);

    const loadCartelle = async () => {
        const r = await api.get("/biblioteca-previdenza/cartelle");
        setCartelle(r.data);
        return r.data;
    };
    const loadDocs = async (cart) => {
        const r = await api.get("/biblioteca-previdenza/documenti", { params: { cartella: cart } });
        setDocs(r.data);
    };
    useEffect(() => {
        loadCartelle().then((c) => {
            if (c?.length) { setSel(c[0].nome); }
        }).catch((e) => toast.error("Errore caricamento: " + e.message));
    }, []);
    useEffect(() => { if (sel) loadDocs(sel).catch(() => {}); }, [sel]);

    const uploadFiles = async (fileList) => {
        const files = Array.from(fileList || []);
        if (!files.length || !sel) return;
        setUploading(true);
        try {
            const fd = new FormData();
            files.forEach((f) => fd.append("files", f));
            fd.append("cartella", sel);
            const r = await api.post("/biblioteca-previdenza/upload", fd, {
                headers: { "Content-Type": "multipart/form-data" },
            });
            const { importati, saltati, errori } = r.data;
            if (importati.length) toast.success(`${importati.length} documenti importati in ${sel}`);
            if (saltati.length) toast.info(`${saltati.length} già presenti (saltati)`);
            (errori || []).forEach((e) => toast.error(`${e.file}: ${e.errore}`));
            await Promise.all([loadCartelle(), loadDocs(sel)]);
        } catch (e) {
            toast.error("Errore upload: " + (e.response?.data?.detail || e.message));
        } finally { setUploading(false); }
    };

    const syncDrive = async () => {
        setSyncing(true);
        try {
            let restanti = 1, tot = 0, giri = 0, msg = null;
            while (restanti > 0 && giri < 10) {
                const r = await api.post("/biblioteca-previdenza/sync-drive", {});
                tot += r.data.importati.length;
                restanti = r.data.restanti || 0;
                giri += 1;
                msg = r.data.messaggio;
                (r.data.errori || []).slice(0, 3).forEach((e) => toast.error(`${e.file}: ${e.errore}`));
                if (msg) break;
            }
            if (msg) toast.info(msg, { duration: 9000 });
            else toast.success(`Sync Drive completata: ${tot} documenti importati`);
            await Promise.all([loadCartelle(), sel ? loadDocs(sel) : Promise.resolve()]);
        } catch (e) {
            toast.error(e.response?.data?.detail || e.message);
        } finally { setSyncing(false); }
    };

    const creaCartella = async () => {
        const nome = nuovaCartella.trim();
        if (!nome) return;
        try {
            await api.post("/biblioteca-previdenza/cartelle", { nome });
            setNuovaCartella("");
            const c = await loadCartelle();
            setSel(nome.toUpperCase());
            toast.success("Cartella creata");
        } catch (e) { toast.error(e.response?.data?.detail || e.message); }
    };

    const deleteDoc = async (d) => {
        if (!window.confirm(`Eliminare "${d.nome_file}"?`)) return;
        await api.delete(`/biblioteca-previdenza/documenti/${d.id}`);
        toast.success("Documento eliminato");
        await Promise.all([loadCartelle(), loadDocs(sel)]);
    };

    const downloadDoc = async (d) => {
        try {
            const r = await api.get(`/biblioteca-previdenza/documenti/${d.id}/download`, { responseType: "blob" });
            const url = URL.createObjectURL(r.data);
            window.open(url, "_blank");
        } catch { toast.error("Download non riuscito"); }
    };

    if (!cartelle) return <Loading />;

    return (
        <div className="space-y-4" data-testid="biblioteca-previdenza-page">
            <PageHeader title="Biblioteca Previdenza"
                subtitle="PDF normativi (PASS PREVIDENZA) usati dall'AI per i calcoli pensione: invalidità, superstiti, premorienza" />

            {/* Cartelle */}
            <div className="flex flex-wrap gap-2 items-center">
                {cartelle.map((c) => (
                    <button key={c.nome} onClick={() => setSel(c.nome)}
                            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${sel === c.nome ? "bg-sky-700 text-white border-sky-700" : "bg-white text-slate-700 border-slate-300 hover:border-sky-500"}`}
                            data-testid={`cartella-${c.nome.toLowerCase().replace(/ /g, "-")}`}>
                        {sel === c.nome ? <FolderOpen size={13} /> : <Folder size={13} />}
                        {c.nome}
                        <span className={`rounded-full px-1.5 text-[10px] ${sel === c.nome ? "bg-white/20" : "bg-slate-100"}`}>{c.documenti}</span>
                    </button>
                ))}
                <div className="flex items-center gap-1">
                    <Input value={nuovaCartella} onChange={(e) => setNuovaCartella(e.target.value)}
                           placeholder="Nuova cartella..." className="h-8 w-36 text-xs"
                           onKeyDown={(e) => e.key === "Enter" && creaCartella()}
                           data-testid="nuova-cartella-input" />
                    <Button size="sm" variant="outline" onClick={creaCartella} data-testid="nuova-cartella-btn">
                        <Plus size={14} />
                    </Button>
                </div>
            </div>

            {/* Upload area */}
            <Card
                className={`p-6 border-2 border-dashed text-center transition-colors ${dragOver ? "border-sky-500 bg-sky-50" : "border-slate-300"}`}
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => { e.preventDefault(); setDragOver(false); uploadFiles(e.dataTransfer.files); }}
                data-testid="upload-dropzone">
                <input ref={fileRef} type="file" multiple accept=".pdf,.txt"
                       className="hidden" onChange={(e) => { uploadFiles(e.target.files); e.target.value = ""; }}
                       data-testid="upload-input" />
                <Upload className="mx-auto text-slate-400 mb-2" size={28} />
                <div className="text-sm text-slate-600">
                    Trascina qui i PDF (anche tutti e 50 in un colpo) oppure{" "}
                    <button className="text-sky-700 font-semibold underline" onClick={() => fileRef.current?.click()}>
                        selezionali
                    </button>
                    {" "}— verranno archiviati in <strong>{sel}</strong>
                </div>
                <div className="mt-3 flex justify-center gap-2">
                    <Button size="sm" variant="outline" disabled={syncing} onClick={syncDrive} data-testid="sync-drive-btn">
                        {syncing ? <Loader2 size={14} className="animate-spin mr-1" /> : <Cloud size={14} className="mr-1" />}
                        Sincronizza da Google Drive
                    </Button>
                </div>
                <div className="mt-2 text-[11px] text-slate-400">
                    La prima sincronizzazione crea su Drive la cartella <strong>Assicura CRM / PASS PREVIDENZA</strong> con
                    le sottocartelle categoria: trascinaci i PDF e premi di nuovo Sincronizza.
                </div>
                {uploading && <div className="mt-2 text-xs text-sky-700 flex items-center justify-center gap-1"><Loader2 size={12} className="animate-spin" /> Caricamento ed estrazione testo in corso...</div>}
            </Card>

            {/* Documenti */}
            <Card className="p-5 border-slate-200">
                <div className="text-sm font-semibold text-slate-800 mb-3 flex items-center gap-2">
                    <FileText size={15} /> Documenti in {sel} ({docs.length})
                </div>
                {docs.length === 0 ? (
                    <div className="text-xs text-slate-400 italic">Nessun documento in questa cartella.</div>
                ) : (
                    <table className="w-full text-xs">
                        <thead>
                            <tr className="text-slate-500 border-b">
                                <th className="text-left py-1.5">Nome file</th>
                                <th className="text-left py-1.5">Pagine</th>
                                <th className="text-left py-1.5">Dimensione</th>
                                <th className="text-left py-1.5">Testo AI</th>
                                <th className="text-left py-1.5">Caricato da</th>
                                <th className="text-left py-1.5">Data</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody>
                            {docs.map((d) => (
                                <tr key={d.id} className="border-b border-slate-100 hover:bg-slate-50" data-testid={`doc-row-${d.id}`}>
                                    <td className="py-1.5 font-medium text-slate-800">{d.nome_file}</td>
                                    <td>{d.pagine || "—"}</td>
                                    <td>{d.size_kb ? `${d.size_kb} KB` : "—"}</td>
                                    <td>{d.testo_ok
                                        ? <span className="text-emerald-600 font-semibold">✓ leggibile</span>
                                        : <span className="text-amber-600">solo archivio</span>}</td>
                                    <td className="text-slate-500">{d.caricato_da_nome || "—"}</td>
                                    <td className="text-slate-500">{(d.created_at || "").slice(0, 10)}</td>
                                    <td className="text-right whitespace-nowrap">
                                        <Button size="sm" variant="ghost" onClick={() => downloadDoc(d)} title="Apri/Scarica"
                                                data-testid={`doc-download-${d.id}`}>
                                            <Download size={13} />
                                        </Button>
                                        <Button size="sm" variant="ghost" onClick={() => deleteDoc(d)} title="Elimina"
                                                data-testid={`doc-delete-${d.id}`}>
                                            <Trash2 size={13} className="text-rose-600" />
                                        </Button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </Card>

            {/* Consulto AI */}
            <ConsultaAI cartelle={cartelle} defaultCartella={sel} />
        </div>
    );
}

function ConsultaAI({ cartelle, defaultCartella }) {
    const [cartella, setCartella] = useState(defaultCartella || "");
    const [domanda, setDomanda] = useState("");
    const [risposta, setRisposta] = useState(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => { if (defaultCartella) setCartella(defaultCartella); }, [defaultCartella]);

    const chiedi = async () => {
        if (!domanda.trim()) { toast.error("Scrivi una domanda"); return; }
        setLoading(true); setRisposta(null);
        try {
            const r = await api.post("/biblioteca-previdenza/consulta-ai", { cartella, domanda });
            setRisposta(r.data);
        } catch (e) {
            toast.error(e.response?.data?.detail || e.message);
        } finally { setLoading(false); }
    };

    return (
        <Card className="p-5 border-violet-200 bg-violet-50/40" data-testid="consulta-ai-card">
            <div className="text-sm font-semibold text-violet-900 mb-2 flex items-center gap-2">
                <Sparkles size={15} /> Chiedi all'AI (usa i documenti della biblioteca come fonte)
            </div>
            <div className="flex flex-col md:flex-row gap-2 mb-2">
                <Select value={cartella} onValueChange={setCartella}>
                    <SelectTrigger className="w-full md:w-64 h-9 text-xs bg-white" data-testid="consulta-ai-cartella">
                        <SelectValue placeholder="Cartella" />
                    </SelectTrigger>
                    <SelectContent>
                        {(cartelle || []).map((c) => (
                            <SelectItem key={c.nome} value={c.nome}>{c.nome} ({c.documenti})</SelectItem>
                        ))}
                    </SelectContent>
                </Select>
                <Textarea value={domanda} onChange={(e) => setDomanda(e.target.value)}
                          placeholder="Es: quali sono i requisiti e la formula di calcolo della pensione di invalidità per un dipendente pubblico?"
                          className="flex-1 text-xs bg-white min-h-[38px]" rows={2}
                          data-testid="consulta-ai-domanda" />
                <Button onClick={chiedi} disabled={loading} className="bg-violet-700 hover:bg-violet-800"
                        data-testid="consulta-ai-btn">
                    {loading ? <Loader2 size={14} className="animate-spin mr-1" /> : <Sparkles size={14} className="mr-1" />}
                    Chiedi
                </Button>
            </div>
            {risposta && (
                <div className="bg-white border border-violet-200 rounded p-3 text-xs text-slate-800 whitespace-pre-wrap"
                     data-testid="consulta-ai-risposta">
                    {risposta.risposta}
                    <div className="mt-2 pt-2 border-t border-slate-100 text-[10px] text-slate-500">
                        Fonti: {(risposta.fonti || []).join(" · ") || "—"}
                    </div>
                </div>
            )}
        </Card>
    );
}
