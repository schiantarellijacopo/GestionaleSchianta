import { useEffect, useMemo, useState } from "react";
import { api, fmtDate } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import {
    BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid,
} from "recharts";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Activity, Route, Printer, Download, PencilLine, Plus, Trash2, LogIn, Search } from "lucide-react";

const AZIONE_LABEL = {
    create: "Creazione", update: "Modifica", delete: "Eliminazione",
    stampa: "Stampa", esportazione: "Esportazione", navigazione: "Navigazione",
    login: "Accesso", logout: "Disconnessione", incasso: "Incasso", invio: "Invio",
    import: "Import", overwrite: "Sovrascrittura", merge: "Unione",
};

const AZIONE_ICON = {
    create: Plus, update: PencilLine, delete: Trash2, stampa: Printer,
    esportazione: Download, navigazione: Route, login: LogIn,
};

const PALETTE = ["#0ea5e9", "#6366f1", "#10b981", "#f59e0b", "#ef4444",
    "#8b5cf6", "#14b8a6", "#ec4899", "#84cc16", "#64748b"];

const fmtDT = (iso) => {
    if (!iso) return "";
    try {
        const d = new Date(iso);
        return d.toLocaleDateString("it-IT") + " " +
            d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
    } catch (e) { return iso; }
};

export default function AuditOperatori() {
    const [stats, setStats] = useState(null);
    const [operatori, setOperatori] = useState([]);
    const [eventi, setEventi] = useState(null);
    const [total, setTotal] = useState(0);
    const [percorso, setPercorso] = useState(null);

    // filtri
    const [fUtente, setFUtente] = useState("all");
    const [fArea, setFArea] = useState("all");
    const [fAzione, setFAzione] = useState("all");
    const [dal, setDal] = useState("");
    const [al, setAl] = useState("");
    const [q, setQ] = useState("");
    const [page, setPage] = useState(0);
    const PAGE = 100;

    const loadStats = () => {
        const params = {};
        if (dal) params.dal = dal;
        if (al) params.al = al;
        api.get("/audit/stats", { params }).then((r) => setStats(r.data)).catch(() => setStats({ operatori: [], aree: [] }));
    };
    const loadEventi = () => {
        const params = { limit: PAGE, skip: page * PAGE };
        if (fUtente !== "all") params.utente_id = fUtente;
        if (fArea !== "all") params.area = fArea;
        if (fAzione !== "all") params.azione = fAzione;
        if (dal) params.dal = dal;
        if (al) params.al = al;
        if (q) params.q = q;
        api.get("/audit/eventi", { params }).then((r) => {
            setEventi(r.data.items); setTotal(r.data.total);
        }).catch(() => { setEventi([]); setTotal(0); });
    };
    const loadPercorso = (uid) => {
        if (!uid || uid === "all") { setPercorso(null); return; }
        const params = { utente_id: uid, limit: 200 };
        if (dal) params.dal = dal;
        if (al) params.al = al;
        api.get("/audit/percorso", { params }).then((r) => setPercorso(r.data.items)).catch(() => setPercorso([]));
    };

    useEffect(() => { api.get("/audit/operatori").then((r) => setOperatori(r.data)).catch(() => {}); }, []);
    useEffect(() => { loadStats(); /* eslint-disable-next-line */ }, [dal, al]);
    useEffect(() => { loadEventi(); /* eslint-disable-next-line */ }, [fUtente, fArea, fAzione, dal, al, page]);
    useEffect(() => { loadPercorso(fUtente); /* eslint-disable-next-line */ }, [fUtente, dal, al]);

    // dati grafico: operatori × top aree
    const { chartData, chartAree } = useMemo(() => {
        if (!stats) return { chartData: [], chartAree: [] };
        const topAree = (stats.aree || []).slice(0, 8);
        const rows = (stats.operatori || []).map((op) => {
            const row = { nome: op.nome || op.email || "?" };
            let altre = 0;
            Object.entries(op.aree || {}).forEach(([a, n]) => {
                if (topAree.includes(a)) row[a] = n; else altre += n;
            });
            if (altre > 0) row["Altre"] = altre;
            return row;
        });
        const keys = [...topAree];
        if (rows.some((r) => r["Altre"])) keys.push("Altre");
        return { chartData: rows, chartAree: keys };
    }, [stats]);

    const azioni = ["create", "update", "delete", "stampa", "esportazione", "navigazione"];

    return (
        <div data-testid="audit-operatori-page">
            <PageHeader
                title="Monitoraggio operatori"
                subtitle="Cronologia completa di ciò che fa ogni operatore — creazioni, modifiche, stampe, esportazioni e percorso di navigazione. Visibile solo all'amministratore."
            />

            {/* Filtri */}
            <div className="flex flex-wrap items-end gap-3 mb-5">
                <div>
                    <label className="block text-xs text-slate-500 mb-1">Operatore</label>
                    <Select value={fUtente} onValueChange={(v) => { setFUtente(v); setPage(0); }}>
                        <SelectTrigger className="w-56" data-testid="audit-filter-operatore"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">Tutti gli operatori</SelectItem>
                            {operatori.map((o) => (
                                <SelectItem key={o.id} value={o.id}>{o.name || o.email}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
                <div>
                    <label className="block text-xs text-slate-500 mb-1">Area</label>
                    <Select value={fArea} onValueChange={(v) => { setFArea(v); setPage(0); }}>
                        <SelectTrigger className="w-48" data-testid="audit-filter-area"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">Tutte le aree</SelectItem>
                            {(stats?.aree || []).map((a) => <SelectItem key={a} value={a}>{a}</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
                <div>
                    <label className="block text-xs text-slate-500 mb-1">Azione</label>
                    <Select value={fAzione} onValueChange={(v) => { setFAzione(v); setPage(0); }}>
                        <SelectTrigger className="w-44" data-testid="audit-filter-azione"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">Tutte le azioni</SelectItem>
                            {azioni.map((a) => <SelectItem key={a} value={a}>{AZIONE_LABEL[a] || a}</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
                <div>
                    <label className="block text-xs text-slate-500 mb-1">Dal</label>
                    <Input type="date" value={dal} onChange={(e) => { setDal(e.target.value); setPage(0); }} className="w-40" data-testid="audit-filter-dal" />
                </div>
                <div>
                    <label className="block text-xs text-slate-500 mb-1">Al</label>
                    <Input type="date" value={al} onChange={(e) => { setAl(e.target.value); setPage(0); }} className="w-40" data-testid="audit-filter-al" />
                </div>
                <div className="flex-1 min-w-[180px]">
                    <label className="block text-xs text-slate-500 mb-1">Cerca nel percorso/endpoint</label>
                    <div className="flex gap-2">
                        <Input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && (setPage(0), loadEventi())} placeholder="es. /polizze" data-testid="audit-filter-q" />
                        <Button variant="secondary" onClick={() => { setPage(0); loadEventi(); }} data-testid="audit-search-btn"><Search size={16} /></Button>
                    </div>
                </div>
            </div>

            {/* Grafico aree più usate per operatore */}
            <div className="bg-white border border-slate-200 rounded-xl p-4 mb-6" data-testid="audit-chart">
                <h3 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
                    <Activity size={16} className="text-sky-600" /> Aree più utilizzate per operatore
                </h3>
                {stats === null ? <Loading /> : chartData.length === 0 ? <Empty message="Nessun dato nel periodo selezionato" /> : (
                    <ResponsiveContainer width="100%" height={Math.max(260, chartData.length * 54)}>
                        <BarChart data={chartData} layout="vertical" margin={{ left: 20, right: 20 }}>
                            <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                            <XAxis type="number" allowDecimals={false} fontSize={12} />
                            <YAxis type="category" dataKey="nome" width={140} fontSize={12} />
                            <Tooltip />
                            <Legend wrapperStyle={{ fontSize: 12 }} />
                            {chartAree.map((a, i) => (
                                <Bar key={a} dataKey={a} stackId="s" fill={PALETTE[i % PALETTE.length]} radius={i === chartAree.length - 1 ? [0, 4, 4, 0] : 0} />
                            ))}
                        </BarChart>
                    </ResponsiveContainer>
                )}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Eventi */}
                <div className="lg:col-span-2">
                    <div className="flex items-center justify-between mb-2">
                        <h3 className="text-sm font-semibold text-slate-700">Eventi</h3>
                        <span className="text-xs text-slate-500 num">{total} eventi</span>
                    </div>
                    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
                        {eventi === null ? <Loading /> : eventi.length === 0 ? <Empty /> : (
                            <ul className="divide-y divide-slate-100 max-h-[560px] overflow-auto">
                                {eventi.map((e) => {
                                    const Ic = AZIONE_ICON[e.azione] || Activity;
                                    return (
                                        <li key={e.id} className="px-4 py-2.5 flex items-start gap-3 hover:bg-slate-50" data-testid={`audit-evento-${e.id}`}>
                                            <div className="w-7 h-7 rounded-full bg-slate-100 text-slate-600 flex items-center justify-center shrink-0 mt-0.5">
                                                <Ic size={13} />
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <div className="text-sm text-slate-900">
                                                    <span className="font-medium">{e.utente_nome || e.utente_email || "?"}</span>
                                                    {" — "}<span className="text-slate-600">{AZIONE_LABEL[e.azione] || e.azione}</span>
                                                    {" · "}<span className="badge badge-neutral">{e.area}</span>
                                                </div>
                                                <div className="text-[11px] text-slate-400 font-mono truncate">{e.metodo} {e.path}</div>
                                            </div>
                                            <div className="text-[11px] text-slate-400 num shrink-0 text-right">{fmtDT(e.created_at)}</div>
                                        </li>
                                    );
                                })}
                            </ul>
                        )}
                    </div>
                    {total > PAGE && (
                        <div className="flex items-center justify-center gap-3 mt-3">
                            <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)} data-testid="audit-prev">Precedente</Button>
                            <span className="text-xs text-slate-500">Pagina {page + 1} di {Math.ceil(total / PAGE)}</span>
                            <Button variant="outline" size="sm" disabled={(page + 1) * PAGE >= total} onClick={() => setPage((p) => p + 1)} data-testid="audit-next">Successiva</Button>
                        </div>
                    )}
                </div>

                {/* Percorso operatore */}
                <div>
                    <h3 className="text-sm font-semibold text-slate-700 mb-2 flex items-center gap-2">
                        <Route size={16} className="text-indigo-600" /> Percorso operatore
                    </h3>
                    <div className="bg-white border border-slate-200 rounded-xl p-3" data-testid="audit-percorso">
                        {fUtente === "all" ? (
                            <p className="text-sm text-slate-500 py-6 text-center">Seleziona un operatore per vedere il percorso di navigazione e le azioni.</p>
                        ) : percorso === null ? <Loading /> : percorso.length === 0 ? <Empty /> : (
                            <ol className="relative border-l border-slate-200 ml-2 space-y-3 max-h-[560px] overflow-auto pr-1">
                                {percorso.map((p) => (
                                    <li key={p.id} className="ml-4" data-testid={`audit-step-${p.id}`}>
                                        <div className="absolute -left-[5px] w-2.5 h-2.5 rounded-full bg-indigo-400 mt-1.5" />
                                        <div className="text-sm text-slate-800">
                                            {p.azione === "navigazione"
                                                ? <>Ha aperto <span className="font-medium">{p.area}</span></>
                                                : <><span className="font-medium">{AZIONE_LABEL[p.azione] || p.azione}</span> in <span className="text-slate-600">{p.area}</span></>}
                                        </div>
                                        <div className="text-[11px] text-slate-400 num">{fmtDT(p.created_at)}</div>
                                    </li>
                                ))}
                            </ol>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
