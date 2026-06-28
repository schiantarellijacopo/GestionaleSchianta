/**
 * useTableSort + <SortHeader/>
 *
 * Hook e componente riusabili per ordinamento cliccabile sulle colonne
 * di QUALSIASI tabella del programma. Esempio d'uso:
 *
 *   const { sorted, sortKey, dir, toggle } = useTableSort(rows, "numero_polizza");
 *   ...
 *   <th><SortHeader sortKey={sortKey} dir={dir} k="numero_polizza" toggle={toggle}>Numero polizza</SortHeader></th>
 *   ...
 *   {sorted.map(...)}
 *
 * Supporta sort: string, number, ISO date, custom accessor (passa `accessor`).
 */
import { useMemo, useState } from "react";
import { ChevronUp, ChevronDown, ChevronsUpDown } from "lucide-react";

const _toComparable = (v) => {
    if (v == null) return "";
    if (typeof v === "number") return v;
    if (typeof v === "boolean") return v ? 1 : 0;
    const s = String(v);
    // ISO date (YYYY-MM-DD…) → ordinabile come stringa è già lessicograficamente OK
    return s.toLowerCase();
};

export function useTableSort(rows, defaultKey = null, defaultDir = "asc", accessors = {}) {
    const [sortKey, setSortKey] = useState(defaultKey);
    const [dir, setDir] = useState(defaultDir);

    const sorted = useMemo(() => {
        if (!Array.isArray(rows)) return rows;
        if (!sortKey) return rows;
        const out = [...rows];
        out.sort((a, b) => {
            const acc = accessors[sortKey];
            const va = _toComparable(acc ? acc(a) : a?.[sortKey]);
            const vb = _toComparable(acc ? acc(b) : b?.[sortKey]);
            if (va < vb) return dir === "asc" ? -1 : 1;
            if (va > vb) return dir === "asc" ? 1 : -1;
            return 0;
        });
        return out;
    }, [rows, sortKey, dir, accessors]);

    const toggle = (k) => {
        if (sortKey === k) {
            setDir((d) => (d === "asc" ? "desc" : "asc"));
        } else {
            setSortKey(k);
            setDir("asc");
        }
    };

    return { sorted, sortKey, dir, toggle, setSortKey, setDir };
}

export default function SortHeader({ k, sortKey, dir, toggle, children, className = "" }) {
    const active = sortKey === k;
    return (
        <button
            type="button"
            onClick={() => toggle(k)}
            className={`inline-flex items-center gap-1 select-none hover:text-sky-700 transition-colors ${
                active ? "text-sky-700" : ""
            } ${className}`}
            data-testid={`th-sort-${k}`}
        >
            {children}
            {!active && <ChevronsUpDown size={11} className="opacity-40" />}
            {active && dir === "asc" && <ChevronUp size={11} />}
            {active && dir === "desc" && <ChevronDown size={11} />}
        </button>
    );
}
