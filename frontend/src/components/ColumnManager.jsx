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
import { Columns3, GripVertical, RotateCcw, ChevronUp, ChevronDown } from "lucide-react";

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
        const keys = (prefs?.order || []).filter((k) => map.has(k));
        // colonne nuove (non presenti nell'ordine salvato): inseriscile nella
        // posizione naturale del default, non in fondo
        const defKeys = defaultCols.map((c) => c.key);
        for (const k of defKeys) {
            if (keys.includes(k)) continue;
            const defIdx = defKeys.indexOf(k);
            let insertAt = keys.length;
            for (let i = defIdx - 1; i >= 0; i--) {
                const prevIdx = keys.indexOf(defKeys[i]);
                if (prevIdx !== -1) { insertAt = prevIdx + 1; break; }
                if (i === 0) insertAt = 0;
            }
            if (defIdx === 0) insertAt = 0;
            keys.splice(insertAt, 0, k);
        }
        return keys.map((k) => map.get(k));
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
    // Sposta su/giù (alternativa al drag, funziona anche su touch)
    const move = (idx, delta) => {
        const to = idx + delta;
        if (to < 0 || to >= ordered.length) return;
        const keys = ordered.map((c) => c.key);
        const [moved] = keys.splice(idx, 1);
        keys.splice(to, 0, moved);
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
                        Trascina o usa ▲▼ per riordinare
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
                             className={`flex items-center gap-2 px-1.5 py-1 rounded text-xs ${
                                 overIdx === i ? "bg-sky-50 border border-sky-300" : "hover:bg-slate-50 border border-transparent"
                             }`}
                             data-testid={`colonna-item-${tableKey}-${c.key}`}>
                            <GripVertical size={13} className="text-slate-400 shrink-0 cursor-grab active:cursor-grabbing" />
                            <input type="checkbox"
                                   checked={c.locked || !hiddenSet.has(c.key)}
                                   disabled={c.locked}
                                   onChange={() => toggle(c.key)}
                                   onClick={(e) => e.stopPropagation()}
                                   data-testid={`colonna-check-${tableKey}-${c.key}`} />
                            <span className="truncate flex-1">{c.label || c.key}</span>
                            <div className="flex flex-col shrink-0 -my-0.5">
                                <button type="button" onClick={(e) => { e.stopPropagation(); move(i, -1); }}
                                        disabled={i === 0}
                                        className="text-slate-300 hover:text-sky-600 disabled:opacity-20 disabled:hover:text-slate-300 leading-none"
                                        title="Sposta su" data-testid={`colonna-up-${tableKey}-${c.key}`}>
                                    <ChevronUp size={13} />
                                </button>
                                <button type="button" onClick={(e) => { e.stopPropagation(); move(i, 1); }}
                                        disabled={i === ordered.length - 1}
                                        className="text-slate-300 hover:text-sky-600 disabled:opacity-20 disabled:hover:text-slate-300 leading-none"
                                        title="Sposta giù" data-testid={`colonna-down-${tableKey}-${c.key}`}>
                                    <ChevronDown size={13} />
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            </PopoverContent>
        </Popover>
    );
}
