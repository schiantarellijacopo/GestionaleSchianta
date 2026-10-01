import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;

export const api = axios.create({
    baseURL: API_BASE,
    withCredentials: true,
});

// memorizziamo anche il token in memoria/localStorage come fallback (cookie httpOnly è preferito)
const stored = localStorage.getItem("token");
if (stored) api.defaults.headers.common["Authorization"] = `Bearer ${stored}`;

export const setToken = (token) => {
    if (token) {
        localStorage.setItem("token", token);
        api.defaults.headers.common["Authorization"] = `Bearer ${token}`;
    } else {
        localStorage.removeItem("token");
        delete api.defaults.headers.common["Authorization"];
    }
};

export function formatError(err) {
    const d = err?.response?.data?.detail;
    if (!d) return err?.message || "Errore sconosciuto";
    if (typeof d === "string") return d;
    if (Array.isArray(d))
        return d.map((e) => e?.msg || JSON.stringify(e)).join(" ");
    if (typeof d === "object" && d.msg) return d.msg;
    return String(d);
}

export const fmtEur = (n) =>
    new Intl.NumberFormat("it-IT", {
        style: "currency",
        currency: "EUR",
        minimumFractionDigits: 2,
    }).format(Number(n || 0));

export const fmtDate = (s) => {
    if (!s) return "-";
    try {
        const d = new Date(s.length === 10 ? s + "T00:00:00" : s);
        return d.toLocaleDateString("it-IT");
    } catch {
        return s;
    }
};

export const fmtNum = (n) =>
    new Intl.NumberFormat("it-IT").format(Number(n || 0));

// Prompt per una data in formato italiano GG/MM/AAAA. Restituisce la data in
// formato ISO (YYYY-MM-DD) pronta per il backend, oppure null se annullato/vuoto.
export const promptDataIt = (messaggio) => {
    const oggi = new Date();
    const pad = (x) => String(x).padStart(2, "0");
    const defIt = `${pad(oggi.getDate())}/${pad(oggi.getMonth() + 1)}/${oggi.getFullYear()}`;
    while (true) {
        const raw = window.prompt(`${messaggio}\nDigita la data di registrazione (GG/MM/AAAA).`, defIt);
        if (!raw) return null;
        const s = raw.trim();
        let iso = null;
        let m = s.match(/^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})$/);
        if (m) iso = `${m[3]}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}`;
        else if (/^\d{4}-\d{2}-\d{2}$/.test(s)) iso = s;
        if (iso && !isNaN(new Date(iso + "T00:00:00").getTime())) return iso;
        window.alert("Data non valida. Usa il formato GG/MM/AAAA (es. 01/10/2026).");
    }
};

// Invio WhatsApp unificato: se l'agenzia ha la WhatsApp API attiva (whatsapp_provider
// = "evolution") invia server-side via Evolution; altrimenti apre il link wa.me.
// Restituisce l'esito e gestisce apertura link / toast.
export async function sendWhatsApp(numero, messaggio, extra = {}) {
    const { toast } = await import("sonner");
    if (!numero) { toast.error("Numero WhatsApp del destinatario mancante"); return { ok: false }; }
    try {
        const r = await api.post("/comunicazioni/whatsapp/invia", { numero, messaggio, ...extra });
        const d = r.data || {};
        if (d.provider === "wame" && d.url) {
            window.open(d.url, "_blank");
        } else if (d.provider === "evolution") {
            toast.success("Messaggio WhatsApp inviato");
        }
        return { ok: true, ...d };
    } catch (e) {
        toast.error(formatError(e));
        return { ok: false };
    }
}
