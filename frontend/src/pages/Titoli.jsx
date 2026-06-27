import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, fmtDate, fmtEur, API_BASE } from "@/lib/api";
import { openPdf } from "@/lib/pdf";
import { PageHeader, StatusBadge, Loading, Empty } from "@/components/Shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import RowActions from "@/components/RowActions";
import AllegatiCell from "@/components/AllegatiCell";
import ChiusuraPill from "@/components/ChiusuraPill";
import DialogIncassoCopertura from "@/components/DialogIncassoCopertura";
import TitoloDialog from "@/components/TitoloDialog";
import useMezziPagamento from "@/hooks/useMezziPagamento";
import { Checkbox } from "@/components/ui/checkbox";
import {
    Search, Filter, X, Printer, FileSpreadsheet, FileText, Wallet, Shield,
    ChevronDown, ChevronUp,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

const PRESETS_CORRENTI = [
    { key: "sospesi", label: "Sospesi (da incassare)" },
    { key: "scadute_oggi", label: "Scadute oggi" },
    { key: "scad_5g", label: "Scadute da 5gg" },
    { key: "scad_10g", label: "Scadute da 10gg" },
    { key: "scad15", label: "Scadute da 15gg" },
    { key: "scad_oltre15", label: "Oltre 15gg" },
    { key: "tutti_aperti", label: "Tutti (da incassare)" },
];

const PRESETS_STORICO = [
    { key: "storico", label: "Tutti incassati" },
    { key: "storico_anno", label: "Anno corrente" },
    { key: "storico_mese", label: "Mese corrente" },
];

const todayISO = () => new Date().toISOString().slice(0, 10);
const firstOfYearISO = () => `${new Date().getFullYear()}-01-01`;
const firstOfMonthISO = () => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
};

const presetParams = (key) => {
    switch (key) {
        case "sospesi": return { stato: "da_incassare", titolo_coperto: true };
        case "tutti_aperti": return { stato_not: "incassato,stornato" };
        case "storico": return { stato: "incassato" };
        case "storico_anno": return { stato: "incassato", dal: firstOfYearISO(), al: todayISO() };
        case "storico_mese": return { stato: "incassato", dal: firstOfMonthISO(), al: todayISO() };
        case "scad15": return { scadute_da_min: 15 };
        case "scad_oltre15": return { scadenza_oltre_giorni: 15 };
        case "scadute_oggi": return { scadute_oggi: true };
        case "scad_5g": return { scadute_da_min: 5 };
        case "scad_10g": return { scadute_da_min: 10 };
        default: return { stato_not: "incassato,stornato" };
    }
};

export default function Titoli({ storicoMode = false } = {}) {
    const { user } = useAuth();
    const [searchParams] = useSearchParams();
    const urlPreset = searchParams.get("preset");
    const [list, setList] = useState(null);
    const [compagnie, setCompagnie] = useState([]);
    const [rami, setRami] = useState([]);
    const [conti, setConti] = useState([]);
    const [utenti, setUtenti] = useState([]);
    const [editing, setEditing] = useState(null);
    const [showFilters, setShowFilters] = useState(false);

    const PRESETS = storicoMode ? PRESETS_STORICO : PRESETS_CORRENTI;
    const ACCEPTED_PRESETS = storicoMode
        ? ["storico", "storico_anno", "storico_mese"]
        : ["sospesi", "tutti_aperti", "scad15", "scad_oltre15", "scadute_oggi", "scad_5g", "scad_10g"];

    const defaultPreset = storicoMode ? "storico" : "tutti_aperti";

    const [filters, setFilters] = useState({
        preset: urlPreset && ACCEPTED_PRESETS.includes(urlPreset) ? urlPreset : defaultPreset,
        q: "",
        stato: "all", compagnia_id: "all", ramo: "all", prodotto: "",
        collaboratore_id: "all", mezzo_pagamento: "", conto_cassa_id: "all",
        dal: "", al: "",
    });

    // Allineamento preset dall'URL (es. /titoli?preset=sospesi)
    useEffect(() => {
        if (urlPreset && ACCEPTED_PRESETS.includes(urlPreset)) {
            setFilters((p) => ({ ...p, preset: urlPreset }));
        }
    }, [urlPreset]);
    const setF = (k, v) => setFilters((p) => ({ ...p, [k]: v }));

    const [selected, setSelected] = useState(new Set());
    const [bulkOpen, setBulkOpen] = useState(null); // "incassa" | "copertura"
    const [paying, setPaying] = useState(null);     // titolo singolo da incassare

    const canEdit = ["admin", "collaboratore", "dipendente"].includes(user?.role);
    const canDelete = ["admin", "collaboratore"].includes(user?.role);

    const buildParams = () => {
        const p = { ...presetParams(filters.preset) };
        if (filters.q) p.q = filters.q;
        if (filters.stato !== "all" && (filters.preset === "tutti_aperti" || filters.preset === "storico")) p.stato = filters.stato;
        if (filters.compagnia_id !== "all") p.compagnia_id = filters.compagnia_id;
        if (filters.ramo !== "all") p.ramo = filters.ramo;
        if (filters.collaboratore_id !== "all") p.collaboratore_id = filters.collaboratore_id;
        if (filters.conto_cassa_id !== "all") p.conto_cassa_id = filters.conto_cassa_id;
        if (filters.prodotto) p.prodotto = filters.prodotto;
        if (filters.mezzo_pagamento) p.mezzo_pagamento = filters.mezzo_pagamento;
        if (filters.dal) p.dal = filters.dal;
        if (filters.al) p.al = filters.al;
        return p;
    };

    const load = () => {
        setSelected(new Set());
        api.get("/titoli", { params: buildParams() }).then((r) => setList(r.data));
    };

    useEffect(() => { load(); }, [filters]);
    useEffect(() => {
        Promise.all([
            api.get("/compagnie"), api.get("/librerie/rami"),
            api.get("/librerie/conti-cassa"),
            api.get("/auth/users").catch(() => ({ data: [] })),
        ]).then(([c, r, cc, u]) => {
            setCompagnie(c.data); setRami(r.data); setConti(cc.data);
            setUtenti((u.data || []).filter((x) => x.role !== "cliente"));
        });
    }, []);

    const displayed = list || [];

    // totali calcolati sui dati visualizzati
    const totali = useMemo(() => {
        const src = list || [];
        const t_lordo = src.reduce((s, t) => s + (t.importo_lordo || 0), 0);
        const t_netto = src.reduce((s, t) => s + (t.importo_netto || 0), 0);
        const t_provv = src.reduce((s, t) => s + (t.provvigione_totale ?? t.provvigioni ?? 0), 0);
        const t_provv_collab = src.reduce((s, t) => s + (t.provvigione_collaboratore || 0), 0);
        const t_provv_margine = src.reduce((s, t) => s + (t.provvigione_margine ?? ((t.provvigione_totale ?? t.provvigioni ?? 0) - (t.provvigione_collaboratore || 0))), 0);
        const da_pagare = src.filter((t) => t.stato !== "incassato").reduce((s, t) => s + (t.importo_lordo || 0), 0);
        const incassato = src.filter((t) => t.stato === "incassato").reduce((s, t) => s + (t.importo_pagato ?? t.importo_lordo ?? 0), 0);
        return { t_lordo, t_netto, t_provv, t_provv_collab, t_provv_margine, da_pagare, incassato };
    }, [list]);

    const toggle = (id) => setSelected((p) => {
        const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n;
    });
    const toggleAll = () => {
        if (selected.size === displayed.length) setSelected(new Set());
        else setSelected(new Set(displayed.map((t) => t.id)));
    };

    const elimina = async (id) => {
        try { await api.delete(`/titoli/${id}`); toast.success("Titolo eliminato"); load(); }
        catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const exportCsv = () => window.open(`${API_BASE}/export/titoli.csv`, "_blank");
    const exportXlsx = () => window.open(`${API_BASE}/export/titoli.xlsx`, "_blank");
    const stampaPdf = () => openPdf("/stampa/titoli", buildParams());

    return (
        <div data-testid={storicoMode ? "titoli-storici-page" : "titoli-page"}>
            <PageHeader
                title={storicoMode ? "Titoli storici" : "Titoli"}
                subtitle={storicoMode
                    ? "Archivio titoli incassati · filtri per periodo · allegati e quietanze"
                    : "Sospesi · in scadenza · coperti non pagati · esportazioni e stampa"
                }
            />

            {/* Preset rapidi */}
            <div className="flex flex-wrap gap-2 mb-3">
                {PRESETS.map((p) => (
                    <button
                        key={p.key}
                        onClick={() => setF("preset", p.key)}
                        data-testid={`preset-${p.key}`}
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
                            data-testid="titoli-search"
                            placeholder="Cerca per polizza, targa, contraente..."
                            value={filters.q}
                            onChange={(e) => setF("q", e.target.value)}
                            className="pl-9"
                        />
                    </div>
                    <Button variant="outline" onClick={() => setShowFilters((s) => !s)} data-testid="toggle-filters">
                        <Filter size={14} className="mr-1" /> Filtri {showFilters ? <ChevronUp size={12} className="ml-1" /> : <ChevronDown size={12} className="ml-1" />}
                    </Button>
                    <div className="ml-auto flex gap-2">
                        <Button variant="outline" onClick={stampaPdf} data-testid="titoli-print">
                            <Printer size={14} className="mr-1" /> Stampa PDF
                        </Button>
                        <Button variant="outline" onClick={exportCsv} data-testid="titoli-csv">
                            <FileText size={14} className="mr-1" /> CSV
                        </Button>
                        <Button variant="outline" onClick={exportXlsx} data-testid="titoli-xlsx">
                            <FileSpreadsheet size={14} className="mr-1" /> Excel
                        </Button>
                    </div>
                </div>

                {showFilters && (
                    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2 mt-2 pt-2 border-t border-slate-100">
                        <Select value={filters.compagnia_id} onValueChange={(v) => setF("compagnia_id", v)}>
                            <SelectTrigger data-testid="f-compagnia"><SelectValue placeholder="Compagnia" /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Tutte compagnie</SelectItem>
                                {compagnie.map((c) => <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}</SelectItem>)}
                            </SelectContent>
                        </Select>
                        <Select value={filters.ramo} onValueChange={(v) => setF("ramo", v)}>
                            <SelectTrigger data-testid="f-ramo"><SelectValue placeholder="Ramo" /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Tutti rami</SelectItem>
                                {rami.map((r) => <SelectItem key={r.id} value={r.codice}>{r.nome}</SelectItem>)}
                            </SelectContent>
                        </Select>
                        <Select value={filters.collaboratore_id} onValueChange={(v) => setF("collaboratore_id", v)}>
                            <SelectTrigger data-testid="f-collab"><SelectValue placeholder="Collaboratore" /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Tutti collaboratori</SelectItem>
                                {utenti.map((u) => <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>)}
                            </SelectContent>
                        </Select>
                        <Select value={filters.conto_cassa_id} onValueChange={(v) => setF("conto_cassa_id", v)}>
                            <SelectTrigger><SelectValue placeholder="Conto / Banca" /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Tutti conti</SelectItem>
                                {conti.map((c) => <SelectItem key={c.id} value={c.id}>{c.nome}</SelectItem>)}
                            </SelectContent>
                        </Select>
                        <Input placeholder="Prodotto..." value={filters.prodotto} onChange={(e) => setF("prodotto", e.target.value)} />
                        <Input placeholder="Mezzo pag." value={filters.mezzo_pagamento} onChange={(e) => setF("mezzo_pagamento", e.target.value)} />
                        <div>
                            <Label className="text-[10px] text-slate-500">Scadenza dal</Label>
                            <Input type="date" value={filters.dal} onChange={(e) => setF("dal", e.target.value)} data-testid="f-dal" />
                        </div>
                        <div>
                            <Label className="text-[10px] text-slate-500">Scadenza al</Label>
                            <Input type="date" value={filters.al} onChange={(e) => setF("al", e.target.value)} data-testid="f-al" />
                        </div>
                        <button onClick={() => setFilters({
                            preset: "sospesi", q: "", stato: "all", compagnia_id: "all", ramo: "all",
                            prodotto: "", collaboratore_id: "all", mezzo_pagamento: "",
                            conto_cassa_id: "all", dal: "", al: "",
                        })} className="text-xs text-slate-500 hover:text-rose-600 inline-flex items-center gap-1 col-span-2">
                            <X size={12} /> Azzera filtri
                        </button>
                    </div>
                )}
            </div>

            {/* Tabella */}
            <div className="bg-white border border-slate-200 rounded-md overflow-x-auto pb-2">
                {list === null ? <Loading /> : list.length === 0 ? <Empty /> : (
                    <table className="tbl-compact w-full text-xs">
                        <thead>
                            <tr>
                                <th className="w-8 text-center">
                                    <input
                                        type="checkbox"
                                        data-testid="select-all-checkbox"
                                        checked={displayed.length > 0 && selected.size === displayed.length}
                                        onChange={toggleAll}
                                    />
                                </th>
                                <th className="w-[140px]">Contratto</th>
                                <th className="w-[100px]">Targa</th>
                                <th>Contraente</th>
                                <th className="w-[120px]">Compagnia</th>
                                <th className="w-[100px]">Collaboratore</th>
                                <th className="text-right w-[80px]">Premio €</th>
                                <th className="text-right w-[70px]" title="Provvigione totale">Provv. tot.</th>
                                <th className="text-right w-[70px]" title="Quota collaboratore">Collab.</th>
                                <th className="text-right w-[70px]" title="Margine agenzia">Margine</th>
                                <th className="w-[80px] whitespace-nowrap">Scadenza</th>
                                <th className="w-[80px] whitespace-nowrap">Copertura</th>
                                {(storicoMode || filters.preset === "storico" || filters.preset === "storico_anno" || filters.preset === "storico_mese") && (
                                    <>
                                        <th className="w-[80px] whitespace-nowrap" data-testid="th-incassato-il">Incassato il</th>
                                        <th className="w-[90px]" data-testid="th-mezzo-pag">Pagato con</th>
                                    </>
                                )}
                                <th className="w-[90px]">Stato</th>
                                <th className="text-right w-[80px]">Da pagare</th>
                                <th className="w-[44px] text-center">All.</th>
                                <th className="w-[110px] text-center">Azione</th>
                                <th className="w-[36px]"></th>
                            </tr>
                        </thead>
                        <tbody>
                            {displayed.map((t) => {
                                const daPagare = t.stato === "incassato" ? 0 : (t.importo_lordo || 0);
                                return (
                                    <tr
                                        key={t.id}
                                        data-testid={`titolo-row-${t.id}`}
                                        className={`${selected.has(t.id) ? "bg-sky-50" : ""} hover:bg-sky-50/60 cursor-pointer`}
                                        onClick={(e) => {
                                            // ignora click su elementi interattivi (checkbox, link, button, menu)
                                            if (e.target.closest("button, a, input, [role='menuitem'], [data-row-noclick]")) return;
                                            if (canEdit) setEditing(t);
                                        }}
                                    >
                                        <td className="text-center">
                                            <input
                                                type="checkbox"
                                                data-testid={`select-${t.id}`}
                                                checked={selected.has(t.id)}
                                                onChange={() => toggle(t.id)}
                                            />
                                        </td>
                                        <td>
                                            <Link to={`/polizze/${t.polizza_id}`} className="text-amber-600 hover:underline font-medium block">
                                                {t.numero_polizza || "—"}
                                            </Link>
                                            <div className="text-[11px] text-slate-500">{t.prodotto || t.ramo}</div>
                                        </td>
                                        <td className="text-xs text-sky-700 font-mono font-medium uppercase">
                                            {t.targa || <span className="text-slate-300">—</span>}
                                        </td>
                                        <td className="text-xs">{t.contraente_nome || "-"}</td>
                                        <td className="text-xs text-slate-700">{t.compagnia_nome || "-"}</td>
                                        <td className="text-xs text-slate-700">{t.collaboratore_nome || "-"}</td>
                                        <td className="num text-right font-medium" data-testid={`titolo-premio-${t.id}`}>{fmtEur(t.importo_lordo)}</td>
                                        <td className="num text-right text-slate-700" data-testid={`titolo-provv-tot-${t.id}`}>{fmtEur(t.provvigione_totale ?? t.provvigioni ?? 0)}</td>
                                        <td className="num text-right text-sky-700 font-medium" data-testid={`titolo-provv-collab-${t.id}`} title={t.provvigione_pct_collab > 0 ? `${t.provvigione_pct_collab}%` : "Nessuno schema"}>{fmtEur(t.provvigione_collaboratore || 0)}</td>
                                        <td className="num text-right text-amber-700 font-medium" data-testid={`titolo-provv-margine-${t.id}`}>{fmtEur(t.provvigione_margine ?? ((t.provvigione_totale ?? t.provvigioni ?? 0) - (t.provvigione_collaboratore || 0)))}</td>
                                        <td className="num text-xs whitespace-nowrap">{fmtDate(t.scadenza)}</td>
                                        <td className="num text-xs text-emerald-700 whitespace-nowrap">{t.data_copertura ? fmtDate(t.data_copertura) : "—"}</td>
                                        {(storicoMode || filters.preset === "storico" || filters.preset === "storico_anno" || filters.preset === "storico_mese") && (
                                            <>
                                                <td className="num text-xs whitespace-nowrap text-emerald-700" data-testid={`titolo-incassato-il-${t.id}`}>{t.data_incasso ? fmtDate(t.data_incasso) : "—"}</td>
                                                <td className="text-xs text-slate-700" data-testid={`titolo-mezzo-${t.id}`}>{t.mezzo_pagamento || "—"}</td>
                                            </>
                                        )}
                                        <td>
                                            <div className="flex items-center gap-1.5">
                                                <StatusBadge stato={t.stato} titolo_coperto={t.titolo_coperto} data_copertura={t.data_copertura} />
                                                <ChiusuraPill data={t.data_incasso} />
                                            </div>
                                        </td>
                                        <td className="num text-right font-semibold text-rose-700">
                                            {daPagare > 0 ? fmtEur(daPagare) : "—"}
                                        </td>
                                        <td className="text-center">
                                            <AllegatiCell
                                                entita_tipo="titolo"
                                                entita_id={t.id}
                                                count={t.allegati_count}
                                                hint={t.data_incasso ? "Allega ricevuta bonifico / assegno" : "Allega documento"}
                                                onChange={load}
                                            />
                                        </td>
                                        <td className="text-center">
                                            {t.stato !== "incassato" && t.stato !== "stornato" ? (
                                                <Button
                                                    size="sm"
                                                    className="h-7 px-2 text-xs bg-emerald-600 hover:bg-emerald-700"
                                                    onClick={() => setPaying(t)}
                                                    data-testid={`titolo-incassa-${t.id}`}
                                                >
                                                    Incasso/Copertura
                                                </Button>
                                            ) : (
                                                <span className="text-xs text-emerald-700">✓ {fmtDate(t.data_incasso)}</span>
                                            )}
                                        </td>
                                        <td className="text-right">
                                            <RowActions
                                                testid={`titolo-actions-${t.id}`}
                                                onEdit={canEdit ? () => setEditing(t) : null}
                                                onDelete={() => elimina(t.id)}
                                                canDelete={canDelete}
                                                label="titolo"
                                            />
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                )}
                {list && list.length >= 2000 && (
                    <div className="px-4 py-2 text-xs text-slate-500 text-center border-t border-slate-100">
                        Visualizzati tutti i {list.length} risultati
                    </div>
                )}
            </div>

            {/* Footer azione bulk + totali */}
            <div className="sticky bottom-0 mt-4 bg-white border-t-2 border-slate-900 shadow-lg rounded-t-md px-4 py-3" data-testid="bulk-footer">
                <div className="flex flex-wrap items-center gap-3">
                    <button onClick={() => setSelected(new Set(displayed.map((t) => t.id)))} className="px-3 py-1.5 bg-amber-500 hover:bg-amber-600 text-slate-900 rounded text-xs font-semibold" data-testid="select-all-btn">
                        SELEZIONA TUTTI
                    </button>
                    <button onClick={() => setSelected(new Set())} className="px-3 py-1.5 bg-slate-200 hover:bg-slate-300 text-slate-700 rounded text-xs font-semibold">
                        DESELEZIONA TUTTI
                    </button>
                    <span className="text-xs text-slate-500">
                        {selected.size > 0 ? `${selected.size} selezionati` : ""}
                    </span>
                    <button
                        disabled={selected.size === 0}
                        onClick={() => setBulkOpen("bulk")}
                        data-testid="bulk-incasso-copertura-btn"
                        className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-200 disabled:text-slate-400 text-white disabled:cursor-not-allowed rounded text-xs font-semibold inline-flex items-center gap-1"
                    >
                        <Wallet size={14} /> INCASSO / COPERTURA
                    </button>
                </div>
                {/* KPI cards in stile pannello laterale Brogliaccio */}
                <div className="mt-3 grid grid-cols-2 md:grid-cols-6 gap-2" data-testid="titoli-kpi-grid">
                    <KpiBar label="Rata totale" value={totali.t_lordo} accent="slate" testid="kpi-lordo" />
                    <KpiBar label="Provv. totali" value={totali.t_provv} accent="sky" testid="kpi-provv" />
                    <KpiBar label="Provv. collab." value={totali.t_provv_collab} accent="indigo" testid="kpi-provv-collab" />
                    <KpiBar label="Margine" value={totali.t_provv_margine} accent="amber" testid="kpi-provv-margine" />
                    <KpiBar label="Da pagare" value={totali.da_pagare} accent="amber" testid="kpi-dapagare" highlight />
                    <KpiBar label="Incassato" value={totali.incassato} accent="emerald" testid="kpi-incassato" />
                </div>
            </div>

            {bulkOpen && (() => {
                const sel = (list || []).filter((t) => selected.has(t.id));
                if (sel.length === 1) {
                    return (
                        <DialogIncassoCopertura
                            titolo={sel[0]}
                            conti={conti}
                            onClose={() => { setBulkOpen(null); setSelected(new Set()); load(); }}
                        />
                    );
                }
                return (
                    <BulkActionDialog
                        action={bulkOpen}
                        ids={Array.from(selected)}
                        titoli={sel}
                        conti={conti}
                        onClose={() => { setBulkOpen(null); load(); }}
                    />
                );
            })()}

            {editing && (
                <TitoloDialog
                    titolo={editing}
                    conti={conti}
                    onClose={() => { setEditing(null); load(); }}
                    onDelete={() => { setEditing(null); load(); }}
                />
            )}

            {paying && (
                <DialogIncassoCopertura
                    titolo={paying}
                    conti={conti}
                    onClose={() => { setPaying(null); load(); }}
                />
            )}
        </div>
    );
}

function BulkActionDialog({ action, ids, titoli = [], conti, onClose }) {
    const { mezzi } = useMezziPagamento();
    const today = new Date().toISOString().slice(0, 10);
    const totaleLordo = (titoli || []).reduce((s, t) => s + (parseFloat(t.importo_lordo) || 0), 0);
    const totaleProvv = (titoli || []).reduce((s, t) => s + (parseFloat(t.provvigioni) || 0), 0);
    // Riepilogo per compagnia (utile quando si selezionano titoli di compagnie diverse)
    const breakdown = (() => {
        const map = new Map();
        for (const t of (titoli || [])) {
            const k = t.compagnia_nome || "—";
            const cur = map.get(k) || { compagnia: k, count: 0, totale: 0 };
            cur.count += 1;
            cur.totale += parseFloat(t.importo_lordo) || 0;
            map.set(k, cur);
        }
        return Array.from(map.values()).sort((a, b) => b.totale - a.totale);
    })();
    const [doCopertura, setDoCopertura] = useState(true);
    const [doIncasso, setDoIncasso] = useState(false);
    const [emailOperatori, setEmailOperatori] = useState(false);
    const [emailContraenti, setEmailContraenti] = useState(false);
    const [inDirezione, setInDirezione] = useState(false);
    const [dataCopertura, setDataCopertura] = useState(today);
    const [dataIncasso, setDataIncasso] = useState(today);
    const [mezzo, setMezzo] = useState("contanti");
    const [contoId, setContoId] = useState(conti?.[0]?.id || "");
    const [file, setFile] = useState(null);
    const [noteEmail, setNoteEmail] = useState("");

    // Per-titolo: importo editabile + sconto/sospeso quando residuo > 0
    const [perTit, setPerTit] = useState(() => {
        const m = {};
        for (const t of (titoli || [])) {
            m[t.id] = {
                importo_pagato: parseFloat(t.importo_lordo) || 0,
                tipo_chiusura: "sconto",
            };
        }
        return m;
    });
    const setPerTitField = (tid, key, value) =>
        setPerTit((p) => ({ ...p, [tid]: { ...(p[tid] || {}), [key]: value } }));
    const totalePagato = Object.values(perTit).reduce((s, v) => s + (parseFloat(v.importo_pagato) || 0), 0);
    const totaleResiduo = (titoli || []).reduce((s, t) => {
        const pag = parseFloat(perTit[t.id]?.importo_pagato) || 0;
        return s + Math.max(0, (parseFloat(t.importo_lordo) || 0) - pag);
    }, 0);

    const submit = async () => {
        if (!doCopertura && !doIncasso) {
            toast.error("Seleziona Copertura e/o Incasso");
            return;
        }
        try {
            const messages = [];
            // 1) Copertura via endpoint multipart se file/email, altrimenti diretto
            if (doCopertura) {
                if (file || emailContraenti || emailOperatori) {
                    const fd = new FormData();
                    if (file) fd.append("file", file);
                    const qs = new URLSearchParams({
                        action: "copertura",
                        ids_json: JSON.stringify(ids),
                        invia_cliente: String(emailContraenti),
                        invia_collaboratore: String(emailOperatori),
                        data_copertura: dataCopertura,
                    });
                    if (noteEmail) qs.append("note_email", noteEmail);
                    const r = await api.post(`/titoli/bulk-azione-allegato?${qs}`, fd, {
                        headers: { "Content-Type": "multipart/form-data" },
                    });
                    messages.push(`Copertura su ${r.data.aggiornati} titoli`);
                    if (r.data.allegato_nome) messages.push(`allegato "${r.data.allegato_nome}"`);
                    if (r.data.email_create) messages.push(`${r.data.email_create} email in coda`);
                } else {
                    const r = await api.post("/titoli/bulk-copertura", {
                        ids, data_copertura: dataCopertura,
                    });
                    messages.push(`Copertura su ${r.data.aggiornati} titoli`);
                }
                if (inDirezione) {
                    await Promise.all(ids.map((id) =>
                        api.put(`/titoli/${id}`, { pagamento_in_direzione: true }).catch(() => null),
                    ));
                }
            }
            // 2) Incasso per ogni titolo selezionato (importo editabile + sconto/sospeso)
            if (doIncasso) {
                let ok = 0, totale = 0;
                for (const t of (titoli || [])) {
                    const pt = perTit[t.id] || {};
                    const importo = parseFloat(pt.importo_pagato);
                    if (isNaN(importo) || importo < 0) continue;
                    const lordo = parseFloat(t.importo_lordo) || 0;
                    const residuo = Math.max(0, lordo - importo);
                    const tipo_ch = residuo > 0 ? (pt.tipo_chiusura || "sconto") : "sconto";
                    try {
                        await api.post(`/titoli/${t.id}/incassa`, {
                            data_incasso: dataIncasso,
                            mezzo_pagamento: mezzo,
                            conto_cassa_id: contoId || null,
                            importo_pagato: importo,
                            tipo_chiusura: tipo_ch,
                        });
                        ok += 1;
                        totale += importo;
                    } catch { /* skip but continue */ }
                }
                messages.push(`${ok}/${(titoli || []).length} titoli incassati per ${fmtEur(totale)}`);
            }
            toast.success(messages.join(" · ") || "Operazione completata");
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        }
    };

    const cellLabel = "bg-slate-100 text-slate-700 font-medium text-right px-3 py-2 align-middle border border-slate-200 w-[180px]";
    const cellValueRO = "bg-cyan-50 text-cyan-900 px-3 py-2 align-middle border border-slate-200";

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-2xl p-0 overflow-hidden bg-white" data-testid="dialog-bulk-incasso-copertura">
                <DialogHeader className="px-6 py-3 border-b border-slate-200 bg-white">
                    <DialogTitle className="text-slate-800 font-semibold">
                        Incasso / Copertura — {ids.length} titoli
                    </DialogTitle>
                </DialogHeader>

                <div className="px-6 py-4 max-h-[78vh] overflow-y-auto space-y-4">
                    <table className="w-full border-collapse text-sm">
                        <tbody>
                            <tr>
                                <td className={cellLabel}>Titoli selezionati</td>
                                <td className={cellValueRO} data-testid="bulk-count">{ids.length}</td>
                            </tr>
                            {breakdown.length > 1 && (
                                <tr>
                                    <td className={cellLabel}>Compagnie</td>
                                    <td className={cellValueRO}>
                                        {breakdown.map((b) => (
                                            <div key={b.compagnia} className="flex justify-between text-xs">
                                                <span>{b.compagnia} ({b.count})</span>
                                                <span className="num font-medium">{fmtEur(b.totale)}</span>
                                            </div>
                                        ))}
                                    </td>
                                </tr>
                            )}
                            <tr>
                                <td className={cellLabel}>Provvigioni totali</td>
                                <td className={cellValueRO + " num"}>{fmtEur(totaleProvv)}</td>
                            </tr>
                        </tbody>
                    </table>

                    {/* ---- COPERTURA ---- */}
                    <div>
                        <label
                            htmlFor="bulk-cb-copertura"
                            className="flex items-center gap-3 cursor-pointer"
                        >
                            <Checkbox
                                id="bulk-cb-copertura"
                                checked={doCopertura}
                                onCheckedChange={(v) => setDoCopertura(v === true)}
                                data-testid="bulk-cb-copertura"
                            />
                            <span className="text-cyan-700 font-semibold text-lg">Copertura</span>
                        </label>
                        {doCopertura && (
                            <div className="pl-8 mt-2 space-y-2" data-testid="bulk-copertura-options">
                                <div className="flex items-center gap-3">
                                    <Label className="text-xs w-32">Data copertura</Label>
                                    <Input
                                        type="date"
                                        value={dataCopertura}
                                        onChange={(e) => setDataCopertura(e.target.value)}
                                        className="max-w-[200px]"
                                        data-testid="bulk-data-copertura"
                                    />
                                </div>
                                <label className="flex items-center gap-2 text-cyan-700 text-sm cursor-pointer">
                                    <Checkbox
                                        checked={emailOperatori}
                                        onCheckedChange={(v) => setEmailOperatori(v === true)}
                                        data-testid="bulk-email-op"
                                    />
                                    Invia email di notifica a operatori
                                </label>
                                <label className="flex items-center gap-2 text-cyan-700 text-sm cursor-pointer">
                                    <Checkbox
                                        checked={emailContraenti}
                                        onCheckedChange={(v) => setEmailContraenti(v === true)}
                                        data-testid="bulk-email-cnt"
                                    />
                                    Invia email di notifica a contraenti
                                </label>
                                <label className="flex items-center gap-2 text-cyan-700 text-sm cursor-pointer">
                                    <Checkbox
                                        checked={inDirezione}
                                        onCheckedChange={(v) => setInDirezione(v === true)}
                                        data-testid="bulk-direzione"
                                    />
                                    Pagamento (premio) effettuato dal cliente direttamente in direzione
                                </label>
                            </div>
                        )}
                    </div>

                    {/* ---- INCASSO ---- */}
                    <div>
                        <label
                            htmlFor="bulk-cb-incasso"
                            className="flex items-center gap-3 cursor-pointer"
                        >
                            <Checkbox
                                id="bulk-cb-incasso"
                                checked={doIncasso}
                                onCheckedChange={(v) => setDoIncasso(v === true)}
                                data-testid="bulk-cb-incasso"
                            />
                            <span className="text-cyan-700 font-semibold text-lg">Incasso</span>
                        </label>
                        {doIncasso && (
                            <div className="pl-8 mt-3 space-y-3" data-testid="bulk-incasso-options">
                                <div className="grid grid-cols-2 gap-3">
                                    <div>
                                        <Label className="text-xs">Data incasso</Label>
                                        <Input
                                            type="date"
                                            value={dataIncasso}
                                            onChange={(e) => setDataIncasso(e.target.value)}
                                            data-testid="bulk-data-incasso"
                                        />
                                    </div>
                                    <div>
                                        <Label className="text-xs">Mezzo pagamento</Label>
                                        <Select value={mezzo} onValueChange={setMezzo}>
                                            <SelectTrigger data-testid="bulk-mezzo"><SelectValue /></SelectTrigger>
                                            <SelectContent>
                                                {mezzi.map((m) => (
                                                    <SelectItem key={m.codice} value={m.codice}>{m.label}</SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>
                                <div>
                                    <Label className="text-xs">Conto cassa</Label>
                                    <Select
                                        value={contoId || "__none__"}
                                        onValueChange={(v) => setContoId(v === "__none__" ? "" : v)}
                                    >
                                        <SelectTrigger data-testid="bulk-conto"><SelectValue /></SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="__none__">— nessuno —</SelectItem>
                                            {(conti || []).map((c) => (
                                                <SelectItem key={c.id} value={c.id}>{c.nome}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                                <div className="bg-amber-50 border border-amber-200 rounded p-2 text-xs text-amber-900">
                                    <strong>Modifica l&apos;importo riga per riga:</strong> sotto puoi editare il pagato di ciascun titolo. Se &lt; premio scegli sconto o sospeso (residuo).
                                </div>

                                <div className="border border-slate-200 rounded overflow-hidden" data-testid="bulk-titoli-list">
                                    <table className="w-full text-xs">
                                        <thead className="bg-slate-50 text-slate-600">
                                            <tr>
                                                <th className="text-left px-2 py-1.5">Contraente</th>
                                                <th className="text-right px-2 py-1.5">Premio</th>
                                                <th className="text-right px-2 py-1.5 w-[110px]">Pagato</th>
                                                <th className="text-right px-2 py-1.5 w-[80px]">Residuo</th>
                                                <th className="text-left px-2 py-1.5 w-[140px]">Se residuo</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {(titoli || []).map((t) => {
                                                const lordo = parseFloat(t.importo_lordo) || 0;
                                                const pt = perTit[t.id] || {};
                                                const pagato = parseFloat(pt.importo_pagato);
                                                const residuo = Math.max(0, lordo - (isNaN(pagato) ? 0 : pagato));
                                                const hasResiduo = residuo > 0.005;
                                                return (
                                                    <tr key={t.id} className="border-t border-slate-100">
                                                        <td className="px-2 py-1 truncate max-w-[200px]" title={t.contraente_nome || ""}>{t.contraente_nome || "—"}</td>
                                                        <td className="px-2 py-1 text-right num text-slate-700">{fmtEur(lordo)}</td>
                                                        <td className="px-2 py-1">
                                                            <Input
                                                                type="number" step="0.01" min="0"
                                                                value={pt.importo_pagato}
                                                                onChange={(e) => setPerTitField(t.id, "importo_pagato", e.target.value)}
                                                                className="h-7 text-right num text-xs px-1"
                                                                data-testid={`bulk-row-importo-${t.id}`}
                                                            />
                                                        </td>
                                                        <td className={`px-2 py-1 text-right num ${hasResiduo ? "text-amber-700 font-semibold" : "text-slate-400"}`}>
                                                            {hasResiduo ? fmtEur(residuo) : "—"}
                                                        </td>
                                                        <td className="px-2 py-1">
                                                            {hasResiduo ? (
                                                                <Select
                                                                    value={pt.tipo_chiusura || "sconto"}
                                                                    onValueChange={(v) => setPerTitField(t.id, "tipo_chiusura", v)}
                                                                >
                                                                    <SelectTrigger
                                                                        className="h-7 text-xs"
                                                                        data-testid={`bulk-row-tipo-${t.id}`}
                                                                    >
                                                                        <SelectValue />
                                                                    </SelectTrigger>
                                                                    <SelectContent>
                                                                        <SelectItem value="sconto">Sconto</SelectItem>
                                                                        <SelectItem value="sospeso">Sospeso</SelectItem>
                                                                    </SelectContent>
                                                                </Select>
                                                            ) : (
                                                                <span className="text-xs text-slate-400">—</span>
                                                            )}
                                                        </td>
                                                    </tr>
                                                );
                                            })}
                                        </tbody>
                                        <tfoot className="bg-slate-50 font-semibold">
                                            <tr>
                                                <td className="px-2 py-1.5 text-right">Totali</td>
                                                <td className="px-2 py-1.5 text-right num">{fmtEur(totaleLordo)}</td>
                                                <td className="px-2 py-1.5 text-right num text-emerald-700" data-testid="bulk-totale-pagato">{fmtEur(totalePagato)}</td>
                                                <td className="px-2 py-1.5 text-right num text-amber-700">{fmtEur(totaleResiduo)}</td>
                                                <td></td>
                                            </tr>
                                        </tfoot>
                                    </table>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* ---- Allegato + Email ---- */}
                    <div className="pt-3 border-t border-slate-200 space-y-3">
                        <div className="text-xs font-semibold uppercase tracking-wider text-slate-600">
                            Allegato (opzionale)
                        </div>
                        <div>
                            <Label className="text-xs">Allega file (PDF, ricevuta, ecc.)</Label>
                            <Input
                                type="file" accept=".pdf,.jpg,.jpeg,.png,.doc,.docx"
                                data-testid="bulk-file"
                                onChange={(e) => setFile(e.target.files?.[0] || null)}
                            />
                            {file && <div className="text-xs text-slate-500 mt-1 truncate">{file.name} · {(file.size / 1024).toFixed(0)} KB</div>}
                        </div>
                        {(emailContraenti || emailOperatori) && (
                            <div>
                                <Label className="text-xs">Testo aggiuntivo email (opzionale)</Label>
                                <Input value={noteEmail} onChange={(e) => setNoteEmail(e.target.value)}
                                    placeholder="Verrà inserito nel corpo dell'email" />
                            </div>
                        )}
                    </div>
                    {/* ---- Totale ---- */}
                    <div className="mt-6 border-t border-slate-200 pt-3 flex justify-end items-center gap-3">
                        <span className="text-slate-700 font-medium">Totale:</span>
                        <span
                            className="bg-cyan-50 border border-slate-200 px-3 py-1.5 text-base num font-semibold text-cyan-900"
                            data-testid="bulk-totale"
                        >
                            {fmtEur(totaleLordo)}
                        </span>
                    </div>
                </div>

                <div className="px-6 py-3 border-t border-slate-200 bg-slate-50 flex justify-end gap-2">
                    <Button variant="outline" onClick={onClose}>Chiudi</Button>
                    <Button
                        onClick={submit}
                        className="bg-slate-800 hover:bg-slate-900"
                        data-testid="bulk-confirm"
                    >
                        Conferma
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    );
}


function KpiBar({ label, value, accent = "slate", testid, highlight = false }) {
    const colors = {
        emerald: "border-l-emerald-500",
        sky: "border-l-sky-500",
        amber: "border-l-amber-500",
        violet: "border-l-violet-500",
        indigo: "border-l-indigo-500",
        rose: "border-l-rose-500",
        slate: "border-l-slate-700",
    };
    return (
        <div
            className={`bg-white border border-slate-200 border-l-4 ${colors[accent] || colors.slate} rounded px-3 py-2 ${highlight ? "bg-amber-50" : ""}`}
            data-testid={testid}
        >
            <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
            <div className={`num font-semibold ${highlight ? "text-amber-800" : "text-slate-900"} text-base`}>
                {fmtEur(value || 0)}
            </div>
        </div>
    );
}

