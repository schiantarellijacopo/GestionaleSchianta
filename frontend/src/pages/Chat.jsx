import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Send, MessageSquare, Paperclip, X, Download, FileText, Image as ImageIcon } from "lucide-react";
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
            <PageHeader title="Chat interna" subtitle="Conversazioni dirette con lo staff e i clienti" />

            <Card className="border-slate-200 overflow-hidden" style={{ height: "calc(100vh - 220px)" }}>
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
