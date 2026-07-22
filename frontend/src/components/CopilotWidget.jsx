/**
 * CopilotWidget — floating button + chat modal disponibile da qualsiasi pagina.
 * Legge dati dal CRM via /api/copilot/chat e opzionalmente riproduce audio TTS.
 */
import { useState, useRef, useEffect } from "react";
import { api } from "@/lib/api";
import { Sparkles, X, Send, Mic, Volume2, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import ReactMarkdown from "react-markdown";

export default function CopilotWidget() {
    const [open, setOpen] = useState(false);
    const [messages, setMessages] = useState([
        { role: "assistant", text: "Ciao! Sono il tuo Copilot AI. Chiedimi qualsiasi cosa sui dati del CRM: clienti, polizze, pagamenti, sinistri, veicoli. Es: *\"Trova le polizze scadute nel 2023 di Rossi\"*." },
    ]);
    const [input, setInput] = useState("");
    const [busy, setBusy] = useState(false);
    const [useTts, setUseTts] = useState(false);
    const [recording, setRecording] = useState(false);
    const scrollRef = useRef(null);
    const audioRef = useRef(null);

    useEffect(() => {
        if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }, [messages]);

    const send = async (text) => {
        const msg = (text || input).trim();
        if (!msg || busy) return;
        setMessages((m) => [...m, { role: "user", text: msg }]);
        setInput("");
        setBusy(true);
        try {
            const r = await api.post("/copilot/chat", { message: msg, use_tts: useTts });
            const ans = r.data.answer;
            setMessages((m) => [...m, { role: "assistant", text: ans, ctx: r.data.context_summary }]);
            if (useTts && r.data.audio_available) playTts(ans);
        } catch (e) {
            setMessages((m) => [...m, { role: "assistant", text: `⚠️ Errore: ${e.response?.data?.detail || e.message}` }]);
        } finally { setBusy(false); }
    };

    const playTts = async (text) => {
        try {
            const r = await api.post("/copilot/tts", { text: text.substring(0, 400) }, { responseType: "blob" });
            const url = URL.createObjectURL(r.data);
            if (audioRef.current) { audioRef.current.src = url; audioRef.current.play(); }
        } catch { /* silent */ }
    };

    // Voice input via Web Speech API (browser nativa)
    const startVoiceInput = () => {
        const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRec) { alert("Il tuo browser non supporta la voce"); return; }
        const rec = new SpeechRec();
        rec.lang = "it-IT";
        rec.continuous = false;
        rec.interimResults = false;
        rec.onstart = () => setRecording(true);
        rec.onend = () => setRecording(false);
        rec.onresult = (e) => {
            const transcript = e.results[0][0].transcript;
            setInput(transcript);
            send(transcript);
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
                title="Copilot AI"
            >
                <Sparkles size={22} />
            </button>
        );
    }

    return (
        <div className="fixed bottom-6 right-6 z-50 w-[420px] max-w-[95vw] h-[600px] max-h-[85vh] bg-white rounded-xl shadow-2xl border border-slate-200 flex flex-col" data-testid="copilot-panel">
            <div className="bg-gradient-to-r from-violet-600 to-sky-600 text-white p-3 rounded-t-xl flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Sparkles size={16} />
                    <span className="font-semibold text-sm">Copilot AI · Programma Assicurativo</span>
                </div>
                <button onClick={() => setOpen(false)} className="hover:bg-white/20 rounded p-1" data-testid="copilot-close">
                    <X size={16} />
                </button>
            </div>

            <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-3 bg-slate-50" data-testid="copilot-messages">
                {messages.map((m, i) => (
                    <div key={i} className={`${m.role === "user" ? "ml-8" : "mr-8"}`}>
                        <div className={`inline-block rounded-lg px-3 py-2 text-sm max-w-full ${m.role === "user" ? "bg-sky-600 text-white ml-auto" : "bg-white border border-slate-200"}`}>
                            {m.role === "assistant"
                                ? <div className="prose prose-sm max-w-none prose-slate"><ReactMarkdown>{m.text}</ReactMarkdown></div>
                                : m.text}
                        </div>
                        {m.ctx && Object.keys(m.ctx).length > 0 && (
                            <div className="text-[10px] text-slate-400 mt-1 ml-1">
                                🔍 {Object.entries(m.ctx).map(([k, v]) => `${k}: ${v}`).join(" · ")}
                            </div>
                        )}
                    </div>
                ))}
                {busy && <div className="text-xs text-slate-500 flex items-center gap-1"><Loader2 size={12} className="animate-spin" /> Sto pensando…</div>}
            </div>

            <div className="p-3 border-t border-slate-200 bg-white rounded-b-xl">
                <div className="flex gap-1 mb-2 items-center text-[11px]">
                    <label className="flex items-center gap-1 cursor-pointer">
                        <input type="checkbox" checked={useTts} onChange={(e) => setUseTts(e.target.checked)} data-testid="copilot-tts-toggle" />
                        <Volume2 size={11} /> Voce
                    </label>
                    <span className="text-slate-300 mx-1">·</span>
                    <span className="text-slate-400">GPT-5.4</span>
                </div>
                <form onSubmit={(e) => { e.preventDefault(); send(); }} className="flex gap-1">
                    <Input
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        placeholder='Es. "Pagamenti di Mario Rossi negli ultimi 3 anni"'
                        className="text-sm"
                        disabled={busy}
                        data-testid="copilot-input"
                    />
                    <Button type="button" size="sm" variant="outline" onClick={startVoiceInput} disabled={busy} data-testid="copilot-mic-btn"
                            className={recording ? "bg-rose-100 border-rose-300" : ""}>
                        <Mic size={13} className={recording ? "text-rose-600" : ""} />
                    </Button>
                    <Button type="submit" size="sm" className="bg-violet-600 hover:bg-violet-700" disabled={busy || !input.trim()} data-testid="copilot-send-btn">
                        <Send size={13} />
                    </Button>
                </form>
            </div>
            <audio ref={audioRef} className="hidden" />
        </div>
    );
}
