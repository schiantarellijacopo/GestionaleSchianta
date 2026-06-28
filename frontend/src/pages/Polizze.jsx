import { useEffect, useMemo, useState, useRef } from "react";
import { Link } from "react-router-dom";
import { api, fmtDate, fmtEur, API_BASE } from "@/lib/api";
import { openPdf } from "@/lib/pdf";
import { PageHeader, StatusBadge, Loading, Empty } from "@/components/Shared";
import SortHeader, { useTableSort } from "@/components/SortHeader";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import {
    Search, Plus, ScanLine, Filter, X, Printer, FileSpreadsheet, FileText,
    ChevronDown, ChevronUp, Car,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

const PRESETS = [
    { key: "tutti", label: "Tutte" },
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
    preset: "tutti", q: "",
    stato: "all", compagnia_id: "all", ramo: "all", prodotto: "",
    collaboratore_id: "all",
    dal: "", al: "",
};

export default function Polizze() {
    const { user } = useAuth();
    const [list, setList] = useState(null);
    const [compagnie, setCompagnie] = useState([]);
    const [rami, setRami] = useState([]);
    const [utenti, setUtenti] = useState([]);
    const [open, setOpen] = useState(false);
    const [showFilters, setShowFilters] = useState(false);
    const [filters, setFilters] = useState(INITIAL_FILTERS);
    const setF = (k, v) => setFilters((p) => ({ ...p, [k]: v }));
    const canCreate = ["admin", "collaboratore", "dipendente"].includes(user?.role);

    const buildParams = () => {
        const p = { ...presetParams(filters.preset) };
        if (filters.q) p.q = filters.q;
        if (filters.stato !== "all" && filters.preset === "tutti") p.stato = filters.stato;
        if (filters.compagnia_id !== "all") p.compagnia_id = filters.compagnia_id;
        if (filters.ramo !== "all") p.ramo = filters.ramo;
        if (filters.collaboratore_id !== "all") p.collaboratore_id = filters.collaboratore_id;
        if (filters.prodotto) p.prodotto = filters.prodotto;
        if (filters.dal) p.dal = filters.dal;
        if (filters.al) p.al = filters.al;
        return p;
    };

    const load = () => {
        api.get("/polizze", { params: buildParams() }).then((r) => setList(r.data));
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [filters]);

    useEffect(() => {
        Promise.all([
            api.get("/compagnie"), api.get("/librerie/rami"),
            api.get("/auth/users").catch(() => ({ data: [] })),
        ]).then(([c, r, u]) => {
            setCompagnie(c.data); setRami(r.data);
            setUtenti((u.data || []).filter((x) => x.role !== "cliente"));
        });
    }, []);

    const baseList = list || [];
    const { sorted, sortKey, dir, toggle } = useTableSort(baseList, "data_scadenza", "asc");
    const displayed = sorted;

    const totali = useMemo(() => {
        const src = list || [];
        const t_lordo = src.reduce((s, p) => s + (p.premio_lordo || 0), 0);
        const t_provv = src.reduce((s, p) => s + (p.provvigioni || 0), 0);
        return { t_lordo, t_provv };
    }, [list]);

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
                    <Dialog open={open} onOpenChange={setOpen}>
                        <DialogTrigger asChild>
                            <Button data-testid="polizza-new-button" className="bg-sky-700 hover:bg-sky-800">
                                <Plus size={16} className="mr-1" /> Nuova polizza
                            </Button>
                        </DialogTrigger>
                        <NuovaPolizzaDialog onClose={() => { setOpen(false); load(); }} />
                    </Dialog>
                )}
            />

            {/* Preset rapidi */}
            <div className="flex flex-wrap gap-2 mb-3">
                {PRESETS.map((p) => (
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
                    </button>
                ))}
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
                        <Input
                            placeholder="Prodotto..." value={filters.prodotto}
                            onChange={(e) => setF("prodotto", e.target.value)}
                            data-testid="pol-f-prodotto"
                        />
                        <div></div>
                        <div>
                            <Label className="text-[10px] text-slate-500">Scadenza dal</Label>
                            <Input type="date" value={filters.dal} onChange={(e) => setF("dal", e.target.value)} data-testid="pol-f-dal" />
                        </div>
                        <div>
                            <Label className="text-[10px] text-slate-500">Scadenza al</Label>
                            <Input type="date" value={filters.al} onChange={(e) => setF("al", e.target.value)} data-testid="pol-f-al" />
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

            <div className="tbl-scroll" style={{ "--c1-w": "160px", "--c2-w": "100px" }}>
                {list === null ? <Loading /> : list.length === 0 ? <Empty /> : (
                    <table className="tbl freeze-3 w-full min-w-[1100px]">
                        <thead>
                            <tr>
                                <th><SortHeader k="numero_polizza" sortKey={sortKey} dir={dir} toggle={toggle}>Numero polizza</SortHeader></th>
                                <th><SortHeader k="targa" sortKey={sortKey} dir={dir} toggle={toggle}>Targa</SortHeader></th>
                                <th><SortHeader k="contraente_nome" sortKey={sortKey} dir={dir} toggle={toggle}>Contraente</SortHeader></th>
                                <th><SortHeader k="compagnia_nome" sortKey={sortKey} dir={dir} toggle={toggle}>Compagnia</SortHeader></th>
                                <th><SortHeader k="collaboratore_nome" sortKey={sortKey} dir={dir} toggle={toggle}>Collaboratore</SortHeader></th>
                                <th><SortHeader k="ramo" sortKey={sortKey} dir={dir} toggle={toggle}>Ramo</SortHeader></th>
                                <th><SortHeader k="stato" sortKey={sortKey} dir={dir} toggle={toggle}>Stato</SortHeader></th>
                                <th><SortHeader k="data_effetto" sortKey={sortKey} dir={dir} toggle={toggle}>Effetto</SortHeader></th>
                                <th><SortHeader k="data_scadenza" sortKey={sortKey} dir={dir} toggle={toggle}>Scadenza</SortHeader></th>
                                <th className="text-right"><SortHeader k="premio_lordo" sortKey={sortKey} dir={dir} toggle={toggle}>Premio lordo</SortHeader></th>
                                <th className="text-right"><SortHeader k="provvigioni" sortKey={sortKey} dir={dir} toggle={toggle}>Provvigioni</SortHeader></th>
                            </tr>
                        </thead>
                        <tbody>
                            {displayed.map((p) => (
                                <tr key={p.id} data-testid={`polizza-row-${p.id}`}>
                                    <td>
                                        <Link to={`/polizze/${p.id}`} className="text-sky-700 hover:underline font-medium">{p.numero_polizza}</Link>
                                    </td>
                                    <td className="text-xs text-sky-700 font-mono font-medium uppercase">
                                        {p.targa || <span className="text-slate-300">—</span>}
                                    </td>
                                    <td className="text-xs">{p.contraente_nome || "—"}</td>
                                    <td className="text-xs text-slate-600">{p.compagnia_nome || "—"}</td>
                                    <td className="text-xs text-slate-600">{p.collaboratore_nome || "—"}</td>
                                    <td><span className="badge badge-neutral">{p.ramo}</span></td>
                                    <td><StatusBadge stato={p.stato} /></td>
                                    <td className="num text-xs">{fmtDate(p.effetto)}</td>
                                    <td className="num text-xs">{fmtDate(p.scadenza)}</td>
                                    <td className="num text-right font-medium">{fmtEur(p.premio_lordo)}</td>
                                    <td className="num text-right text-slate-600">{fmtEur(p.provvigioni)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
                {list && list.length >= 2000 && (
                    <div className="px-4 py-2 text-xs text-slate-500 text-center border-t border-slate-100">
                        Visualizzate tutte le {list.length} polizze
                    </div>
                )}
            </div>

            {/* Footer totali */}
            <div className="sticky bottom-0 mt-4 bg-slate-900 text-slate-100 rounded-t-md px-4 py-3 flex flex-wrap items-center gap-3" data-testid="pol-footer">
                <span className="text-xs text-slate-400">
                    {list ? `${list.length} polizze${filters.preset !== "tutti" ? ` · preset: ${filters.preset}` : ""}` : ""}
                </span>
                <div className="ml-auto flex gap-6">
                    <div className="text-right">
                        <div className="text-[10px] uppercase tracking-widest text-slate-400">Premio totale</div>
                        <div className="text-base font-semibold num">{fmtEur(totali.t_lordo)}</div>
                    </div>
                    <div className="text-right">
                        <div className="text-[10px] uppercase tracking-widest text-slate-400">Provvigioni</div>
                        <div className="text-base font-semibold num">{fmtEur(totali.t_provv)}</div>
                    </div>
                </div>
            </div>
        </div>
    );
}

function NuovaPolizzaDialog({ onClose }) {
    const [ana, setAna] = useState([]);
    const [comp, setComp] = useState([]);
    const [rami, setRami] = useState([]);
    const [prodotti, setProdotti] = useState([]);
    const [collaboratori, setCollaboratori] = useState([]);
    const [contraenteQuery, setContraenteQuery] = useState("");
    const [showContraenteList, setShowContraenteList] = useState(false);
    const [ocrLoading, setOcrLoading] = useState(false);
    const ocrRef = useRef(null);
    const [polizzaFile, setPolizzaFile] = useState(null);
    // Suggerimenti targa per autocomplete live (search nei veicoli del libro matricola)
    const [targheSuggest, setTargheSuggest] = useState([]);
    const [veicoloInfo, setVeicoloInfo] = useState(null);  // {fonte: "libro_matricola"|"polizza", polizze_collegate: [...]}
    const [f, setF] = useState({
        numero_polizza: "", compagnia_id: "", contraente_id: "",
        ramo: "", prodotto: "", effetto: "", scadenza: "",
        premio_lordo: 0, premio_netto: 0, provvigioni: 0,
        targa: "", frazionamento: "annuale", stato: "attiva",
        collaboratore_id: "",
    });
    useEffect(() => {
        api.get("/compagnie").then((r) => setComp(r.data));
        api.get("/librerie/rami").then((r) => setRami(r.data || []));
        api.get("/auth/users", { params: { role: "collaboratore" } })
            .then((r) => setCollaboratori(r.data || []))
            .catch(() => setCollaboratori([]));
    }, []);

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

    // Anagrafica selezionata (per mostrare nome nel campo di ricerca)
    const contraenteSelezionato = ana.find((a) => a.id === f.contraente_id);

    // Lista filtrata = quanto restituito dal server (gia' filtrato per query con AND multi-token).
    const anaFiltrate = ana.slice(0, 50);
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const onOcrPolizza = async (file) => {
        if (!file) return;
        setOcrLoading(true);
        setPolizzaFile(file);
        const fd = new FormData();
        fd.append("file", file);
        try {
            const r = await api.post("/utility/ocr-polizza", fd,
                { headers: { "Content-Type": "multipart/form-data" }, timeout: 90000 });
            const d = r.data;
            const ramoMap = { RCAUTO: "RCA", INFR: "INFORTUNI" };
            const ramo = ramoMap[d.ramo] || d.ramo || "RCA";
            const compMatch = d.compagnia
                ? comp.find((c) => c.ragione_sociale?.toUpperCase().includes(d.compagnia.toUpperCase().split(" ")[0]))
                : null;
            const cfContr = d.contraente?.codice_fiscale || d.contraente?.partita_iva;
            const contrMatch = cfContr
                ? ana.find((a) => a.codice_fiscale === cfContr || a.partita_iva === cfContr)
                : null;
            setF((p) => ({
                ...p,
                numero_polizza: d.numero_polizza || p.numero_polizza,
                compagnia_id: compMatch?.id || p.compagnia_id,
                contraente_id: contrMatch?.id || p.contraente_id,
                ramo, prodotto: d.prodotto || p.prodotto,
                effetto: d.data_decorrenza || p.effetto,
                scadenza: d.data_scadenza || p.scadenza,
                premio_lordo: d.premio_lordo_totale ?? p.premio_lordo,
                premio_netto: d.premio_netto_totale ?? p.premio_netto,
                provvigioni: d.provvigioni_totali ?? p.provvigioni,
                targa: d.veicolo?.targa || p.targa,
                frazionamento: d.frazionamento || p.frazionamento,
            }));
            let msg = `Polizza riconosciuta: ${d.numero_polizza || "?"}`;
            if (!compMatch && d.compagnia) msg += ` · ⚠ Compagnia "${d.compagnia}" da abbinare manualmente`;
            if (!contrMatch && cfContr) msg += ` · ⚠ Contraente CF ${cfContr} da abbinare manualmente`;
            toast.success(msg);
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
                provvigioni: parseFloat(f.provvigioni) || 0,
                assicurato_ids: [f.contraente_id],
            };
            // Se la targa è stata associata a un veicolo del libro matricola, lo collego
            if (f.veicolo_id) {
                payload.veicoli_ids = [f.veicolo_id];
            }
            const created = await api.post("/polizze", payload);
            if (polizzaFile && created.data?.id) {
                const fd = new FormData();
                fd.append("file", polizzaFile);
                fd.append("salva_come_allegato", "true");
                fd.append("polizza_id", created.data.id);
                api.post("/utility/ocr-polizza", fd,
                    { headers: { "Content-Type": "multipart/form-data" } }).catch(() => {});
            }
            toast.success("Polizza creata");
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        }
    };

    return (
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader><DialogTitle>Nuova polizza</DialogTitle></DialogHeader>

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
                        </SelectContent>
                    </Select>
                </div>
                <div>
                    <Label>Compagnia *</Label>
                    <Select value={f.compagnia_id} onValueChange={(v) => set("compagnia_id", v)}>
                        <SelectTrigger data-testid="pol-comp-select"><SelectValue placeholder="Seleziona" /></SelectTrigger>
                        <SelectContent>
                            {comp.map((c) => <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
                <div className="col-span-2">
                    <Label>Contraente *</Label>
                    <div className="relative">
                        <Input
                            value={
                                showContraenteList
                                    ? contraenteQuery
                                    : (contraenteSelezionato?.ragione_sociale || contraenteQuery)
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
                                            setContraenteQuery("");
                                            setShowContraenteList(false);
                                        }}
                                        data-testid={`contraente-opt-${a.id}`}
                                    >
                                        <div className="text-sm font-medium">{a.ragione_sociale}</div>
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
                <div><Label>Effetto *</Label><Input type="date" value={f.effetto} onChange={(e) => set("effetto", e.target.value)} /></div>
                <div><Label>Scadenza *</Label><Input type="date" value={f.scadenza} onChange={(e) => set("scadenza", e.target.value)} /></div>
                <div><Label>Premio lordo €</Label><Input type="number" step="0.01" value={f.premio_lordo} onChange={(e) => set("premio_lordo", e.target.value)} /></div>
                <div><Label>Premio netto €</Label><Input type="number" step="0.01" value={f.premio_netto} onChange={(e) => set("premio_netto", e.target.value)} /></div>
                <div><Label>Provvigioni €</Label><Input type="number" step="0.01" value={f.provvigioni} onChange={(e) => set("provvigioni", e.target.value)} /></div>
                <div>
                    <Label>Targa (se RCA)</Label>
                    <Input
                        value={f.targa}
                        list="targhe-suggest"
                        autoComplete="off"
                        onChange={async (e) => {
                            const t = e.target.value.toUpperCase();
                            set("targa", t);
                            setVeicoloInfo(null);
                            // Live search nei veicoli (>= 2 caratteri)
                            if (t.length >= 2) {
                                try {
                                    const r = await api.get("/veicoli", { params: { q: t, limit: 10 } });
                                    setTargheSuggest(r.data || []);
                                } catch { /* silenzio */ }
                            } else {
                                setTargheSuggest([]);
                            }
                        }}
                        onBlur={async (e) => {
                            const t = e.target.value.trim().toUpperCase();
                            if (!t || t.length < 4) return;
                            // 1) Prima cerca nel Libro Matricola (sorgente "ufficiale" / più completa)
                            try {
                                const r = await api.get(`/veicoli/by-targa/${encodeURIComponent(t)}`);
                                const v = r.data?.veicolo;
                                if (v) {
                                    setF((prev) => ({
                                        ...prev,
                                        targa: t,
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
                                        veicolo_id: v.id,  // collegamento esplicito
                                    }));
                                    setVeicoloInfo({
                                        fonte: "libro_matricola",
                                        veicolo: v,
                                        polizze_collegate: r.data?.polizze_collegate || [],
                                    });
                                    const npol = (r.data?.polizze_collegate || []).length;
                                    toast.success(
                                        `Veicolo dal Libro Matricola: ${v.marca || ""} ${v.modello || ""} `
                                        + `${npol ? `(${npol} polizz${npol === 1 ? "a" : "e"} già collegat${npol === 1 ? "a" : "e"})` : ""}`
                                    );
                                    return;
                                }
                            } catch { /* not found, fallback */ }
                            // 2) Fallback: lookup nelle polizze precedenti (vecchio endpoint)
                            try {
                                const r = await api.get("/polizze/veicolo-by-targa", { params: { targa: t } });
                                if (r.data && r.data.trovata) {
                                    setF((prev) => ({
                                        ...prev,
                                        targa: t,
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
                                    toast.success(
                                        `Veicolo trovato in polizza precedente: ${r.data.veicolo_marca || ""} `
                                        + `${r.data.veicolo_modello || ""} (${r.data.n_polizze} polizze)`
                                    );
                                }
                            } catch (err) {
                                console.warn("targa lookup", err?.message);
                            }
                        }}
                        data-testid="pol-targa-input"
                    />
                    {/* Datalist suggerimenti live mentre digita */}
                    <datalist id="targhe-suggest">
                        {targheSuggest.map((v) => (
                            <option key={v.id} value={v.targa}>
                                {[v.marca, v.modello, v.proprietario].filter(Boolean).join(" · ")}
                            </option>
                        ))}
                    </datalist>
                    {/* Info box veicolo trovato + polizze collegate */}
                    {veicoloInfo && (
                        <div className="mt-2 p-2 bg-sky-50 border border-sky-200 rounded text-xs" data-testid="veicolo-info-box">
                            <div className="flex items-center gap-1.5 font-medium text-sky-900">
                                <Car size={12} />
                                {veicoloInfo.fonte === "libro_matricola"
                                    ? "Dati dal Libro Matricola"
                                    : "Dati da polizza precedente"}
                            </div>
                            {veicoloInfo.veicolo && (
                                <div className="text-slate-700 mt-0.5">
                                    {veicoloInfo.veicolo.marca} {veicoloInfo.veicolo.modello}
                                    {veicoloInfo.veicolo.proprietario && <> · <span className="text-slate-500">Proprietario: {veicoloInfo.veicolo.proprietario}</span></>}
                                </div>
                            )}
                            {(veicoloInfo.polizze_collegate || []).length > 0 && (
                                <div className="mt-1.5">
                                    <div className="font-medium text-slate-600 text-[11px]">Polizze già su questa targa:</div>
                                    <ul className="list-disc pl-4 mt-0.5">
                                        {(veicoloInfo.polizze_collegate || []).map((p) => (
                                            <li key={p.id} className="text-[11px]">
                                                <span className="font-mono">{p.numero_polizza}</span>
                                                {p.ramo && <> · {p.ramo}</>}
                                                {p.stato && <span className="ml-1 text-slate-500">[{p.stato}]</span>}
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            )}
                        </div>
                    )}
                </div>
                <div className="col-span-2">
                    <Label>Collaboratore (Operatore)</Label>
                    <Select
                        value={f.collaboratore_id || "__none__"}
                        onValueChange={(v) => set("collaboratore_id", v === "__none__" ? "" : v)}
                    >
                        <SelectTrigger data-testid="pol-collab-select"><SelectValue placeholder="Nessun collaboratore" /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="__none__">— Nessuno —</SelectItem>
                            {collaboratori.map((c) => (
                                <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
            </div>
            <DialogFooter>
                <Button data-testid="pol-save-button" onClick={save} className="bg-sky-700 hover:bg-sky-800">Crea polizza</Button>
            </DialogFooter>
        </DialogContent>
    );
}
