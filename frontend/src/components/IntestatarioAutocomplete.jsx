/**
 * IntestatarioAutocomplete — campo "Contraente" con autocomplete su anagrafiche.
 *
 * Comportamento:
 *  - Digita >= 2 caratteri: cerca in /anagrafiche?q=… e mostra dropdown
 *  - Click su una anagrafica: collega (setta anagraficaId + intestatario testo)
 *  - Nessun match: mostra pulsante "+ Crea anagrafica al volo"
 *  - Badge 🔗 quando è collegato + X per scollegare
 *
 * Props:
 *  value            testo Intestatario (persona/azienda)
 *  anagraficaId     id dell'anagrafica collegata (o null)
 *  onChange(name, anagraficaId)   callback chiamato ad ogni modifica
 *  compact          se true, layout più stretto (per dialog stretti)
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Plus, X } from "lucide-react";
import { toast } from "sonner";

export default function IntestatarioAutocomplete({ value, anagraficaId, onChange }) {
    const [q, setQ] = useState(value || "");
    const [results, setResults] = useState([]);
    const [loading, setLoading] = useState(false);
    const [showList, setShowList] = useState(false);
    const [creatingNew, setCreatingNew] = useState(false);

    // Sync q with external value changes (es. edit di applicazione esistente)
    useEffect(() => { setQ(value || ""); }, [value]);

    useEffect(() => {
        if (!q || q.length < 2) { setResults([]); return; }
        const t = setTimeout(async () => {
            setLoading(true);
            try {
                const r = await api.get("/anagrafiche", { params: { q, limit: 8 } });
                setResults((r.data || []).slice(0, 8));
            } catch { setResults([]); }
            finally { setLoading(false); }
        }, 300);
        return () => clearTimeout(t);
    }, [q]);

    const collega = (a) => {
        const display = a.ragione_sociale || a.cognome_nome
            || `${a.cognome || ""} ${a.nome || ""}`.trim();
        onChange(display, a.id);
        setQ(display);
        setShowList(false);
        toast.success(`Collegato a ${display}`);
    };

    const scollega = () => {
        onChange(q, null);
        toast.info("Anagrafica scollegata (resta il testo libero)");
    };

    const creaAlVolo = async () => {
        if (!q || q.length < 2) return;
        setCreatingNew(true);
        try {
            const upper = q.toUpperCase();
            const isAzienda = /\b(SRL|SPA|SNC|SAS|SS|SCARL|COOP|SC|SRLS|S\.R\.L\.|S\.P\.A\.|S\.N\.C\.|S\.A\.S\.)\b/.test(upper);
            const payload = isAzienda
                ? { tipo_soggetto: "giuridico", ragione_sociale: q.trim().toUpperCase() }
                : (() => {
                    const parts = q.trim().split(/\s+/);
                    return {
                        tipo_soggetto: "fisico",
                        cognome: (parts[0] || "").toUpperCase(),
                        nome: parts.slice(1).join(" ").toUpperCase(),
                    };
                })();
            const r = await api.post("/anagrafiche", payload);
            const nuovaId = r.data?.id;
            const display = isAzienda ? payload.ragione_sociale
                                       : `${payload.cognome} ${payload.nome}`.trim();
            onChange(display, nuovaId);
            setQ(display);
            setShowList(false);
            toast.success(`Anagrafica creata: ${display}`);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore creazione anagrafica");
        } finally { setCreatingNew(false); }
    };

    return (
        <div className="relative">
            <Input
                value={q}
                onChange={(e) => { setQ(e.target.value); setShowList(true); onChange(e.target.value, null); }}
                onFocus={() => setShowList(true)}
                onBlur={() => setTimeout(() => setShowList(false), 200)}
                placeholder="Cerca cognome, nome o ragione sociale…"
                data-testid="intestatario-autocomplete"
                className={anagraficaId ? "border-emerald-400 pr-28" : "pr-6"}
            />
            {anagraficaId && (
                <div className="absolute right-1 top-1 text-[10px] flex items-center gap-1">
                    <span className="bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded">🔗 collegato</span>
                    <button onClick={scollega} className="text-slate-400 hover:text-rose-600" title="Scollega anagrafica">
                        <X size={12} />
                    </button>
                </div>
            )}
            {showList && q.length >= 2 && (
                <div className="absolute z-30 top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded shadow-lg max-h-64 overflow-y-auto">
                    {loading && <div className="p-2 text-xs text-slate-400">Cerco…</div>}
                    {!loading && results.length === 0 && (
                        <div className="p-2">
                            <div className="text-xs text-slate-500 mb-1">Nessuna anagrafica trovata per <b>{q}</b></div>
                            <button onClick={creaAlVolo}
                                    disabled={creatingNew}
                                    className="w-full text-[11px] px-2 py-1.5 rounded bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50">
                                <Plus size={11} className="inline mr-1" />
                                {creatingNew ? "Creazione…" : `+ Crea anagrafica "${q}"`}
                            </button>
                        </div>
                    )}
                    {!loading && results.map((a) => {
                        const label = a.ragione_sociale || a.cognome_nome
                            || `${a.cognome || ""} ${a.nome || ""}`.trim();
                        const sub = [a.codice_fiscale, a.partita_iva, a.comune_residenza].filter(Boolean).join(" · ");
                        return (
                            <button key={a.id}
                                    onClick={() => collega(a)}
                                    className="w-full text-left px-2 py-1.5 hover:bg-sky-50 border-b border-slate-100 text-xs">
                                <div className="font-medium">{label}</div>
                                {sub && <div className="text-[10px] text-slate-500">{sub}</div>}
                            </button>
                        );
                    })}
                    {!loading && results.length > 0 && (
                        <button onClick={creaAlVolo}
                                disabled={creatingNew}
                                className="w-full text-left px-2 py-1.5 text-[11px] bg-emerald-50 text-emerald-700 hover:bg-emerald-100">
                            <Plus size={11} className="inline mr-1" /> + Crea nuova anagrafica &quot;{q}&quot;
                        </button>
                    )}
                </div>
            )}
        </div>
    );
}
