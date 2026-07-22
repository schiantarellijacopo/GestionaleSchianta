import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";

export default function ProtectedRoute({ children, roles, superAdminOnly, blockSuperAdmin }) {
    const { user, loading } = useAuth();
    const loc = useLocation();
    if (loading || user === null) {
        return (
            <div className="flex items-center justify-center min-h-screen text-slate-500 text-sm">
                Caricamento...
            </div>
        );
    }
    if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
    // Super admin: se blockSuperAdmin=true, redirect a /super-admin
    // (impedisce ai super_admin di vedere le pagine client-facing)
    if (blockSuperAdmin && user.is_super_admin) {
        return <Navigate to="/super-admin" replace />;
    }
    // superAdminOnly: solo super_admin può accedere
    if (superAdminOnly && !user.is_super_admin) {
        return <Navigate to="/" replace />;
    }
    if (roles && !roles.includes(user.role)) {
        return <Navigate to="/" replace />;
    }
    return children;
}
