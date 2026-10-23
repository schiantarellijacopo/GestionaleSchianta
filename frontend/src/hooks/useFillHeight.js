import { useRef } from "react";

// Le tabelle crescono con il contenuto: mostra tutte le righe della pagina
// (50/100/200) e a scorrere è la pagina, senza scroll interno con altezza fissa.
// Manteniamo la firma { ref, style } per retro-compatibilità con le pagine che
// la usano, ma non impostiamo più un'altezza.
export default function useFillHeight() {
    const ref = useRef(null);
    return { ref, style: undefined };
}
