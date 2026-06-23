import { api } from "@/lib/api";
import { toast } from "sonner";

/**
 * Scarica un PDF dal backend (con header Authorization) e lo apre in una nuova
 * tab via Blob URL. Per evitare ERR_BLOCKED_BY_CLIENT (Chrome blocca window.open
 * asincrone dopo await), la popup va aperta DENTRO il click handler.
 *
 * @param {string} path - path API (es. "/anagrafiche/X/privacy/genera-pdf")
 * @param {object} params - query params opzionali
 * @param {Window} preopenedWindow - finestra già aperta dal click handler
 *        per preservare il gesto utente. Se omessa la funzione prova ad aprirla
 *        da sola (potrebbe essere bloccata).
 */
export async function openPdf(path, params = {}, preopenedWindow = null) {
    const clean = {};
    Object.entries(params || {}).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== "" && v !== "all") clean[k] = v;
    });

    let popup = preopenedWindow;
    if (!popup) {
        popup = window.open("", "_blank");
    }
    if (popup) {
        try {
            popup.document.write(
                "<html><head><title>Caricamento PDF...</title></head>" +
                "<body style='font-family:system-ui;padding:40px;color:#475569;'>" +
                "<div style='font-size:14px;'>⏳ Caricamento PDF in corso...</div>" +
                "</body></html>"
            );
        } catch (_) { /* alcune browser bloccano write su about:blank */ }
    }

    try {
        const res = await api.get(path, { params: clean, responseType: "blob" });
        const ct = res.headers["content-type"] || "application/pdf";
        const blob = new Blob([res.data], { type: ct });
        const url = URL.createObjectURL(blob);
        if (popup && !popup.closed) {
            popup.location.href = url;
        } else {
            // Fallback: download diretto
            const a = document.createElement("a");
            a.href = url;
            a.download = path.split("/").pop() + ".pdf";
            document.body.appendChild(a);
            a.click();
            a.remove();
            toast.info("Popup bloccata dal browser — PDF scaricato");
        }
        setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (e) {
        if (popup && !popup.closed) popup.close();
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
