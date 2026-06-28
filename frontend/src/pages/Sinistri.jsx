/**
 * Sinistri — lista con filtri estesi, colonne complete, totali in fondo,
 * navigazione al dettaglio (SinistroDetail) e stampa elenco PDF.
 *
 * Colonne: Num.Int · N. Sinistro · N. Contratto · Data avv. · Contraente ·
 * Compagnia · Tipologia · Danneggiato · Targa · Collaboratore · Riserva · Liquidato · Stato
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, fmtDate, fmtEur, API_BASE } from "@/lib/api";
import { PageHeader, StatusBadge, Loading, Empty } from "@/components/Shared";
import KpiBar from "@/components/KpiBar";
import SortHeader, { useTableSort } from "@/components/SortHeader";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import {
    Plus, Search, Filter, X, Printer, FileText, FileSpreadsheet, ChevronDown, ChevronUp,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

const STATI = [
    { v: "aperto", l: "Aperti" },
    { v: "in_istruttoria", l: "In istruttoria" },
    { v: "liquidato", l: "Liquidati" },
    { v: "chiuso", l: "Chiusi" },
    { v: "chiuso_senza_seguito", l: "Chiusi senza seguito" },
    { v: "respinto", l: "Respinti" },
];

export default function Sinistri() {
    const { user } = useAuth();
    const navigate = useNavigate();
    const [params] = useSearchParams();
    const initialStato = params.get("stato") || "all";
    const polizzaIdFilter = params.get("polizza_id");

    const [list, setList] = useState(null);
    const [compagnie, setCompagnie] = useState([]);
    const [rami, setRami] = useState([]);
    const [utenti, setUtenti] = useState([]);
    const [tipologie, setTipologie] = useState([]);
    const [showFilters, setShowFilters] = useState(false);
    const [open, setOpen] = useState(false);

    const [filters, setFilters] = useState({
        q: "", stato: initialStato, compagnia_id: "all", ramo: "all",
        collaboratore_id: "all", tipologia: "all", dal: "", al: "",
    });
    const setF = (k, v) => setFilters((p) => ({ ...p, [k]: v }));

    const canCreate = ["admin", "collaboratore", "dipendente"].includes(user?.role);

    const buildParams = () => {
        const p = {};
        if (filters.q) p.q = filters.q;
        if (filters.stato !== "all") p.stato = filters.stato;
        if (filters.compagnia_id !== "all") p.compagnia_id = filters.compagnia_id;
        if (filters.ramo !== "all") p.ramo = filters.ramo;
        if (filters.collaboratore_id !== "all") p.collaboratore_id = filters.collaboratore_id;
        if (filters.tipologia !== "all") p.tipologia = filters.tipologia;
        if (filters.dal) p.dal = filters.dal;
        if (filters.al) p.al = filters.al;
        if (polizzaIdFilter) p.polizza_id = polizzaIdFilter;
        return p;
    };

    const load = () => api.get("/sinistri", { params: buildParams() }).then((r) => {
        setList(r.data);
        // estrai tipologie uniche per dropdown
        const tip = [...new Set((r.data || []).map((s) => s.tipologia_sinistro).filter(Boolean))];
        setTipologie(tip);
    });

    useEffect(() => { load(); /* eslint-disable-next-line */ }, [filters, polizzaIdFilter]);
    useEffect(() => {
        Promise.all([
            api.get("/compagnie").catch(() => ({ data: [] })),
            api.get("/librerie/rami").catch(() => ({ data: [] })),
            api.get("/auth/users").catch(() => ({ data: [] })),
        ]).then(([c, r, u]) => {
            setCompagnie(c.data); setRami(r.data);
            setUtenti((u.data || []).filter((x) => x.role !== "cliente"));
        });
    }, []);

    const { sorted, sortKey, dir, toggle } = useTableSort(list || [], "data_avvenimento", "desc");

    const totali = useMemo(() => {
        const src = list || [];
        return {
            n: src.length,
            stimato: src.reduce((s, x) => s + (x.riserva || 0), 0),
            liquidato: src.reduce((s, x) => s + (x.liquidazione || 0), 0),
        };
    }, [list]);

    const stampaPdf = () => window.open(
        `${API_BASE}/stampa/sinistri${filters.stato !== "all" ? `?stato=${filters.stato}` : ""}`,
        "_blank",
    );

    return (
        <div data-testid="sinistri-page">
            <PageHeader
                title="Sinistri"
                subtitle="Denunce di sinistro · filtri estesi · stampa elenco"
                actions={canCreate && (
                    <Dialog open={open} onOpenChange={setOpen}>
                        <DialogTrigger asChild>
                            <Button data-testid="sinistro-new-button" className="bg-sky-700 hover:bg-sky-800">
                                <Plus size={16} className="mr-1" /> Nuova denuncia
                            </Button>
                        </DialogTrigger>
                        <NuovoSinistroDialog onClose={() => { setOpen(false); load(); }} />
                    </Dialog>
                )}
            />

            <KpiBar sezione="sinistri" />

            {/* Toolbar */}
            <div className="bg-white border border-slate-200 rounded-md p-3 mb-3">
                <div className="flex flex-wrap items-center gap-2 mb-2">
                    <div className="relative flex-1 min-w-[260px]">
                        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                        <Input
                            data-testid="sin-search"
                            placeholder="Cerca per n. sinistro, n. interno, luogo, tipologia…"
                            value={filters.q} onChange={(e) => setF("q", e.target.value)} className="pl-9"
                        />
                    </div>
                    <Button variant="outline" onClick={() => setShowFilters((s) => !s)} data-testid="sin-toggle-filters">
                        <Filter size={14} className="mr-1" /> Filtri
                        {showFilters ? <ChevronUp size={12} className="ml-1" /> : <ChevronDown size={12} className="ml-1" />}
                    </Button>
                    <div className="ml-auto flex gap-2">
                        <Button variant="outline" onClick={stampaPdf} data-testid="sin-print-list">
                            <Printer size={14} className="mr-1" /> Stampa PDF
                        </Button>
                    </div>
                </div>

                {showFilters && (
                    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2 mt-2 pt-2 border-t border-slate-100">
                        <Select value={filters.stato} onValueChange={(v) => setF("stato", v)}>
                            <SelectTrigger data-testid="sin-f-stato"><SelectValue placeholder="Stato" /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Tutti gli stati</SelectItem>
                                {STATI.map((s) => <SelectItem key={s.v} value={s.v}>{s.l}</SelectItem>)}
                            </SelectContent>
                        </Select>
                        <Select value={filters.compagnia_id} onValueChange={(v) => setF("compagnia_id", v)}>
                            <SelectTrigger data-testid="sin-f-compagnia"><SelectValue placeholder="Compagnia" /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Tutte compagnie</SelectItem>
                                {compagnie.map((c) => <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}</SelectItem>)}
                            </SelectContent>
                        </Select>
                        <Select value={filters.ramo} onValueChange={(v) => setF("ramo", v)}>
                            <SelectTrigger data-testid="sin-f-ramo"><SelectValue placeholder="Ramo" /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Tutti rami</SelectItem>
                                {rami.map((r) => <SelectItem key={r.id} value={r.codice}>{r.nome}</SelectItem>)}
                            </SelectContent>
                        </Select>
                        <Select value={filters.collaboratore_id} onValueChange={(v) => setF("collaboratore_id", v)}>
                            <SelectTrigger data-testid="sin-f-collab"><SelectValue placeholder="Collaboratore" /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Tutti collaboratori</SelectItem>
                                {utenti.map((u) => <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>)}
                            </SelectContent>
                        </Select>
                        <Select value={filters.tipologia} onValueChange={(v) => setF("tipologia", v)}>
                            <SelectTrigger data-testid="sin-f-tipologia"><SelectValue placeholder="Tipologia" /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Tutte tipologie</SelectItem>
                                {tipologie.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                            </SelectContent>
                        </Select>
                        <div>
                            <Label className="text-[10px] text-slate-500">Avvenimento dal</Label>
                            <Input type="date" value={filters.dal} onChange={(e) => setF("dal", e.target.value)} data-testid="sin-f-dal" />
                        </div>
                        <div>
                            <Label className="text-[10px] text-slate-500">al</Label>
                            <Input type="date" value={filters.al} onChange={(e) => setF("al", e.target.value)} data-testid="sin-f-al" />
                        </div>
                        <button onClick={() => setFilters({
                            q: "", stato: "all", compagnia_id: "all", ramo: "all",
                            collaboratore_id: "all", tipologia: "all", dal: "", al: "",
                        })} className="text-xs text-slate-500 hover:text-rose-600 inline-flex items-center gap-1 col-span-2"
                          data-testid="sin-clear-filters">
                            <X size={12} /> Azzera filtri
                        </button>
                    </div>
                )}
            </div>

            {polizzaIdFilter && (
                <div className="mb-3 flex items-center gap-2 text-xs bg-amber-50 border border-amber-200 text-amber-900 rounded px-3 py-2">
                    <span>Filtrato per polizza specifica.</span>
                    <Link to="/sinistri" className="underline hover:text-amber-700">Rimuovi filtro</Link>
                </div>
            )}

            <div className="tbl-scroll" style={{ "--c1-w": "120px", "--c2-w": "140px" }}>
                {list === null ? <Loading /> : list.length === 0 ? <Empty /> : (
                    <table className="tbl-compact freeze-2 w-full text-xs">
                        <thead>
                            <tr>
                                <th className="w-[120px]"><SortHeader k="numero_interno" sortKey={sortKey} dir={dir} toggle={toggle}>Num. Int.</SortHeader></th>
                                <th className="w-[140px]"><SortHeader k="numero_sinistro" sortKey={sortKey} dir={dir} toggle={toggle}>N. Sinistro</SortHeader></th>
                                <th className="w-[110px]"><SortHeader k="numero_polizza" sortKey={sortKey} dir={dir} toggle={toggle}>Contratto</SortHeader></th>
                                <th className="w-[90px]"><SortHeader k="data_avvenimento" sortKey={sortKey} dir={dir} toggle={toggle}>Data</SortHeader></th>
                                <th><SortHeader k="contraente_nome" sortKey={sortKey} dir={dir} toggle={toggle}>Contraente</SortHeader></th>
                                <th className="w-[110px]"><SortHeader k="compagnia_nome" sortKey={sortKey} dir={dir} toggle={toggle}>Compagnia</SortHeader></th>
                                <th className="w-[150px]"><SortHeader k="tipologia_sinistro" sortKey={sortKey} dir={dir} toggle={toggle}>Tipologia</SortHeader></th>
                                <th className="w-[140px]"><SortHeader k="danneggiato_nome" sortKey={sortKey} dir={dir} toggle={toggle}>Danneggiato</SortHeader></th>
                                <th className="w-[80px]"><SortHeader k="targa" sortKey={sortKey} dir={dir} toggle={toggle}>Targa</SortHeader></th>
                                <th className="w-[110px]"><SortHeader k="collaboratore_nome" sortKey={sortKey} dir={dir} toggle={toggle}>Collaboratore</SortHeader></th>
                                <th className="text-right w-[80px]"><SortHeader k="riserva" sortKey={sortKey} dir={dir} toggle={toggle}>Riserva €</SortHeader></th>
                                <th className="text-right w-[90px]"><SortHeader k="liquidazione" sortKey={sortKey} dir={dir} toggle={toggle}>Liquidato €</SortHeader></th>
                                <th className="w-[80px]"><SortHeader k="stato" sortKey={sortKey} dir={dir} toggle={toggle}>Stato</SortHeader></th>
                            </tr>
                        </thead>
                        <tbody>
                            {sorted.map((s) => {
                                const stato = (s.stato || "").toLowerCase();
                                const dotColor = stato === "aperto" ? "bg-emerald-500"
                                    : stato === "liquidato" ? "bg-sky-500"
                                    : stato === "respinto" ? "bg-rose-500"
                                    : "bg-slate-400";
                                return (
                                    <tr key={s.id} data-testid={`sinistro-row-${s.id}`}
                                        className="hover:bg-sky-50/60 cursor-pointer"
                                        onClick={() => navigate(`/sinistri/${s.id}`)}>
                                        <td className="font-medium text-amber-700">{s.numero_interno || "—"}</td>
                                        <td className="font-medium">{s.numero_sinistro}</td>
                                        <td>
                                            <Link to={`/polizze/${s.polizza_id}`} onClick={(e) => e.stopPropagation()}
                                                  className="text-sky-700 hover:underline">{s.numero_polizza || "—"}</Link>
                                        </td>
                                        <td className="num">{fmtDate(s.data_avvenimento)}</td>
                                        <td className="truncate max-w-[180px]">{s.contraente_nome}</td>
                                        <td>{s.compagnia_nome || "—"}</td>
                                        <td className="truncate max-w-[150px]" title={s.tipologia_sinistro}>{s.tipologia_sinistro || "—"}</td>
                                        <td>{s.danneggiato_nome || "—"}</td>
                                        <td className="font-mono">{s.targa || "—"}</td>
                                        <td>{s.collaboratore_nome || "—"}</td>
                                        <td className="num text-right">{fmtEur(s.riserva)}</td>
                                        <td className="num text-right">{fmtEur(s.liquidazione)}</td>
                                        <td>
                                            <div className="flex items-center gap-1.5">
                                                <span className={`inline-block w-2 h-2 rounded-full ${dotColor}`} />
                                                <span className="capitalize">{(s.stato || "").replace("_", " ")}</span>
                                            </div>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                        <tfoot className="bg-slate-50 border-t-2 border-slate-300 font-semibold sticky bottom-0">
                            <tr>
                                <td colSpan={10} className="px-2 py-2">
                                    Totale: <span className="text-slate-900">{totali.n}</span> sinistri
                                </td>
                                <td className="text-right num">{fmtEur(totali.stimato)}</td>
                                <td className="text-right num">{fmtEur(totali.liquidato)}</td>
                                <td></td>
                            </tr>
                        </tfoot>
                    </table>
                )}
            </div>
        </div>
    );
}

// ============ Nuova denuncia (Dialog) ============
function NuovoSinistroDialog({ onClose }) {
    const navigate = useNavigate();
    const [polizze, setPolizze] = useState([]);
    const [f, setF] = useState({
        numero_sinistro: "", numero_interno: "", polizza_id: "",
        data_avvenimento: new Date().toISOString().slice(0, 10),
        data_denuncia: new Date().toISOString().slice(0, 10),
        luogo: "", descrizione: "", riserva: 0, stato: "aperto",
        tipologia_sinistro: "",
    });
    useEffect(() => { api.get("/polizze").then((r) => setPolizze(r.data)); }, []);
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const save = async () => {
        if (!f.numero_sinistro || !f.polizza_id || !f.data_avvenimento) {
            toast.error("Compila i campi obbligatori"); return;
        }
        const pol = polizze.find((p) => p.id === f.polizza_id);
        try {
            const r = await api.post("/sinistri", {
                ...f,
                compagnia_id: pol?.compagnia_id || "",
                contraente_id: pol?.contraente_id || "",
                ramo: pol?.ramo,
                riserva: parseFloat(f.riserva) || 0,
                anno: parseInt((f.data_avvenimento || "").slice(0, 4)) || null,
                data_apertura: f.data_denuncia,
            });
            toast.success("Sinistro creato");
            onClose();
            // Vai direttamente al detail
            if (r.data?.id) navigate(`/sinistri/${r.data.id}`);
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <DialogContent className="max-w-2xl">
            <DialogHeader><DialogTitle>Nuova denuncia sinistro</DialogTitle></DialogHeader>
            <div className="grid grid-cols-2 gap-3 py-2">
                <div><Label className="text-xs">Numero sinistro *</Label>
                    <Input value={f.numero_sinistro} onChange={(e) => set("numero_sinistro", e.target.value)} data-testid="sin-numero-input" /></div>
                <div><Label className="text-xs">Numero interno</Label>
                    <Input value={f.numero_interno} onChange={(e) => set("numero_interno", e.target.value)} data-testid="sin-numero-interno-input" /></div>
                <div className="col-span-2">
                    <Label className="text-xs">Polizza *</Label>
                    <Select value={f.polizza_id} onValueChange={(v) => set("polizza_id", v)}>
                        <SelectTrigger data-testid="sin-polizza-select"><SelectValue placeholder="Seleziona polizza" /></SelectTrigger>
                        <SelectContent>
                            {polizze.map((p) => <SelectItem key={p.id} value={p.id}>{p.numero_polizza} — {p.contraente_nome} ({p.ramo})</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
                <div><Label className="text-xs">Tipologia sinistro</Label>
                    <Input value={f.tipologia_sinistro} onChange={(e) => set("tipologia_sinistro", e.target.value)}
                        placeholder="es. SINISTRI FENOMENO ELETTRICO" /></div>
                <div>
                    <Label className="text-xs">Stato</Label>
                    <Select value={f.stato} onValueChange={(v) => set("stato", v)}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                            {STATI.map((s) => <SelectItem key={s.v} value={s.v}>{s.l}</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
                <div><Label className="text-xs">Data avvenimento *</Label>
                    <Input type="date" value={f.data_avvenimento} onChange={(e) => set("data_avvenimento", e.target.value)} /></div>
                <div><Label className="text-xs">Data denuncia</Label>
                    <Input type="date" value={f.data_denuncia} onChange={(e) => set("data_denuncia", e.target.value)} /></div>
                <div className="col-span-2"><Label className="text-xs">Luogo</Label>
                    <Input value={f.luogo} onChange={(e) => set("luogo", e.target.value)} /></div>
                <div className="col-span-2"><Label className="text-xs">Descrizione</Label>
                    <Textarea rows={3} value={f.descrizione} onChange={(e) => set("descrizione", e.target.value)} /></div>
                <div><Label className="text-xs">Riserva €</Label>
                    <Input type="number" step="0.01" value={f.riserva} onChange={(e) => set("riserva", e.target.value)} /></div>
            </div>
            <DialogFooter>
                <Button onClick={save} data-testid="sin-save-button" className="bg-sky-700 hover:bg-sky-800">
                    Crea sinistro
                </Button>
            </DialogFooter>
        </DialogContent>
    );
}
