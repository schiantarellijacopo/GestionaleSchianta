import { api } from "@/lib/api";
import { toast } from "sonner";

/**
 * Scarica il PDF come blob (con Authorization header) e lo apre in una nuova tab
 * tramite Blob URL. Evita problemi di ad-blocker (ERR_BLOCKED_BY_CLIENT) e di
 * autenticazione persa nella nuova finestra.
 */
export async function openPdf(path, params = {}) {
    const clean = {};
    Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== "" && v !== "all") clean[k] = v;
    });
    try {
        const res = await api.get(path, { params: clean, responseType: "blob" });
        const ct = res.headers["content-type"] || "application/pdf";
        const blob = new Blob([res.data], { type: ct });
        const url = URL.createObjectURL(blob);
        const win = window.open(url, "_blank", "noopener");
        if (!win) {
            // Fallback: download
            const a = document.createElement("a");
            a.href = url;
            a.download = path.split("/").pop() + ".pdf";
            document.body.appendChild(a);
            a.click();
            a.remove();
        }
        // Revoke after 60s so the tab has time to display
        setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (e) {
        // Se il server ha restituito un JSON di errore, lo leggiamo dal blob
        let msg = "Errore nella generazione del PDF";
        if (e.response?.data instanceof Blob) {
            try {
                const txt = await e.response.data.text();
                const j = JSON.parse(txt);
                msg = j.detail || msg;
            } catch (_) { /* keep default */ }
        } else if (e.response?.data?.detail) {
            msg = e.response.data.detail;
        }
        toast.error(msg);
    }
}
