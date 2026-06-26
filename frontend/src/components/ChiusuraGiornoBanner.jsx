/**
 * Banner avviso "Prima Nota chiusa" per una data specifica.
 *
 * Mostra un avviso giallo sticky in cima alla sezione operativa quando la data
 * indicata corrisponde a una chiusura attiva (non riaperta) di Prima Nota.
 * Permette all'admin di aprire direttamente lo storico chiusure per riaprirla.
 *
 * Props:
 *  - data: stringa YYYY-MM-DD da controllare. Se vuota, niente banner.
 *  - className: opzionale, override stili wrapper.
 *  - showWhenOpen: se true, mostra anche un mini-pill verde "Prima Nota aperta".
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { api } from "@/lib/api";

export default function ChiusuraGiornoBanner({ data, className = "", showWhenOpen = false }) {
    const [stato, setStato] = useState(null);

    useEffect(() => {
        if (!data || !/^\d{4}-\d{2}-\d{2}$/.test(data)) {
            setStato(null);
            return;
        }
        let cancelled = false;
        api.get(`/contabilita/giornata-stato/${data}`)
            .then((r) => { if (!cancelled) setStato(r.data); })
            .catch(() => { if (!cancelled) setStato(null); });
        return () => { cancelled = true; };
    }, [data]);

    if (!stato) return null;

    if (!stato.chiusa) {
        if (!showWhenOpen) return null;
        return (
            <div
                className={`inline-flex items-center gap-1.5 text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-1 rounded ${className}`}
                data-testid="banner-prima-nota-aperta"
            >
                <CheckCircle2 size={13} /> Prima Nota del {stato.data} aperta
            </div>
        );
    }

    const closedBy = stato.closed_by_name ? ` da ${stato.closed_by_name}` : "";
    return (
        <div
            className={`flex items-center gap-3 border border-amber-300 bg-amber-50 text-amber-900 rounded-md px-4 py-3 ${className}`}
            data-testid="banner-prima-nota-chiusa"
            role="alert"
        >
            <AlertTriangle size={20} className="text-amber-600 shrink-0" />
            <div className="flex-1 text-sm">
                <span className="font-semibold">Prima Nota del {stato.data} chiusa</span>
                <span className="text-amber-800">
                    {closedBy}. Le operazioni che impattano la contabilità di questo giorno
                    (incassi, coperture, movimenti, giroconti, pagamenti) sono bloccate.
                </span>
            </div>
            {stato.can_riapri && (
                <Link
                    to="/contabilita?tab=storico"
                    className="text-xs font-medium px-3 py-1.5 bg-amber-600 text-white rounded hover:bg-amber-700 transition-colors whitespace-nowrap"
                    data-testid="banner-riapri-link"
                >
                    Riapri Prima Nota
                </Link>
            )}
        </div>
    );
}
