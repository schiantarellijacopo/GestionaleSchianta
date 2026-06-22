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
        return <Navigate to="/" replace />;
    }
    return children;
}
