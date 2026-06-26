/**
 * Mini-pillola "🔒 PN chiusa" da mostrare accanto allo stato di una riga
 * (titolo, movimento, rappel, ...) quando la giornata di riferimento è
 * in Prima Nota chiusa.
 *
 * Props:
 *   - data: stringa YYYY-MM-DD da controllare. Se vuota → renderless.
 *   - className: opzionale
 *   - showOpen: se true mostra anche un pill verde "aperta" (default false)
 */
import { Lock } from "lucide-react";
import useGiornateChiuse from "@/hooks/useGiornateChiuse";

export default function ChiusuraPill({ data, className = "", showOpen = false }) {
    const chiuseSet = useGiornateChiuse();
    if (!data || !/^\d{4}-\d{2}-\d{2}$/.test(data)) return null;
    const isChiusa = chiuseSet.has(data);
    if (!isChiusa) {
        if (!showOpen) return null;
        return (
            <span
                className={`inline-flex items-center gap-1 text-[10px] text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-full px-1.5 py-0.5 ${className}`}
                data-testid={`pill-pn-aperta-${data}`}
                title={`Prima Nota del ${data} aperta`}
            >
                PN aperta
            </span>
        );
    }
    return (
        <span
            className={`inline-flex items-center gap-1 text-[10px] font-medium text-amber-800 bg-amber-100 border border-amber-300 rounded-full px-1.5 py-0.5 ${className}`}
            data-testid={`pill-pn-chiusa-${data}`}
            title={`Prima Nota del ${data} CHIUSA — riaprire per modificare`}
        >
            <Lock size={9} className="text-amber-700" /> PN chiusa
        </span>
    );
}
