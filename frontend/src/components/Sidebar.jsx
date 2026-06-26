import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { useEffect, useState } from "react";
import {
    LayoutDashboard, Users, FileText, Receipt, AlertTriangle,
    BookOpen, Building2, Upload, Calculator, Mail, Activity, LogOut, Shield,
    Library, Kanban, Map, GraduationCap, MessageCircle, Wallet, Calendar, Coins, TimerReset,
    GripVertical, Settings2, Check, Megaphone, Bell, BookUser, Gift, Eye, EyeOff, RotateCcw, Zap,
} from "lucide-react";

const ROLE_LABEL = {
    admin: "Amministratore",
    collaboratore: "Collaboratore / Sub-agente",
    dipendente: "Dipendente",
    cliente: "Cliente",
};

// Definizione completa delle voci con ruoli ammessi
const ALL_MENU_ITEMS = [
    { id: "dashboard", path: "/", icon: "LayoutDashboard", label: "Dashboard", section: "main", roles: null },
    { id: "pipeline", path: "/pipeline", icon: "Kanban", label: "Pipeline", section: "main", roles: null },
    { id: "anagrafiche", path: "/anagrafiche", icon: "Users", label: "Clienti", section: "anagrafiche", roles: null },
    { id: "mappa", path: "/mappa", icon: "Map", label: "Mappa clienti", section: "anagrafiche", roles: ["admin", "collaboratore", "dipendente"] },
    { id: "polizze", path: "/polizze", icon: "FileText", label: "Portafoglio", section: "assicurazione", roles: null },
    { id: "titoli", path: "/titoli", icon: "Receipt", label: "Titoli", section: "assicurazione", roles: null },
    { id: "sinistri", path: "/sinistri", icon: "AlertTriangle", label: "Sinistri", section: "assicurazione", roles: null },
    { id: "avvisi", path: "/avvisi", icon: "Bell", label: "Avvisi", section: "assicurazione", roles: ["admin", "collaboratore", "dipendente"] },
    { id: "alert", path: "/alert", icon: "Zap", label: "Alert & Automazioni", section: "assicurazione", roles: ["admin", "collaboratore", "dipendente"] },
    { id: "primanota", path: "/contabilita", icon: "BookOpen", label: "Prima nota", section: "contabilita", roles: ["admin", "collaboratore", "dipendente"] },
    { id: "titoli_storici", path: "/titoli-storici", icon: "Receipt", label: "Titoli storici", section: "contabilita", roles: ["admin", "collaboratore", "dipendente"] },
    { id: "sospesi", path: "/sospesi", icon: "TimerReset", label: "Sospesi (anticipati)", section: "contabilita", roles: ["admin", "collaboratore", "dipendente"] },
    { id: "provvigioni", path: "/provvigioni", icon: "Wallet", label: "Estratto Conto Collaboratori", section: "contabilita", roles: ["admin", "collaboratore", "dipendente"] },
    { id: "ec_compagnie", path: "/compagnie-estratto", icon: "Coins", label: "E/C compagnie", section: "contabilita", roles: ["admin", "collaboratore", "dipendente"] },
    { id: "rappel", path: "/rappel", icon: "Gift", label: "Rappel", section: "contabilita", roles: ["admin", "collaboratore", "dipendente"] },
    { id: "calendario", path: "/calendario", icon: "Calendar", label: "Calendario", section: "contabilita", roles: ["admin", "collaboratore", "dipendente"] },
    { id: "corsi", path: "/corsi", icon: "GraduationCap", label: "Corsi", section: "strumenti", roles: null },
    { id: "marketing", path: "/marketing", icon: "Megaphone", label: "Marketing", section: "strumenti", roles: ["admin", "collaboratore", "dipendente"] },
    { id: "chat", path: "/chat", icon: "MessageCircle", label: "Chat", section: "strumenti", roles: null },
    { id: "email", path: "/email", icon: "Mail", label: "Pipeline Email", section: "strumenti", roles: ["admin", "collaboratore", "dipendente"] },
    { id: "pensioni", path: "/pensioni", icon: "Calculator", label: "Calcolo INPS", section: "strumenti", roles: null },
    { id: "rubrica_compagnie", path: "/rubrica-compagnie", icon: "BookUser", label: "Rubrica compagnie", section: "amministrazione", roles: ["admin", "collaboratore", "dipendente"] },
    { id: "librerie", path: "/librerie", icon: "Library", label: "Librerie", section: "amministrazione", roles: ["admin", "collaboratore"] },
    { id: "importazione", path: "/importazione", icon: "Upload", label: "Importazione ANIA", section: "amministrazione", roles: ["admin", "collaboratore"] },
    { id: "attivita", path: "/attivita", icon: "Activity", label: "Log attività", section: "amministrazione", roles: ["admin", "collaboratore"] },
];

const ICON_MAP = {
    LayoutDashboard, Users, FileText, Receipt, AlertTriangle, BookOpen, Building2,
    Upload, Calculator, Mail, Activity, Library, Kanban, Map, GraduationCap,
    MessageCircle, Wallet, Calendar, Coins, TimerReset, Megaphone, Bell, BookUser, Gift, Zap,
};

const SECTION_LABELS = {
    main: null,
    anagrafiche: "Anagrafiche",
    assicurazione: "Assicurazione",
    contabilita: "Contabilità",
    strumenti: "Strumenti",
    amministrazione: "Amministrazione",
};

const STORAGE_KEY = "assicura.sidebar.order";
const HIDDEN_KEY = "assicura.sidebar.hidden";

export default function Sidebar() {
    const { user, logout } = useAuth();
    const nav = useNavigate();
    const role = user?.role;
    const [editMode, setEditMode] = useState(false);
    const [order, setOrder] = useState(() => {
        try {
            const stored = localStorage.getItem(STORAGE_KEY);
            if (stored) return JSON.parse(stored);
        } catch (e) { /* fallback */ }
        return ALL_MENU_ITEMS.map((m) => m.id);
    });
    const [hidden, setHidden] = useState(() => {
        try {
            const stored = localStorage.getItem(HIDDEN_KEY);
            if (stored) return new Set(JSON.parse(stored));
        } catch (e) { /* fallback */ }
        return new Set();
    });
    const [dragId, setDragId] = useState(null);

    useEffect(() => {
        try { localStorage.setItem(STORAGE_KEY, JSON.stringify(order)); } catch (e) { /* ignore */ }
    }, [order]);
    useEffect(() => {
        try { localStorage.setItem(HIDDEN_KEY, JSON.stringify(Array.from(hidden))); } catch (e) { /* ignore */ }
    }, [hidden]);

    const toggleHide = (id) => {
        setHidden((prev) => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id); else next.add(id);
            return next;
        });
    };

    // Costruisce la lista visibile: applica ordine custom + filtra per ruolo
    const visibleItems = order
        .map((id) => ALL_MENU_ITEMS.find((m) => m.id === id))
        .filter((m) => m && (!m.roles || m.roles.includes(role)))
        .concat(ALL_MENU_ITEMS.filter((m) => !order.includes(m.id) && (!m.roles || m.roles.includes(role))));

    // In edit mode mostra tutto, altrimenti filtra le voci nascoste
    const itemsToRender = editMode ? visibleItems : visibleItems.filter((m) => !hidden.has(m.id));

    // Raggruppa per sezione mantenendo l'ordine del custom
    const sezioni = [];
    let lastSec = null;
    for (const it of itemsToRender) {
        if (it.section !== lastSec) {
            sezioni.push({ key: it.section, items: [it] });
            lastSec = it.section;
        } else {
            sezioni[sezioni.length - 1].items.push(it);
        }
    }

    const onDragStart = (id) => setDragId(id);
    const onDragOver = (e, overId) => {
        if (!editMode || !dragId || dragId === overId) return;
        e.preventDefault();
        setOrder((prev) => {
            const fromIdx = prev.indexOf(dragId);
            const toIdx = prev.indexOf(overId);
            if (fromIdx < 0 || toIdx < 0) return prev;
            const copy = [...prev];
            const [moved] = copy.splice(fromIdx, 1);
            copy.splice(toIdx, 0, moved);
            return copy;
        });
    };
    const resetOrder = () => {
        if (!window.confirm("Ripristinare l'ordine predefinito del menu?")) return;
        const def = ALL_MENU_ITEMS.map((m) => m.id);
        setOrder(def);
    };

    const renderItem = (m) => {
        const Icon = ICON_MAP[m.icon] || LayoutDashboard;
        const isHidden = hidden.has(m.id);
        if (editMode) {
            return (
                <div
                    key={m.id}
                    draggable
                    onDragStart={() => onDragStart(m.id)}
                    onDragOver={(e) => onDragOver(e, m.id)}
                    onDragEnd={() => setDragId(null)}
                    className={`flex items-center gap-2 px-2 py-1.5 rounded text-xs cursor-grab active:cursor-grabbing ${
                        dragId === m.id ? "bg-sky-700 opacity-60" : isHidden ? "bg-slate-800/30 opacity-50" : "bg-slate-800 hover:bg-slate-700"
                    }`}
                    data-testid={`drag-${m.id}`}
                >
                    <GripVertical size={12} className="text-slate-400 shrink-0" />
                    <Icon size={14} className="shrink-0" />
                    <span className="flex-1 truncate">{m.label}</span>
                    <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); toggleHide(m.id); }}
                        className="p-1 rounded hover:bg-slate-600 shrink-0"
                        title={isHidden ? "Mostra voce" : "Nascondi voce"}
                        data-testid={`toggle-hide-${m.id}`}
                    >
                        {isHidden ? <EyeOff size={12} className="text-slate-400" /> : <Eye size={12} className="text-emerald-400" />}
                    </button>
                </div>
            );
        }
        return (
            <NavLink
                key={m.id}
                to={m.path}
                end={m.path === "/"}
                data-testid={`nav-${m.id}`}
                className={({ isActive }) =>
                    `flex items-center gap-2.5 px-3 py-1.5 rounded text-sm ${
                        isActive ? "bg-sky-700 text-white" : "text-slate-300 hover:bg-slate-800 hover:text-white"
                    }`
                }
            >
                <Icon size={16} />
                <span>{m.label}</span>
            </NavLink>
        );
    };

    return (
        <aside className="w-64 bg-slate-900 text-slate-100 flex flex-col min-h-screen" data-testid="sidebar">
            <div className="px-5 py-5 border-b border-slate-800 flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Shield size={22} className="text-sky-400" />
                    <div>
                        <div className="font-semibold tracking-tight">Assicura</div>
                        <div className="text-[11px] text-slate-400 -mt-0.5">Gestione Assicurazioni</div>
                    </div>
                </div>
                <button
                    onClick={() => setEditMode(!editMode)}
                    className={`p-1.5 rounded transition-colors ${
                        editMode ? "bg-sky-600 text-white" : "text-slate-400 hover:bg-slate-800 hover:text-white"
                    }`}
                    title={editMode ? "Termina riordino" : "Riordina menu"}
                    data-testid="sidebar-edit-toggle"
                >
                    {editMode ? <Check size={14} /> : <Settings2 size={14} />}
                </button>
            </div>

            {editMode && (
                <div className="px-3 py-2 bg-sky-900/40 border-b border-sky-800 text-[11px] text-sky-100">
                    Trascina le voci per riordinarle. Premi <Eye size={10} className="inline mx-0.5" /> per mostrare / nascondere. Le preferenze sono salvate sul tuo dispositivo.
                    <button onClick={resetOrder} className="flex items-center gap-1 text-[10px] underline mt-1 text-sky-200 hover:text-white" data-testid="sidebar-reset">
                        <RotateCcw size={10} /> Ripristina predefinito
                    </button>
                </div>
            )}

            <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-0.5">
                {sezioni.map((sec, i) => (
                    <div key={`${sec.key}-${i}`}>
                        {SECTION_LABELS[sec.key] && (
                            <div className="sidebar-section">{SECTION_LABELS[sec.key]}</div>
                        )}
                        {sec.items.map(renderItem)}
                    </div>
                ))}
            </nav>

            <div className="border-t border-slate-800 p-3">
                <div className="flex items-center gap-3 mb-3">
                    <div className="w-9 h-9 rounded-full bg-sky-600 flex items-center justify-center text-sm font-semibold">
                        {(user?.name || "?").slice(0, 1).toUpperCase()}
                    </div>
                    <div className="min-w-0">
                        <div className="text-sm font-medium truncate">{user?.name}</div>
                        <div className="text-[11px] text-slate-400 truncate">
                            {ROLE_LABEL[role] || role}
                        </div>
                    </div>
                </div>
                <button
                    data-testid="logout-button"
                    onClick={async () => { await logout(); nav("/login"); }}
                    className="w-full flex items-center justify-center gap-2 text-xs text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-md py-2 transition-colors"
                >
                    <LogOut size={14} /> Esci
                </button>
            </div>
        </aside>
    );
}
