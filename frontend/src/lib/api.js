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
