import { api } from "@/lib/api";
import { toast } from "sonner";

/**
 * Generico: scarica un file (PDF/CSV/XLSX/ecc.) via fetch+blob+<a download>
 * per bypassare ERR_BLOCKED_BY_CLIENT su tutti i browser/adblocker.
 */
export async function downloadFile(path, params = {}, opts = {}) {
    const clean = {};
    Object.entries(params || {}).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== "" && v !== "all") clean[k] = v;
    });
    if (params?.sezione === "all") clean.sezione = "all";
    const fallbackName = opts.filename || path.split("/").filter(Boolean).pop() || "file";
    const toastId = opts.silent ? null : toast.loading("Download in corso...");
    try {
        const res = await api.get(path, { params: clean, responseType: "blob" });
        const ct = res.headers["content-type"] || "application/octet-stream";
        const blob = new Blob([res.data], { type: ct });
        const url = URL.createObjectURL(blob);
        let filename = fallbackName;
        const cd = res.headers["content-disposition"];
        if (cd) {
            const m = cd.match(/filename[*]?=(?:UTF-8'')?["']?([^"';]+)/);
            if (m) filename = decodeURIComponent(m[1]);
        }
        const a = document.createElement("a");
        a.href = url; a.download = filename; a.style.display = "none";
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 30000);
        if (toastId) toast.success("File scaricato", { id: toastId, duration: 1500 });
    } catch (e) {
        let msg = "Errore download file";
        if (e.response?.data instanceof Blob) {
            try {
                const txt = await e.response.data.text();
                const j = JSON.parse(txt);
                msg = j.detail || msg;
            } catch (_) { /* keep default */ }
        } else if (e.response?.data?.detail) {
            msg = e.response.data.detail;
        }
        if (toastId) toast.error(msg, { id: toastId });
        else toast.error(msg);
    }
}

/**
 * Scarica un PDF dal backend (con header Authorization) e lo apre/salva senza
 * usare popup, per evitare definitivamente ERR_BLOCKED_BY_CLIENT.
 *
 * Strategia: fetch blob → crea <a download> → click → l'utente vede il PDF
 * scaricato (e Chrome lo apre automaticamente nel viewer di sistema).
 */
export async function openPdf(path, params = {}) {
    const clean = {};
    Object.entries(params || {}).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== "" && v !== "all") clean[k] = v;
    });
    // Permetti che "all" passi se è esplicitamente nei params per la stampa unica
    if (params?.sezione === "all") clean.sezione = "all";

    const toastId = toast.loading("Generazione PDF in corso...");
    try {
        const res = await api.get(path, { params: clean, responseType: "blob" });
        const ct = res.headers["content-type"] || "application/pdf";
        const blob = new Blob([res.data], { type: ct });
        const url = URL.createObjectURL(blob);

        // Nome file dal Content-Disposition se disponibile
        let filename = "documento.pdf";
        const cd = res.headers["content-disposition"];
        if (cd) {
            const m = cd.match(/filename[*]?=(?:UTF-8'')?["']?([^"';]+)/);
            if (m) filename = decodeURIComponent(m[1]);
        } else {
            filename = path.split("/").filter(Boolean).pop() + ".pdf";
        }

        // Download diretto via <a download>
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        a.style.display = "none";
        document.body.appendChild(a);
        a.click();
        a.remove();

        setTimeout(() => URL.revokeObjectURL(url), 30000);
        toast.success("PDF scaricato", { id: toastId, duration: 2000 });
    } catch (e) {
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
        toast.error(msg, { id: toastId });
    }
}
