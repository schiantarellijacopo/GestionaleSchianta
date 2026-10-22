import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import {
    FileSignature, Upload, Trash2, ArrowLeft, Copy, Play, Loader2, PenTool, Save,
} from "lucide-react";
import FirmaDesigner from "@/components/FirmaDesigner";

export default function ModelliFirma() {
    const [lista, setLista] = useState([]);
    const [sel, setSel] = useState(null);
    const [campiDisp, setCampiDisp] = useState([]);
    const [uploadNome, setUploadNome] = useState("");
    const [dragOver, setDragOver] = useState(false);
    const [campi, setCampi] = useState([]);
    const [savingCampi, setSavingCampi] = useState(false);

    const loadLista = () => api.get("/firma/modelli").then((r) => setLista(r.data)).catch(() => {});
    useEffect(() => {
        loadLista();
        api.get("/firma/modelli/campi-disponibili").then((r) => setCampiDisp(r.data)).catch(() => {});
    }, []);

    const apri = async (mid) => {
        try {
            const d = (await api.get(`/firma/modelli/${mid}`)).data;
            setSel(d);
            setCampi(d.campi || []);
        } catch { toast.error("Errore apertura modello"); }
    };

    const salvaCampi = async () => {
        if (!sel) return;
        setSavingCampi(true);
        try {
            await api.put(`/firma/modelli/${sel.id}`, { campi });
            toast.success("Posizione firma salvata nel modello");
        } catch (e) { toast.error(e.response?.data?.detail || "Errore salvataggio"); }
        finally { setSavingCampi(false); }
    };

    const upload = async (file) => {
        if (!file) return;
        const nome = uploadNome.trim() || file.name.replace(/\.[^.]+$/, "");
        const fd = new FormData();
        fd.append("file", file);
        fd.append("nome", nome);
        try {
            const r = await api.post("/firma/modelli", fd, { headers: { "Content-Type": "multipart/form-data" } });
            toast.success("Modello caricato");
            setUploadNome("");
            await loadLista();
            apri(r.data.id);
        } catch (e) { toast.error(e.response?.data?.detail || "Errore upload"); }
    };

    const elimina = async (mid) => {
        if (!window.confirm("Eliminare questo modello?")) return;
        await api.delete(`/firma/modelli/${mid}`);
        if (sel?.id === mid) setSel(null);
        loadLista();
    };

    const copia = (txt) => {
        navigator.clipboard?.writeText(txt);
        toast.success(`Copiato ${txt}`);
    };

    if (sel) {
        return (
            <div className="space-y-4" data-testid="mf-detail">
                <div className="flex items-center gap-2">
                    <button onClick={() => setSel(null)} className="text-slate-500 hover:text-slate-800"><ArrowLeft size={18} /></button>
                    <h2 className="text-lg font-medium text-slate-800">{sel.nome}</h2>
                </div>

                <Card className="p-4 border-sky-200 bg-sky-50/40">
                    <div className="text-sm font-medium text-sky-900 mb-1">Come funziona</div>
                    <p className="text-xs text-slate-600">
                        Nel tuo documento Word/PDF scrivi i <strong>segnaposto</strong> tra parentesi graffe (es. <code>{"{nome_cliente}"}</code>) nel punto esatto in cui vuoi il dato,
                        e <code>{"{firma}"}</code> dove deve apparire la firma. In compilazione l'app sostituisce i segnaposto coi dati reali e invia a firma.
                        Clicca un segnaposto per copiarlo.
                    </p>
                </Card>

                <Card className="p-4">
                    <div className="text-sm font-medium text-slate-700 mb-2">Segnaposto disponibili</div>
                    <div className="flex flex-wrap gap-2">
                        <button onClick={() => copia("{firma}")} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs bg-violet-100 text-violet-800 hover:bg-violet-200 border border-violet-300" data-testid="ph-firma">
                            <PenTool size={11} /> {"{firma}"} <Copy size={11} />
                        </button>
                        {campiDisp.map((k) => (
                            <button key={k.chiave} onClick={() => copia(`{${k.chiave}}`)} title={k.label}
                                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs bg-slate-100 text-slate-700 hover:bg-slate-200 border border-slate-300" data-testid={`ph-${k.chiave}`}>
                                {`{${k.chiave}}`} <Copy size={11} className="opacity-50" />
                            </button>
                        ))}
                    </div>
                </Card>

                {(sel.immagini || []).length > 0 && (
                    <Card className="p-4 border-violet-200" data-testid="mf-designer-card">
                        <div className="flex items-center justify-between mb-2">
                            <div className="text-sm font-medium text-violet-900 flex items-center gap-1"><PenTool size={14} /> Posiziona la firma (trascina sul documento)</div>
                            <Button onClick={salvaCampi} disabled={savingCampi} size="sm" className="bg-violet-600 hover:bg-violet-700" data-testid="mf-save-campi">
                                {savingCampi ? <Loader2 size={14} className="animate-spin mr-1" /> : <Save size={14} className="mr-1" />} Salva posizione nel modello
                            </Button>
                        </div>
                        <p className="text-xs text-slate-500 mb-3">In alternativa ai segnaposto {"{firma}"}, puoi trascinare qui il riquadro di firma: la posizione viene salvata nel modello e riusata ad ogni invio.</p>
                        <FirmaDesigner pages={sel.pages} immagini={sel.immagini} campi={campi} onChange={setCampi} campiDisp={campiDisp} />
                    </Card>
                )}

                <ProvaCompila modello={sel} />
            </div>
        );
    }

    return (
        <div className="space-y-5" data-testid="modelli-firma-page">
            <div className="flex items-center gap-2">
                <FileSignature className="text-violet-600" />
                <h2 className="text-xl font-light text-slate-800">Modelli Firma</h2>
            </div>

            <Card className="p-4 border-violet-200 bg-violet-50/40">
                <div className="text-sm font-medium text-violet-900 mb-2">Carica un nuovo modello (PDF o Word)</div>
                <div className="flex flex-wrap items-end gap-3">
                    <div className="flex-1 min-w-[220px]">
                        <Label className="text-xs">Nome modello</Label>
                        <Input value={uploadNome} onChange={(e) => setUploadNome(e.target.value)}
                            placeholder="Es. Dichiarazione IVASS 128" data-testid="mf-nome" />
                    </div>
                    <label className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-violet-600 hover:bg-violet-700 text-white text-sm cursor-pointer" data-testid="mf-upload">
                        <Upload size={15} /> Sfoglia file
                        <input type="file" accept=".pdf,.docx,.doc" hidden onChange={(e) => upload(e.target.files?.[0])} />
                    </label>
                </div>
                <div
                    onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                    onDragLeave={() => setDragOver(false)}
                    onDrop={(e) => { e.preventDefault(); setDragOver(false); upload(e.dataTransfer.files?.[0]); }}
                    className={`mt-3 border-2 border-dashed rounded-lg p-6 text-center text-sm transition ${dragOver ? "border-violet-500 bg-violet-100 text-violet-800" : "border-violet-300 text-violet-600"}`}
                    data-testid="mf-dropzone">
                    <Upload size={20} className="inline mb-1" /><br />
                    Trascina qui il tuo <strong>PDF o Word</strong> già pronto (con i segnaposto {"{...}"})
                </div>
                <p className="text-[11px] text-slate-500 mt-2">Word (.docx/.doc) viene convertito automaticamente in PDF.</p>
            </Card>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {lista.map((m) => (
                    <Card key={m.id} className="p-4 hover:shadow-md transition" data-testid={`mf-card-${m.id}`}>
                        <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                                <div className="font-medium text-slate-800 truncate">{m.nome}</div>
                                <div className="text-xs text-slate-500">agg. {(m.updated_at || "").slice(0, 10)}</div>
                            </div>
                            <button onClick={() => elimina(m.id)} className="text-slate-400 hover:text-rose-600" data-testid={`mf-del-${m.id}`}><Trash2 size={16} /></button>
                        </div>
                        <Button variant="outline" className="w-full mt-3" onClick={() => apri(m.id)} data-testid={`mf-open-${m.id}`}>
                            <Play size={14} className="mr-1" /> Apri / Compila
                        </Button>
                    </Card>
                ))}
                {lista.length === 0 && <div className="text-sm text-slate-400 italic col-span-full">Nessun modello. Carica un PDF o Word per iniziare.</div>}
            </div>
        </div>
    );
}

function ProvaCompila({ modello }) {
    const [anagrafiche, setAnagrafiche] = useState([]);
    const [aid, setAid] = useState("");
    const [email, setEmail] = useState("");
    const [inviaFirma, setInviaFirma] = useState(true);
    const [loading, setLoading] = useState(false);
    const [res, setRes] = useState(null);

    useEffect(() => {
        api.get("/anagrafiche?limit=30").then((r) => {
            const items = Array.isArray(r.data) ? r.data : (r.data.items || []);
            setAnagrafiche(items);
        }).catch(() => {});
    }, []);

    const run = async () => {
        if (!aid) { toast.error("Seleziona un cliente"); return; }
        setLoading(true); setRes(null);
        try {
            const r = await api.post(`/firma/modelli/${modello.id}/compila`, {
                anagrafica_id: aid, invia_firma: inviaFirma, email_firmatario: email || undefined,
            });
            setRes(r.data);
            toast.success("Documento compilato");
        } catch (e) { toast.error(e.response?.data?.detail || "Errore compilazione"); }
        finally { setLoading(false); }
    };

    return (
        <Card className="p-4 border-emerald-200 bg-emerald-50/40" data-testid="mf-prova">
            <div className="text-sm font-medium text-emerald-900 mb-2 flex items-center gap-1"><Play size={14} /> Compila per un cliente</div>
            <div className="flex flex-wrap items-end gap-3">
                <div>
                    <Label className="text-xs">Cliente</Label>
                    <Select value={aid} onValueChange={setAid}>
                        <SelectTrigger className="w-64" data-testid="mf-prova-cliente"><SelectValue placeholder="Seleziona cliente" /></SelectTrigger>
                        <SelectContent>
                            {anagrafiche.map((a) => <SelectItem key={a.id} value={a.id}>{a.ragione_sociale || `${a.cognome || ""} ${a.nome || ""}`}</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
                <div>
                    <Label className="text-xs">Email firmatario (facolt.)</Label>
                    <Input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="in sandbox: tua email org" className="w-64" data-testid="mf-prova-email" />
                </div>
                <label className="flex items-center gap-1.5 text-xs text-slate-700 mb-2">
                    <input type="checkbox" checked={inviaFirma} onChange={(e) => setInviaFirma(e.target.checked)} /> Invia a Yousign
                </label>
                <Button onClick={run} disabled={loading} className="bg-emerald-600 hover:bg-emerald-700" data-testid="mf-prova-run">
                    {loading ? <Loader2 size={14} className="animate-spin mr-1" /> : <Play size={14} className="mr-1" />} Genera
                </Button>
            </div>
            {res && (
                <div className="mt-3 text-xs bg-white rounded border p-3" data-testid="mf-prova-res">
                    <div>✅ PDF generato: <strong>{res.nome_file}</strong> (salvato negli allegati del cliente)</div>
                    {!res.firma_presente && <div className="text-amber-600 mt-1">Nessun segnaposto {"{firma}"} nel documento: nessuna firma inviata.</div>}
                    {res.firma && (res.firma.ok
                        ? <div className="mt-1">✍️ Firma inviata — stato <strong>{res.firma.status}</strong>{res.firma.signing_url ? <> · <a href={res.firma.signing_url} target="_blank" rel="noreferrer" className="text-violet-700 underline">apri link firma</a></> : <> · email inviata a {res.firma.email}</>}</div>
                        : <div className="mt-1 text-rose-600">Firma non inviata: {res.firma.error}</div>)}
                </div>
            )}
        </Card>
    );
}
