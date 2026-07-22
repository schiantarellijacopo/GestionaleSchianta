import { Outlet, useNavigate, Link, useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Shield, LogOut, LayoutDashboard } from "lucide-react";
import { toast } from "sonner";

/**
 * Layout dedicato SOLO al Super Admin (proprietario piattaforma SaaS).
 * Nessuna sidebar client-facing. Solo header minimale con logo + logout.
 * Tutte le route super-admin sono figlie di questo layout.
 */
export default function SuperAdminLayout() {
    const { user, logout } = useAuth();
    const nav = useNavigate();
    const loc = useLocation();

    const doLogout = async () => {
        await logout();
        toast.success("Disconnesso");
        nav("/admin-login", { replace: true });
    };

    return (
        <div className="min-h-screen bg-slate-50 flex flex-col" data-testid="super-admin-layout">
            <header className="bg-gradient-to-r from-slate-900 to-violet-900 text-white px-4 sm:px-8 py-3 flex items-center justify-between border-b border-violet-800 shadow-md">
                <Link to="/super-admin" className="flex items-center gap-2">
                    <div className="w-9 h-9 rounded-md bg-violet-600 flex items-center justify-center">
                        <Shield size={18} />
                    </div>
                    <div>
                        <div className="text-sm font-semibold tracking-tight leading-none">Assicura · Platform Owner</div>
                        <div className="text-[10px] uppercase tracking-widest text-violet-300 mt-0.5">Super Admin Console</div>
                    </div>
                </Link>
                <div className="flex items-center gap-4">
                    <Link to="/super-admin"
                        className={`text-xs font-semibold px-3 py-1.5 rounded-md flex items-center gap-1 transition-colors ${
                            loc.pathname === "/super-admin" ? "bg-violet-600 text-white" : "text-violet-200 hover:bg-violet-800"
                        }`}
                        data-testid="sa-nav-dashboard">
                        <LayoutDashboard size={14} /> Dashboard
                    </Link>
                    <div className="text-right hidden sm:block">
                        <div className="text-xs font-semibold">{user?.name || user?.email}</div>
                        <div className="text-[10px] text-violet-300 uppercase tracking-wider">Owner</div>
                    </div>
                    <button onClick={doLogout}
                        className="text-xs font-semibold px-3 py-1.5 rounded-md bg-rose-600 hover:bg-rose-700 text-white flex items-center gap-1"
                        data-testid="sa-logout-btn">
                        <LogOut size={12} /> Esci
                    </button>
                </div>
            </header>
            <main className="flex-1">
                <Outlet />
            </main>
        </div>
    );
}
