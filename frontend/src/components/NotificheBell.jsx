/**
 * Dropdown notifiche in-app per il TopBar.
 *
 * Polling unread-count ogni 30s. Cliccando sulla campanella si apre il
 * pannello con le ultime 20 notifiche; "Segna tutte come lette" + link al
 * dettaglio. Aggiorna badge a destra della campanella.
 */
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, fmtDate } from "@/lib/api";
import { Bell, CheckCheck, X } from "lucide-react";

const TIPO_BG = {
    info: "bg-sky-50 border-l-sky-400",
    warning: "bg-amber-50 border-l-amber-400",
    success: "bg-emerald-50 border-l-emerald-400",
    danger: "bg-rose-50 border-l-rose-400",
};

export default function NotificheBell() {
    const nav = useNavigate();
    const [count, setCount] = useState(0);
    const [open, setOpen] = useState(false);
    const [items, setItems] = useState([]);
    const ref = useRef();

    const loadCount = () => {
        api.get("/notifications/me/unread-count")
            .then((r) => setCount(r.data?.count || 0))
            .catch(() => {});
    };
    const loadItems = () => {
        api.get("/notifications/me?limit=20")
            .then((r) => setItems(r.data || []))
            .catch(() => {});
    };

    useEffect(() => {
        loadCount();
        const t = setInterval(loadCount, 30000);
        return () => clearInterval(t);
    }, []);

    useEffect(() => {
        if (open) loadItems();
    }, [open]);

    useEffect(() => {
        const onClick = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
        document.addEventListener("mousedown", onClick);
        return () => document.removeEventListener("mousedown", onClick);
    }, []);

    const markAll = async () => {
        await api.post("/notifications/me/mark-read", {});
        setCount(0);
        loadItems();
    };

    const onItemClick = async (n) => {
        if (!n.letta) {
            await api.post("/notifications/me/mark-read", { ids: [n.id] });
            loadCount();
        }
        setOpen(false);
        if (n.link) nav(n.link);
    };

    const archive = async (e, n) => {
        e.stopPropagation();
        await api.delete(`/notifications/me/${n.id}`);
        setItems((arr) => arr.filter((x) => x.id !== n.id));
        loadCount();
    };

    return (
        <div ref={ref} className="relative">
            <button
                data-testid="notif-bell"
                onClick={() => setOpen((o) => !o)}
                className="relative p-2 rounded-full hover:bg-slate-100 text-slate-600"
                title={count > 0 ? `${count} notifiche non lette` : "Notifiche"}
            >
                <Bell size={18} />
                {count > 0 && (
                    <span
                        className="absolute top-0.5 right-0.5 min-w-[16px] h-4 bg-rose-600 text-white text-[9px] rounded-full flex items-center justify-center px-1 font-semibold"
                        data-testid="notif-count"
                    >
                        {count > 99 ? "99+" : count}
                    </span>
                )}
            </button>
            {open && (
                <div className="absolute top-full right-0 mt-1.5 w-[380px] max-h-[70vh] bg-white border border-slate-200 rounded-md shadow-xl overflow-hidden flex flex-col z-40" data-testid="notif-panel">
                    <div className="flex items-center justify-between px-3 py-2 border-b bg-slate-50">
                        <div className="font-semibold text-sm">Notifiche</div>
                        <div className="flex items-center gap-2">
                            <button
                                onClick={markAll}
                                className="text-[11px] text-slate-600 hover:text-slate-900 inline-flex items-center gap-1"
                                data-testid="notif-mark-all"
                            >
                                <CheckCheck size={12} /> Segna tutte
                            </button>
                            <button onClick={() => nav("/alert")} className="text-[11px] text-sky-700 hover:underline">
                                Gestione →
                            </button>
                        </div>
                    </div>
                    <div className="flex-1 overflow-y-auto">
                        {items.length === 0 ? (
                            <div className="text-center text-sm text-slate-500 py-8">Nessuna notifica</div>
                        ) : items.map((n) => (
                            <button
                                key={n.id}
                                onClick={() => onItemClick(n)}
                                className={`w-full text-left px-3 py-2.5 border-b border-slate-100 hover:bg-slate-50 transition-colors border-l-4 ${TIPO_BG[n.tipo] || TIPO_BG.info} ${!n.letta ? "font-medium" : "opacity-70"}`}
                                data-testid={`notif-item-${n.id}`}
                            >
                                <div className="flex items-start justify-between gap-2">
                                    <div className="flex-1 min-w-0">
                                        <div className="text-sm truncate">{n.titolo}</div>
                                        <div className="text-[11px] text-slate-600 line-clamp-2 mt-0.5">{n.messaggio}</div>
                                        <div className="text-[10px] text-slate-400 mt-1">{fmtDate(n.created_at)} {(n.created_at || "").slice(11, 16)}</div>
                                    </div>
                                    <button
                                        onClick={(e) => archive(e, n)}
                                        className="text-slate-400 hover:text-rose-600 p-1"
                                        title="Archivia"
                                    >
                                        <X size={12} />
                                    </button>
                                </div>
                            </button>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
