import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { MessageCircle, RefreshCw, FileText, Video, Mic, Image as ImageIcon } from "lucide-react";

// Anteprima conversazione stile WhatsApp (bolle + media)
function MediaBubble({ msg }) {
    const [url, setUrl] = useState(null);
    const [err, setErr] = useState(false);
    const isImage = (msg.attachment_mimetype || "").startsWith("image/") || msg.message_type === "imageMessage" || msg.message_type === "stickerMessage";
    useEffect(() => {
        let revoke;
        if (isImage) {
            api.get(`/whatsapp-evo/messages/${msg.id}/media`, { responseType: "blob" })
                .then((r) => { const u = URL.createObjectURL(r.data); revoke = u; setUrl(u); })
                .catch(() => setErr(true));
        }
        return () => { if (revoke) URL.revokeObjectURL(revoke); };
        /* eslint-disable-next-line */
    }, [msg.id]);

    if (isImage) {
        if (err) return <div className="text-[11px] text-slate-400 italic flex items-center gap-1"><ImageIcon size={12} /> immagine non disponibile</div>;
        if (!url) return <div className="w-40 h-40 bg-slate-200 rounded-md animate-pulse" />;
        return <img src={url} alt="allegato" className="rounded-md max-w-[220px] max-h-[260px] object-cover" data-testid={`wa-media-${msg.id}`} />;
    }
    const t = msg.message_type || "";
    const icon = t.includes("video") ? <Video size={14} /> : t.includes("audio") ? <Mic size={14} /> : <FileText size={14} />;
    const label = t.includes("video") ? "Video" : t.includes("audio") ? "Messaggio vocale" : (msg.attachment_name || "Documento");
    return (
        <a href={`${api.defaults.baseURL}/whatsapp-evo/messages/${msg.id}/media`} target="_blank" rel="noreferrer"
           className="flex items-center gap-2 text-xs bg-white/60 rounded-md px-2 py-1.5 text-slate-700 hover:underline">
            {icon} {label}
        </a>
    );
}

function fmtOra(iso) {
    if (!iso) return "";
    try { return new Date(iso).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }); }
    catch { return ""; }
}

export default function WhatsAppChatPreview({ anagrafica_id }) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);

    const load = () => {
        setLoading(true);
        api.get(`/anagrafiche/${anagrafica_id}/whatsapp-chat`)
            .then((r) => setData(r.data))
            .catch(() => setData({ messages: [] }))
            .finally(() => setLoading(false));
    };
    useEffect(load, [anagrafica_id]);

    const msgs = data?.messages || [];

    return (
        <div className="mt-4" data-testid="whatsapp-chat-preview">
            <div className="flex items-center justify-between mb-2">
                <h3 className="font-semibold flex items-center gap-2 text-slate-800">
                    <MessageCircle size={18} className="text-emerald-600" /> Anteprima chat WhatsApp
                    {data?.number && <span className="text-xs font-normal text-slate-400">· +{data.number}</span>}
                </h3>
                <button onClick={load} disabled={loading} className="text-xs text-emerald-700 hover:underline flex items-center gap-1" data-testid="wa-chat-refresh">
                    <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Aggiorna
                </button>
            </div>

            {!data?.number ? (
                <div className="text-center py-10 text-sm text-slate-500 bg-slate-50 rounded-lg border border-slate-200">
                    Nessun numero di cellulare valido su questa anagrafica.
                </div>
            ) : msgs.length === 0 ? (
                <div className="text-center py-10 text-sm text-slate-500 bg-slate-50 rounded-lg border border-slate-200">
                    Nessun messaggio WhatsApp registrato per questo numero.
                </div>
            ) : (
                <div
                    className="rounded-lg border border-slate-200 p-3 space-y-1.5 max-h-[560px] overflow-y-auto"
                    style={{ background: "#efeae2" }}
                    data-testid="wa-chat-thread"
                >
                    {msgs.map((m) => {
                        const out = m.direction === "out";
                        return (
                            <div key={m.id} className={`flex ${out ? "justify-end" : "justify-start"}`}>
                                <div
                                    className={`max-w-[78%] rounded-lg px-2.5 py-1.5 shadow-sm ${out ? "bg-[#d9fdd3]" : "bg-white"}`}
                                    data-testid={`wa-msg-${m.direction}`}
                                >
                                    {!out && m.push_name && <div className="text-[10px] font-semibold text-emerald-700 mb-0.5">{m.push_name}</div>}
                                    {(m.has_media || m.attachment_name) && <div className="mb-1"><MediaBubble msg={m} /></div>}
                                    {m.text && <div className="text-sm text-slate-800 whitespace-pre-wrap break-words">{m.text}</div>}
                                    <div className="text-[9px] text-slate-400 text-right mt-0.5">{fmtOra(m.created_at)}</div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
