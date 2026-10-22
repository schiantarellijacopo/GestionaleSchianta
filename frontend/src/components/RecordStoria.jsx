import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { History, UserCircle2 } from "lucide-react";

const fmtDT = (iso) => {
    if (!iso) return "";
    try {
        const d = new Date(iso);
        if (isNaN(d.getTime())) return iso;
        return d.toLocaleDateString("it-IT") + " " +
            d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
    } catch (e) { return iso; }
};

/**
 * Badge "Creato / Ultima modifica" su un record (polizza, sinistro, titolo,
 * anagrafica, ...). Ricostruito dal log attività. Visibile SOLO all'admin.
 *
 * Props: entita (es. "polizza"), entitaId, className
 */
export default function RecordStoria({ entita, entitaId, className = "" }) {
    const { user } = useAuth();
    const [data, setData] = useState(null);
    const isAdmin = user?.role === "admin";

    useEffect(() => {
        if (!isAdmin || !entita || !entitaId) return;
        let alive = true;
        api.get("/audit/record-storia", { params: { entita, entita_id: entitaId } })
            .then((r) => { if (alive) setData(r.data); })
            .catch(() => {});
        return () => { alive = false; };
    }, [entita, entitaId, isAdmin]);

    if (!isAdmin) return null;
    if (!data || (!data.creato && !data.modificato)) return null;

    const { creato, modificato } = data;
    return (
        <div
            data-testid={`record-storia-${entita}-${entitaId}`}
            className={`flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2 ${className}`}
        >
            <span className="inline-flex items-center gap-1.5 text-emerald-700 font-medium">
                <History size={14} /> Storico
            </span>
            {creato && (
                <span className="inline-flex items-center gap-1" data-testid="record-storia-creato">
                    <span className="text-emerald-600/80">Creato il</span>
                    <span className="font-medium text-emerald-900 num">{fmtDT(creato.quando)}</span>
                    <span className="text-emerald-600/80">da</span>
                    <span className="inline-flex items-center gap-1 font-semibold text-emerald-900">
                        <UserCircle2 size={13} />{creato.da}
                    </span>
                </span>
            )}
            {modificato && (!creato || modificato.quando !== creato.quando) && (
                <span className="inline-flex items-center gap-1" data-testid="record-storia-modificato">
                    <span className="text-emerald-600/80">· Ultima modifica il</span>
                    <span className="font-medium text-emerald-900 num">{fmtDT(modificato.quando)}</span>
                    <span className="text-emerald-600/80">da</span>
                    <span className="inline-flex items-center gap-1 font-semibold text-emerald-900">
                        <UserCircle2 size={13} />{modificato.da}
                    </span>
                </span>
            )}
        </div>
    );
}
