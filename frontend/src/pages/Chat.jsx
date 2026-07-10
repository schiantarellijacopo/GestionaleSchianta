import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Send, MessageSquare, Paperclip, X, Download, FileText, Image as ImageIcon, MessageCircle, Phone, RefreshCcw } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

const BACKEND = process.env.REACT_APP_BACKEND_URL;

export default function Chat() {
    const { user } = useAuth();
    const [contatti, setContatti] = useState(null);
    const [sel, setSel] = useState(null);
    const [msgs, setMsgs] = useState([]);
    const [text, setText] = useState("");
    const [file, setFile] = useState(null);
    const [sending, setSending] = useState(false);
    const scrollRef = useRef();
    const fileInputRef = useRef();

    const loadContatti = () => api.get("/chat/utenti").then((r) => setContatti(r.data));
    const loadMsgs = (uid) => api.get("/chat/messaggi", { params: { con: uid } }).then((r) => setMsgs(r.data));

    useEffect(() => { loadContatti(); }, []);
    useEffect(() => {
        if (!sel) return;
        loadMsgs(sel.id);
        const t = setInterval(() => loadMsgs(sel.id), 5000);
        return () => clearInterval(t);
    }, [sel]);

    useEffect(() => {
        scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight);
    }, [msgs]);

    const invia = async (e) => {
        e?.preventDefault();
        if ((!text.trim() && !file) || !sel || sending) return;
        setSending(true);
        try {
            if (file) {
                // multipart: invia file + testo come query params
                const fd = new FormData();
                fd.append("file", file);
                await api.post("/chat/messaggi", fd, {
                    params: { destinatario_id: sel.id, testo: text || "" },
                    headers: { "Content-Type": "multipart/form-data" },
                });
            } else {
                // JSON: solo testo
                await api.post("/chat/messaggi", { destinatario_id: sel.id, testo: text });
            }
            setText("");
            setFile(null);
            if (fileInputRef.current) fileInputRef.current.value = "";
            loadMsgs(sel.id);
            loadContatti();
        } catch (err) {
            toast.error(err.response?.data?.detail || "Errore invio messaggio");
            console.warn("chat invia:", err?.message || err);
        } finally {
            setSending(false);
        }
    };

    const onFilePick = (e) => {
        const f = e.target.files?.[0];
        if (!f) return;
        if (f.size > 25 * 1024 * 1024) {
            toast.error("File troppo grande (max 25 MB)");
            return;
        }
        setFile(f);
    };

    return (
        <div data-testid="chat-page">
            <PageHeader title="Chat" subtitle="Conversazioni interne staff/clienti + WhatsApp Business" />

            <Tabs defaultValue="interna" className="mt-3">
                <TabsList data-testid="chat-tabs">
                    <TabsTrigger value="interna" data-testid="chat-tab-interna">
                        <MessageSquare size={14} className="mr-1.5" /> Chat interna
                    </TabsTrigger>
                    <TabsTrigger value="whatsapp" data-testid="chat-tab-whatsapp">
                        <MessageCircle size={14} className="mr-1.5 text-emerald-600" /> WhatsApp
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="interna" className="mt-3">
            <Card className="border-slate-200 overflow-hidden" style={{ height: "calc(100vh - 260px)" }}>
                <div className="grid grid-cols-12 h-full">
                    <div className="col-span-4 border-r border-slate-200 overflow-y-auto" data-testid="chat-contatti-list">
                        {contatti === null ? <Loading /> : contatti.length === 0 ? <Empty message="Nessun contatto" /> : (
                            <ul className="divide-y divide-slate-100">
                                {contatti.map((c) => (
                                    <li
                                        key={c.id}
                                        onClick={() => setSel(c)}
                                        data-testid={`chat-contact-${c.id}`}
                                        className={`px-4 py-3 cursor-pointer hover:bg-slate-50 ${sel?.id === c.id ? "bg-sky-50 border-l-2 border-sky-600" : ""}`}
                                    >
                                        <div className="flex items-center gap-3">
                                            <div className="w-9 h-9 rounded-full bg-slate-200 text-slate-700 flex items-center justify-center text-sm font-medium">
                                                {(c.name || "?").charAt(0).toUpperCase()}
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <div className="text-sm font-medium text-slate-900 truncate flex items-center justify-between gap-2">
                                                    <span className="truncate">{c.name}</span>
                                                    {c.unread > 0 && (
                                                        <span className="bg-sky-600 text-white rounded-full text-[10px] px-1.5 py-0.5 min-w-[18px] text-center" data-testid={`unread-${c.id}`}>
                                                            {c.unread}
                                                        </span>
                                                    )}
                                                </div>
                                                <div className="text-xs text-slate-500 truncate">
                                                    {c.role}{" "}
                                                    {c.ultimo_messaggio?.testo && `· ${c.ultimo_messaggio.testo.slice(0, 30)}`}
                                                    {c.ultimo_messaggio?.allegato_nome && !c.ultimo_messaggio?.testo && (
                                                        <span className="inline-flex items-center gap-1"><Paperclip size={10} />Allegato</span>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>

                    <div className="col-span-8 flex flex-col" data-testid="chat-conversation">
                        {!sel ? (
                            <div className="flex-1 flex items-center justify-center text-slate-400 text-sm">
                                <div className="text-center">
                                    <MessageSquare size={32} className="mx-auto mb-2 text-slate-300" />
                                    Seleziona un contatto per iniziare
                                </div>
                            </div>
                        ) : (
                            <>
                                <div className="px-4 py-3 border-b border-slate-200 bg-slate-50">
                                    <div className="font-medium text-slate-900">{sel.name}</div>
                                    <div className="text-xs text-slate-500">{sel.email} · {sel.role}</div>
                                </div>
                                <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-2 bg-slate-50">
                                    {msgs.length === 0 ? (
                                        <div className="text-center text-slate-400 text-sm py-8">Nessun messaggio. Scrivi qualcosa!</div>
                                    ) : msgs.map((m) => {
                                        const mine = m.mittente_id === user.id;
                                        return (
                                            <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`} data-testid={`msg-${m.id}`}>
                                                <div className={`max-w-[70%] px-3 py-2 rounded-lg text-sm ${mine ? "bg-sky-600 text-white" : "bg-white border border-slate-200 text-slate-800"}`}>
                                                    {m.testo && <div className="whitespace-pre-wrap break-words">{m.testo}</div>}
                                                    {m.allegato_id && (
                                                        <ChatAttachment
                                                            allegato_id={m.allegato_id}
                                                            nome={m.allegato_nome}
                                                            content_type={m.allegato_content_type}
                                                            mine={mine}
                                                        />
                                                    )}
                                                    <div className={`text-[10px] mt-1 ${mine ? "text-sky-100" : "text-slate-400"}`}>
                                                        {new Date(m.created_at).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })}
                                                    </div>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                                {file && (
                                    <div className="px-3 py-2 bg-sky-50 border-t border-sky-200 flex items-center gap-2" data-testid="chat-file-preview">
                                        <Paperclip size={14} className="text-sky-600" />
                                        <span className="text-xs text-sky-900 flex-1 truncate">{file.name}</span>
                                        <span className="text-[10px] text-slate-500">{(file.size / 1024).toFixed(1)} KB</span>
                                        <button
                                            type="button"
                                            onClick={() => { setFile(null); if (fileInputRef.current) fileInputRef.current.value = ""; }}
                                            className="p-1 rounded hover:bg-sky-100"
                                            data-testid="chat-file-clear"
                                        >
                                            <X size={12} />
                                        </button>
                                    </div>
                                )}
                                <form onSubmit={invia} className="border-t border-slate-200 p-3 flex gap-2 bg-white items-center">
                                    <input
                                        ref={fileInputRef}
                                        type="file"
                                        className="hidden"
                                        onChange={onFilePick}
                                        accept="image/*,application/pdf,.doc,.docx,.xls,.xlsx"
                                        data-testid="chat-file-input"
                                    />
                                    <Button
                                        type="button"
                                        variant="outline"
                                        size="icon"
                                        onClick={() => fileInputRef.current?.click()}
                                        data-testid="chat-attach-button"
                                        title="Allega file (max 25 MB)"
                                    >
                                        <Paperclip size={14} />
                                    </Button>
                                    <Input
                                        data-testid="chat-input"
                                        placeholder="Scrivi un messaggio..."
                                        value={text}
                                        onChange={(e) => setText(e.target.value)}
                                    />
                                    <Button
                                        type="submit"
                                        disabled={sending || (!text.trim() && !file)}
                                        data-testid="chat-send-button"
                                        className="bg-sky-700 hover:bg-sky-800"
                                    >
                                        <Send size={14} />
                                    </Button>
                                </form>
                            </>
                        )}
                    </div>
                </div>
            </Card>
                </TabsContent>

                <TabsContent value="whatsapp" className="mt-3">
                    <WhatsAppInbox />
                </TabsContent>
            </Tabs>
        </div>
    );
}


// =====================================================================
// TAB WHATSAPP — Inbox multi-istanza con vista chat live
// =====================================================================
function MessageAttachment({ msg }) {
    const [imgUrl, setImgUrl] = useState(null);
    const isImage = (msg.attachment_mimetype || "").startsWith("image/");
    const isAudio = (msg.attachment_mimetype || "").startsWith("audio/");
    const isVideo = (msg.attachment_mimetype || "").startsWith("video/");
    const hasAttachment = msg.has_media || msg.attachment_name;

    useEffect(() => {
        if (!hasAttachment || !isImage) return;
        let stopped = false;
        api.get(`/whatsapp-evo/messages/${msg.id}/media`, { responseType: "blob" })
            .then((r) => { if (!stopped) setImgUrl(URL.createObjectURL(r.data)); })
            .catch(() => { /* ignore */ });
        return () => { stopped = true; if (imgUrl) URL.revokeObjectURL(imgUrl); };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [msg.id, hasAttachment, isImage]);

    if (!hasAttachment) return null;

    const bytesLabel = msg.attachment_size
        ? msg.attachment_size > 1024 * 1024
            ? `${(msg.attachment_size / 1024 / 1024).toFixed(1)} MB`
            : `${Math.round(msg.attachment_size / 1024)} KB`
        : "";

    const download = async () => {
        try {
            const r = await api.get(`/whatsapp-evo/messages/${msg.id}/media`, { responseType: "blob" });
            const url = URL.createObjectURL(r.data);
            const a = document.createElement("a");
            a.href = url;
            a.download = msg.attachment_name || "allegato";
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (e) {
            toast.error("Errore download allegato");
        }
    };

    if (isImage) {
        return (
            <div className="mb-1">
                {imgUrl ? (
                    <img src={imgUrl} alt={msg.attachment_name || "immagine"}
                         className="max-w-full rounded cursor-pointer max-h-72 object-contain"
                         onClick={() => window.open(imgUrl, "_blank")}
                         data-testid={`wa-msg-img-${msg.id}`} />
                ) : (
                    <div className="flex items-center gap-2 py-6 px-4 bg-slate-100 rounded text-slate-500 text-xs">
                        <ImageIcon size={16} /> Caricamento immagine…
                    </div>
                )}
            </div>
        );
    }

    if (isVideo) {
        return (
            <div className="mb-1">
                <button onClick={download}
                        className="flex items-center gap-2 text-xs underline opacity-90"
                        data-testid={`wa-msg-video-${msg.id}`}>
                    <Download size={13} /> Video — {msg.attachment_name} {bytesLabel && `(${bytesLabel})`}
                </button>
            </div>
        );
    }

    if (isAudio) {
        return (
            <div className="mb-1">
                <button onClick={download}
                        className="flex items-center gap-2 text-xs underline opacity-90"
                        data-testid={`wa-msg-audio-${msg.id}`}>
                    <Download size={13} /> 🎵 Audio {bytesLabel && `(${bytesLabel})`}
                </button>
            </div>
        );
    }

    // documento / altro
    return (
        <button onClick={download}
                className="flex items-center gap-2 py-1.5 px-2 bg-black/10 rounded text-xs mb-1 hover:bg-black/20"
                data-testid={`wa-msg-doc-${msg.id}`}>
            <FileText size={14} />
            <div className="text-left">
                <div className="font-medium truncate max-w-[220px]">{msg.attachment_name || "documento"}</div>
                {bytesLabel && <div className="text-[10px] opacity-70">{bytesLabel}</div>}
            </div>
            <Download size={12} />
        </button>
    );
}


function WhatsAppInbox() {
    const [instances, setInstances] = useState([]);
    const [selInst, setSelInst] = useState(null);       // istanza selezionata
    const [chats, setChats] = useState([]);
    const [selChat, setSelChat] = useState(null);       // { number, anagrafica_id?, anagrafica_nome? }
    const [msgs, setMsgs] = useState([]);
    const [text, setText] = useState("");
    const [sending, setSending] = useState(false);
    const [reconnecting, setReconnecting] = useState(false);
    const [savingDiary, setSavingDiary] = useState(false);
    const [uploadingFile, setUploadingFile] = useState(false);
    const scrollRef = useRef();
    const fileInputRef = useRef();

    // Carica istanze
    useEffect(() => {
        api.get("/whatsapp-evo/instances").then((r) => {
            setInstances(r.data || []);
            const first = (r.data || []).find((i) => (i.state_live || i.state) === "open") || (r.data || [])[0];
            if (first) setSelInst(first.instance_name);
        }).catch(() => setInstances([]));
    }, []);

    // Carica chat per istanza (con gestione errore graceful "Riconnessione…")
    useEffect(() => {
        if (!selInst) return;
        let stopped = false;
        const load = async () => {
            try {
                const r = await api.get(`/whatsapp-evo/instances/${selInst}/chats`);
                if (!stopped) { setChats(r.data || []); setReconnecting(false); }
            } catch {
                if (!stopped) setReconnecting(true);
            }
        };
        load();
        const t = setInterval(load, 5000);
        return () => { stopped = true; clearInterval(t); };
    }, [selInst]);

    // Carica messaggi conversazione selezionata
    useEffect(() => {
        if (!selInst || !selChat?.number) { setMsgs([]); return; }
        let stopped = false;
        const load = async () => {
            try {
                const r = await api.get(`/whatsapp-evo/instances/${selInst}/messages`, {
                    params: { number: selChat.number, limit: 100 },
                });
                if (!stopped) { setMsgs((r.data || []).slice().reverse()); setReconnecting(false); }
            } catch {
                if (!stopped) setReconnecting(true);
            }
        };
        load();
        const t = setInterval(load, 3000);
        return () => { stopped = true; clearInterval(t); };
    }, [selInst, selChat]);

    useEffect(() => {
        scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight);
    }, [msgs]);

    const invia = async (e) => {
        e?.preventDefault();
        if (!selInst || !selChat?.number || !text.trim() || sending) return;
        setSending(true);
        try {
            await api.post(`/whatsapp-evo/instances/${selInst}/send-text`, {
                number: selChat.number, text: text.trim(),
            });
            setText("");
            const r = await api.get(`/whatsapp-evo/instances/${selInst}/messages`, {
                params: { number: selChat.number, limit: 100 },
            });
            setMsgs((r.data || []).slice().reverse());
        } catch (err) {
            toast.error(err.response?.data?.detail || "Errore invio");
        } finally { setSending(false); }
    };

    // Invio allegato (PDF/immagine/documento) via WhatsApp
    const inviaFile = async (file) => {
        if (!file || !selInst || !selChat?.number) return;
        if (file.size > 15 * 1024 * 1024) { toast.error("File max 15 MB"); return; }
        setUploadingFile(true);
        try {
            const base64 = await new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => {
                    const result = reader.result || "";
                    const b64 = String(result).split(",")[1] || String(result);
                    resolve(b64);
                };
                reader.onerror = reject;
                reader.readAsDataURL(file);
            });
            await api.post(`/whatsapp-evo/instances/${selInst}/send-media`, {
                number: selChat.number,
                media_base64: base64,
                filename: file.name,
                mimetype: file.type || "application/octet-stream",
                caption: text.trim() || null,
            });
            toast.success(`Allegato inviato: ${file.name}`);
            setText("");
            if (fileInputRef.current) fileInputRef.current.value = "";
            const r = await api.get(`/whatsapp-evo/instances/${selInst}/messages`, {
                params: { number: selChat.number, limit: 100 },
            });
            setMsgs((r.data || []).slice().reverse());
        } catch (err) {
            toast.error(err.response?.data?.detail || "Errore invio allegato");
        } finally { setUploadingFile(false); }
    };

    // Salva conversazione WhatsApp nel diario del cliente
    const salvaNelDiario = async () => {
        if (!selChat?.anagrafica_id) {
            toast.error("Cliente non associato — impossibile salvare nel diario");
            return;
        }
        setSavingDiary(true);
        try {
            const r = await api.post(`/whatsapp-evo/instances/${selInst}/save-to-diary`, {
                number: selChat.number,
                anagrafica_id: selChat.anagrafica_id,
            });
            toast.success(`${r.data.messaggi_salvati} messaggi salvati nel diario di ${selChat.anagrafica_nome}`);
        } catch (err) {
            toast.error(err.response?.data?.detail || "Errore salvataggio diario");
        } finally { setSavingDiary(false); }
    };

    if (instances.length === 0) {
        return (
            <Card className="p-8 text-center text-slate-500">
                <MessageCircle size={32} className="mx-auto mb-2 text-slate-300" />
                <div className="text-sm">Nessuna istanza WhatsApp configurata.</div>
                <div className="text-xs mt-1">
                    Vai in <a href="/librerie" className="text-sky-700 underline">Librerie → Comunicazioni</a> per crearne una.
                </div>
            </Card>
        );
    }

    return (
        <div>
            {/* Tabs istanze (se più di 1) */}
            {instances.length > 1 && (
                <div className="flex gap-1 mb-3 overflow-x-auto">
                    {instances.map((inst) => {
                        const st = inst.state_live || inst.state;
                        return (
                            <button
                                key={inst.instance_name}
                                onClick={() => { setSelInst(inst.instance_name); setSelChat(null); }}
                                className={`px-3 py-1.5 text-xs rounded-md border whitespace-nowrap ${selInst === inst.instance_name ? "bg-emerald-600 text-white border-emerald-600" : "bg-white border-slate-300 text-slate-700 hover:border-emerald-400"}`}
                                data-testid={`wa-inst-tab-${inst.instance_name}`}
                            >
                                {st === "open" && <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400 mr-1.5" />}
                                {inst.agenzia_nome}
                            </button>
                        );
                    })}
                </div>
            )}

            <Card className="border-slate-200 overflow-hidden" style={{ height: "calc(100vh - 300px)" }}>
                {reconnecting && (
                    <div className="bg-amber-50 border-b border-amber-200 px-3 py-1.5 text-xs text-amber-800 flex items-center gap-2">
                        <span className="inline-block w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
                        Riconnessione in corso alle Evolution API…
                    </div>
                )}
                <div className="grid grid-cols-12 h-full">
                    {/* Lista chat */}
                    <div className="col-span-4 border-r border-slate-200 overflow-y-auto" data-testid="wa-chats-list">
                        <div className="px-3 py-2 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
                            <div className="text-xs font-medium text-slate-700">
                                Conversazioni ({chats.length})
                            </div>
                            <button onClick={() => { setSelChat(null); }} className="text-slate-400 hover:text-slate-700" title="Refresh">
                                <RefreshCcw size={12} />
                            </button>
                        </div>
                        {chats.length === 0 ? (
                            <div className="p-6 text-center text-xs text-slate-400">
                                Nessuna conversazione ancora.<br />
                                I messaggi in ingresso appariranno qui.
                            </div>
                        ) : (
                            <ul className="divide-y divide-slate-100">
                                {chats.map((c) => (
                                    <li
                                        key={c.number}
                                        onClick={() => setSelChat(c)}
                                        data-testid={`wa-chat-${c.number}`}
                                        className={`px-4 py-3 cursor-pointer hover:bg-slate-50 ${selChat?.number === c.number ? "bg-emerald-50 border-l-2 border-emerald-600" : ""}`}
                                    >
                                        <div className="flex items-center gap-3">
                                            <div className={`w-9 h-9 rounded-full flex items-center justify-center ${c.anagrafica_id ? "bg-sky-100 text-sky-700" : "bg-emerald-100 text-emerald-700"}`}>
                                                {c.anagrafica_id ? (c.anagrafica_nome || "?").charAt(0).toUpperCase() : <Phone size={14} />}
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <div className="text-sm font-medium text-slate-900 truncate flex items-center gap-1">
                                                    {c.anagrafica_nome || c.last_push_name || `+${c.number}`}
                                                    {c.anagrafica_id && (
                                                        <span className="text-[9px] px-1 py-0 rounded bg-sky-100 text-sky-700 border border-sky-200" title="Cliente in anagrafica">
                                                            CLIENTE
                                                        </span>
                                                    )}
                                                </div>
                                                {c.anagrafica_nome && (
                                                    <div className="text-[10px] text-slate-500 font-mono">+{c.number}</div>
                                                )}
                                                <div className="text-xs text-slate-500 truncate">
                                                    {c.last_direction === "out" && <span className="text-emerald-600">➜ </span>}
                                                    {c.last_text?.slice(0, 40) || "(allegato)"}
                                                </div>
                                                <div className="text-[10px] text-slate-400">
                                                    {c.count_in} in · {c.count_out} out
                                                </div>
                                            </div>
                                        </div>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>

                    {/* Conversazione */}
                    <div className="col-span-8 flex flex-col" data-testid="wa-conversation">
                        {!selChat ? (
                            <div className="flex-1 flex items-center justify-center text-slate-400 text-sm">
                                <div className="text-center">
                                    <MessageCircle size={32} className="mx-auto mb-2 text-slate-300" />
                                    Seleziona una conversazione
                                </div>
                            </div>
                        ) : (
                            <>
                                <div className="border-b border-slate-200 px-4 py-2 bg-slate-50 flex items-center gap-2 flex-wrap">
                                    <div className={`w-8 h-8 rounded-full flex items-center justify-center ${selChat.anagrafica_id ? "bg-sky-100 text-sky-700 font-medium" : "bg-emerald-100 text-emerald-700"}`}>
                                        {selChat.anagrafica_id ? (selChat.anagrafica_nome || "?").charAt(0).toUpperCase() : <Phone size={13} />}
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="text-sm font-medium truncate flex items-center gap-2">
                                            {selChat.anagrafica_nome || `+${selChat.number}`}
                                            {selChat.anagrafica_id && (
                                                <a href={`/anagrafiche/${selChat.anagrafica_id}`} target="_blank" rel="noreferrer"
                                                   className="text-[10px] px-1.5 py-0 rounded bg-sky-100 text-sky-700 border border-sky-200 hover:bg-sky-200">
                                                    Apri scheda ↗
                                                </a>
                                            )}
                                        </div>
                                        {selChat.anagrafica_nome && (
                                            <div className="text-[10px] text-slate-500 font-mono">+{selChat.number}</div>
                                        )}
                                    </div>
                                    {selChat.anagrafica_id && (
                                        <Button
                                            size="sm" variant="outline"
                                            onClick={salvaNelDiario}
                                            disabled={savingDiary || msgs.length === 0}
                                            className="text-xs"
                                            data-testid="wa-save-diary"
                                        >
                                            {savingDiary ? "Salvataggio…" : "💾 Salva nel diario"}
                                        </Button>
                                    )}
                                </div>
                                <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-2 bg-slate-50">
                                    {msgs.map((m) => (
                                        <div key={m.id} className={`flex ${m.direction === "out" ? "justify-end" : "justify-start"}`}>
                                            <div className={`max-w-[70%] px-3 py-2 rounded-lg text-sm ${m.direction === "out" ? "bg-emerald-600 text-white" : "bg-white border border-slate-200 text-slate-800"}`}>
                                                <MessageAttachment msg={m} />
                                                {m.text && (
                                                    <div className="whitespace-pre-wrap break-words">{m.text}</div>
                                                )}
                                                {!m.text && !m.has_media && !m.attachment_name && (
                                                    <em className="opacity-60">(vuoto)</em>
                                                )}
                                                <div className={`text-[10px] mt-1 ${m.direction === "out" ? "text-emerald-100" : "text-slate-400"}`}>
                                                    {m.created_at?.slice(11, 16)}
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                                <form onSubmit={invia} className="border-t border-slate-200 p-3 flex gap-2 items-center bg-white">
                                    <input
                                        ref={fileInputRef}
                                        type="file"
                                        className="hidden"
                                        onChange={(e) => e.target.files?.[0] && inviaFile(e.target.files[0])}
                                        accept="image/*,application/pdf,.doc,.docx,.xls,.xlsx"
                                        data-testid="wa-file-input"
                                    />
                                    <Button
                                        type="button" variant="outline" size="icon"
                                        onClick={() => fileInputRef.current?.click()}
                                        disabled={uploadingFile}
                                        title="Allega file (max 15 MB) — la didascalia è il testo qui a fianco"
                                        data-testid="wa-attach-button"
                                    >
                                        <Paperclip size={14} />
                                    </Button>
                                    <Input
                                        value={text}
                                        onChange={(e) => setText(e.target.value)}
                                        placeholder={uploadingFile ? "Invio allegato…" : "Scrivi un messaggio WhatsApp..."}
                                        data-testid="wa-msg-input"
                                        disabled={uploadingFile}
                                    />
                                    <Button type="submit" disabled={sending || uploadingFile || !text.trim()} className="bg-emerald-600 hover:bg-emerald-700" data-testid="wa-msg-send">
                                        <Send size={14} />
                                    </Button>
                                </form>
                            </>
                        )}
                    </div>
                </div>
            </Card>
        </div>
    );
}


function ChatAttachment({ allegato_id, nome, content_type, mine }) {
    const url = `${BACKEND}/api/allegati/${allegato_id}/download`;
    const isImage = (content_type || "").startsWith("image/");
    const isPdf = content_type === "application/pdf";
    const Icon = isPdf ? FileText : ImageIcon;
    if (isImage) {
        return (
            <a href={url} target="_blank" rel="noreferrer" className="block mt-2" data-testid="chat-attach-image">
                <img
                    src={url}
                    alt={nome}
                    className="max-w-full max-h-60 rounded border border-slate-200 cursor-zoom-in"
                />
                <div className={`text-[10px] mt-1 truncate ${mine ? "text-sky-100" : "text-slate-500"}`}>{nome}</div>
            </a>
        );
    }
    return (
        <a
            href={url}
            target="_blank"
            rel="noreferrer"
            className={`inline-flex items-center gap-2 mt-2 px-2 py-1 rounded border ${
                mine ? "bg-sky-700 border-sky-500 text-white" : "bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100"
            }`}
            data-testid="chat-attach-file"
        >
            <Icon size={14} />
            <span className="text-xs truncate max-w-[180px]">{nome}</span>
            <Download size={12} className="opacity-60" />
        </a>
    );
}
