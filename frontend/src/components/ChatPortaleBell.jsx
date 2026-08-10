/**
 * Campanella dedicata ai messaggi non letti dal Portale Cliente.
 * Polling ogni 20s su GET /api/chat-portale/unread.
 * Al click porta l'admin sul tab "Portale Clienti" della pagina /chat.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { MessageCircle } from "lucide-react";

export default function ChatPortaleBell() {
    const nav = useNavigate();
    const [count, setCount] = useState(0);

    useEffect(() => {
        const load = () => api.get("/chat-portale/unread")
            .then((r) => setCount(r.data?.unread || 0))
            .catch(() => {});
        load();
        const t = setInterval(load, 20000);
        return () => clearInterval(t);
    }, []);

    return (
        <button
            data-testid="portale-chat-bell"
            onClick={() => nav("/chat?tab=portale")}
            className="relative p-2 rounded-full hover:bg-sky-50 text-slate-600 hover:text-sky-600 transition-colors"
            title={count > 0 ? `${count} messaggi non letti dal Portale Cliente` : "Chat Portale Cliente"}
        >
            <MessageCircle size={18} />
            {count > 0 && (
                <span
                    className="absolute top-0.5 right-0.5 min-w-[16px] h-4 bg-sky-600 text-white text-[9px] rounded-full flex items-center justify-center px-1 font-semibold"
                    data-testid="portale-chat-bell-count"
                >
                    {count > 99 ? "99+" : count}
                </span>
            )}
        </button>
    );
}
