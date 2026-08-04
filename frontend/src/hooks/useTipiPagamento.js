import { useEffect, useState } from "react";
import { api } from "@/lib/api";

// Cache in-memory dei CONTI/BANCHE attivi (Librerie → Conti / Banche).
// È l'unica sorgente per i dropdown di pagamento di tutto il programma:
// il valore salvato in `mezzo_pagamento` è il NOME del conto (es. "BPER Sondrio").
let _cache = null;
let _inflight = null;
const _subs = new Set();

const _fetch = () => {
    if (_inflight) return _inflight;
    _inflight = api.get("/librerie/conti-cassa", { params: { attivi: true } })
        .then((r) => {
            _cache = (r.data || []).map((c) => ({ id: c.id, label: c.nome, tipo: c.tipo }));
            _subs.forEach((cb) => cb(_cache));
            return _cache;
        })
        .catch(() => {
            _cache = [];
            return _cache;
        })
        .finally(() => { _inflight = null; });
    return _inflight;
};

export default function useTipiPagamento() {
    const [tipi, setTipi] = useState(_cache || []);
    const [loading, setLoading] = useState(_cache === null);

    useEffect(() => {
        const onUpdate = (v) => { setTipi(v); setLoading(false); };
        _subs.add(onUpdate);
        if (_cache === null) {
            _fetch().then(onUpdate);
        }
        return () => { _subs.delete(onUpdate); };
    }, []);

    return { tipi, loading };
}

export const refreshTipiPagamento = () => {
    _cache = null;
    return _fetch();
};
