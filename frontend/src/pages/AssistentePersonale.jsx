/**
 * Cervello — Agente AI che suggerisce attività ai collaboratori in base a
 * regole automatiche: polizze in scadenza, sinistri lenti, upsell catastrofale,
 * obbligo catastrofale per aziende (D.Lgs ICAT).
 *
 * Lista interattiva: click su una card naviga al record (polizza/sinistro/cliente).
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Loading, PageHeader } from "@/components/Shared";
import { Brain, AlertTriangle, RefreshCw, ChevronRight, Sparkles, Search } from "lucide-react";
import { toast } from "sonner";

const PRIORITA_COLOR = {
    alta: "border-rose-400 bg-rose-50/40",
    media: "border-amber-400 bg-amber-50/40",
    bassa: "border-slate-300 bg-slate-50/40",
};
const TIPO_LABEL = {
    rinnovo_imminente: "Rinnovo",
    sinistro_lento: "Sinistro fermo",
    upsell_catastrofale: "Upsell catastrofale",
    obbligo_catastrofale_azienda: "Obbligo di legge",
    cliente_fedele: "Cliente fedele",
    polizza_ferma_5y: "Polizza ferma 5+ anni",
    molti_sinistri: "Alto rischio",
    aumento_premio_auto: "Aumento premio",
};

export default function AssistentePersonale() {
    const navigate = useNavigate();
    const [items, setItems] = useState(null);
    const [filter, setFilter] = useState("all");
    const [soloMiei, setSoloMiei] = useState(false);
    const load = () => {
        setItems(null);
        api.get("/cervello/suggerimenti", { params: { limit: 100, solo_miei: soloMiei } })
            .then((r) => setItems(r.data || []));
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [soloMiei]);
    if (items === null) return <Loading />;
    const filtered = filter === "all" ? items : items.filter((i) => i.priorita === filter);
    const counts = items.reduce((acc, i) => { acc[i.priorita] = (acc[i.priorita] || 0) + 1; return acc; }, {});
    const go = (s) => {
        if (s.sinistro_id) navigate(`/sinistri/${s.sinistro_id}`);
        else if (s.polizza_id) navigate(`/polizze/${s.polizza_id}`);
        else if (s.anagrafica_id) navigate(`/clienti/${s.anagrafica_id}`);
    };
    return (
        <div data-testid="assistente-page" className="space-y-4">
            <PageHeader
                title={<span className="flex items-center gap-2"><Brain className="text-violet-600" /> Assistente Personale</span>}
                subtitle="Suggerimenti AI personalizzati sui clienti e portafoglio"
                actions={
                    <Button onClick={load} variant="outline" data-testid="cervello-refresh">
                        <RefreshCw size={14} className="mr-1" /> Aggiorna
                    </Button>
                }
            />

            <AiConsiglioPanel />


            <Card className="p-3 flex flex-wrap gap-2 items-center">
                <span className="text-xs text-slate-500 font-medium">Filtra per priorità:</span>
                {["all", "alta", "media"].map((p) => (
                    <button key={p} onClick={() => setFilter(p)}
                        className={`text-xs px-2 py-1 rounded border ${
                            filter === p ? "bg-violet-600 text-white border-violet-600"
                                : "border-slate-300 text-slate-700 hover:bg-slate-50"
                        }`}
                        data-testid={`cerv-filter-${p}`}>
                        {p === "all" ? `Tutti (${items.length})`
                            : `${p === "alta" ? "Alta" : "Media"} (${counts[p] || 0})`}
                    </button>
                ))}
                <label className="ml-auto inline-flex items-center gap-1.5 text-xs cursor-pointer select-none" data-testid="solo-miei-toggle">
                    <input type="checkbox" checked={soloMiei} onChange={(e) => setSoloMiei(e.target.checked)} className="accent-violet-600" />
                    <span className={soloMiei ? "font-semibold text-violet-700" : "text-slate-600"}>👤 Solo i miei clienti</span>
                </label>
            </Card>

            {filtered.length === 0 ? (
                <Card className="p-10 text-center">
                    <Brain size={48} className="mx-auto text-slate-300 mb-3" />
                    <div className="text-slate-500">Nessun suggerimento. Portafoglio in ottimo stato.</div>
                </Card>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {filtered.map((s, i) => (
                        <Card
                            key={i}
                            onClick={() => go(s)}
                            className={`p-3 border-l-4 cursor-pointer hover:shadow-md transition-all ${PRIORITA_COLOR[s.priorita]}`}
                            data-testid={`cerv-card-${i}`}
                        >
                            <div className="flex items-start gap-2">
                                <AlertTriangle size={18} className={s.priorita === "alta" ? "text-rose-600" : "text-amber-600"} />
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center justify-between gap-2">
                                        <div className="text-[10px] uppercase tracking-wider font-semibold text-slate-500">
                                            {TIPO_LABEL[s.tipo] || s.tipo}
                                        </div>
                                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold uppercase ${
                                            s.priorita === "alta" ? "bg-rose-100 text-rose-700" : "bg-amber-100 text-amber-700"
                                        }`}>{s.priorita}</span>
                                    </div>
                                    <div className="font-semibold text-slate-800 mt-1 truncate">{s.titolo}</div>
                                    <div className="text-xs text-slate-600 mt-1">{s.descrizione}</div>
                                </div>
                                <ChevronRight size={16} className="text-slate-400 mt-1 shrink-0" />
                            </div>
                        </Card>
                    ))}
                </div>
            )}
        </div>
    );
}


// ============ AI Consiglio personalizzato (Claude Sonnet 4.6) ============
function AiConsiglioPanel() {
    const [query, setQuery] = useState("");
    const [risultati, setRisultati] = useState([]);
    const [selected, setSelected] = useState(null);
    const [contesto, setContesto] = useState("");
    const [consiglio, setConsiglio] = useState(null);
    const [loading, setLoading] = useState(false);

    const search = async (q) => {
        setQuery(q);
        if (q.length < 2) { setRisultati([]); return; }
        try {
            const r = await api.get("/anagrafiche", { params: { q, limit: 8 } });
            setRisultati(r.data || []);
        } catch { setRisultati([]); }
    };

    const genera = async () => {
        if (!selected) { toast.error("Seleziona prima un cliente"); return; }
        setLoading(true); setConsiglio(null);
        try {
            const r = await api.post("/assistente-personale/genera-consiglio", {
                anagrafica_id: selected.id, contesto_extra: contesto,
            });
            setConsiglio(r.data.consiglio);
        } catch (e) { toast.error(e.response?.data?.detail || "Errore AI"); }
        finally { setLoading(false); }
    };

    return (
        <Card className="p-4 border-2 border-violet-200 bg-gradient-to-br from-violet-50 to-white" data-testid="ai-panel">
            <div className="flex items-center gap-2 mb-3">
                <Sparkles className="text-violet-600" size={18} />
                <h2 className="font-semibold text-slate-800">Consiglio AI personalizzato (Claude Sonnet 4.6)</h2>
            </div>
            <div className="space-y-3">
                <div>
                    <div className="text-xs text-slate-600 mb-1">Cerca cliente</div>
                    <div className="relative">
                        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                        <Input value={query} onChange={(e) => search(e.target.value)}
                            placeholder="Inizia a digitare nome o cognome…" className="pl-9"
                            data-testid="ai-search" />
                    </div>
                    {risultati.length > 0 && !selected && (
                        <div className="mt-1 max-h-40 overflow-y-auto bg-white border border-slate-200 rounded shadow text-sm">
                            {risultati.map((a) => (
                                <button key={a.id} className="block w-full text-left px-3 py-1.5 hover:bg-violet-50"
                                    onClick={() => { setSelected(a); setQuery(a.ragione_sociale || `${a.cognome || ""} ${a.nome || ""}`); setRisultati([]); }}
                                    data-testid={`ai-cli-${a.id}`}>
                                    <span className="font-medium">{a.ragione_sociale || `${a.cognome || ""} ${a.nome || ""}`}</span>
                                    <span className="text-xs text-slate-500 ml-2">{a.codice_fiscale || a.partita_iva || ""}</span>
                                </button>
                            ))}
                        </div>
                    )}
                    {selected && (
                        <div className="mt-1 bg-white border-2 border-violet-300 rounded p-2 flex items-center gap-2">
                            <span className="text-sm font-medium flex-1">{selected.ragione_sociale || `${selected.cognome || ""} ${selected.nome || ""}`}</span>
                            <button onClick={() => { setSelected(null); setQuery(""); setConsiglio(null); }}
                                className="text-xs text-rose-600 hover:underline">cambia</button>
                        </div>
                    )}
                </div>
                <div>
                    <div className="text-xs text-slate-600 mb-1">Contesto extra (opzionale)</div>
                    <Textarea rows={2} value={contesto} onChange={(e) => setContesto(e.target.value)}
                        placeholder="es. Ha appena cambiato lavoro, mi ha chiesto info sulla casa al mare…"
                        data-testid="ai-contesto" />
                </div>
                <Button onClick={genera} disabled={!selected || loading}
                    className="bg-violet-700 hover:bg-violet-800" data-testid="ai-genera">
                    <Sparkles size={14} className="mr-1" /> {loading ? "Claude sta scrivendo…" : "Genera consiglio AI"}
                </Button>
                {consiglio && (
                    <div className="bg-white border-l-4 border-violet-500 rounded p-3 shadow-sm whitespace-pre-wrap text-sm" data-testid="ai-result">
                        {consiglio}
                    </div>
                )}
            </div>
        </Card>
    );
}

