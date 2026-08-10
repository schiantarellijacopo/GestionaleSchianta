/**
 * IconForRamo — Icona lucide-react automatica in base al ramo assicurativo.
 *
 * Uso:
 *   <IconForRamo ramo="RC AUTO" />                    // Car
 *   <IconForRamo ramo="INCENDIO CASA" size={18} />    // Home
 *   <IconForRamo ramo="VITA" className="text-white" /> // Heart
 *   <IconForRamo ramo="IMPRESA" />                     // Building2
 *   <IconForRamo ramo="RESPONSABILITA" />              // Shield (default)
 *
 * Riconoscimento tramite regex sul nome del ramo:
 *  - Car    → RCA, CVT, AUTO, MOTO, VEICOLO
 *  - Home   → CASA, ABITAZIONE, IMMOBILE, CONDOMINIO
 *  - Heart  → VITA, SALUTE, MALATTIA, INFORTUNI, SANITARIO
 *  - Building2 → IMPRESA, COMMERCIO, ARTIGIANO, AZIENDA
 *  - Shield → fallback (rischi generici, RC, danni)
 */
import { Car, Home, Heart, Building2, Shield } from "lucide-react";

export default function IconForRamo({ ramo, size = 18, className = "" }) {
    const r = (ramo || "").toUpperCase();
    if (/(RCA|CVT|AUTO|MOTO|VEICOL)/.test(r)) return <Car size={size} className={className} />;
    if (/(CASA|ABITAZ|IMMOBIL|CONDOM)/.test(r)) return <Home size={size} className={className} />;
    if (/(VITA|SALUTE|MALATT|INFORTU|SANIT)/.test(r)) return <Heart size={size} className={className} />;
    if (/(IMPRE|COMMERC|ARTIG|AZIEND)/.test(r)) return <Building2 size={size} className={className} />;
    return <Shield size={size} className={className} />;
}

/** Colore Tailwind consigliato per l'icona in base al ramo — utile per background gradienti. */
export function ramoColor(ramo) {
    const r = (ramo || "").toUpperCase();
    if (/(RCA|CVT|AUTO|MOTO|VEICOL)/.test(r)) return "sky";
    if (/(CASA|ABITAZ|IMMOBIL|CONDOM)/.test(r)) return "emerald";
    if (/(VITA|SALUTE|MALATT|INFORTU|SANIT)/.test(r)) return "rose";
    if (/(IMPRE|COMMERC|ARTIG|AZIEND)/.test(r)) return "amber";
    return "violet";
}
