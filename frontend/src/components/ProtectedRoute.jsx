import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";

export default function ProtectedRoute({ children, roles }) {
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
    if (roles && !roles.includes(user.role)) {
        return (
            <div className="p-10 text-center text-slate-600">
                Accesso negato per il ruolo <b>{user.role}</b>.
            </div>
        );
    }
    return children;
}
