import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import { Outlet, useLocation } from "react-router-dom";
import { createContext, useContext, useState, useEffect, useRef } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

// Contesto per il drawer mobile della sidebar
const SidebarCtx = createContext(null);
export const useSidebar = () => useContext(SidebarCtx);

const NAV_TITOLI = {
    "/": "Dashboard", "/anagrafiche": "Clienti", "/polizze": "Portafoglio",
    "/titoli": "Titoli", "/sinistri": "Sinistri", "/contabilita": "Prima Nota",
    "/statistiche": "Statistiche", "/cervello": "Il Cervello", "/avvisi": "Avvisi",
    "/libro-matricola": "Libro Matricola", "/provvigioni": "Estratto Conto Collaboratori",
    "/documenti-inbox": "Documenti Inbox", "/audit-operatori": "Monitoraggio operatori",
};

function useNavTracking() {
    const location = useLocation();
    const { user } = useAuth();
    const last = useRef(null);
    useEffect(() => {
        const role = user?.role;
        if (!role || !["admin", "collaboratore", "dipendente"].includes(role)) return;
        const path = location.pathname;
        if (path === last.current) return;
        last.current = path;
        // Etichetta area: match esatto o primo segmento
        const seg = "/" + (path.split("/")[1] || "");
        const titolo = NAV_TITOLI[path] || NAV_TITOLI[seg] || "";
        api.post("/audit/navigazione", { path, titolo }).catch(() => {});
    }, [location.pathname, user?.role]);
}

export default function Layout() {
    const [mobileOpen, setMobileOpen] = useState(false);
    useNavTracking();
    return (
        <SidebarCtx.Provider value={{ mobileOpen, setMobileOpen }}>
            <div className="flex min-h-screen bg-slate-50">
                {/* Overlay mobile: chiude il menu cliccando fuori */}
                {mobileOpen && (
                    <button
                        type="button"
                        aria-label="Chiudi menu"
                        className="fixed inset-0 z-30 bg-black/40 lg:hidden"
                        onClick={() => setMobileOpen(false)}
                        data-testid="sidebar-overlay"
                    />
                )}
                <Sidebar />
                <main className="flex-1 min-w-0 flex flex-col">
                    <TopBar />
                    <div className="max-w-[1400px] mx-auto w-full px-3 sm:px-5 lg:px-8 py-4 sm:py-6 lg:py-8 page-fade flex-1">
                        <Outlet />
                    </div>
                </main>
            </div>
        </SidebarCtx.Provider>
    );
}
