/**
 * CopilotWidget — Floating chat AI omnipresente.
 * Stessa esperienza di ChatCopilotPanel (Assistente AI Conversazionale · Claude Sonnet 4.6):
 *  - Chat multi-turno con memoria sessione persistente
 *  - Chip suggerimenti iniziali + follow-up dinamici
 *  - Link Markdown cliccabili verso schede CRM
 *  - Tabelle GFM, formato italiano
 *  - Input vocale (Web Speech API it-IT)
 *  - Rispetta permessi RBAC del backend
 */
import { useState, useRef, useEffect } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { Sparkles, X, Send, Mic, Loader2, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const CHIP_INIT = [
    "Riepilogo del mio portafoglio",
    "Polizze in scadenza nei prossimi 30 giorni",
    "Titoli sospesi da incassare",
    "Sinistri aperti",
];
const CHIP_FOLLOW = [
    "Dammi più dettagli",
    "Filtra solo i più urgenti",
    "Chi ha più polizze scadute?",
    "Genera un piano di azione",
];

const MD_COMPONENTS = {
    a: function MdLink({ href, children }) {
        if (href && href.startsWith("/")) {
            return <Link to={href} className="text-violet-700 underline underline-offset-2 font-medium hover:text-violet-900">{children}</Link>;
        }
        return <a href={href} target="_blank" rel="noopener noreferrer" className="text-violet-700 underline">{children}</a>;
    },
};

export default function CopilotWidget() {
    const [open, setOpen] = useState(false);
    const [sessionId, setSessionId] = useState(null);
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState("");
    const [busy, setBusy] = useState(false);
    const [recording, setRecording] = useState(false);
    const scrollRef = useRef(null);

    useEffect(() => {
        if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }, [messages, busy]);

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
        } catch (e) {
            const err = e.response?.data?.detail || e.message;
            setMessages((m) => [...m, { role: "assistant", text: `⚠️ Errore: ${err}` }]);
        } finally { setBusy(false); }
    };

    const newChat = () => {
        setSessionId(null);
        setMessages([]);
        setInput("");
    };

    const startVoice = () => {
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SR) return;
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

    if (!open) {
        return (
            <button
                onClick={() => setOpen(true)}
                className="fixed bottom-6 right-6 z-50 bg-gradient-to-br from-violet-600 to-sky-600 text-white rounded-full w-14 h-14 shadow-lg hover:scale-105 transition-transform flex items-center justify-center"
                data-testid="copilot-fab"
                title="Assistente AI Conversazionale"
            >
                <Sparkles size={22} />
            </button>
        );
    }

    const chips = messages.length === 0 ? CHIP_INIT : CHIP_FOLLOW;

    return (
        <div className="fixed bottom-6 right-6 z-50 w-[440px] max-w-[95vw] h-[640px] max-h-[85vh] bg-white rounded-xl shadow-2xl border border-violet-200 flex flex-col overflow-hidden" data-testid="copilot-panel">
            {/* Header stile Assistente AI */}
            <div className="px-4 py-3 border-b border-violet-200 bg-gradient-to-r from-violet-600/10 to-sky-600/10 flex items-center justify-between shrink-0">
                <div className="flex items-center gap-2">
                    <Sparkles className="text-violet-600" size={18} />
                    <div>
                        <div className="font-semibold text-slate-800 text-sm">Assistente AI Conversazionale</div>
                        <div className="text-[10px] text-slate-500">Claude Sonnet 4.6 · accesso READ al tuo CRM · rispetta i tuoi permessi</div>
                    </div>
                </div>
                <div className="flex items-center gap-1">
                    <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={newChat} data-testid="copilot-new" title="Nuova conversazione">
                        <Plus size={13} />
                    </Button>
                    <button onClick={() => setOpen(false)} className="hover:bg-white/60 rounded p-1" data-testid="copilot-close">
                        <X size={16} />
                    </button>
                </div>
            </div>

            {/* Messages */}
            <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-3 bg-slate-50/30" data-testid="copilot-messages">
                {messages.length === 0 && (
                    <div className="text-center py-6 space-y-2">
                        <Sparkles size={32} className="mx-auto text-violet-400" />
                        <div className="text-sm font-semibold text-slate-700">Ciao! Chiedimi qualsiasi cosa sul tuo CRM.</div>
                        <div className="text-[11px] text-slate-500 px-4">Cerco clienti, polizze, sinistri, pagamenti sospesi, scadenze… con link cliccabili.</div>
                    </div>
                )}
                {messages.map((m, i) => <Bubble key={i} m={m} />)}
                {busy && (
                    <div className="flex items-center gap-2 text-xs text-violet-600 pl-2">
                        <Loader2 size={12} className="animate-spin" /> Claude sta pensando…
                    </div>
                )}
            </div>

            {/* Chips */}
            {!busy && (
                <div className="px-3 py-2 border-t border-slate-100 bg-white/60 flex flex-wrap gap-1.5 shrink-0" data-testid="copilot-chips">
                    {chips.map((s, i) => (
                        <button
                            key={i}
                            onClick={() => send(s)}
                            className="text-[11px] px-2.5 py-1 bg-white border border-violet-200 rounded-full text-violet-700 hover:bg-violet-50 hover:border-violet-400 transition-colors"
                            data-testid={`copilot-chip-${i}`}
                        >{s}</button>
                    ))}
                </div>
            )}

            {/* Input */}
            <form onSubmit={(e) => { e.preventDefault(); send(); }} className="p-3 border-t border-slate-200 bg-white flex gap-1.5 items-center shrink-0">
                <Input
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder='Es. "Titoli sospesi di Rossi ultimi 3 anni"'
                    className="flex-1 text-sm"
                    disabled={busy}
                    data-testid="copilot-input"
                />
                <Button type="button" size="sm" variant="outline"
                    onClick={startVoice} disabled={busy}
                    className={recording ? "border-rose-400 bg-rose-50" : ""}
                    data-testid="copilot-voice">
                    <Mic size={13} className={recording ? "text-rose-600" : ""} />
                </Button>
                <Button type="submit" size="sm" className="bg-violet-600 hover:bg-violet-700"
                    disabled={busy || !input.trim()}
                    data-testid="copilot-send">
                    <Send size={13} />
                </Button>
            </form>
        </div>
    );
}

function Bubble({ m }) {
    const isUser = m.role === "user";
    return (
        <div className={isUser ? "flex justify-end" : "flex justify-start"}>
            <div className={`max-w-[92%] rounded-2xl px-3.5 py-2 text-sm ${
                isUser ? "bg-sky-600 text-white" : "bg-white border border-slate-200 shadow-sm"
            }`}>
                {isUser ? (
                    <div className="whitespace-pre-wrap">{m.text}</div>
                ) : (
                    <>
                        <div className="prose prose-sm max-w-none prose-slate prose-p:my-1 prose-table:my-2 prose-a:text-violet-700 prose-a:font-medium prose-headings:my-2 prose-headings:text-slate-800 prose-td:px-2 prose-td:py-1 prose-th:px-2 prose-th:py-1 prose-th:bg-slate-100 prose-table:border prose-table:border-slate-200 prose-th:border prose-th:border-slate-200 prose-td:border prose-td:border-slate-200 prose-ul:my-1 prose-ol:my-1">
                            <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>{m.text}</ReactMarkdown>
                        </div>
                        {m.ctx && Object.keys(m.ctx).length > 0 && (
                            <div className="text-[10px] text-slate-400 mt-2 pt-1.5 border-t border-slate-100 flex items-center gap-1 flex-wrap">
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
