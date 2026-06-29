import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { Search, Users, FileText, AlertTriangle, Receipt, Building2, X, Menu, User as UserIcon } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useSidebar } from "./Layout";
import NotificheBell from "./NotificheBell";

export default function TopBar() {
    const { user } = useAuth();
    const { setMobileOpen = () => {} } = useSidebar() || {};
    const [q, setQ] = useState("");
    const [results, setResults] = useState(null);
    const [open, setOpen] = useState(false);
    const [azienda, setAzienda] = useState(null);
    const ref = useRef();
    const nav = useNavigate();

    // Carica config azienda per il logo (uno-shot)
    useEffect(() => {
        api.get("/librerie/azienda").then((r) => setAzienda(r.data)).catch(() => {});
    }, []);

    // ricerca con debounce
    useEffect(() => {
        if (!q || q.length < 2) { setResults(null); return; }
        const t = setTimeout(() => {
            api.get("/search", { params: { q } }).then((r) => setResults(r.data));
        }, 250);
        return () => clearTimeout(t);
    }, [q]);

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

    const total = (results?.anagrafiche?.length || 0) + (results?.polizze?.length || 0)
        + (results?.sinistri?.length || 0) + (results?.titoli?.length || 0) + (results?.compagnie?.length || 0);

    return (
        <div className="sticky top-0 z-30 bg-white border-b border-slate-200 px-3 sm:px-6 py-2.5 flex items-center gap-2 sm:gap-4" data-testid="topbar">
            {/* Hamburger - solo mobile/tablet */}
            <button
                type="button"
                onClick={() => setMobileOpen(true)}
                className="lg:hidden text-slate-700 hover:text-slate-900 p-1"
                aria-label="Apri menu"
                data-testid="hamburger-btn"
            >
                <Menu size={22} />
            </button>

            {/* Utente loggato — avatar + nome (alto a sinistra, vicino al menu) */}
            <button
                type="button"
                onClick={() => nav("/profilo")}
                className="hidden md:flex items-center gap-2 px-2 py-1 rounded-md hover:bg-slate-100 transition-colors"
                data-testid="topbar-user-block"
                title="Profilo utente"
            >
                {user?.avatar_url ? (
                    <img src={user.avatar_url} alt={user.name}
                        className="w-8 h-8 rounded-full object-cover border-2 border-slate-200" />
                ) : (
                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-sky-500 to-violet-600 text-white flex items-center justify-center text-xs font-semibold">
                        {(user?.name || user?.email || "?").trim().split(/\s+/).map((s) => s[0]).slice(0, 2).join("").toUpperCase()}
                    </div>
                )}
                <div className="text-left leading-tight">
                    <div className="text-sm font-semibold text-slate-800">{user?.name || user?.email}</div>
                    <div className="text-[10px] text-slate-500 uppercase tracking-wider">{user?.role}</div>
                </div>
            </button>

            <div ref={ref} className="relative flex-1 max-w-xl mx-auto">
                <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                    type="text"
                    value={q}
                    onChange={(e) => { setQ(e.target.value); setOpen(true); }}
                    onFocus={() => setOpen(true)}
                    placeholder="Cerca clienti, polizze, ramo, prodotto, telefono, email, targa, sinistri… (Ctrl+K)"
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
                                        <div className="text-[11px] text-slate-500 num">
                                            {a.codice_fiscale || ""} · {a.comune || ""}
                                            {a.cellulare && <> · 📱 {a.cellulare}</>}
                                            {a.email && <> · ✉ {a.email}</>}
                                        </div>
                                    </button>
                                )}
                            />
                        )}
                        {results.polizze?.length > 0 && (
                            <ResultGroup
                                title="Polizze" icon={<FileText size={12} />} items={results.polizze}
                                render={(p) => (
                                    <button key={p.id} onClick={() => go(`/polizze/${p.id}`)} className="w-full text-left px-4 py-2 hover:bg-sky-50 border-b border-slate-50">
                                        <div className="font-medium text-sm">N. {p.numero_polizza}{p.prodotto && <span className="ml-1 text-slate-600">· {p.prodotto}</span>}</div>
                                        <div className="text-[11px] text-slate-500">
                                            {p.contraente_nome || "—"} · {p.ramo} · <span className="badge badge-neutral">{p.stato}</span>
                                            {p.targa && <span className="ml-1 text-sky-700 num">{p.targa}</span>}
                                        </div>
                                    </button>
                                )}
                            />
                        )}
                        {results.titoli?.length > 0 && (
                            <ResultGroup
                                title="Titoli" icon={<Receipt size={12} />} items={results.titoli}
                                render={(t) => (
                                    <button key={t.id} onClick={() => go(`/polizze/${t.polizza_id}`)} className="w-full text-left px-4 py-2 hover:bg-sky-50 border-b border-slate-50">
                                        <div className="font-medium text-sm">Titolo {t.numero_titolo || "—"} · Pol. {t.numero_polizza}</div>
                                        <div className="text-[11px] text-slate-500">{t.contraente_nome || "—"} · {t.stato} · scad. {t.data_scadenza || "—"}</div>
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
                        {results.compagnie?.length > 0 && (
                            <ResultGroup
                                title="Compagnie" icon={<Building2 size={12} />} items={results.compagnie}
                                render={(c) => (
                                    <button key={c.id} onClick={() => go(`/compagnie`)} className="w-full text-left px-4 py-2 hover:bg-sky-50 border-b border-slate-50">
                                        <div className="font-medium text-sm">{c.ragione_sociale}</div>
                                        <div className="text-[11px] text-slate-500">{c.codice || ""}</div>
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

            <NotificheBell />

            {/* Logo agenzia — alto a destra */}
            {azienda?.logo_url && (
                <img
                    src={azienda.logo_url}
                    alt={azienda.ragione_sociale || "Logo"}
                    className="h-9 max-w-[140px] object-contain hidden md:block"
                    title={azienda.ragione_sociale}
                    data-testid="topbar-azienda-logo"
                />
            )}
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
