import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import { Outlet } from "react-router-dom";
import { createContext, useContext, useState } from "react";

// Contesto per il drawer mobile della sidebar
const SidebarCtx = createContext(null);
export const useSidebar = () => useContext(SidebarCtx);

export default function Layout() {
    const [mobileOpen, setMobileOpen] = useState(false);
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
