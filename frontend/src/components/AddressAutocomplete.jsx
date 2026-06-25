import { useEffect, useRef, useState } from "react";
import { MapPin } from "lucide-react";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

/**
 * Autocomplete indirizzo via Nominatim (gratis, OpenStreetMap).
 * Mostra un dropdown con suggerimenti mentre l'utente digita.
 * Quando un suggerimento viene selezionato chiama `onSelect(payload)`
 * con: {indirizzo, comune, cap, provincia, regione, nazione, lat, lng, display_name}.
 *
 * Props:
 *  - value: stringa indirizzo corrente
 *  - onChange(string): change manuale (utente digita)
 *  - onSelect(payload): scelta dal dropdown
 *  - placeholder, testid, disabled, className
 */
export default function AddressAutocomplete({
    value,
    onChange,
    onSelect,
    placeholder = "Digita indirizzo, comune o CAP…",
    testid = "address-autocomplete",
    disabled = false,
    className = "",
}) {
    const [open, setOpen] = useState(false);
    const [items, setItems] = useState([]);
    const [highlight, setHighlight] = useState(-1);
    const [loading, setLoading] = useState(false);
    const wrapRef = useRef(null);
    const timerRef = useRef(null);
    const lastQuery = useRef("");

    useEffect(() => {
        // chiudi su click esterno
        const onDoc = (e) => {
            if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
        };
        document.addEventListener("mousedown", onDoc);
        return () => document.removeEventListener("mousedown", onDoc);
    }, []);

    const fetchSuggest = (q) => {
        if (timerRef.current) clearTimeout(timerRef.current);
        if (!q || q.trim().length < 3) {
            setItems([]); setOpen(false); return;
        }
        // debounce 450ms (rispetta rate-limit Nominatim 1 req/sec)
        timerRef.current = setTimeout(async () => {
            if (lastQuery.current === q) return;
            lastQuery.current = q;
            setLoading(true);
            try {
                const r = await api.get("/geo/suggest", { params: { q } });
                setItems(r.data || []);
                setOpen((r.data || []).length > 0);
                setHighlight(-1);
            } catch {
                setItems([]);
            } finally {
                setLoading(false);
            }
        }, 450);
    };

    const handleChange = (e) => {
        const v = e.target.value;
        onChange && onChange(v);
        fetchSuggest(v);
    };

    const pick = (it) => {
        setOpen(false);
        setItems([]);
        onSelect && onSelect(it);
    };

    const onKey = (e) => {
        if (!open || items.length === 0) return;
        if (e.key === "ArrowDown") {
            e.preventDefault(); setHighlight((h) => Math.min(items.length - 1, h + 1));
        } else if (e.key === "ArrowUp") {
            e.preventDefault(); setHighlight((h) => Math.max(0, h - 1));
        } else if (e.key === "Enter" && highlight >= 0) {
            e.preventDefault(); pick(items[highlight]);
        } else if (e.key === "Escape") {
            setOpen(false);
        }
    };

    return (
        <div ref={wrapRef} className={`relative ${className}`}>
            <div className="relative">
                <Input
                    value={value || ""}
                    onChange={handleChange}
                    onKeyDown={onKey}
                    onFocus={() => items.length > 0 && setOpen(true)}
                    placeholder={placeholder}
                    disabled={disabled}
                    data-testid={testid}
                    autoComplete="off"
                />
                <MapPin
                    size={16}
                    className={`absolute right-2 top-1/2 -translate-y-1/2 ${loading ? "animate-pulse text-sky-500" : "text-slate-400"}`}
                />
            </div>
            {open && items.length > 0 && (
                <div
                    className="absolute z-50 left-0 right-0 mt-1 bg-white border border-slate-200 rounded-md shadow-lg max-h-72 overflow-y-auto"
                    data-testid={`${testid}-dropdown`}
                >
                    {items.map((it, idx) => (
                        <button
                            type="button"
                            key={`${it.lat}-${it.lng}-${idx}`}
                            onClick={() => pick(it)}
                            onMouseEnter={() => setHighlight(idx)}
                            className={`w-full text-left px-3 py-2 flex gap-3 items-start border-b border-slate-100 last:border-0 ${
                                idx === highlight ? "bg-sky-50" : "hover:bg-slate-50"
                            }`}
                            data-testid={`${testid}-item-${idx}`}
                        >
                            <MapPin size={16} className="text-slate-400 mt-0.5 shrink-0" />
                            <div className="min-w-0">
                                <div className="text-sm font-medium text-slate-900 truncate">
                                    {it.indirizzo || it.name || it.display_name}
                                </div>
                                <div className="text-xs text-slate-500 truncate">{it.display_name}</div>
                            </div>
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}
