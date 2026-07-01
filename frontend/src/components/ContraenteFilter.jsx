/**
 * ContraenteFilter — selector autocompleting che cerca le anagrafiche
 * mentre si digita. Usato come filtro standard in tutte le liste
 * (Polizze, Titoli, Sinistri, Trattative, …).
 */
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { User, X, Search } from "lucide-react";

export default function ContraenteFilter({ value, onChange, placeholder = "Filtra per contraente…" }) {
    const [q, setQ] = useState("");
    const [resolved, setResolved] = useState(null); // anagrafica object
    const [results, setResults] = useState([]);
    const [showList, setShowList] = useState(false);
    const ref = useRef(null);

    // se value cambia esternamente, risolvilo
    useEffect(() => {
        if (!value || value === "all") { setResolved(null); return; }
        api.get(`/anagrafiche/${value}`).then((r) => setResolved(r.data)).catch(() => setResolved(null));
    }, [value]);

    // chiudi su click esterno
    useEffect(() => {
        const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setShowList(false); };
        document.addEventListener("mousedown", h);
        return () => document.removeEventListener("mousedown", h);
    }, []);

    // ricerca debouncing
    useEffect(() => {
        if (!q || q.length < 2) { setResults([]); return; }
        const t = setTimeout(() => {
            api.get("/search", { params: { q, limit: 12 } }).then((r) => {
                setResults(r.data.anagrafiche || []);
            }).catch(() => setResults([]));
        }, 250);
        return () => clearTimeout(t);
    }, [q]);

    const pick = (a) => {
        onChange(a.id);
        setShowList(false);
        setQ("");
    };

    const clear = () => {
        onChange("all");
        setQ("");
        setResolved(null);
    };

    if (resolved) {
        return (
            <div className="relative">
                <div className="flex items-center gap-2 h-9 px-3 border border-sky-300 bg-sky-50 rounded text-sm" data-testid="contraente-filter-active">
                    <User size={12} className="text-sky-600" />
                    <span className="flex-1 truncate text-sky-900 font-medium">{resolved.ragione_sociale || `${resolved.cognome || ""} ${resolved.nome || ""}`}</span>
                    <button onClick={clear} className="text-sky-700 hover:text-rose-600" title="Rimuovi filtro" data-testid="contraente-filter-clear">
                        <X size={12} />
                    </button>
                </div>
            </div>
        );
    }
    return (
        <div className="relative" ref={ref}>
            <div className="relative">
                <Search size={12} className="absolute left-2.5 top-2.5 text-slate-400" />
                <Input
                    placeholder={placeholder}
                    value={q}
                    onChange={(e) => { setQ(e.target.value); setShowList(true); }}
                    onFocus={() => setShowList(true)}
                    className="pl-7 text-sm"
                    data-testid="contraente-filter"
                />
            </div>
            {showList && q.length >= 2 && (
                <div className="absolute z-50 mt-1 w-full bg-white border border-slate-200 rounded shadow-lg max-h-64 overflow-y-auto"
                    data-testid="contraente-filter-results">
                    {results.length === 0 ? (
                        <div className="p-3 text-xs text-slate-400 italic">Nessun contraente trovato</div>
                    ) : results.map((a) => (
                        <button key={a.id} onClick={() => pick(a)}
                            className="block w-full text-left px-3 py-1.5 hover:bg-sky-50 border-b border-slate-100 last:border-b-0"
                            data-testid={`contraente-opt-${a.id}`}>
                            <div className="text-sm font-medium">{a.ragione_sociale || `${a.cognome || ""} ${a.nome || ""}`}</div>
                            <div className="text-[10px] text-slate-500">
                                {a.codice_fiscale || ""} {a.cellulare && `· 📱 ${a.cellulare}`} {a.email && `· ✉ ${a.email}`}
                            </div>
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}
