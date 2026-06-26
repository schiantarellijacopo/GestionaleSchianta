/**
 * Hook che restituisce un Set di date YYYY-MM-DD per le quali la Prima Nota
 * risulta CHIUSA (non riaperta).
 *
 * Cache shared module-level (60s TTL) + dedup promesse in volo per evitare
 * decine di chiamate quando molti componenti pillola montano insieme.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

let _cache = null;         // { ts, set }
let _inflight = null;      // Promise in-flight (singleton)
const TTL_MS = 60_000;
const _subscribers = new Set();   // setChiuse callbacks per notifica multipla

function _isCacheFresh() {
    return _cache && (Date.now() - _cache.ts) < TTL_MS;
}

function _doFetch() {
    if (_inflight) return _inflight;
    _inflight = api.get("/contabilita/giornate-chiuse")
        .then((r) => {
            _cache = { ts: Date.now(), set: new Set(r.data || []) };
            // notifica tutti i subscriber attivi
            _subscribers.forEach((cb) => cb(_cache.set));
            return _cache.set;
        })
        .catch(() => new Set())
        .finally(() => { _inflight = null; });
    return _inflight;
}

export default function useGiornateChiuse() {
    const [chiuse, setChiuse] = useState(_cache?.set || new Set());

    useEffect(() => {
        if (_isCacheFresh()) {
            setChiuse(_cache.set);
            return;
        }
        let cancelled = false;
        const cb = (s) => { if (!cancelled) setChiuse(s); };
        _subscribers.add(cb);
        _doFetch();
        return () => { cancelled = true; _subscribers.delete(cb); };
    }, []);

    return chiuse;
}

/** Forza il refresh della cache (es. dopo chiusura/riapertura). */
export function invalidateGiornateChiuseCache() {
    _cache = null;
    _doFetch();
}
