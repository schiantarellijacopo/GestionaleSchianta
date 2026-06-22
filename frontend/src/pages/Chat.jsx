import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Send, MessageSquare } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

export default function Chat() {
    const { user } = useAuth();
    const [contatti, setContatti] = useState(null);
    const [sel, setSel] = useState(null);
    const [msgs, setMsgs] = useState([]);
    const [text, setText] = useState("");
    const scrollRef = useRef();

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
        if (!text.trim() || !sel) return;
        try {
            await api.post("/chat/messaggi", { destinatario_id: sel.id, testo: text });
            setText("");
            loadMsgs(sel.id);
            loadContatti();
        } catch (err) { /* skip */ }
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
                                                        <span className="bg-sky-600 text-white rounded-full text-[10px] px-1.5 py-0.5 min-w-[18px] text-center">
                                                            {c.unread}
                                                        </span>
                                                    )}
                                                </div>
                                                <div className="text-xs text-slate-500 truncate">
                                                    {c.role} {c.ultimo_messaggio?.testo ? `· ${c.ultimo_messaggio.testo.slice(0, 30)}` : ""}
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
                                                    {m.testo}
                                                    <div className={`text-[10px] mt-1 ${mine ? "text-sky-100" : "text-slate-400"}`}>
                                                        {new Date(m.created_at).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })}
                                                    </div>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                                <form onSubmit={invia} className="border-t border-slate-200 p-3 flex gap-2 bg-white">
                                    <Input
                                        data-testid="chat-input"
                                        placeholder="Scrivi un messaggio..."
                                        value={text}
                                        onChange={(e) => setText(e.target.value)}
                                    />
                                    <Button type="submit" data-testid="chat-send-button" className="bg-sky-700 hover:bg-sky-800">
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
