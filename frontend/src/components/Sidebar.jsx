import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import {
    LayoutDashboard, Users, FileText, Receipt, AlertTriangle,
    BookOpen, Building2, Upload, Calculator, Mail, Activity, LogOut, Shield,
    Library, Kanban, Map, GraduationCap, MessageCircle, Wallet,
} from "lucide-react";

const ROLE_LABEL = {
    admin: "Amministratore",
    collaboratore: "Collaboratore",
    dipendente: "Dipendente",
    cliente: "Cliente",
};

export default function Sidebar() {
    const { user, logout } = useAuth();
    const nav = useNavigate();
    const role = user?.role;

    const item = (to, icon, label, testid) => (
        <NavLink
            to={to}
            data-testid={testid}
            end={to === "/"}
            className={({ isActive }) => `sidebar-link ${isActive ? "active" : ""}`}
        >
            {icon}
            <span>{label}</span>
        </NavLink>
    );

    return (
        <aside className="w-64 bg-slate-900 text-slate-100 flex flex-col min-h-screen" data-testid="sidebar">
            <div className="px-5 py-5 border-b border-slate-800">
                <div className="flex items-center gap-2">
                    <Shield size={22} className="text-sky-400" />
                    <div>
                        <div className="font-semibold tracking-tight">Assicura</div>
                        <div className="text-[11px] text-slate-400 -mt-0.5">Gestione Assicurazioni</div>
                    </div>
                </div>
            </div>

            <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-0.5">
                {item("/", <LayoutDashboard size={16} />, "Dashboard", "nav-dashboard")}
                {item("/pipeline", <Kanban size={16} />, "Pipeline", "nav-pipeline")}

                <div className="sidebar-section">Anagrafiche</div>
                {item("/anagrafiche", <Users size={16} />, "Clienti", "nav-anagrafiche")}
                {(role === "admin" || role === "collaboratore" || role === "dipendente") && (
                    item("/mappa", <Map size={16} />, "Mappa clienti", "nav-mappa")
                )}

                <div className="sidebar-section">Assicurazione</div>
                {item("/polizze", <FileText size={16} />, "Polizze", "nav-polizze")}
                {item("/titoli", <Receipt size={16} />, "Titoli", "nav-titoli")}
                {item("/sinistri", <AlertTriangle size={16} />, "Sinistri", "nav-sinistri")}

                {(role === "admin" || role === "collaboratore" || role === "dipendente") && (
                    <>
                        <div className="sidebar-section">Contabilità</div>
                        {item("/contabilita", <BookOpen size={16} />, "Prima nota", "nav-contabilita")}
                        {item("/provvigioni", <Wallet size={16} />, "Provvigioni", "nav-provvigioni")}
                    </>
                )}

                <div className="sidebar-section">Strumenti</div>
                {item("/corsi", <GraduationCap size={16} />, "Corsi", "nav-corsi")}
                {item("/chat", <MessageCircle size={16} />, "Chat", "nav-chat")}
                {(role === "admin" || role === "collaboratore" || role === "dipendente") && (
                    item("/email", <Mail size={16} />, "Pipeline Email", "nav-email")
                )}
                {(role === "admin" || role === "collaboratore") && (
                    <>
                        {item("/compagnie", <Building2 size={16} />, "Compagnie", "nav-compagnie")}
                        {item("/librerie", <Library size={16} />, "Librerie", "nav-librerie")}
                        {item("/importazione", <Upload size={16} />, "Importazione ANIA", "nav-importazione")}
                        {item("/attivita", <Activity size={16} />, "Log attività", "nav-attivita")}
                    </>
                )}
                {item("/pensioni", <Calculator size={16} />, "Calcolo INPS", "nav-pensioni")}
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
