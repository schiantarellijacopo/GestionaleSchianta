import { useLayoutEffect, useRef, useState } from "react";

// Calcola l'altezza disponibile dall'elemento fino al fondo della viewport,
// così il blocco (tabella scrollabile + footer totali) riempie esattamente lo
// spazio senza che il footer copra le righe né finisca sotto la viewport.
// Si ricalcola al resize della finestra e quando cambia il layout sopra la
// tabella (es. caricamento KPI async, apertura filtri) tramite ResizeObserver.
export default function useFillHeight(deps = [], bottomGap = 12) {
    const ref = useRef(null);
    const [h, setH] = useState(null);
    useLayoutEffect(() => {
        const el = ref.current;
        if (!el) return;
        let raf = 0;
        const calc = () => {
            cancelAnimationFrame(raf);
            raf = requestAnimationFrame(() => {
                const top = el.getBoundingClientRect().top;
                const next = Math.max(260, Math.round(window.innerHeight - top - bottomGap));
                setH((prev) => (prev === next ? prev : next));
            });
        };
        calc();
        const timers = [60, 250, 600, 1100, 1800].map((ms) => setTimeout(calc, ms));
        window.addEventListener("resize", calc);
        const ro = new ResizeObserver(calc);
        ro.observe(document.body);
        if (el.offsetParent) ro.observe(el.offsetParent);
        return () => {
            timers.forEach(clearTimeout);
            cancelAnimationFrame(raf);
            window.removeEventListener("resize", calc);
            ro.disconnect();
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, deps);
    return { ref, style: h ? { height: `${h}px` } : undefined };
}
