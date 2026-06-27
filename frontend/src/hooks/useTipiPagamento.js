import { useEffect, useState } from "react";
import { api } from "@/lib/api";

// Cache in-memory dei "tipi pagamento" (l'unica libreria utilizzata nei
// dialoghi di incasso/uscita di tutto il programma).
let _cache = null;
let _inflight = null;
const _subs = new Set();

const _fetch = () => {
    if (_inflight) return _inflight;
    _inflight = api.get("/librerie/tipi-pagamento", { params: { attivi: true } })
        .then((r) => {
            _cache = r.data || [];
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
