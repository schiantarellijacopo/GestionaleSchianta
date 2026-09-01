/**
 * ColumnManager — colonne selezionabili + drag & drop, salvate per utente.
 *
 * Uso:
 *   const { cols, picker } = useTableColumns("polizze", DEFAULT_COLS);
 *   // DEFAULT_COLS: [{ key, label, sort?, thClass?, tdClass?, header?(), render(row, ctx), locked? }]
 *   // {picker} = bottone "Colonne"; cols = colonne visibili nell'ordine scelto.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Columns3, GripVertical, RotateCcw } from "lucide-react";

let PREFS_CACHE = null;
let PREFS_PROMISE = null;
function loadAllPrefs() {
    if (PREFS_CACHE) return Promise.resolve(PREFS_CACHE);
    if (!PREFS_PROMISE) {
        PREFS_PROMISE = api.get("/preferenze/colonne")
            .then((r) => { PREFS_CACHE = r.data || {}; return PREFS_CACHE; })
            .catch(() => { PREFS_CACHE = {}; return PREFS_CACHE; });
    }
    return PREFS_PROMISE;
}

export function useTableColumns(tableKey, defaultCols) {
    const [prefs, setPrefs] = useState(() => {
        try { return JSON.parse(localStorage.getItem(`colprefs:${tableKey}`)); } catch { return null; }
    });

    useEffect(() => {
        let alive = true;
        loadAllPrefs().then((all) => {
            if (alive && all && all[tableKey]) {
                setPrefs(all[tableKey]);
                localStorage.setItem(`colprefs:${tableKey}`, JSON.stringify(all[tableKey]));
            }
        });
        return () => { alive = false; };
    }, [tableKey]);

    const ordered = useMemo(() => {
        const map = new Map(defaultCols.map((c) => [c.key, c]));
        const order = (prefs?.order || []).filter((k) => map.has(k));
        const rest = defaultCols.map((c) => c.key).filter((k) => !order.includes(k));
        return [...order, ...rest].map((k) => map.get(k));
    }, [defaultCols, prefs]);

    const hiddenSet = useMemo(() => new Set(prefs?.hidden || []), [prefs]);
    const cols = useMemo(() => ordered.filter((c) => c.locked || !hiddenSet.has(c.key)),
        [ordered, hiddenSet]);

    const save = (next) => {
        setPrefs(next);
        if (PREFS_CACHE) PREFS_CACHE[tableKey] = next;
        localStorage.setItem(`colprefs:${tableKey}`, JSON.stringify(next));
        api.put(`/preferenze/colonne/${tableKey}`, next).catch(() => {});
    };
    const reset = () => {
        setPrefs(null);
        if (PREFS_CACHE) delete PREFS_CACHE[tableKey];
        localStorage.removeItem(`colprefs:${tableKey}`);
        api.delete(`/preferenze/colonne/${tableKey}`).catch(() => {});
    };

    const picker = (
        <ColumnPicker tableKey={tableKey} ordered={ordered} hiddenSet={hiddenSet}
                      save={save} reset={reset} />
    );
    return { cols, picker };
}

function ColumnPicker({ tableKey, ordered, hiddenSet, save, reset }) {
    const dragIdx = useRef(null);
    const [overIdx, setOverIdx] = useState(null);

    const toggle = (key) => {
        const hidden = new Set(hiddenSet);
        if (hidden.has(key)) hidden.delete(key); else hidden.add(key);
        save({ order: ordered.map((c) => c.key), hidden: [...hidden] });
    };
    const drop = (idx) => {
        const from = dragIdx.current;
        dragIdx.current = null;
        setOverIdx(null);
        if (from == null || from === idx) return;
        const keys = ordered.map((c) => c.key);
        const [moved] = keys.splice(from, 1);
        keys.splice(idx, 0, moved);
        save({ order: keys, hidden: [...hiddenSet] });
    };

    return (
        <Popover>
            <PopoverTrigger asChild>
                <Button variant="outline" size="sm" className="h-8 text-xs"
                        data-testid={`colonne-btn-${tableKey}`}>
                    <Columns3 size={13} className="mr-1" /> Colonne
                </Button>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-64 p-2" data-testid={`colonne-popover-${tableKey}`}>
                <div className="flex items-center justify-between mb-1 px-1">
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                        Trascina per riordinare
                    </span>
                    <button onClick={reset} className="text-slate-400 hover:text-sky-600 flex items-center gap-1 text-[10px]"
                            title="Ripristina colonne predefinite"
                            data-testid={`colonne-reset-${tableKey}`}>
                        <RotateCcw size={11} /> Predefinite
                    </button>
                </div>
                <div className="space-y-0.5 max-h-80 overflow-y-auto">
                    {ordered.map((c, i) => (
                        <div key={c.key}
                             draggable
                             onDragStart={() => (dragIdx.current = i)}
                             onDragOver={(e) => { e.preventDefault(); setOverIdx(i); }}
                             onDragLeave={() => setOverIdx((v) => (v === i ? null : v))}
                             onDrop={() => drop(i)}
                             onDragEnd={() => { dragIdx.current = null; setOverIdx(null); }}
                             className={`flex items-center gap-2 px-1.5 py-1 rounded text-xs cursor-grab active:cursor-grabbing ${
                                 overIdx === i ? "bg-sky-50 border border-sky-300" : "hover:bg-slate-50 border border-transparent"
                             }`}
                             data-testid={`colonna-item-${tableKey}-${c.key}`}>
                            <GripVertical size={12} className="text-slate-300 shrink-0" />
                            <input type="checkbox"
                                   checked={c.locked || !hiddenSet.has(c.key)}
                                   disabled={c.locked}
                                   onChange={() => toggle(c.key)}
                                   onClick={(e) => e.stopPropagation()}
                                   data-testid={`colonna-check-${tableKey}-${c.key}`} />
                            <span className="truncate flex-1">{c.label || c.key}</span>
                        </div>
                    ))}
                </div>
            </PopoverContent>
        </Popover>
    );
}
