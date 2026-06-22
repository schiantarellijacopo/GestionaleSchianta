import { API_BASE } from "@/lib/api";

/** Apre una stampa PDF in nuova tab includendo cookies (withCredentials non funziona per window.open).
 * Costruiamo l'URL con query string; il backend usa il cookie httpOnly già impostato.
 */
export function openPdf(path, params = {}) {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== "" && v !== "all") qs.append(k, v);
    });
    const url = `${API_BASE}${path}${qs.toString() ? `?${qs}` : ""}`;
    window.open(url, "_blank", "noopener");
}
