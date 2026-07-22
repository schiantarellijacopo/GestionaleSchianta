/**
 * ChatCopilotPanel — Chat AI conversazionale multi-turno (Claude Sonnet 4.6).
 * Sostituisce il vecchio form statico "Cerca cliente → Genera consiglio".
 * - History persistente in Mongo (session_id)
 * - Suggerimenti rapidi cliccabili (initial + follow-up dinamici)
 * - Link Markdown cliccabili verso /anagrafiche, /polizze, /sinistri
 * - Input vocale via Web Speech API (opzionale)
 */
import { useState, useRef, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sparkles, Send, Mic, Loader2, Plus, Trash2, MessageSquare, ChevronRight } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const MARKDOWN_COMPONENTS = {
    // Render internal /anagrafiche, /polizze, ... as react-router Links
    a: function MdLink({ href, children }) {
        if (href && href.startsWith("/")) {
            return <Link to={href} className="text-violet-700 underline underline-offset-2 font-medium hover:text-violet-900">{children}</Link>;
        }
        return <a href={href} target="_blank" rel="noopener noreferrer" className="text-violet-700 underline">{children}</a>;
    },
};
import { toast } from "sonner";

const SUGGERIMENTI_INIZIALI = [
    "Riepilogo del mio portafoglio",
    "Polizze in scadenza nei prossimi 30 giorni",
    "Titoli sospesi da incassare",
    "Sinistri aperti in gestione",
    "Cerca cliente Rossi",
    "Cross-sell per Mario Bianchi",
];

const SUGGERIMENTI_FOLLOW_UP = [
    "Dammi più dettagli",
    "Filtra solo i più urgenti",
    "Genera un piano di azione",
    "Chi ha più polizze scadute?",
    "Quali rami mancano nel portafoglio?",
];

export default function ChatCopilotPanel() {
    const [sessionId, setSessionId] = useState(null);
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState("");
    const [busy, setBusy] = useState(false);
    const [sessions, setSessions] = useState([]);
    const [showSessions, setShowSessions] = useState(false);
    const [recording, setRecording] = useState(false);
    const scrollRef = useRef(null);

    // Carica lista sessioni
    const loadSessions = useCallback(() => {
        api.get("/copilot/sessions").then((r) => setSessions(r.data || [])).catch(() => setSessions([]));
    }, []);

    useEffect(() => { loadSessions(); }, [loadSessions]);

    useEffect(() => {
        if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }, [messages, busy]);

    const openSession = async (sid) => {
        setSessionId(sid);
        try {
            const r = await api.get(`/copilot/sessions/${sid}/messages`);
            setMessages((r.data || []).map((m) => ({
                role: m.role, text: m.content, ctx: m.context_summary || {},
            })));
        } catch {
            setMessages([]);
        }
    };

    const newChat = () => {
        setSessionId(null);
        setMessages([]);
        setInput("");
    };

    const deleteSession = async (sid, e) => {
        e.stopPropagation();
        if (!window.confirm("Eliminare la conversazione?")) return;
        try {
            await api.delete(`/copilot/sessions/${sid}`);
            if (sid === sessionId) newChat();
            loadSessions();
            toast.success("Conversazione eliminata");
        } catch { toast.error("Errore eliminazione"); }
    };

    const send = async (rawText) => {
        const msg = (rawText || input).trim();
        if (!msg || busy) return;
        setMessages((m) => [...m, { role: "user", text: msg }]);
        setInput("");
        setBusy(true);
        try {
            const r = await api.post("/copilot/chat", { message: msg, session_id: sessionId });
            const { answer, session_id: newSid, context_summary } = r.data;
            if (!sessionId && newSid) setSessionId(newSid);
            setMessages((m) => [...m, { role: "assistant", text: answer, ctx: context_summary || {} }]);
            loadSessions();  // refresh titoli sessioni
        } catch (e) {
            const err = e.response?.data?.detail || e.message;
            setMessages((m) => [...m, { role: "assistant", text: `⚠️ Errore: ${err}` }]);
        } finally { setBusy(false); }
    };

    // Voice input
    const startVoice = () => {
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SR) { toast.error("Il tuo browser non supporta la voce"); return; }
        const rec = new SR();
        rec.lang = "it-IT";
        rec.continuous = false;
        rec.interimResults = false;
        rec.onstart = () => setRecording(true);
        rec.onend = () => setRecording(false);
        rec.onresult = (e) => {
            const t = e.results[0][0].transcript;
            setInput(t);
            send(t);
        };
        rec.onerror = () => setRecording(false);
        rec.start();
    };

    // Suggerimenti dinamici: usa follow-up dopo il primo scambio
    const suggerimenti = messages.length === 0
        ? SUGGERIMENTI_INIZIALI
        : SUGGERIMENTI_FOLLOW_UP;

    return (
        <Card className="border-2 border-violet-200 bg-gradient-to-br from-violet-50/50 via-white to-sky-50/30 overflow-hidden" data-testid="chat-copilot-panel">
            <div className="flex flex-col md:flex-row min-h-[560px]">
                {/* Sidebar sessioni */}
                {showSessions && (
                    <div className="w-full md:w-56 border-r border-slate-200 bg-white/70 flex flex-col shrink-0" data-testid="chat-sessions-list">
                        <div className="p-2 border-b border-slate-200 flex items-center justify-between">
                            <span className="text-xs font-semibold text-slate-600 uppercase tracking-wider">Cronologia</span>
                            <Button size="sm" variant="ghost" className="h-6 px-2" onClick={newChat} data-testid="chat-new-btn">
                                <Plus size={12} />
                            </Button>
                        </div>
                        <div className="flex-1 overflow-y-auto p-1 space-y-1 max-h-[520px]">
                            {sessions.length === 0 ? (
                                <div className="text-[11px] text-slate-400 p-3 text-center">Nessuna conversazione</div>
                            ) : sessions.map((s) => (
                                <button
                                    key={s.id}
                                    onClick={() => openSession(s.id)}
                                    className={`w-full text-left text-xs p-2 rounded hover:bg-violet-100 group relative ${sessionId === s.id ? "bg-violet-100 border border-violet-300" : ""}`}
                                    data-testid={`chat-session-${s.id}`}
                                >
                                    <div className="flex items-start gap-1">
                                        <MessageSquare size={11} className="text-violet-500 mt-0.5 shrink-0" />
                                        <span className="flex-1 truncate">{s.title || "Nuova conversazione"}</span>
                                        <button onClick={(e) => deleteSession(s.id, e)}
                                            className="opacity-0 group-hover:opacity-100 text-rose-500 hover:text-rose-700"
                                            data-testid={`chat-del-${s.id}`}>
                                            <Trash2 size={10} />
                                        </button>
                                    </div>
                                </button>
                            ))}
                        </div>
                    </div>
                )}

                {/* Chat area */}
                <div className="flex-1 flex flex-col min-w-0">
                    {/* Header */}
                    <div className="px-4 py-3 border-b border-violet-200 bg-gradient-to-r from-violet-600/10 to-sky-600/10 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <Sparkles className="text-violet-600" size={18} />
                            <div>
                                <div className="font-semibold text-slate-800 text-sm">Assistente AI Conversazionale</div>
                                <div className="text-[10px] text-slate-500">Claude Sonnet 4.6 · accesso READ al tuo CRM · rispetta i tuoi permessi</div>
                            </div>
                        </div>
                        <div className="flex items-center gap-1">
                            <Button
                                size="sm" variant="outline" className="h-8 text-xs"
                                onClick={() => setShowSessions((s) => !s)}
                                data-testid="chat-toggle-sessions"
                            >
                                <MessageSquare size={12} className="mr-1" />
                                {sessions.length} chat
                            </Button>
                            <Button
                                size="sm" variant="outline" className="h-8 text-xs border-violet-300 text-violet-700"
                                onClick={newChat}
                                data-testid="chat-new-conv"
                            >
                                <Plus size={12} className="mr-1" />
                                Nuova
                            </Button>
                        </div>
                    </div>

                    {/* Messages */}
                    <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3 min-h-[380px] max-h-[520px] bg-slate-50/30" data-testid="chat-messages">
                        {messages.length === 0 && (
                            <div className="text-center py-6 space-y-3">
                                <Sparkles size={36} className="mx-auto text-violet-400" />
                                <div>
                                    <div className="font-semibold text-slate-700">Ciao! Chiedimi qualsiasi cosa sul tuo CRM.</div>
                                    <div className="text-xs text-slate-500 mt-1">Cerco clienti, polizze, sinistri, pagamenti sospesi, scadenze… con link cliccabili.</div>
                                </div>
                            </div>
                        )}
                        {messages.map((m, i) => (
                            <MessageBubble key={i} m={m} />
                        ))}
                        {busy && (
                            <div className="flex items-center gap-2 text-xs text-violet-600 pl-2">
                                <Loader2 size={12} className="animate-spin" /> Claude sta pensando…
                            </div>
                        )}
                    </div>

                    {/* Suggerimenti chip */}
                    {!busy && (
                        <div className="px-3 py-2 border-t border-slate-100 bg-white/60 flex flex-wrap gap-1.5" data-testid="chat-chips">
                            {suggerimenti.map((s, i) => (
                                <button
                                    key={i}
                                    onClick={() => send(s)}
                                    className="text-[11px] px-2.5 py-1 bg-white border border-violet-200 rounded-full text-violet-700 hover:bg-violet-50 hover:border-violet-400 transition-colors"
                                    data-testid={`chat-chip-${i}`}
                                >
                                    {s}
                                </button>
                            ))}
                        </div>
                    )}

                    {/* Input */}
                    <form onSubmit={(e) => { e.preventDefault(); send(); }}
                        className="p-3 border-t border-slate-200 bg-white flex gap-2 items-center">
                        <Input
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            placeholder='Es. "Titoli sospesi di Rossi ultimi 3 anni"'
                            className="flex-1 text-sm"
                            disabled={busy}
                            data-testid="chat-input"
                        />
                        <Button
                            type="button" size="sm" variant="outline"
                            onClick={startVoice} disabled={busy}
                            className={recording ? "border-rose-400 bg-rose-50" : ""}
                            data-testid="chat-voice-btn"
                        >
                            <Mic size={13} className={recording ? "text-rose-600" : ""} />
                        </Button>
                        <Button
                            type="submit" size="sm" className="bg-violet-600 hover:bg-violet-700"
                            disabled={busy || !input.trim()}
                            data-testid="chat-send-btn"
                        >
                            <Send size={13} />
                        </Button>
                    </form>
                </div>
            </div>
        </Card>
    );
}

function MessageBubble({ m }) {
    const isUser = m.role === "user";
    return (
        <div className={isUser ? "flex justify-end" : "flex justify-start"}>
            <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 ${
                isUser ? "bg-sky-600 text-white" : "bg-white border border-slate-200 shadow-sm"
            }`}>
                {isUser ? (
                    <div className="text-sm whitespace-pre-wrap">{m.text}</div>
                ) : (
                    <>
                        <div className="prose prose-sm max-w-none prose-slate prose-p:my-1 prose-table:my-2 prose-a:text-violet-700 prose-a:font-medium prose-headings:my-2 prose-headings:text-slate-800 prose-td:px-2 prose-td:py-1 prose-th:px-2 prose-th:py-1 prose-th:bg-slate-100 prose-table:border prose-table:border-slate-200 prose-th:border prose-th:border-slate-200 prose-td:border prose-td:border-slate-200 prose-ul:my-1 prose-ol:my-1">
                            <ReactMarkdown
                                remarkPlugins={[remarkGfm]}
                                components={MARKDOWN_COMPONENTS}
                            >{m.text}</ReactMarkdown>
                        </div>
                        {m.ctx && Object.keys(m.ctx).length > 0 && (
                            <div className="text-[10px] text-slate-400 mt-2 pt-2 border-t border-slate-100 flex items-center gap-1 flex-wrap">
                                <ChevronRight size={9} />
                                {Object.entries(m.ctx).map(([k, v]) => (
                                    <span key={k} className="bg-violet-50 text-violet-700 px-1.5 py-0.5 rounded font-mono">
                                        {k}: {v}
                                    </span>
                                ))}
                            </div>
                        )}
                    </>
                )}
            </div>
        </div>
    );
}
