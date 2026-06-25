import { useEffect, useState } from "react";
import { api } from "@/lib/api";

// Cache in-memory: una sola fetch finché la app è aperta.
let _cache = null;
let _inflight = null;
const _subs = new Set();

const _fetch = () => {
    if (_inflight) return _inflight;
    _inflight = api.get("/librerie/mezzi-pagamento", { params: { attivi: true } })
        .then((r) => {
            _cache = r.data || [];
            _subs.forEach((cb) => cb(_cache));
            return _cache;
        })
        .catch(() => {
            // fallback statico se l'endpoint non risponde
            _cache = [
                { codice: "contanti", label: "Contanti", ordine: 1 },
                { codice: "bonifico", label: "Bonifico bancario", ordine: 2 },
                { codice: "assegno", label: "Assegno", ordine: 3 },
                { codice: "pos", label: "POS / Carta", ordine: 4 },
                { codice: "rid", label: "RID / SDD", ordine: 5 },
                { codice: "altro", label: "Altro", ordine: 99 },
            ];
            return _cache;
        })
        .finally(() => { _inflight = null; });
    return _inflight;
};

/** Restituisce { mezzi, loading } — i mezzi pagamento ATTIVI ordinati per `ordine`. */
export default function useMezziPagamento() {
    const [mezzi, setMezzi] = useState(_cache || []);
    const [loading, setLoading] = useState(_cache === null);

    useEffect(() => {
        const onUpdate = (val) => { setMezzi(val); setLoading(false); };
        _subs.add(onUpdate);
        if (_cache === null) {
            _fetch().then(onUpdate);
        }
        return () => { _subs.delete(onUpdate); };
    }, []);

    return { mezzi, loading };
}

/** Forza il refresh del cache (chiamare dopo edit/delete della libreria). */
export const refreshMezziPagamento = () => {
    _cache = null;
    return _fetch();
};
