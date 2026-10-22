import { useEffect, useRef, useState } from "react";
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
    FileSignature, Upload, Plus, Trash2, Save, ArrowLeft, PenTool, Type, Play, Loader2,
} from "lucide-react";

const COLORS = { dato: "#0ea5e9", firma: "#9333ea" };

export default function ModelliFirma() {
    const [lista, setLista] = useState([]);
    const [sel, setSel] = useState(null);         // modello aperto (detail)
    const [campi, setCampi] = useState([]);
    const [campiDisp, setCampiDisp] = useState([]);
    const [nuovoTipo, setNuovoTipo] = useState("dato");
    const [nuovaChiave, setNuovaChiave] = useState("nome_cliente");
    const [uploadNome, setUploadNome] = useState("");
    const [saving, setSaving] = useState(false);
    const dragRef = useRef(null);

    const loadLista = () => api.get("/firma/modelli").then((r) => setLista(r.data)).catch(() => {});
    useEffect(() => {
        loadLista();
        api.get("/firma/modelli/campi-disponibili").then((r) => setCampiDisp(r.data)).catch(() => {});
    }, []);

    const apri = async (mid) => {
        try {
            const r = await api.get(`/firma/modelli/${mid}`);
            setSel(r.data);
            setCampi(r.data.campi || []);
        } catch { toast.error("Errore apertura modello"); }
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
        } catch (e) { toast.error(e.response?.data?.detail || "Errore upload (carica un PDF)"); }
    };

    const aggiungiCampo = (page) => {
        const nuovo = {
            id: `tmp-${Date.now()}`, tipo: nuovoTipo,
            chiave: nuovoTipo === "dato" ? nuovaChiave : null,
            page, x: 0.3, y: 0.4, w: 0.35, h: nuovoTipo === "firma" ? 0.06 : 0.03,
            font_size: 11,
        };
        setCampi((c) => [...c, nuovo]);
    };

    const updateCampo = (id, patch) => setCampi((c) => c.map((x) => x.id === id ? { ...x, ...patch } : x));
    const removeCampo = (id) => setCampi((c) => c.filter((x) => x.id !== id));

    const salva = async () => {
        setSaving(true);
        try {
            await api.put(`/firma/modelli/${sel.id}`, { campi });
            toast.success("Campi salvati sul modello");
        } catch { toast.error("Errore salvataggio"); }
        finally { setSaving(false); }
    };

    const elimina = async (mid) => {
        if (!window.confirm("Eliminare questo modello?")) return;
        await api.delete(`/firma/modelli/${mid}`);
        if (sel?.id === mid) setSel(null);
        loadLista();
    };

    // ---- drag & resize ----
    const onPointerDown = (e, campo, mode) => {
        e.preventDefault();
        e.stopPropagation();
        const wrap = e.currentTarget.closest("[data-page-wrap]");
        const rect = wrap.getBoundingClientRect();
        dragRef.current = {
            id: campo.id, mode, rect,
            startX: e.clientX, startY: e.clientY,
            ox: campo.x, oy: campo.y, ow: campo.w, oh: campo.h,
        };
        window.addEventListener("pointermove", onPointerMove);
        window.addEventListener("pointerup", onPointerUp);
    };
    const onPointerMove = (e) => {
        const d = dragRef.current;
        if (!d) return;
        const dx = (e.clientX - d.startX) / d.rect.width;
        const dy = (e.clientY - d.startY) / d.rect.height;
        if (d.mode === "move") {
            updateCampo(d.id, {
                x: Math.min(0.98, Math.max(0, d.ox + dx)),
                y: Math.min(0.98, Math.max(0, d.oy + dy)),
            });
        } else {
            updateCampo(d.id, {
                w: Math.min(1, Math.max(0.05, d.ow + dx)),
                h: Math.min(0.3, Math.max(0.02, d.oh + dy)),
            });
        }
    };
    const onPointerUp = () => {
        dragRef.current = null;
        window.removeEventListener("pointermove", onPointerMove);
        window.removeEventListener("pointerup", onPointerUp);
    };

    const labelCampo = (c) => c.tipo === "firma" ? "FIRMA"
        : (campiDisp.find((k) => k.chiave === c.chiave)?.label || c.chiave);

    // ====== LISTA ======
    if (!sel) {
        return (
            <div className="space-y-5" data-testid="modelli-firma-page">
                <div className="flex items-center gap-2">
                    <FileSignature className="text-violet-600" />
                    <h1 className="text-2xl font-light text-slate-800">Modelli Firma</h1>
                </div>
                <Card className="p-4 border-violet-200 bg-violet-50/40">
                    <div className="text-sm font-medium text-violet-900 mb-2">Carica un nuovo modello (PDF)</div>
                    <div className="flex flex-wrap items-end gap-3">
                        <div className="flex-1 min-w-[220px]">
                            <Label className="text-xs">Nome modello</Label>
                            <Input value={uploadNome} onChange={(e) => setUploadNome(e.target.value)}
                                placeholder="Es. Dichiarazione IVASS 128" data-testid="mf-nome" />
                        </div>
                        <label className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-violet-600 hover:bg-violet-700 text-white text-sm cursor-pointer" data-testid="mf-upload">
                            <Upload size={15} /> Carica PDF
                            <input type="file" accept=".pdf" hidden onChange={(e) => upload(e.target.files?.[0])} />
                        </label>
                    </div>
                    <p className="text-[11px] text-slate-500 mt-2">Il supporto Word arriverà a breve: per ora da Word usa "Salva come → PDF".</p>
                </Card>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {lista.map((m) => (
                        <Card key={m.id} className="p-4 hover:shadow-md transition" data-testid={`mf-card-${m.id}`}>
                            <div className="flex items-start justify-between gap-2">
                                <div className="min-w-0">
                                    <div className="font-medium text-slate-800 truncate">{m.nome}</div>
                                    <div className="text-xs text-slate-500">{(m.campi?.length || 0)} campi · agg. {(m.updated_at || "").slice(0, 10)}</div>
                                </div>
                                <button onClick={() => elimina(m.id)} className="text-slate-400 hover:text-rose-600" data-testid={`mf-del-${m.id}`}><Trash2 size={16} /></button>
                            </div>
                            <Button variant="outline" className="w-full mt-3" onClick={() => apri(m.id)} data-testid={`mf-open-${m.id}`}>
                                <PenTool size={14} className="mr-1" /> Imposta campi
                            </Button>
                        </Card>
                    ))}
                    {lista.length === 0 && <div className="text-sm text-slate-400 italic col-span-full">Nessun modello. Carica un PDF per iniziare.</div>}
                </div>
            </div>
        );
    }

    // ====== EDITOR ======
    return (
        <div className="space-y-4" data-testid="mf-editor">
            <div className="flex items-center justify-between flex-wrap gap-2 sticky top-0 bg-white/90 backdrop-blur z-20 py-2 border-b">
                <div className="flex items-center gap-2">
                    <button onClick={() => setSel(null)} className="text-slate-500 hover:text-slate-800"><ArrowLeft size={18} /></button>
                    <h1 className="text-lg font-medium text-slate-800">{sel.nome}</h1>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                    <Select value={nuovoTipo} onValueChange={setNuovoTipo}>
                        <SelectTrigger className="w-32 h-9" data-testid="mf-tipo"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="dato"><span className="inline-flex items-center gap-1"><Type size={12} /> Dato</span></SelectItem>
                            <SelectItem value="firma"><span className="inline-flex items-center gap-1"><PenTool size={12} /> Firma</span></SelectItem>
                        </SelectContent>
                    </Select>
                    {nuovoTipo === "dato" && (
                        <Select value={nuovaChiave} onValueChange={setNuovaChiave}>
                            <SelectTrigger className="w-48 h-9" data-testid="mf-chiave"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                {campiDisp.map((k) => <SelectItem key={k.chiave} value={k.chiave}>{k.label}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    )}
                    <Button onClick={salva} disabled={saving} className="bg-violet-600 hover:bg-violet-700 h-9" data-testid="mf-salva">
                        {saving ? <Loader2 size={14} className="animate-spin mr-1" /> : <Save size={14} className="mr-1" />} Salva
                    </Button>
                </div>
            </div>

            <p className="text-xs text-slate-500">Scegli tipo campo e clicca <strong>+ su pagina</strong>, poi <strong>trascina</strong> il riquadro dove vuoi. L'angolo in basso a destra ridimensiona.</p>

            {(sel.immagini || []).map((img, pno) => (
                <div key={pno} className="relative mx-auto shadow border border-slate-200" style={{ maxWidth: 720 }}>
                    <div className="absolute -top-6 left-0 text-xs text-slate-500">Pagina {pno + 1}
                        <button onClick={() => aggiungiCampo(pno)} className="ml-2 inline-flex items-center gap-1 text-violet-600 hover:text-violet-800" data-testid={`mf-add-${pno}`}>
                            <Plus size={12} /> aggiungi campo
                        </button>
                    </div>
                    <div data-page-wrap className="relative select-none" style={{ width: "100%" }}>
                        <img src={img} alt={`pag ${pno + 1}`} className="w-full block pointer-events-none" draggable={false} />
                        {campi.filter((c) => c.page === pno).map((c) => (
                            <div key={c.id}
                                data-testid={`mf-box-${c.id}`}
                                onPointerDown={(e) => onPointerDown(e, c, "move")}
                                className="absolute rounded-sm text-[10px] font-semibold text-white flex items-center justify-center cursor-move group"
                                style={{
                                    left: `${c.x * 100}%`, top: `${c.y * 100}%`,
                                    width: `${c.w * 100}%`, height: `${c.h * 100}%`,
                                    background: (COLORS[c.tipo]) + "cc", border: `1px solid ${COLORS[c.tipo]}`,
                                }}>
                                <span className="truncate px-1 pointer-events-none">{labelCampo(c)}</span>
                                <button onPointerDown={(e) => e.stopPropagation()} onClick={() => removeCampo(c.id)}
                                    className="absolute -top-2 -right-2 bg-white text-rose-600 rounded-full border border-rose-300 w-4 h-4 flex items-center justify-center opacity-0 group-hover:opacity-100" data-testid={`mf-boxdel-${c.id}`}>×</button>
                                <div onPointerDown={(e) => onPointerDown(e, c, "resize")}
                                    className="absolute bottom-0 right-0 w-3 h-3 bg-white border border-slate-400 cursor-nwse-resize" />
                            </div>
                        ))}
                    </div>
                </div>
            ))}

            <ProvaCompila modello={sel} />
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
                anagrafica_id: aid, invia_firma: inviaFirma,
                email_firmatario: email || undefined,
            });
            setRes(r.data);
            toast.success("Documento compilato");
        } catch (e) { toast.error(e.response?.data?.detail || "Errore compilazione"); }
        finally { setLoading(false); }
    };

    return (
        <Card className="p-4 mt-6 border-emerald-200 bg-emerald-50/40" data-testid="mf-prova">
            <div className="text-sm font-medium text-emerald-900 mb-2 flex items-center gap-1"><Play size={14} /> Prova: compila per un cliente</div>
            <div className="flex flex-wrap items-end gap-3">
                <div className="min-w-[220px]">
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
                    <input type="checkbox" checked={inviaFirma} onChange={(e) => setInviaFirma(e.target.checked)} /> Invia a Yousign (firma)
                </label>
                <Button onClick={run} disabled={loading} className="bg-emerald-600 hover:bg-emerald-700" data-testid="mf-prova-run">
                    {loading ? <Loader2 size={14} className="animate-spin mr-1" /> : <Play size={14} className="mr-1" />} Genera
                </Button>
            </div>
            {res && (
                <div className="mt-3 text-xs bg-white rounded border p-3" data-testid="mf-prova-res">
                    <div>✅ PDF generato: <strong>{res.nome_file}</strong> (salvato negli allegati del cliente)</div>
                    {res.firma && (res.firma.ok
                        ? <div className="mt-1">✍️ Firma inviata — stato <strong>{res.firma.status}</strong>{res.firma.signing_url ? <> · <a href={res.firma.signing_url} target="_blank" rel="noreferrer" className="text-violet-700 underline">apri link firma</a></> : <> · email inviata a {res.firma.email}</>}</div>
                        : <div className="mt-1 text-rose-600">Firma non inviata: {res.firma.error}</div>)}
                </div>
            )}
        </Card>
    );
}
