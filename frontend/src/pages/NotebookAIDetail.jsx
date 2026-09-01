/**
 * Notebook AI — workspace stile NotebookLM: Fonti | Chat | Studio.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, API_BASE, formatError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Loading } from "@/components/Shared";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { toast } from "sonner";
import {
    Sparkles, ArrowLeft, Upload, FileText, Trash2, Send, Loader2, Database,
    BookOpen, HelpCircle, GraduationCap, Headphones, Download, X,
} from "lucide-react";

const ORIGINE_LABEL = { upload: "Upload", biblioteca: "Biblioteca", allegato: "Allegato" };

export default function NotebookAIDetail() {
    const { id } = useParams();
    const navigate = useNavigate();
    const [nb, setNb] = useState(null);
    const [messages, setMessages] = useState([]);
    const [openOutput, setOpenOutput] = useState(null);

    const load = useCallback(async () => {
        try {
            const [r1, r2] = await Promise.all([
                api.get(`/notebooklm/notebooks/${id}`),
                api.get(`/notebooklm/notebooks/${id}/messages`),
            ]);
            setNb(r1.data);
            setMessages(r2.data || []);
        } catch (e) {
            toast.error(formatError(e));
            navigate("/notebook-ai");
        }
    }, [id, navigate]);
    useEffect(() => { load(); }, [load]);

    // Poll outputs finché ce ne sono in generazione
    useEffect(() => {
        if (!nb?.outputs?.some((o) => o.stato === "generating")) return;
        const t = setInterval(async () => {
            const r = await api.get(`/notebooklm/notebooks/${id}`);
            setNb(r.data);
        }, 4000);
        return () => clearInterval(t);
    }, [nb, id]);

    if (!nb) return <Loading />;
    const fontiReady = (nb.fonti || []).filter((f) => f.stato === "ready").length;

    return (
        <div data-testid="notebook-detail-page" className="space-y-3">
            <div className="flex items-center gap-3 flex-wrap">
                <Button variant="ghost" size="sm" onClick={() => navigate("/notebook-ai")} data-testid="nb-back-btn">
                    <ArrowLeft size={15} />
                </Button>
                <Sparkles size={18} className="text-teal-600" />
                <div>
                    <div className="font-bold text-slate-800">{nb.titolo}</div>
                    {nb.descrizione && <div className="text-xs text-slate-500">{nb.descrizione}</div>}
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-[290px_1fr_290px] gap-3 items-start">
                <FontiPanel nb={nb} reload={load} />
                <ChatPanel id={id} messages={messages} setMessages={setMessages} fontiReady={fontiReady} />
                <StudioPanel id={id} nb={nb} reload={load} onOpen={setOpenOutput} fontiReady={fontiReady} />
            </div>

            <OutputDialog output={openOutput} onClose={() => setOpenOutput(null)} />
        </div>
    );
}

// ─────────────────────────── FONTI ───────────────────────────
function FontiPanel({ nb, reload }) {
    const fileRef = useRef(null);
    const [uploading, setUploading] = useState(false);
    const [crmOpen, setCrmOpen] = useState(false);

    const upload = async (files) => {
        if (!files?.length) return;
        setUploading(true);
        const fd = new FormData();
        [...files].forEach((f) => fd.append("files", f));
        try {
            await api.post(`/notebooklm/notebooks/${nb.id}/fonti/upload`, fd);
            toast.success(`${files.length} document${files.length === 1 ? "o caricato" : "i caricati"}`);
            reload();
        } catch (e) { toast.error(formatError(e)); }
        finally { setUploading(false); if (fileRef.current) fileRef.current.value = ""; }
    };

    const elimina = async (f) => {
        if (!window.confirm(`Rimuovere la fonte "${f.nome_file}"?`)) return;
        try { await api.delete(`/notebooklm/fonti/${f.id}`); reload(); }
        catch (e) { toast.error(formatError(e)); }
    };

    return (
        <Card className="p-3 space-y-2" data-testid="nb-fonti-panel">
            <div className="text-xs font-semibold text-slate-600 uppercase tracking-wider flex items-center gap-1.5">
                <FileText size={13} /> Fonti ({(nb.fonti || []).length})
            </div>
            <div className="grid grid-cols-2 gap-1.5">
                <Button size="sm" variant="outline" className="text-xs h-8"
                        disabled={uploading} onClick={() => fileRef.current?.click()}
                        data-testid="nb-upload-btn">
                    {uploading ? <Loader2 size={12} className="animate-spin mr-1" /> : <Upload size={12} className="mr-1" />}
                    Carica
                </Button>
                <Button size="sm" variant="outline" className="text-xs h-8"
                        onClick={() => setCrmOpen(true)} data-testid="nb-crm-btn">
                    <Database size={12} className="mr-1" /> Dal CRM
                </Button>
            </div>
            <input ref={fileRef} type="file" multiple accept=".pdf,.docx,.txt" className="hidden"
                   onChange={(e) => upload(e.target.files)} data-testid="nb-file-input" />

            <div className="space-y-1 max-h-[440px] overflow-y-auto">
                {(nb.fonti || []).length === 0 && (
                    <div className="text-[11px] text-slate-400 text-center py-6">
                        Carica PDF di condizioni di polizza, preventivi, normative o circolari.
                    </div>
                )}
                {(nb.fonti || []).map((f) => (
                    <div key={f.id} className="flex items-start gap-1.5 p-1.5 rounded hover:bg-slate-50 group"
                         data-testid={`nb-fonte-${f.id}`}>
                        <FileText size={13} className={f.stato === "ready" ? "text-teal-600 mt-0.5 shrink-0" : "text-rose-500 mt-0.5 shrink-0"} />
                        <div className="flex-1 min-w-0">
                            <div className="text-xs text-slate-700 truncate" title={f.nome_file}>{f.nome_file}</div>
                            <div className="text-[10px] text-slate-400">
                                {ORIGINE_LABEL[f.origine] || f.origine}
                                {f.n_pagine ? ` · ${f.n_pagine} pag.` : ""}
                                {f.stato === "errore" && <span className="text-rose-500"> · testo non leggibile</span>}
                            </div>
                        </div>
                        <button onClick={() => elimina(f)}
                                className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-rose-600 shrink-0"
                                data-testid={`nb-fonte-del-${f.id}`}>
                            <Trash2 size={12} />
                        </button>
                    </div>
                ))}
            </div>
            <CrmDocsDialog open={crmOpen} onClose={() => setCrmOpen(false)} notebookId={nb.id} reload={reload} />
        </Card>
    );
}

function CrmDocsDialog({ open, onClose, notebookId, reload }) {
    const [docs, setDocs] = useState(null);
    const [sel, setSel] = useState({ biblioteca: new Set(), allegati: new Set() });
    const [adding, setAdding] = useState(false);

    useEffect(() => {
        if (open) {
            api.get("/notebooklm/crm-docs").then((r) => setDocs(r.data));
            setSel({ biblioteca: new Set(), allegati: new Set() });
        }
    }, [open]);

    const toggle = (group, id) => setSel((s) => {
        const nx = new Set(s[group]);
        nx.has(id) ? nx.delete(id) : nx.add(id);
        return { ...s, [group]: nx };
    });

    const aggiungi = async () => {
        setAdding(true);
        try {
            await api.post(`/notebooklm/notebooks/${notebookId}/fonti/da-crm`, {
                biblioteca_ids: [...sel.biblioteca],
                allegato_ids: [...sel.allegati],
            });
            toast.success("Fonti aggiunte dal CRM");
            onClose(); reload();
        } catch (e) { toast.error(formatError(e)); }
        finally { setAdding(false); }
    };

    const nSel = sel.biblioteca.size + sel.allegati.size;
    return (
        <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
            <DialogContent className="max-w-lg" data-testid="nb-crm-dialog">
                <DialogHeader><DialogTitle>Aggiungi documenti dal CRM</DialogTitle></DialogHeader>
                {!docs ? <Loading /> : (
                    <div className="space-y-3 max-h-[420px] overflow-y-auto">
                        <div>
                            <div className="text-xs font-semibold text-slate-600 uppercase mb-1">Biblioteca ({docs.biblioteca.length})</div>
                            {docs.biblioteca.map((d) => (
                                <label key={d.id} className="flex items-center gap-2 text-xs p-1 rounded hover:bg-slate-50 cursor-pointer">
                                    <input type="checkbox" checked={sel.biblioteca.has(d.id)}
                                           onChange={() => toggle("biblioteca", d.id)}
                                           data-testid={`nb-crm-bibl-${d.id}`} />
                                    <span className="truncate flex-1">{d.nome_file}</span>
                                    <span className="text-[10px] text-slate-400 shrink-0">{d.cartella}</span>
                                </label>
                            ))}
                            {docs.biblioteca.length === 0 && <div className="text-[11px] text-slate-400">Nessun documento leggibile in Biblioteca.</div>}
                        </div>
                        <div>
                            <div className="text-xs font-semibold text-slate-600 uppercase mb-1">Allegati ({docs.allegati.length})</div>
                            {docs.allegati.map((d) => (
                                <label key={d.id} className="flex items-center gap-2 text-xs p-1 rounded hover:bg-slate-50 cursor-pointer">
                                    <input type="checkbox" checked={sel.allegati.has(d.id)}
                                           onChange={() => toggle("allegati", d.id)}
                                           data-testid={`nb-crm-alleg-${d.id}`} />
                                    <span className="truncate flex-1">{d.nome_file}</span>
                                    <span className="text-[10px] text-slate-400 shrink-0">{d.entita_tipo}</span>
                                </label>
                            ))}
                            {docs.allegati.length === 0 && <div className="text-[11px] text-slate-400">Nessun allegato PDF/testo.</div>}
                        </div>
                    </div>
                )}
                <div className="flex justify-end gap-2">
                    <Button variant="outline" size="sm" onClick={onClose}>Annulla</Button>
                    <Button size="sm" onClick={aggiungi} disabled={adding || nSel === 0}
                            className="bg-teal-600 hover:bg-teal-700" data-testid="nb-crm-add-btn">
                        {adding ? "Aggiunta…" : `Aggiungi ${nSel} font${nSel === 1 ? "e" : "i"}`}
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    );
}

// ─────────────────────────── CHAT ───────────────────────────
const CHIPS = [
    "Riassumi le garanzie principali",
    "Quali sono franchigie e scoperti?",
    "Cosa NON è coperto?",
    "Confronta i massimali tra i documenti",
];

function ChatPanel({ id, messages, setMessages, fontiReady }) {
    const [input, setInput] = useState("");
    const [busy, setBusy] = useState(false);
    const scrollRef = useRef(null);

    useEffect(() => {
        if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }, [messages, busy]);

    const send = async (raw) => {
        const msg = (raw || input).trim();
        if (!msg || busy) return;
        if (fontiReady === 0) { toast.error("Carica prima almeno una fonte leggibile"); return; }
        setInput("");
        setBusy(true);
        setMessages((m) => [...m, { role: "user", content: msg }, { role: "assistant", content: "" }]);
        try {
            const token = localStorage.getItem("token");
            const res = await fetch(`${API_BASE}/notebooklm/notebooks/${id}/chat`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    ...(token ? { Authorization: `Bearer ${token}` } : {}),
                },
                credentials: "include",
                body: JSON.stringify({ message: msg }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || `Errore ${res.status}`);
            }
            const reader = res.body.getReader();
            const dec = new TextDecoder();
            let buf = "";
            for (;;) {
                const { done, value } = await reader.read();
                if (done) break;
                buf += dec.decode(value, { stream: true });
                const events = buf.split("\n\n");
                buf = events.pop();
                for (const ev of events) {
                    if (!ev.startsWith("data: ")) continue;
                    const d = JSON.parse(ev.slice(6));
                    if (d.delta) {
                        setMessages((m) => {
                            const nx = [...m];
                            nx[nx.length - 1] = { ...nx[nx.length - 1], content: nx[nx.length - 1].content + d.delta };
                            return nx;
                        });
                    }
                }
            }
        } catch (e) {
            setMessages((m) => {
                const nx = [...m];
                nx[nx.length - 1] = { role: "assistant", content: `⚠️ ${e.message}` };
                return nx;
            });
        } finally { setBusy(false); }
    };

    const clearChat = async () => {
        if (!window.confirm("Svuotare la conversazione?")) return;
        await api.delete(`/notebooklm/notebooks/${id}/messages`);
        setMessages([]);
    };

    return (
        <Card className="flex flex-col h-[600px] overflow-hidden" data-testid="nb-chat-panel">
            <div className="px-3 py-2 border-b border-slate-200 flex items-center justify-between bg-teal-50/50">
                <div className="text-xs font-semibold text-slate-700 flex items-center gap-1.5">
                    <Sparkles size={13} className="text-teal-600" /> Chat con le fonti
                    <span className="text-[10px] font-normal text-slate-400">· risposte solo dai documenti, con citazioni</span>
                </div>
                {messages.length > 0 && (
                    <button onClick={clearChat} className="text-[10px] text-slate-400 hover:text-rose-600" data-testid="nb-chat-clear">
                        <X size={12} />
                    </button>
                )}
            </div>
            <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-3 min-h-0 bg-slate-50/30" data-testid="nb-chat-messages">
                {messages.length === 0 && (
                    <div className="text-center py-8">
                        <Sparkles size={32} className="mx-auto text-teal-300 mb-2" />
                        <div className="text-sm text-slate-500">
                            {fontiReady === 0 ? "Carica le fonti a sinistra, poi fai la tua prima domanda."
                                : "Fai una domanda sui documenti caricati."}
                        </div>
                    </div>
                )}
                {messages.map((m, i) => (
                    <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
                        <div className={`max-w-[88%] rounded-2xl px-3.5 py-2 text-sm ${
                            m.role === "user" ? "bg-teal-600 text-white" : "bg-white border border-slate-200 shadow-sm"
                        }`}>
                            {m.role === "user" ? (
                                <div className="whitespace-pre-wrap">{m.content}</div>
                            ) : (
                                <div className="prose prose-sm max-w-none prose-slate prose-p:my-1 prose-table:my-2 prose-td:px-2 prose-td:py-1 prose-th:px-2 prose-th:py-1 prose-th:bg-slate-100 prose-table:border prose-td:border prose-th:border prose-td:border-slate-200 prose-th:border-slate-200 prose-ul:my-1">
                                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                        {m.content || (busy && i === messages.length - 1 ? "…" : "")}
                                    </ReactMarkdown>
                                </div>
                            )}
                        </div>
                    </div>
                ))}
            </div>
            {!busy && messages.length === 0 && fontiReady > 0 && (
                <div className="px-3 py-1.5 border-t border-slate-100 flex flex-wrap gap-1.5">
                    {CHIPS.map((c, i) => (
                        <button key={i} onClick={() => send(c)}
                                className="text-[11px] px-2 py-0.5 bg-white border border-teal-200 rounded-full text-teal-700 hover:bg-teal-50"
                                data-testid={`nb-chip-${i}`}>
                            {c}
                        </button>
                    ))}
                </div>
            )}
            <form onSubmit={(e) => { e.preventDefault(); send(); }}
                  className="p-2.5 border-t border-slate-200 bg-white flex gap-2">
                <Input value={input} onChange={(e) => setInput(e.target.value)}
                       placeholder="Chiedi qualcosa sui documenti…" className="flex-1 text-sm"
                       disabled={busy} data-testid="nb-chat-input" />
                <Button type="submit" size="sm" className="bg-teal-600 hover:bg-teal-700"
                        disabled={busy || !input.trim()} data-testid="nb-chat-send">
                    {busy ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />}
                </Button>
            </form>
        </Card>
    );
}

// ─────────────────────────── STUDIO ───────────────────────────
const STUDIO_BTNS = [
    { tipo: "riassunto", label: "Riassunto", icon: BookOpen },
    { tipo: "faq", label: "FAQ", icon: HelpCircle },
    { tipo: "guida", label: "Guida studio", icon: GraduationCap },
];
const TIPO_ICON = { riassunto: BookOpen, faq: HelpCircle, guida: GraduationCap, audio: Headphones };

function StudioPanel({ id, nb, reload, onOpen, fontiReady }) {
    const genera = async (tipo) => {
        if (fontiReady === 0) { toast.error("Carica prima almeno una fonte leggibile"); return; }
        try {
            if (tipo === "audio") await api.post(`/notebooklm/notebooks/${id}/audio-overview`);
            else await api.post(`/notebooklm/notebooks/${id}/genera`, { tipo });
            toast.success("Generazione avviata — pochi istanti…");
            reload();
        } catch (e) { toast.error(formatError(e)); }
    };

    const apri = async (o) => {
        if (o.stato !== "ready") return;
        const r = await api.get(`/notebooklm/outputs/${o.id}`);
        onOpen(r.data);
    };

    const elimina = async (o, e) => {
        e.stopPropagation();
        if (!window.confirm("Eliminare questo output?")) return;
        await api.delete(`/notebooklm/outputs/${o.id}`);
        reload();
    };

    return (
        <Card className="p-3 space-y-2" data-testid="nb-studio-panel">
            <div className="text-xs font-semibold text-slate-600 uppercase tracking-wider">Studio</div>
            <div className="grid grid-cols-3 gap-1.5">
                {STUDIO_BTNS.map(({ tipo, label, icon: Icon }) => (
                    <Button key={tipo} size="sm" variant="outline"
                            className="text-[10px] h-auto py-2 flex-col gap-1"
                            onClick={() => genera(tipo)} data-testid={`nb-gen-${tipo}`}>
                        <Icon size={14} className="text-teal-600" />
                        {label}
                    </Button>
                ))}
            </div>
            <Button size="sm" variant="outline" className="w-full text-xs border-teal-300 text-teal-700 hover:bg-teal-50"
                    onClick={() => genera("audio")} data-testid="nb-gen-audio">
                <Headphones size={13} className="mr-1.5" /> Audio Overview (podcast 2 voci)
            </Button>

            <div className="space-y-1.5 max-h-[400px] overflow-y-auto pt-1">
                {(nb.outputs || []).map((o) => {
                    const Icon = TIPO_ICON[o.tipo] || BookOpen;
                    return (
                        <div key={o.id} onClick={() => apri(o)}
                             className={`p-2 rounded border text-xs group ${
                                 o.stato === "ready" ? "border-slate-200 hover:border-teal-300 cursor-pointer bg-white"
                                     : o.stato === "errore" ? "border-rose-200 bg-rose-50/50"
                                         : "border-amber-200 bg-amber-50/50"
                             }`}
                             data-testid={`nb-output-${o.id}`}>
                            <div className="flex items-center gap-1.5">
                                <Icon size={13} className="text-teal-600 shrink-0" />
                                <span className="flex-1 truncate font-medium text-slate-700">{o.titolo}</span>
                                {o.stato === "generating" && <Loader2 size={11} className="animate-spin text-amber-600 shrink-0" />}
                                <button onClick={(e) => elimina(o, e)}
                                        className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-rose-600 shrink-0">
                                    <Trash2 size={11} />
                                </button>
                            </div>
                            {o.stato === "generating" && (
                                <div className="text-[10px] text-amber-700 mt-0.5">{o.progress || "In generazione…"}</div>
                            )}
                            {o.stato === "errore" && (
                                <div className="text-[10px] text-rose-600 mt-0.5 truncate">{o.errore}</div>
                            )}
                        </div>
                    );
                })}
                {(nb.outputs || []).length === 0 && (
                    <div className="text-[11px] text-slate-400 text-center py-4">
                        Genera riassunti, FAQ, guide studio o un podcast audio dalle fonti.
                    </div>
                )}
            </div>
        </Card>
    );
}

function OutputDialog({ output, onClose }) {
    if (!output) return null;
    const token = localStorage.getItem("token") || "";
    const audioUrl = output.audio_path
        ? `${API_BASE}/notebooklm/outputs/${output.id}/audio?token=${encodeURIComponent(token)}`
        : null;
    return (
        <Dialog open onOpenChange={(v) => !v && onClose()}>
            <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto" data-testid="nb-output-dialog">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        {output.tipo === "audio" && <Headphones size={16} className="text-teal-600" />}
                        {output.titolo}
                    </DialogTitle>
                </DialogHeader>
                {audioUrl && (
                    <div className="space-y-2">
                        <audio controls className="w-full" src={audioUrl} data-testid="nb-audio-player" />
                        <a href={audioUrl} download className="inline-flex items-center gap-1 text-xs text-teal-700 hover:underline"
                           data-testid="nb-audio-download">
                            <Download size={12} /> Scarica MP3
                            {output.durata_stimata_min ? ` (~${output.durata_stimata_min} min)` : ""}
                        </a>
                        <div className="text-xs font-semibold text-slate-500 uppercase pt-2">Trascrizione</div>
                    </div>
                )}
                <div className="prose prose-sm max-w-none prose-slate prose-table:border prose-td:border prose-th:border prose-td:px-2 prose-th:px-2 prose-td:border-slate-200 prose-th:border-slate-200 prose-th:bg-slate-100">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{output.contenuto_md || ""}</ReactMarkdown>
                </div>
            </DialogContent>
        </Dialog>
    );
}
