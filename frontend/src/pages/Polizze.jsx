import { useEffect, useState, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, fmtDate, fmtEur, API_BASE } from "@/lib/api";
import { useAutoRefresh } from "@/hooks/useAutoRefresh";
import { openPdf } from "@/lib/pdf";
import { PageHeader, StatusBadge, Loading, Empty } from "@/components/Shared";
import CollaboratoreCell from "@/components/CollaboratoreCell";
import IconForRamo from "@/components/IconForRamo";
import ContraenteFilter from "@/components/ContraenteFilter";
import SortHeader from "@/components/SortHeader";
import DateInputIt from "@/components/DateInputIt";
import useFillHeight from "@/hooks/useFillHeight";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter, DialogDescription,
} from "@/components/ui/dialog";
import {
    Search, Plus, ScanLine, Filter, X, Printer, FileSpreadsheet, FileText,
    ChevronDown, ChevronUp, Car, Upload,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import KpiBar from "@/components/KpiBar";
import ImportExcelDialog from "@/components/ImportExcelDialog";
import { useTableColumns } from "@/components/ColumnManager";

// Colonne tabella Polizze — selezionabili/riordinabili per utente
const POLIZZE_COLS = [
    {
        key: "numero_polizza", label: "Numero polizza", sort: "numero_polizza",
        render: (p) => <Link to={`/polizze/${p.id}`} className="text-sky-700 hover:underline font-medium">{p.numero_polizza}</Link>,
    },
    {
        key: "targa", label: "Targa", sort: "targa",
        tdClass: "text-xs text-sky-700 font-mono font-medium uppercase",
        render: (p) => p.targa || <span className="text-slate-300">—</span>,
    },
    { key: "contraente", label: "Contraente", sort: "contraente_nome", tdClass: "text-xs", render: (p) => p.contraente_nome || "—" },
    { key: "compagnia", label: "Compagnia", sort: "compagnia_nome", tdClass: "text-xs text-slate-600", render: (p) => p.compagnia_nome || "—" },
    {
        key: "collaboratore", label: "Collaboratore", sort: "collaboratore_nome", tdClass: "text-xs text-slate-600",
        render: (p) => p.collaboratore_nome ? <CollaboratoreCell nome={p.collaboratore_nome} avatarUrl={p.collaboratore_avatar_url} /> : "—",
    },
    {
        key: "ramo", label: "Ramo", sort: "ramo",
        render: (p) => (
            <>
                <div className="flex items-center gap-1.5">
                    <span className="inline-flex w-6 h-6 rounded-md items-center justify-center bg-slate-100 text-slate-600" title={p.ramo}>
                        <IconForRamo ramo={p.ramo} size={13} />
                    </span>
                    <span className="badge badge-neutral">{p.ramo}</span>
                </div>
                {p.catastrofale && (
                    <span className="ml-1 text-[9px] bg-amber-100 text-amber-800 border border-amber-300 px-1 py-0.5 rounded font-bold" title="Garanzia catastrofale (terremoto/alluvione)">🌊 CAT</span>
                )}
                {p.check_up && (
                    <span className="ml-1 text-[9px] bg-emerald-100 text-emerald-800 border border-emerald-300 px-1 py-0.5 rounded font-bold" title="Garanzia Check-up sanitario">🏥 CHK</span>
                )}
                {p.inabilita_malattia && (
                    <span className="ml-1 text-[9px] bg-rose-100 text-rose-800 border border-rose-300 px-1 py-0.5 rounded font-bold" title="Inabilità da malattia">🤒 INA</span>
                )}
                {p.tutela_legale && (
                    <span className="ml-1 text-[9px] bg-indigo-100 text-indigo-800 border border-indigo-300 px-1 py-0.5 rounded font-bold" title="Tutela legale">⚖️ TL</span>
                )}
                {p.infortuni_conducente && (
                    <span className="ml-1 text-[9px] bg-violet-100 text-violet-800 border border-violet-300 px-1 py-0.5 rounded font-bold" title="Infortuni conducente">🚗 IC</span>
                )}
            </>
        ),
    },
    { key: "stato", label: "Stato", sort: "stato", render: (p) => <StatusBadge stato={p.stato} /> },
    { key: "effetto", label: "Effetto", sort: "data_effetto", tdClass: "num text-xs", render: (p) => fmtDate(p.effetto) },
    { key: "scadenza", label: "Scadenza", sort: "data_scadenza", tdClass: "num text-xs", render: (p) => fmtDate(p.scadenza) },
    { key: "premio_lordo", label: "Premio lordo", sort: "premio_lordo", thClass: "text-right", tdClass: "num text-right font-medium", render: (p) => fmtEur(p.premio_lordo) },
    { key: "provvigioni", label: "Provvigioni", sort: "provvigioni", thClass: "text-right", tdClass: "num text-right text-slate-600", render: (p) => fmtEur(p.provvigioni) },
];

const PRESETS = [
    { key: "attive", label: "Attive" },
    { key: "scadute", label: "Scadute" },
    { key: "sospese", label: "Sospese" },
    { key: "annullate", label: "Annullate" },
];

const presetParams = (key) => {
    switch (key) {
        case "attive": return { stato: "attiva" };
        case "sospese": return { stato: "sospesa" };
        case "scadute": return { stato: "scaduta" };
        case "annullate": return { stato: "annullata" };
        case "sostituite": return { stato: "sostituita" };
        case "scad15": return { in_scadenza_giorni: 15 };
        case "scad_oltre15": return { scadenza_oltre_giorni: 15 };
        case "scadute_oggi": return { scadute_oggi: true };
        case "scad_5g": return { scadute_da_min: 5 };
        case "scad_10g": return { scadute_da_min: 10 };
        case "scad_14g": return { scadute_da_min: 14 };
        default: return {};
    }
};

const INITIAL_FILTERS = {
    preset: "attive", q: "",
    stato: "all", compagnia_id: "all", ramo: "all", tag: "all", prodotto: "",
    collaboratore_id: "all", contraente_id: "all",
    dal: "", al: "",
};

export default function Polizze() {
    const { user } = useAuth();
    const [list, setList] = useState(null);
    const [compagnie, setCompagnie] = useState([]);
    const [rami, setRami] = useState([]);
    const [tagOptions, setTagOptions] = useState([]);
    const [utenti, setUtenti] = useState([]);
    const [open, setOpen] = useState(false);
    const [importOpen, setImportOpen] = useState(false);
    const [showFilters, setShowFilters] = useState(false);
    const [filters, setFilters] = useState(INITIAL_FILTERS);
    const setF = (k, v) => setFilters((p) => ({ ...p, [k]: v }));
    const canCreate = ["admin", "collaboratore", "dipendente"].includes(user?.role);
    const [page, setPage] = useState(1);
    const [pageSize, setPageSize] = useState(50);
    const PAGE_SIZE = pageSize;
    const fill = useFillHeight([showFilters]);
    const [total, setTotal] = useState(0);
    const [pages, setPages] = useState(1);
    const [serverTotali, setServerTotali] = useState({ t_lordo: 0, t_netto: 0, t_provv: 0 });
    const [sortBy, setSortBy] = useState("data_scadenza");
    const [sortDir, setSortDir] = useState("asc");
    const toggleSort = (k) => {
        if (sortBy === k) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
        else { setSortBy(k); setSortDir("asc"); }
        setPage(1);
    };

    const buildParams = () => {
        const p = { ...presetParams(filters.preset) };
        if (filters.q) p.q = filters.q;
        if (filters.stato !== "all") p.stato = filters.stato;
        // Le polizze ANNULLATE si vedono solo scegliendo esplicitamente lo stato/preset
        // "annullata" (velocizza il caricamento delle altre viste).
        if (p.stato !== "annullata") p.escludi_annullate = true;
        if (filters.compagnia_id !== "all") p.compagnia_id = filters.compagnia_id;
        if (filters.ramo !== "all") p.ramo = filters.ramo;
        if (filters.tag && filters.tag !== "all") p.tag = filters.tag;
        if (filters.collaboratore_id !== "all") p.collaboratore_id = filters.collaboratore_id;
        if (filters.contraente_id !== "all") p.contraente_id = filters.contraente_id;
        if (filters.prodotto) p.prodotto = filters.prodotto;
        if (filters.dal) p.dal = filters.dal;
        if (filters.al) p.al = filters.al;
        return p;
    };

    const load = () => {
        api.get("/polizze", { params: { ...buildParams(), paged: true, page, page_size: PAGE_SIZE, sort: sortBy, dir: sortDir } })
            .then((r) => {
                setList(r.data.items || []);
                setTotal(r.data.total || 0);
                setPages(r.data.pages || 1);
                setServerTotali(r.data.totali || { t_lordo: 0, t_netto: 0, t_provv: 0 });
            });
    };
    const [conteggi, setConteggi] = useState({});
    const [marcandoScadute, setMarcandoScadute] = useState(false);
    const loadConteggi = () => {
        api.get("/polizze/conteggi-stato").then((r) => setConteggi(r.data || {})).catch(() => {});
    };
    const contaPreset = (key) => {
        const map = { tutti: "_tot", attive: "attiva", scadute: "scaduta", sospese: "sospesa", annullate: "annullata", sostituite: "sostituita" };
        const k = map[key];
        return k ? (conteggi[k] ?? 0) : null;
    };
    const segnaScadute = async () => {
        if (!window.confirm("Marcare come 'scadute' le polizze attive con scadenza passata e senza rinnovo attivo?")) return;
        setMarcandoScadute(true);
        try {
            const r = await api.post("/polizze/ricalcola-scadute");
            toast.success(`${r.data.marcate_scadute} polizze marcate come scadute`);
            loadConteggi(); load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        } finally { setMarcandoScadute(false); }
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [filters, page, sortBy, sortDir, pageSize]);
    useEffect(() => { setPage(1); /* eslint-disable-next-line */ }, [filters, pageSize]);
    useEffect(() => { loadConteggi(); /* eslint-disable-next-line */ }, []);
    // Aggiornamento automatico (10s + al rientro finestra)
    useAutoRefresh(() => { load(); loadConteggi(); }, 10000);

    useEffect(() => {
        Promise.all([
            api.get("/compagnie"), api.get("/librerie/rami?dedup=1&con_polizze=1"),
            api.get("/auth/users").catch(() => ({ data: [] })),
        ]).then(([c, r, u]) => {
            setCompagnie(c.data); setRami(r.data);
            setUtenti((u.data || []).filter((x) => x.role !== "cliente" && x.attivo !== false));
        });
        api.get("/anagrafiche/tags").then((r) => setTagOptions(r.data || [])).catch(() => {});
    }, []);

    const baseList = list || [];
    const { cols, picker } = useTableColumns("polizze", POLIZZE_COLS);
    const displayed = baseList;

    const totali = serverTotali;

    const qs = (params) => {
        const u = new URLSearchParams();
        Object.entries(params).forEach(([k, v]) => {
            if (v !== undefined && v !== null && v !== "" && v !== false) u.append(k, String(v));
        });
        return u.toString();
    };

    const exportCsv = () => {
        const link = document.createElement("a");
        link.href = `${API_BASE}/export/polizze.csv?${qs(buildParams())}`;
        link.target = "_blank";
        document.body.appendChild(link); link.click(); link.remove();
    };
    const exportXlsx = () => {
        const link = document.createElement("a");
        link.href = `${API_BASE}/export/polizze.xlsx?${qs(buildParams())}`;
        link.target = "_blank";
        document.body.appendChild(link); link.click(); link.remove();
    };
    const stampaPdf = () => openPdf("/stampa/polizze", buildParams());

    return (
        <div data-testid="polizze-page">
            <PageHeader
                title="Polizze"
                subtitle="Portafoglio polizze - filtri, presets ed esportazioni"
                actions={canCreate && (
                    <div className="flex items-center gap-2">
                        <Button variant="outline"
                                onClick={() => setImportOpen(true)}
                                data-testid="polizza-import-button"
                                className="border-emerald-300 text-emerald-700 hover:bg-emerald-50">
                            <Upload size={16} className="mr-1" /> Importa Excel/CSV
                        </Button>
                        <Dialog open={open} onOpenChange={setOpen}>
                            <DialogTrigger asChild>
                                <Button data-testid="polizza-new-button" className="bg-sky-700 hover:bg-sky-800">
                                    <Plus size={16} className="mr-1" /> Nuova polizza
                                </Button>
                            </DialogTrigger>
                            <NuovaPolizzaDialog onClose={() => { setOpen(false); load(); }} />
                        </Dialog>
                    </div>
                )}
            />

            <KpiBar sezione="polizze" />

            {/* Preset rapidi */}
            <div className="flex flex-wrap items-center gap-2 mb-3">
                {PRESETS.map((p) => {
                    const cnt = contaPreset(p.key);
                    return (
                    <button
                        key={p.key}
                        onClick={() => setF("preset", p.key)}
                        data-testid={`pol-preset-${p.key}`}
                        className={`px-3 py-1.5 rounded-md text-xs font-medium border transition-colors ${
                            filters.preset === p.key
                                ? "bg-slate-900 text-white border-slate-900"
                                : "bg-white border-slate-200 text-slate-700 hover:bg-slate-50"
                        }`}
                    >
                        {p.label}
                        {cnt !== null && (
                            <span className={`ml-1.5 px-1.5 py-0.5 rounded-full text-[10px] font-semibold ${
                                filters.preset === p.key ? "bg-white/20 text-white" : "bg-slate-100 text-slate-600"
                            }`} data-testid={`pol-preset-count-${p.key}`}>{cnt}</span>
                        )}
                    </button>
                    );
                })}
                {canCreate && (
                    <button
                        onClick={segnaScadute}
                        disabled={marcandoScadute}
                        data-testid="pol-segna-scadute"
                        className="ml-auto px-3 py-1.5 rounded-md text-xs font-medium border border-amber-300 bg-amber-50 text-amber-700 hover:bg-amber-100 transition-colors disabled:opacity-50"
                        title="Marca come scadute le polizze attive con scadenza passata e senza rinnovo"
                    >
                        {marcandoScadute ? "Aggiorno…" : "⚑ Segna scadute"}
                    </button>
                )}
            </div>

            {/* Toolbar */}
            <div className="bg-white border border-slate-200 rounded-md p-3 mb-3">
                <div className="flex flex-wrap items-center gap-2 mb-2">
                    <div className="relative flex-1 min-w-[260px]">
                        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                        <Input
                            data-testid="polizze-search"
                            placeholder="Cerca per polizza, targa, contraente..."
                            value={filters.q}
                            onChange={(e) => setF("q", e.target.value)}
                            className="pl-9"
                        />
                    </div>
                    <Button variant="outline" onClick={() => setShowFilters((s) => !s)} data-testid="pol-toggle-filters">
                        <Filter size={14} className="mr-1" /> Filtri {showFilters ? <ChevronUp size={12} className="ml-1" /> : <ChevronDown size={12} className="ml-1" />}
                    </Button>
                    <div className="ml-auto flex gap-2">
                        <Button variant="outline" onClick={stampaPdf} data-testid="polizze-print">
                            <Printer size={14} className="mr-1" /> Stampa PDF
                        </Button>
                        <Button variant="outline" onClick={exportCsv} data-testid="polizze-csv">
                            <FileText size={14} className="mr-1" /> CSV
                        </Button>
                        <Button variant="outline" onClick={exportXlsx} data-testid="polizze-xlsx">
                            <FileSpreadsheet size={14} className="mr-1" /> Excel
                        </Button>
                    </div>
                </div>

                {showFilters && (
                    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2 mt-2 pt-2 border-t border-slate-100">
                        <Select value={filters.stato} onValueChange={(v) => setF("stato", v)}>
                            <SelectTrigger data-testid="pol-f-stato"><SelectValue placeholder="Stato" /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Tutti stati</SelectItem>
                                <SelectItem value="attiva">Attiva</SelectItem>
                                <SelectItem value="sospesa">Sospesa</SelectItem>
                                <SelectItem value="in_emissione">In emissione</SelectItem>
                                <SelectItem value="scaduta">Scaduta</SelectItem>
                                <SelectItem value="annullata">Annullata</SelectItem>
                                <SelectItem value="sostituita">Sostituita</SelectItem>
                            </SelectContent>
                        </Select>
                        <Select value={filters.compagnia_id} onValueChange={(v) => setF("compagnia_id", v)}>
                            <SelectTrigger data-testid="pol-f-compagnia"><SelectValue placeholder="Compagnia" /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Tutte compagnie</SelectItem>
                                {compagnie.map((c) => <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}</SelectItem>)}
                            </SelectContent>
                        </Select>
                        <Select value={filters.ramo} onValueChange={(v) => setF("ramo", v)}>
                            <SelectTrigger data-testid="pol-f-ramo"><SelectValue placeholder="Ramo" /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Tutti rami</SelectItem>
                                {rami.map((r) => <SelectItem key={r.id} value={r.codice}>{r.nome}</SelectItem>)}
                            </SelectContent>
                        </Select>
                        <Select value={filters.collaboratore_id} onValueChange={(v) => setF("collaboratore_id", v)}>
                            <SelectTrigger data-testid="pol-f-collab"><SelectValue placeholder="Collaboratore" /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Tutti collaboratori</SelectItem>
                                {utenti.map((u) => <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>)}
                            </SelectContent>
                        </Select>
                        <Select value={filters.tag} onValueChange={(v) => setF("tag", v)}>
                            <SelectTrigger data-testid="pol-f-tag"><SelectValue placeholder="Tag" /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Tutti i tag</SelectItem>
                                {tagOptions.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                            </SelectContent>
                        </Select>
                        <button
                            onClick={async () => {
                                try {
                                    const r = await api.post("/polizze/auto-tag", {});
                                    toast.success(`Auto-tag applicati: ${r.data.polizze_aggiornate} polizze, ${r.data.titoli_aggiornati} titoli`);
                                    api.get("/anagrafiche/tags").then((rr) => setTagOptions(rr.data || []));
                                    load();
                                } catch (e) { toast.error(e.response?.data?.detail || "Errore auto-tag"); }
                            }}
                            className="text-xs px-3 py-1.5 rounded-md bg-fuchsia-700 text-white hover:bg-fuchsia-800 whitespace-nowrap"
                            title="Applica tag automatici (in_scadenza, scaduta, sinistrosa)"
                            data-testid="pol-autotag-btn">
                            Auto-tag
                        </button>
                        <Input
                            placeholder="Prodotto..." value={filters.prodotto}
                            onChange={(e) => setF("prodotto", e.target.value)}
                            data-testid="pol-f-prodotto"
                        />
                        <ContraenteFilter value={filters.contraente_id} onChange={(v) => setF("contraente_id", v)} />
                        <div>
                            <Label className="text-[10px] text-slate-500">Scadenza dal</Label>
                            <DateInputIt value={filters.dal} onChange={(v) => setF("dal", v)} data-testid="pol-f-dal" />
                        </div>
                        <div>
                            <Label className="text-[10px] text-slate-500">Scadenza al</Label>
                            <DateInputIt value={filters.al} onChange={(v) => setF("al", v)} data-testid="pol-f-al" />
                        </div>
                        <button
                            onClick={() => setFilters(INITIAL_FILTERS)}
                            className="text-xs text-slate-500 hover:text-rose-600 inline-flex items-center gap-1 col-span-2"
                            data-testid="pol-clear-filters"
                        >
                            <X size={12} /> Azzera filtri
                        </button>
                    </div>
                )}
            </div>

            <div className="flex justify-end mb-2">{picker}</div>
            <div ref={fill.ref} style={fill.style} className="flex flex-col min-h-0">
            <div className="tbl-scroll flex-fill flex-1" style={{ "--c1-w": "160px", "--c2-w": "100px" }}>
                {list === null ? <Loading /> : list.length === 0 ? <Empty /> : (
                    <table className="tbl freeze-3 w-full min-w-[1100px]">
                        <thead>
                            <tr>
                                {cols.map((c) => (
                                    <th key={c.key} className={c.thClass}>
                                        {c.sort
                                            ? <SortHeader k={c.sort} sortKey={sortBy} dir={sortDir} toggle={toggleSort}>{c.label}</SortHeader>
                                            : c.label}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {displayed.map((p) => (
                                <tr key={p.id} data-testid={`polizza-row-${p.id}`}>
                                    {cols.map((c) => (
                                        <td key={c.key} className={c.tdClass}>{c.render(p)}</td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
                {list && total > 0 && (
                    <div className="flex items-center justify-center gap-3 px-4 py-2.5 border-t border-slate-100 bg-white" data-testid="pol-pager">
                        <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))} data-testid="pol-page-prev">‹ Prec.</Button>
                        <span className="text-xs text-slate-600">Pagina {page} di {pages} · {total} polizze</span>
                        <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => setPage((p) => Math.min(pages, p + 1))} data-testid="pol-page-next">Succ. ›</Button>
                        <select value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))}
                            className="ml-2 text-xs border border-slate-200 rounded px-2 py-1 bg-white" data-testid="pol-page-size">
                            <option value={50}>50 / pagina</option>
                            <option value={100}>100 / pagina</option>
                            <option value={200}>200 / pagina</option>
                        </select>
                    </div>
                )}
            </div>

            {/* Footer totali */}
            <div className="mt-2 bg-slate-900 text-slate-100 rounded-t-md px-4 py-3 flex flex-wrap items-center gap-3 flex-none" data-testid="pol-footer">
                <span className="text-xs text-slate-400">
                    {list ? `${total} polizze${filters.preset !== "tutti" ? ` · preset: ${filters.preset}` : ""}` : ""}
                </span>
                <div className="ml-auto flex gap-6">
                    <div className="text-right">
                        <div className="text-[10px] uppercase tracking-widest text-slate-400">Premio totale lordo</div>
                        <div className="text-base font-semibold num" data-testid="pol-tot-lordo">{fmtEur(totali.t_lordo)}</div>
                    </div>
                    <div className="text-right">
                        <div className="text-[10px] uppercase tracking-widest text-slate-400">Premio totale netto</div>
                        <div className="text-base font-semibold num" data-testid="pol-tot-netto">{fmtEur(totali.t_netto)}</div>
                    </div>
                    <div className="text-right">
                        <div className="text-[10px] uppercase tracking-widest text-slate-400">Provvigioni</div>
                        <div className="text-base font-semibold num">{fmtEur(totali.t_provv)}</div>
                    </div>
                </div>
            </div>
            </div>
            {/* Dialog import Excel/CSV per Polizze */}
            <ImportExcelDialog
                open={importOpen}
                onClose={() => setImportOpen(false)}
                onSuccess={() => load()}
                entity="polizze"
                title="Importa Polizze da Excel/CSV"
                required={["numero_polizza"]}
            />
        </div>
    );
}

const _MESI_FRAZ = { annuale: 12, semestrale: 6, quadrimestrale: 4, trimestrale: 3, mensile: 1, unica: 12 };
function addPeriodo(dateStr, frazionamento) {
    if (!dateStr) return "";
    const m = _MESI_FRAZ[frazionamento] ?? 12;
    const [y, mo, d] = dateStr.slice(0, 10).split("-").map(Number);
    if (!y || !mo || !d) return "";
    const base = new Date(y, mo - 1, d);
    const target = new Date(base.getFullYear(), base.getMonth() + m, 1);
    // clamp del giorno all'ultimo giorno valido del mese target
    const lastDay = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate();
    target.setDate(Math.min(d, lastDay));
    const pad = (n) => String(n).padStart(2, "0");
    return `${target.getFullYear()}-${pad(target.getMonth() + 1)}-${pad(target.getDate())}`;
}

function NuovaPolizzaDialog({ onClose }) {
    const navigate = useNavigate();
    const [ana, setAna] = useState([]);
    const [comp, setComp] = useState([]);
    const [agenzie, setAgenzie] = useState([]);
    const [rami, setRami] = useState([]);
    const [prodotti, setProdotti] = useState([]);
    const [collaboratori, setCollaboratori] = useState([]);
    const [contraenteQuery, setContraenteQuery] = useState("");
    const [showContraenteList, setShowContraenteList] = useState(false);
    // Oggetto contraente selezionato — memoria persistente indipendente dai risultati
    // della ricerca (server-side): risolve il bug per cui il nome sparisce dopo la
    // selezione se l'anagrafica non è più nei primi 50 risultati.
    const [contraenteSel, setContraenteSel] = useState(null);
    const [ocrLoading, setOcrLoading] = useState(false);
    const ocrRef = useRef(null);
    // Nome prodotto grezzo da OCR in attesa che la lista `prodotti` del ramo si carichi,
    // per risolverlo al nome ESATTO presente in DB (altrimenti il Select resta vuoto).
    const pendingProdRef = useRef(null);
    const [polizzaFile, setPolizzaFile] = useState(null);
    // Suggerimenti targa per autocomplete live (search nei veicoli del libro matricola)
    const [targheSuggest, setTargheSuggest] = useState([]);
    const [veicoloInfo, setVeicoloInfo] = useState(null);  // {fonte: "libro_matricola"|"polizza", polizze_collegate: [...]}
    const [collabQuery, setCollabQuery] = useState("");
    const [showCollabList, setShowCollabList] = useState(false);
    const [targaLoading, setTargaLoading] = useState(false);
    const [f, setF] = useState({
        numero_polizza: "", compagnia_id: "", contraente_id: "",
        ramo: "", prodotto: "", effetto: "", scadenza: "",
        premio_lordo: 0, premio_netto: 0, premio_tasse: 0, premio_ssn: 0, provvigioni: 0,
        targa: "", frazionamento: "annuale", stato: "attiva",
        prossima_quietanza: "", collaboratore_id: "", mandato: "",
        veicolo_marca: "", veicolo_modello: "", veicolo_tipo: "", veicolo_alimentazione: "",
        veicolo_uso: "", veicolo_data_immatricolazione: "", veicolo_cv_fiscali: "",
        veicolo_kw: "", veicolo_cilindrata: "", veicolo_posti: "", telaio: "",
    });
    const [quietanzaTouched, setQuietanzaTouched] = useState(false);
    // Auto-calcolo Data prima quietanza = effetto + periodo del frazionamento
    // (resta modificabile: se l'utente la cambia a mano non viene ricalcolata).
    useEffect(() => {
        if (quietanzaTouched || !f.effetto || !f.frazionamento) return;
        const q = addPeriodo(f.effetto, f.frazionamento);
        if (q && q !== f.prossima_quietanza) setF((p) => ({ ...p, prossima_quietanza: q }));
        /* eslint-disable-next-line */
    }, [f.effetto, f.frazionamento]);
    // Premio lordo = netto + imposta (tasse) + ssn (auto-calcolato)
    const setPremio = (k, v) => setF((p) => {
        const n = { ...p, [k]: v };
        const netto = parseFloat(n.premio_netto) || 0;
        const imposta = parseFloat(n.premio_tasse) || 0;
        const ssn = parseFloat(n.premio_ssn) || 0;
        n.premio_lordo = Math.round((netto + imposta + ssn) * 100) / 100;
        return n;
    });
    useEffect(() => {
        api.get("/compagnie").then((r) => setComp(r.data));
        api.get("/agenzie").then((r) => setAgenzie(r.data || [])).catch(() => setAgenzie([]));
        api.get("/librerie/rami?dedup=1").then((r) => setRami(r.data || []));
        api.get("/auth/users", { params: { role: "collaboratore" } })
            .then((r) => setCollaboratori((r.data || []).filter((u) => u.attivo !== false)))
            .catch(() => setCollaboratori([]));
    }, []);

    // Auto-imposta l'agenzia partner (mandato) in base alla compagnia scelta:
    // se la compagnia è "collaborazione" → agenzia partner collegata, altrimenti la principale.
    useEffect(() => {
        if (!f.compagnia_id || agenzie.length === 0) return;
        const sel = comp.find((c) => c.id === f.compagnia_id);
        if (!sel) return;
        const linked = sel.tipo_mandato === "collaborazione" && sel.agenzia_partner_id
            ? agenzie.find((a) => a.id === sel.agenzia_partner_id)
            : agenzie.find((a) => a.tipo === "principale");
        setF((p) => ({ ...p, mandato: linked ? linked.ragione_sociale : p.mandato }));
        /* eslint-disable-next-line */
    }, [f.compagnia_id, agenzie]);

    // Se cambio l'agenzia partner, azzero la compagnia se non è collegata a quell'agenzia.
    useEffect(() => {
        if (!f.mandato || !f.compagnia_id) return;
        const ag = agenzie.find((a) => a.ragione_sociale === f.mandato);
        if (!ag) return;
        const sel = comp.find((c) => c.id === f.compagnia_id);
        if (!sel) return;
        const ok = ag.tipo === "principale" ? !sel.agenzia_partner_id : sel.agenzia_partner_id === ag.id;
        if (!ok) setF((p) => ({ ...p, compagnia_id: "" }));
        /* eslint-disable-next-line */
    }, [f.mandato]);

    // Ricerca anagrafiche SERVER-SIDE con debounce 250ms.
    // Funziona anche con DB di milioni di record perche' il filtraggio e' su Mongo (regex AND multi-token).
    useEffect(() => {
        const q = contraenteQuery.trim();
        const handler = setTimeout(() => {
            api.get("/anagrafiche", { params: { q: q || undefined, limit: 50 } })
                .then((r) => setAna(r.data))
                .catch(() => setAna([]));
        }, q ? 250 : 0);
        return () => clearTimeout(handler);
    }, [contraenteQuery]);

    // Carica prodotti filtrati per ramo
    useEffect(() => {
        if (!f.ramo) { setProdotti([]); return; }
        const params = { ramo: f.ramo };
        if (f.compagnia_id) params.compagnia_id = f.compagnia_id;
        api.get("/librerie/prodotti", { params }).then((r) => setProdotti(r.data || []));
    }, [f.ramo, f.compagnia_id]);

    // Quando la lista prodotti si carica dopo l'OCR, risolvi il prodotto grezzo al nome
    // ESATTO presente in DB (match normalizzato) così il Select lo visualizza.
    useEffect(() => {
        if (!pendingProdRef.current || prodotti.length === 0) return;
        const norm = (s) => (s || "").toString().toUpperCase().replace(/[^A-Z0-9]/g, "");
        const want = norm(pendingProdRef.current);
        const m = prodotti.find((p) => norm(p.nome) === want)
            || prodotti.find((p) => norm(p.nome).includes(want) || want.includes(norm(p.nome)))
            || prodotti.find((p) => want && norm(p.nome).startsWith(want.slice(0, 8)));
        if (m) set("prodotto", m.nome);
        pendingProdRef.current = null;
    }, [prodotti]); /* eslint-disable-line */

    // Anagrafica selezionata (memoria persistente + fallback ricerca in lista)
    const contraenteSelezionato = contraenteSel || ana.find((a) => a.id === f.contraente_id);
    // Etichetta display: ragione_sociale (giuridica) / cognome_nome / cognome+nome (fisica)
    const labelAna = (a) => a?.ragione_sociale
        || a?.cognome_nome
        || `${a?.cognome || ""} ${a?.nome || ""}`.trim()
        || a?.codice_fiscale || a?.partita_iva || "—";

    // Lista filtrata = quanto restituito dal server (gia' filtrato per query con AND multi-token).
    const anaFiltrate = ana.slice(0, 50);
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    // Sezione "Dati veicolo" in creazione: mostrata se il ramo è RCA/veicoli OPPURE
    // il prodotto scelto ha il flag `mostra_sezione_veicolo` (coerente con la scheda polizza).
    const _selProd = prodotti.find((p) => p.nome === f.prodotto);
    const showVeicolo = /rca|rc\s*auto|autovettur|autocarr|motocicl|ciclomotor|\bauto\b|\bmoto\b|veicol|natant|imbarcaz/i
        .test(`${f.ramo || ""} ${f.prodotto || ""}`) || !!_selProd?.mostra_sezione_veicolo;

    // Lookup targa: Libro Matricola → fallback polizze precedenti. Riusato da onBlur e dal pulsante "Cerca".
    const lookupTarga = async (raw) => {
        const t = (raw ?? f.targa ?? "").trim().toUpperCase();
        if (!t || t.length < 4) {
            toast.error("Inserisci una targa valida (min 4 caratteri)");
            return;
        }
        setTargaLoading(true);
        try {
            try {
                const r = await api.get(`/veicoli/by-targa/${encodeURIComponent(t)}`);
                const v = r.data?.veicolo;
                if (v) {
                    setF((prev) => ({
                        ...prev, targa: t,
                        veicolo_marca: prev.veicolo_marca || v.marca || "",
                        veicolo_modello: prev.veicolo_modello || v.modello || "",
                        veicolo_alimentazione: prev.veicolo_alimentazione || v.alimentazione || "",
                        veicolo_kw: prev.veicolo_kw || v.kw || "",
                        veicolo_cilindrata: prev.veicolo_cilindrata || v.cilindrata || "",
                        veicolo_data_immatricolazione: prev.veicolo_data_immatricolazione || v.data_immatricolazione || "",
                        veicolo_uso: prev.veicolo_uso || v.uso || "",
                        veicolo_posti: prev.veicolo_posti || v.posti || "",
                        veicolo_quintali: prev.veicolo_quintali || v.quintali || "",
                        veicolo_settore: prev.veicolo_settore || v.settore || "",
                        telaio: prev.telaio || v.telaio || "",
                        veicolo_id: v.id,
                    }));
                    setVeicoloInfo({ fonte: "libro_matricola", veicolo: v, polizze_collegate: r.data?.polizze_collegate || [] });
                    const npol = (r.data?.polizze_collegate || []).length;
                    toast.success(`Veicolo dal Libro Matricola: ${v.marca || ""} ${v.modello || ""} ${npol ? `(${npol} polizz${npol === 1 ? "a" : "e"} già collegat${npol === 1 ? "a" : "e"})` : ""}`);
                    return;
                }
            } catch { /* not found, fallback */ }
            try {
                const r = await api.get("/polizze/veicolo-by-targa", { params: { targa: t, tipo: f.veicolo_tipo || "" } });
                if (r.data?.tipo_diverso) {
                    toast.info(`Targa ${t} già presente ma di tipo diverso (${(r.data.tipi_esistenti || []).join(", ")}): è un altro veicolo, dati non copiati.`);
                    setF((prev) => ({ ...prev, targa: t }));
                } else if (r.data && r.data.trovata) {
                    setF((prev) => ({
                        ...prev, targa: t,
                        veicolo_marca: prev.veicolo_marca || r.data.veicolo_marca || "",
                        veicolo_modello: prev.veicolo_modello || r.data.veicolo_modello || "",
                        veicolo_tipo: prev.veicolo_tipo || r.data.veicolo_tipo || "",
                        veicolo_alimentazione: prev.veicolo_alimentazione || r.data.veicolo_alimentazione || "",
                        veicolo_kw: prev.veicolo_kw || r.data.veicolo_kw || "",
                        veicolo_cv_fiscali: prev.veicolo_cv_fiscali || r.data.veicolo_cv_fiscali || "",
                        veicolo_cilindrata: prev.veicolo_cilindrata || r.data.veicolo_cilindrata || "",
                        veicolo_data_immatricolazione: prev.veicolo_data_immatricolazione || r.data.veicolo_data_immatricolazione || "",
                        veicolo_uso: prev.veicolo_uso || r.data.veicolo_uso || "",
                        veicolo_posti: prev.veicolo_posti || r.data.veicolo_posti || "",
                        telaio: prev.telaio || r.data.telaio || "",
                    }));
                    setVeicoloInfo({ fonte: "polizza", n_polizze: r.data.n_polizze });
                    toast.success(`Veicolo trovato in polizza precedente: ${r.data.veicolo_marca || ""} ${r.data.veicolo_modello || ""} (${r.data.n_polizze} polizze)`);
                } else {
                    toast.info("Nessun veicolo trovato per questa targa");
                }
            } catch (err) {
                console.warn("targa lookup", err?.message);
                toast.info("Nessun veicolo trovato per questa targa");
            }
        } finally {
            setTargaLoading(false);
        }
    };

    const onOcrPolizza = async (file) => {
        if (!file) return;
        setOcrLoading(true);
        setPolizzaFile(file);
        const fd = new FormData();
        fd.append("file", file);
        try {
            const r = await api.post("/utility/ocr-polizza", fd,
                { headers: { "Content-Type": "multipart/form-data" }, timeout: 120000 });
            const d = r.data;
            // Risolvi il RAMO sul nome ESATTO presente nella lista rami del backend
            // (es. OCR 'RCAUTO'/'RCA' → 'RC Auto'); altrimenti il Select resta vuoto.
            const normR = (s) => (s || "").toString().toUpperCase().replace(/[^A-Z0-9]/g, "");
            const ramoSyn = { RCAUTO: "RCAUTO", RCA: "RCAUTO", INFR: "INFORTUNI" };
            const ocrR = normR(d.ramo);
            const targetR = ramoSyn[ocrR] || ocrR;
            const ramo = (
                rami.find((x) => normR(x.nome) === targetR)
                || rami.find((x) => targetR && (normR(x.nome).includes(targetR) || targetR.includes(normR(x.nome))))
            )?.nome || d.ramo || "";
            // Prodotto: risolto quando la lista prodotti del ramo si carica (useEffect).
            pendingProdRef.current = d.prodotto || null;
            const compMatch = d.compagnia
                ? comp.find((c) => c.ragione_sociale?.toUpperCase().includes(d.compagnia.toUpperCase().split(" ")[0]))
                : null;
            // Contraente: match AFFIDABILE dal backend (ricerca per CF/P.IVA su tutto il DB).
            const anaEsist = d.anagrafica_esistente || null;
            const cfContr = d.contraente?.codice_fiscale || d.contraente?.partita_iva;
            if (anaEsist) {
                setContraenteSel(anaEsist);
                setContraenteQuery("");
                if (anaEsist.collaboratore_id) set("collaboratore_id", anaEsist.collaboratore_id);
            } else {
                // Nessuna anagrafica: pre-compila la ricerca col nome del PDF per crearla.
                setContraenteSel(null);
                setContraenteQuery(d.contraente?.cognome_nome_o_ragione_sociale || cfContr || "");
            }
            const v = d.veicolo || {};
            setF((p) => ({
                ...p,
                numero_polizza: d.numero_polizza || p.numero_polizza,
                compagnia_id: compMatch?.id || p.compagnia_id,
                contraente_id: anaEsist?.id || "",
                ramo, prodotto: "",
                effetto: d.data_decorrenza || p.effetto,
                scadenza: d.data_scadenza || p.scadenza,
                frazionamento: (d.frazionamento || "").toLowerCase() || p.frazionamento,
                // Premi: netto / imposte(tasse)+diritti / SSN separato → lordo.
                // Provvigioni NON importate (inserite manualmente). Identico al flusso email.
                premio_netto: d.premio_netto_totale ?? p.premio_netto,
                premio_tasse: (d.imposte_totali != null || d.diritti != null)
                    ? Math.round(((d.imposte_totali || 0) + (d.diritti || 0)) * 100) / 100
                    : p.premio_tasse,
                premio_ssn: d.contributo_ssn ?? p.premio_ssn,
                premio_lordo: d.premio_lordo_totale
                    ?? Math.round(((d.premio_netto_totale || 0) + (d.imposte_totali || 0) + (d.contributo_ssn || 0) + (d.diritti || 0)) * 100) / 100,
                // Sostituzione: la catena viene applicata alla creazione.
                sostituisce_polizza: d.sostituisce_polizza || p.sostituisce_polizza || "",
                // Dati veicolo
                targa: v.targa || p.targa,
                veicolo_marca: v.marca || p.veicolo_marca,
                veicolo_modello: v.modello || p.veicolo_modello,
                veicolo_tipo: v.tipo_veicolo || p.veicolo_tipo,
                veicolo_alimentazione: v.alimentazione || p.veicolo_alimentazione,
                veicolo_uso: v.uso_veicolo || p.veicolo_uso,
                veicolo_data_immatricolazione: v.data_immatricolazione || p.veicolo_data_immatricolazione,
                veicolo_cv_fiscali: v.cv_fiscali ?? p.veicolo_cv_fiscali,
                veicolo_kw: v.kw ?? p.veicolo_kw,
                veicolo_cilindrata: v.cilindrata ?? p.veicolo_cilindrata,
                veicolo_posti: v.numero_posti ?? p.veicolo_posti,
            }));
            let msg = `Polizza riconosciuta: ${d.numero_polizza || "?"}`;
            if (d.polizza_esistente) msg += ` · ⚠ Polizza GIÀ presente (stato: ${d.polizza_esistente.stato || "?"})`;
            if (!compMatch && d.compagnia) msg += ` · ⚠ Compagnia "${d.compagnia}" da abbinare`;
            if (anaEsist) msg += ` · 👤 Contraente collegato: ${labelAna(anaEsist)}${d.anagrafica_match_fuzzy ? " (CF corretto automaticamente)" : ""}`;
            else if (cfContr) msg += d.cf_ocr_valido === false
                ? ` · ⚠ Contraente NUOVO (CF ${cfContr} forse letto male, verificalo)`
                : ` · ⚠ Contraente NUOVO (${cfContr}) da creare`;
            if (d.sostituisce_polizza) msg += ` · 🔗 Sostituisce la n° ${d.sostituisce_polizza}`;
            if (d.polizza_esistente) toast.warning(msg); else toast.success(msg);
        } catch (e) {
            toast.error("OCR fallito: " + (e.response?.data?.detail || e.message));
        } finally { setOcrLoading(false); }
    };

    const save = async () => {
        if (!f.numero_polizza || !f.compagnia_id || !f.contraente_id || !f.effetto || !f.scadenza) {
            toast.error("Compila tutti i campi obbligatori");
            return;
        }
        try {
            const payload = {
                ...f,
                premio_lordo: parseFloat(f.premio_lordo) || 0,
                premio_netto: parseFloat(f.premio_netto) || 0,
                premio_tasse: parseFloat(f.premio_tasse) || 0,
                premio_ssn: parseFloat(f.premio_ssn) || 0,
                provvigioni: parseFloat(f.provvigioni) || 0,
                assicurato_ids: [f.contraente_id],
            };
            // Se la targa è stata associata a un veicolo del libro matricola, lo collego
            if (f.veicolo_id) {
                payload.veicoli_ids = [f.veicolo_id];
            }
            // Pulisci i campi veicolo vuoti (i numerici non accettano stringa vuota lato modello)
            ["veicolo_marca", "veicolo_modello", "veicolo_tipo", "veicolo_alimentazione",
             "veicolo_uso", "veicolo_data_immatricolazione", "veicolo_cv_fiscali",
             "veicolo_kw", "veicolo_cilindrata", "veicolo_posti", "telaio"].forEach((k) => {
                if (payload[k] === "" || payload[k] == null) delete payload[k];
            });
            const created = await api.post("/polizze", payload);
            if (polizzaFile && created.data?.id) {
                const fd = new FormData();
                fd.append("file", polizzaFile);
                fd.append("salva_come_allegato", "true");
                fd.append("polizza_id", created.data.id);
                api.post("/utility/ocr-polizza", fd,
                    { headers: { "Content-Type": "multipart/form-data" } }).catch(() => {});
            }
            toast.success("Polizza creata — ora inserisci premi e provvigioni");
            onClose();
            if (created.data?.id) navigate(`/polizze/${created.data.id}?edit=1`);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        }
    };

    return (
        <DialogContent className="max-w-2xl max-h-[92vh] overflow-y-auto gap-3 [&_input]:h-8 [&_[role=combobox]]:h-8 [&_label]:text-xs">
            <DialogHeader className="space-y-0"><DialogTitle className="text-base">Nuova polizza</DialogTitle><DialogDescription className="text-xs text-slate-500">Compila i dati o carica il PDF per l'auto-compilazione.</DialogDescription></DialogHeader>

            <div className="bg-sky-50 border border-sky-200 rounded-md p-3 flex items-center gap-3 flex-wrap" data-testid="pol-ocr-toolbar">
                <div className="text-xs text-sky-900 flex-1">
                    <strong>Auto-compila</strong> caricando il PDF della polizza (Cattolica, UnipolSai, Generali, Allianz, ecc.).
                    Verrà anche salvata come allegato.
                </div>
                <input
                    ref={ocrRef}
                    type="file"
                    accept=".pdf,image/*"
                    className="hidden"
                    onChange={(e) => onOcrPolizza(e.target.files?.[0])}
                    data-testid="pol-ocr-input"
                />
                <Button
                    type="button" variant="outline" size="sm"
                    onClick={() => ocrRef.current?.click()}
                    disabled={ocrLoading}
                    data-testid="pol-ocr-button"
                >
                    <ScanLine size={13} className="mr-1" />
                    {ocrLoading ? "Riconoscimento..." : "Carica PDF polizza"}
                </Button>
            </div>

            <div className="grid grid-cols-2 gap-4 py-2">
                <div><Label>Numero polizza *</Label><Input data-testid="pol-numero-input" value={f.numero_polizza} onChange={(e) => set("numero_polizza", e.target.value)} /></div>
                <div>
                    <Label>Stato</Label>
                    <Select value={f.stato} onValueChange={(v) => set("stato", v)}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="attiva">Attiva</SelectItem>
                            <SelectItem value="sospesa">Sospesa</SelectItem>
                            <SelectItem value="in_emissione">In emissione</SelectItem>
                            <SelectItem value="scaduta">Scaduta</SelectItem>
                            <SelectItem value="annullata">Annullata</SelectItem>
                                <SelectItem value="sostituita">Sostituita</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
                <div>
                    <Label>Agenzia (mandato) *</Label>
                    <Select value={f.mandato || ""} onValueChange={(v) => { set("mandato", v); set("compagnia_id", ""); }}>
                        <SelectTrigger data-testid="pol-agenzia-partner-select"><SelectValue placeholder="Scegli prima l'agenzia" /></SelectTrigger>
                        <SelectContent>
                            {agenzie.map((a) => (
                                <SelectItem key={a.id} value={a.ragione_sociale}>
                                    {a.ragione_sociale}{a.tipo === "principale" ? " (diretto)" : " (partner)"}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                    <div className="text-[11px] text-slate-400 mt-1">Scegli l'agenzia principale (mandato diretto) o l'agenzia partner: sotto vedrai solo le sue compagnie.</div>
                </div>
                <div>
                    <Label>Compagnia *</Label>
                    <Select value={f.compagnia_id} onValueChange={(v) => set("compagnia_id", v)} disabled={!f.mandato}>
                        <SelectTrigger data-testid="pol-comp-select"><SelectValue placeholder={f.mandato ? "Seleziona compagnia" : "Scegli prima l'agenzia"} /></SelectTrigger>
                        <SelectContent>
                            {comp.filter((c) => {
                                if (!f.mandato) return false;
                                const ag = agenzie.find((a) => a.ragione_sociale === f.mandato);
                                if (!ag) return true;
                                return ag.tipo === "principale" ? !c.agenzia_partner_id : c.agenzia_partner_id === ag.id;
                            }).map((c) => <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
                <div className="col-span-2">
                    <Label>Collaboratore (Operatore)</Label>
                    <div className="relative">
                        {(() => {
                            const sel = collaboratori.find((c) => c.id === f.collaboratore_id);
                            return (
                                <Input
                                    value={showCollabList ? collabQuery : (sel ? sel.name : "")}
                                    placeholder="Digita per cercare un collaboratore..."
                                    onChange={(e) => { setCollabQuery(e.target.value); setShowCollabList(true); }}
                                    onFocus={() => { setCollabQuery(""); setShowCollabList(true); }}
                                    onBlur={() => setTimeout(() => setShowCollabList(false), 200)}
                                    data-testid="pol-collab-search"
                                />
                            );
                        })()}
                        {showCollabList && (
                            <div className="absolute top-full left-0 right-0 z-50 mt-1 bg-white border border-slate-200 rounded-md shadow-lg max-h-60 overflow-y-auto" data-testid="collab-suggestions">
                                <button
                                    type="button"
                                    className="w-full text-left px-3 py-2 hover:bg-sky-50 border-b border-slate-100 text-sm text-slate-500"
                                    onMouseDown={() => { set("collaboratore_id", ""); setShowCollabList(false); }}
                                    data-testid="collab-opt-none"
                                >
                                    — Nessuno —
                                </button>
                                {collaboratori
                                    .filter((c) => !collabQuery.trim() || (c.name || "").toLowerCase().includes(collabQuery.trim().toLowerCase()))
                                    .map((c) => (
                                        <button
                                            type="button"
                                            key={c.id}
                                            className="w-full text-left px-3 py-2 hover:bg-sky-50 border-b border-slate-100 last:border-0 text-sm"
                                            onMouseDown={() => { set("collaboratore_id", c.id); setShowCollabList(false); }}
                                            data-testid={`collab-opt-${c.id}`}
                                        >
                                            {c.name}
                                        </button>
                                    ))}
                                {collaboratori.filter((c) => !collabQuery.trim() || (c.name || "").toLowerCase().includes(collabQuery.trim().toLowerCase())).length === 0 && (
                                    <div className="p-3 text-xs text-slate-500">Nessun collaboratore trovato</div>
                                )}
                            </div>
                        )}
                    </div>
                </div>
                <div className="col-span-2">
                    <Label>Contraente *</Label>
                    <div className="relative">
                        <Input
                            value={
                                showContraenteList
                                    ? contraenteQuery
                                    : (contraenteSelezionato ? labelAna(contraenteSelezionato) : contraenteQuery)
                            }
                            placeholder="Digita per cercare nome, CF, P.IVA..."
                            onChange={(e) => { setContraenteQuery(e.target.value); setShowContraenteList(true); }}
                            onFocus={() => setShowContraenteList(true)}
                            onBlur={() => setTimeout(() => setShowContraenteList(false), 200)}
                            data-testid="pol-contraente-search"
                        />
                        {showContraenteList && (
                            <div className="absolute top-full left-0 right-0 z-50 mt-1 bg-white border border-slate-200 rounded-md shadow-lg max-h-72 overflow-y-auto" data-testid="contraente-suggestions">
                                {anaFiltrate.length === 0 ? (
                                    <div className="p-3 text-xs text-slate-500">Nessun contraente trovato</div>
                                ) : anaFiltrate.map((a) => (
                                    <button
                                        type="button"
                                        key={a.id}
                                        className="w-full text-left px-3 py-2 hover:bg-sky-50 border-b border-slate-100 last:border-0"
                                        onMouseDown={() => {
                                            set("contraente_id", a.id);
                                            setContraenteSel(a);
                                            setContraenteQuery("");
                                            setShowContraenteList(false);
                                            // Auto-imposta il collaboratore collegato all'anagrafica
                                            if (a.collaboratore_id) {
                                                setF((prev) => ({ ...prev, collaboratore_id: a.collaboratore_id }));
                                            }
                                        }}
                                        data-testid={`contraente-opt-${a.id}`}
                                    >
                                        <div className="text-sm font-medium">{labelAna(a)}</div>
                                        <div className="text-[10px] text-slate-500">
                                            {a.codice_fiscale || a.partita_iva || "—"}
                                            {a.comune && ` · ${a.comune}`}
                                        </div>
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
                <div>
                    <Label>Ramo</Label>
                    <Select value={f.ramo || ""} onValueChange={(v) => { set("ramo", v); set("prodotto", ""); }}>
                        <SelectTrigger data-testid="pol-ramo-select"><SelectValue placeholder="Seleziona ramo" /></SelectTrigger>
                        <SelectContent>
                            {rami.map((r) => (
                                <SelectItem key={r.id || r.nome} value={r.nome}>{r.nome}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
                <div>
                    <Label>Prodotto</Label>
                    <Select
                        value={f.prodotto || ""}
                        onValueChange={(v) => set("prodotto", v)}
                        disabled={!f.ramo}
                    >
                        <SelectTrigger data-testid="pol-prodotto-select">
                            <SelectValue placeholder={f.ramo ? (prodotti.length ? "Seleziona prodotto" : "Nessun prodotto per questo ramo") : "Scegli prima un ramo"} />
                        </SelectTrigger>
                        <SelectContent>
                            {prodotti.map((p) => (
                                <SelectItem key={p.id || p.nome} value={p.nome}>{p.nome}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
                <div><Label>Effetto *</Label><Input type="date" value={f.effetto} onChange={(e) => {
                    const v = e.target.value; set("effetto", v);
                    if (v) { const d = new Date(v); d.setFullYear(d.getFullYear() + 1); set("scadenza", d.toISOString().slice(0, 10)); }
                }} /></div>
                <div><Label>Scadenza *</Label><Input type="date" value={f.scadenza} onChange={(e) => set("scadenza", e.target.value)} /></div>
                <div>
                    <Label>Frazionamento</Label>
                    <Select value={f.frazionamento} onValueChange={(v) => set("frazionamento", v)}>
                        <SelectTrigger data-testid="pol-frazionamento-select"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="annuale">Annuale</SelectItem>
                            <SelectItem value="semestrale">Semestrale</SelectItem>
                            <SelectItem value="quadrimestrale">Quadrimestrale</SelectItem>
                            <SelectItem value="trimestrale">Trimestrale</SelectItem>
                            <SelectItem value="mensile">Mensile</SelectItem>
                            <SelectItem value="unica">Unica</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
                <div><Label>Data prima quietanza</Label><Input type="date" value={f.prossima_quietanza || ""} onChange={(e) => { setQuietanzaTouched(true); set("prossima_quietanza", e.target.value); }} data-testid="pol-prima-quietanza" /></div>
                {showVeicolo && (
                    <div className="col-span-2 border border-sky-200 bg-sky-50/40 rounded-md p-3 mt-1" data-testid="pol-veicolo-sezione">
                        <div className="text-[11px] uppercase tracking-wide text-sky-700 font-semibold pb-2 flex items-center gap-1">
                            <Car size={13} /> Dati veicolo
                        </div>
                        <div className="col-span-2 mb-3">
                            <Label>Targa</Label>
                            <div className="flex gap-2">
                                <Input
                                    value={f.targa}
                                    placeholder="Es. AB123CD"
                                    onChange={(e) => set("targa", e.target.value.toUpperCase())}
                                    onBlur={(e) => { const t = e.target.value.trim(); if (t.length >= 4) lookupTarga(t); }}
                                    data-testid="pol-targa-input"
                                />
                                <Button type="button" variant="outline" size="sm" onClick={() => lookupTarga()} disabled={targaLoading} data-testid="pol-targa-cerca">
                                    <Search size={13} className="mr-1" />{targaLoading ? "Cerco..." : "Cerca"}
                                </Button>
                            </div>
                            {veicoloInfo && (
                                <div className="text-[11px] text-emerald-700 mt-1">
                                    {veicoloInfo.fonte === "libro_matricola" ? "Dati dal Libro Matricola" : "Dati da polizza precedente"} — compilati automaticamente
                                </div>
                            )}
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                            <div><Label>Marca</Label><Input value={f.veicolo_marca} onChange={(e) => set("veicolo_marca", e.target.value)} data-testid="pol-veicolo-marca" /></div>
                            <div><Label>Modello</Label><Input value={f.veicolo_modello} onChange={(e) => set("veicolo_modello", e.target.value)} data-testid="pol-veicolo-modello" /></div>
                            <div><Label>Tipo veicolo</Label><Input value={f.veicolo_tipo} onChange={(e) => set("veicolo_tipo", e.target.value)} /></div>
                            <div><Label>Alimentazione</Label><Input value={f.veicolo_alimentazione} onChange={(e) => set("veicolo_alimentazione", e.target.value)} /></div>
                            <div><Label>Tipo uso</Label><Input value={f.veicolo_uso} onChange={(e) => set("veicolo_uso", e.target.value)} /></div>
                            <div><Label>Immatricolazione</Label><Input type="date" value={f.veicolo_data_immatricolazione} onChange={(e) => set("veicolo_data_immatricolazione", e.target.value)} /></div>
                            <div><Label>CV fiscali</Label><Input value={f.veicolo_cv_fiscali} onChange={(e) => set("veicolo_cv_fiscali", e.target.value)} /></div>
                            <div><Label>KW</Label><Input value={f.veicolo_kw} onChange={(e) => set("veicolo_kw", e.target.value)} /></div>
                            <div><Label>Cilindrata</Label><Input value={f.veicolo_cilindrata} onChange={(e) => set("veicolo_cilindrata", e.target.value)} /></div>
                            <div><Label>Numero posti</Label><Input value={f.veicolo_posti} onChange={(e) => set("veicolo_posti", e.target.value)} /></div>
                        </div>
                    </div>
                )}
                <div className="col-span-2 text-[11px] text-slate-500 bg-slate-50 border border-slate-200 rounded-md px-3 py-2">
                    💡 Premi (netto/lordo/imposte/SSN) e provvigioni si inseriscono e si modificano nella scheda della polizza dopo la creazione.
                </div>
            </div>
            <DialogFooter>
                <Button data-testid="pol-save-button" onClick={save} className="bg-sky-700 hover:bg-sky-800">Crea polizza</Button>
            </DialogFooter>
        </DialogContent>
    );
}
