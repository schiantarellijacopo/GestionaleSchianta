import { useEffect, useRef } from "react";

/**
 * Aggiornamento automatico leggero delle liste: richiama `callback`
 * ogni `intervalMs` (default 10s) SOLO quando la scheda è visibile, e
 * immediatamente quando l'utente riporta il focus sulla finestra/scheda.
 * Così gli altri utenti vedono le nuove scritture senza ricaricare la pagina.
 */
export function useAutoRefresh(callback, intervalMs = 10000) {
    const cbRef = useRef(callback);
    cbRef.current = callback;

    useEffect(() => {
        const run = () => {
            if (typeof document === "undefined" || document.visibilityState === "visible") {
                try { cbRef.current && cbRef.current(); } catch { /* noop */ }
            }
        };
        const id = setInterval(run, intervalMs);
        const onFocus = () => run();
        window.addEventListener("focus", onFocus);
        document.addEventListener("visibilitychange", onFocus);
        return () => {
            clearInterval(id);
            window.removeEventListener("focus", onFocus);
            document.removeEventListener("visibilitychange", onFocus);
        };
    }, [intervalMs]);
}

export default useAutoRefresh;
