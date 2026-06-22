import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { Search, Users, FileText, AlertTriangle, Bell, X } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

export default function TopBar() {
    const { user } = useAuth();
    const [q, setQ] = useState("");
    const [results, setResults] = useState(null);
    const [open, setOpen] = useState(false);
    const [notif, setNotif] = useState({ totale: 0 });
    const ref = useRef();
    const nav = useNavigate();

    // ricerca con debounce
    useEffect(() => {
        if (!q || q.length < 2) { setResults(null); return; }
        const t = setTimeout(() => {
            api.get("/search", { params: { q } }).then((r) => setResults(r.data));
        }, 250);
        return () => clearTimeout(t);
    }, [q]);

    // notifiche polling
    useEffect(() => {
        const load = () => api.get("/notifiche/sommario").then((r) => setNotif(r.data)).catch(() => {});
        load();
        const t = setInterval(load, 30000);
        return () => clearInterval(t);
    }, []);

    // chiudi su click esterno
    useEffect(() => {
        const onClick = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
        document.addEventListener("mousedown", onClick);
        return () => document.removeEventListener("mousedown", onClick);
    }, []);

    // keyboard shortcut: cmd/ctrl+K
    useEffect(() => {
        const onKey = (e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "k") {
                e.preventDefault();
                ref.current?.querySelector("input")?.focus();
                setOpen(true);
            }
            if (e.key === "Escape") setOpen(false);
        };
        document.addEventListener("keydown", onKey);
        return () => document.removeEventListener("keydown", onKey);
    }, []);

    const go = (path) => {
        setOpen(false); setQ(""); setResults(null);
        nav(path);
    };

    const total = (results?.anagrafiche?.length || 0) + (results?.polizze?.length || 0) + (results?.sinistri?.length || 0);

    return (
        <div className="sticky top-0 z-30 bg-white border-b border-slate-200 px-6 py-2.5 flex items-center gap-4" data-testid="topbar">
            <div ref={ref} className="relative flex-1 max-w-xl mx-auto">
                <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                    type="text"
                    value={q}
                    onChange={(e) => { setQ(e.target.value); setOpen(true); }}
                    onFocus={() => setOpen(true)}
                    placeholder="Cerca clienti, polizze, targhe, sinistri... (Ctrl+K)"
                    data-testid="global-search-input"
                    className="w-full pl-9 pr-9 py-2 text-sm rounded-md border border-slate-200 bg-slate-50 focus:bg-white focus:border-sky-400 focus:ring-2 focus:ring-sky-100 outline-none transition"
                />
                {q && (
                    <button onClick={() => { setQ(""); setResults(null); }} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700">
                        <X size={14} />
                    </button>
                )}

                {open && results && total > 0 && (
                    <div
                        data-testid="global-search-results"
                        className="absolute top-full left-0 right-0 mt-1.5 bg-white border border-slate-200 rounded-md shadow-xl overflow-hidden max-h-[60vh] overflow-y-auto"
                    >
                        {results.anagrafiche?.length > 0 && (
                            <ResultGroup
                                title="Clienti" icon={<Users size={12} />} items={results.anagrafiche}
                                render={(a) => (
                                    <button key={a.id} onClick={() => go(`/anagrafiche/${a.id}`)} className="w-full text-left px-4 py-2 hover:bg-sky-50 border-b border-slate-50">
                                        <div className="font-medium text-sm">{a.ragione_sociale}</div>
                                        <div className="text-[11px] text-slate-500 num">{a.codice_fiscale || ""} · {a.comune || ""}</div>
                                    </button>
                                )}
                            />
                        )}
                        {results.polizze?.length > 0 && (
                            <ResultGroup
                                title="Polizze" icon={<FileText size={12} />} items={results.polizze}
                                render={(p) => (
                                    <button key={p.id} onClick={() => go(`/polizze/${p.id}`)} className="w-full text-left px-4 py-2 hover:bg-sky-50 border-b border-slate-50">
                                        <div className="font-medium text-sm">{p.numero_polizza}</div>
                                        <div className="text-[11px] text-slate-500">
                                            {p.contraente_nome || "—"} · {p.ramo} · <span className="badge badge-neutral">{p.stato}</span>
                                            {p.targa && <span className="ml-1 text-sky-700 num">{p.targa}</span>}
                                        </div>
                                    </button>
                                )}
                            />
                        )}
                        {results.sinistri?.length > 0 && (
                            <ResultGroup
                                title="Sinistri" icon={<AlertTriangle size={12} />} items={results.sinistri}
                                render={(s) => (
                                    <button key={s.id} onClick={() => go(`/sinistri`)} className="w-full text-left px-4 py-2 hover:bg-sky-50 border-b border-slate-50">
                                        <div className="font-medium text-sm">{s.numero_sinistro}</div>
                                        <div className="text-[11px] text-slate-500">{s.data_avvenimento} · {s.stato}</div>
                                    </button>
                                )}
                            />
                        )}
                    </div>
                )}
                {open && q.length >= 2 && results && total === 0 && (
                    <div className="absolute top-full left-0 right-0 mt-1.5 bg-white border border-slate-200 rounded-md p-4 text-center text-sm text-slate-500">
                        Nessun risultato per <b>&quot;{q}&quot;</b>
                    </div>
                )}
            </div>

            <button
                data-testid="notif-bell"
                onClick={() => nav("/chat")}
                className="relative p-2 rounded-full hover:bg-slate-100 text-slate-600"
                title={notif.totale > 0 ? `${notif.totale} notifiche` : "Nessuna notifica"}
            >
                <Bell size={18} />
                {notif.totale > 0 && (
                    <span className="absolute top-0.5 right-0.5 min-w-[16px] h-4 bg-rose-600 text-white text-[9px] rounded-full flex items-center justify-center px-1 font-semibold">
                        {notif.totale > 99 ? "99+" : notif.totale}
                    </span>
                )}
            </button>
            <div className="text-sm text-slate-600 hidden md:block">
                <span className="font-medium">{user?.name}</span>
                <span className="text-xs text-slate-400 ml-1">({user?.role})</span>
            </div>
        </div>
    );
}

function ResultGroup({ title, icon, items, render }) {
    return (
        <div>
            <div className="px-4 py-1.5 bg-slate-50 text-[10px] uppercase tracking-widest font-semibold text-slate-500 inline-flex items-center gap-1 w-full">
                {icon} {title} ({items.length})
            </div>
            {items.map(render)}
        </div>
    );
}
