import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
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
import DialogIncassoCopertura from "@/components/DialogIncassoCopertura";
import {
    Search, Filter, X, Printer, FileSpreadsheet, FileText, Wallet, Shield,
    ChevronDown, ChevronUp,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

const PRESETS = [
    { key: "tutti", label: "Tutti" },
    { key: "sospesi", label: "Sospesi (da incassare)" },
    { key: "scad15", label: "In scadenza 15gg" },
    { key: "scad_oltre15", label: "Oltre 15gg" },
    { key: "scadute_oggi", label: "Scadute oggi" },
    { key: "scad_5g", label: "Scadute da 5gg" },
    { key: "scad_10g", label: "Scadute da 10gg" },
    { key: "scad_14g", label: "Scadute da 14gg" },
    { key: "coperti", label: "Coperti non pagati" },
];

const presetParams = (key) => {
    switch (key) {
        case "sospesi": return { stato: "da_incassare" };
        case "scad15": return { in_scadenza_giorni: 15 };
        case "scad_oltre15": return { scadenza_oltre_giorni: 15 };
        case "scadute_oggi": return { scadute_oggi: true };
        case "scad_5g": return { scadute_da_min: 5 };
        case "scad_10g": return { scadute_da_min: 10 };
        case "scad_14g": return { scadute_da_min: 14 };
        case "coperti": return { coperti_non_pagati: true };
        default: return {};
    }
};

export default function Titoli() {
    const { user } = useAuth();
    const [list, setList] = useState(null);
    const [compagnie, setCompagnie] = useState([]);
    const [rami, setRami] = useState([]);
    const [conti, setConti] = useState([]);
    const [utenti, setUtenti] = useState([]);
    const [editing, setEditing] = useState(null);
    const [showFilters, setShowFilters] = useState(false);
    const [pageSize, setPageSize] = useState(50);

    const [filters, setFilters] = useState({
        preset: "sospesi", q: "",
        stato: "all", compagnia_id: "all", ramo: "all", prodotto: "",
        collaboratore_id: "all", mezzo_pagamento: "", conto_cassa_id: "all",
        dal: "", al: "",
    });
    const setF = (k, v) => setFilters((p) => ({ ...p, [k]: v }));

    const [selected, setSelected] = useState(new Set());
    const [bulkOpen, setBulkOpen] = useState(null); // "incassa" | "copertura"
    const [paying, setPaying] = useState(null);     // titolo singolo da incassare

    const canEdit = ["admin", "collaboratore", "dipendente"].includes(user?.role);
    const canDelete = ["admin", "collaboratore"].includes(user?.role);

    const buildParams = () => {
        const p = { ...presetParams(filters.preset) };
        if (filters.q) p.q = filters.q;
        if (filters.stato !== "all" && filters.preset === "tutti") p.stato = filters.stato;
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

    useEffect(() => { load(); /* eslint-disable-next-line */ }, [filters]);
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

    const displayed = useMemo(() => (list || []).slice(0, pageSize), [list, pageSize]);

    // totali calcolati sui dati visualizzati
    const totali = useMemo(() => {
        const src = list || [];
        const t_lordo = src.reduce((s, t) => s + (t.importo_lordo || 0), 0);
        const t_provv = src.reduce((s, t) => s + (t.provvigioni || 0), 0);
        const da_pagare = src.filter((t) => t.stato !== "incassato").reduce((s, t) => s + (t.importo_lordo || 0), 0);
        return { t_lordo, t_provv, da_pagare };
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
        <div data-testid="titoli-page">
            <PageHeader
                title="Titoli"
                subtitle="Sospesi · in scadenza · coperti non pagati · esportazioni e stampa"
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
                    <span className="text-xs text-slate-600 hidden md:block">Visualizza</span>
                    <Select value={String(pageSize)} onValueChange={(v) => setPageSize(parseInt(v))}>
                        <SelectTrigger className="w-20"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            {[25, 50, 100, 250, 500].map((n) => <SelectItem key={n} value={String(n)}>{n}</SelectItem>)}
                        </SelectContent>
                    </Select>
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
                    <table className="tbl w-full min-w-[1200px]">
                        <thead>
                            <tr>
                                <th className="w-10 text-center">
                                    <input
                                        type="checkbox"
                                        data-testid="select-all-checkbox"
                                        checked={displayed.length > 0 && selected.size === displayed.length}
                                        onChange={toggleAll}
                                    />
                                </th>
                                <th>Contratto / Targa</th>
                                <th>Contraente</th>
                                <th>Compagnia</th>
                                <th>Collaboratore</th>
                                <th className="text-right">Premio €</th>
                                <th className="text-right">Provv.</th>
                                <th>Scadenza</th>
                                <th>Copertura</th>
                                <th>Stato</th>
                                <th className="text-right">Da pagare</th>
                                <th className="w-12 text-center">Allegati</th>
                                <th className="w-24 text-center">Azione</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody>
                            {displayed.map((t) => {
                                const daPagare = t.stato === "incassato" ? 0 : (t.importo_lordo || 0);
                                return (
                                    <tr key={t.id} data-testid={`titolo-row-${t.id}`} className={selected.has(t.id) ? "bg-sky-50" : ""}>
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
                                            {t.targa && (
                                                <div className="text-xs text-sky-700 font-medium num mt-0.5">{t.targa}</div>
                                            )}
                                        </td>
                                        <td className="text-xs">{t.contraente_nome || "-"}</td>
                                        <td className="text-xs text-slate-700">{t.compagnia_nome || "-"}</td>
                                        <td className="text-xs text-slate-700">{t.collaboratore_nome || "-"}</td>
                                        <td className="num text-right font-medium" data-testid={`titolo-premio-${t.id}`}>{fmtEur(t.importo_lordo)}</td>
                                        <td className="num text-right text-slate-600">{fmtEur(t.provvigioni)}</td>
                                        <td className="num text-xs">{fmtDate(t.scadenza)}</td>
                                        <td className="num text-xs text-emerald-700">{t.data_copertura ? fmtDate(t.data_copertura) : "—"}</td>
                                        <td><StatusBadge stato={t.stato} /></td>
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
                {list && list.length > pageSize && (
                    <div className="px-4 py-2 text-xs text-slate-500 text-center border-t border-slate-100">
                        Visualizzati {pageSize} di {list.length} risultati - aumenta &quot;Visualizza&quot; per vederne di più
                    </div>
                )}
            </div>

            {/* Footer azione bulk + totali */}
            <div className="sticky bottom-0 mt-4 bg-slate-900 text-slate-100 rounded-t-md px-4 py-3 flex flex-wrap items-center gap-3" data-testid="bulk-footer">
                <button onClick={() => setSelected(new Set(displayed.map((t) => t.id)))} className="px-3 py-1.5 bg-amber-500 hover:bg-amber-600 text-slate-900 rounded text-xs font-semibold" data-testid="select-all-btn">
                    SELEZIONA TUTTI
                </button>
                <button onClick={() => setSelected(new Set())} className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 rounded text-xs font-semibold">
                    DESELEZIONA TUTTI
                </button>
                <span className="text-xs text-slate-400">
                    {selected.size > 0 ? `${selected.size} selezionati` : ""}
                </span>
                <button
                    disabled={selected.size === 0}
                    onClick={() => setBulkOpen("incassa")}
                    data-testid="bulk-incassa-btn"
                    className="px-4 py-1.5 bg-emerald-500 hover:bg-emerald-600 disabled:bg-slate-700 disabled:text-slate-500 text-slate-900 disabled:cursor-not-allowed rounded text-xs font-semibold inline-flex items-center gap-1"
                >
                    <Wallet size={14} /> INCASSA
                </button>
                <button
                    disabled={selected.size === 0}
                    onClick={() => setBulkOpen("copertura")}
                    data-testid="bulk-copertura-btn"
                    className="px-4 py-1.5 bg-sky-500 hover:bg-sky-600 disabled:bg-slate-700 disabled:text-slate-500 text-white disabled:cursor-not-allowed rounded text-xs font-semibold inline-flex items-center gap-1"
                >
                    <Shield size={14} /> COPERTURA
                </button>
                <div className="ml-auto flex gap-6">
                    <div className="text-right">
                        <div className="text-[10px] uppercase tracking-widest text-slate-400">Rata totale</div>
                        <div className="text-base font-semibold num">{fmtEur(totali.t_lordo)}</div>
                    </div>
                    <div className="text-right">
                        <div className="text-[10px] uppercase tracking-widest text-slate-400">Provvigioni</div>
                        <div className="text-base font-semibold num">{fmtEur(totali.t_provv)}</div>
                    </div>
                    <div className="text-right">
                        <div className="text-[10px] uppercase tracking-widest text-amber-300">Da pagare</div>
                        <div className="text-base font-semibold num text-amber-300">{fmtEur(totali.da_pagare)}</div>
                    </div>
                </div>
            </div>

            {bulkOpen && (
                <BulkActionDialog
                    action={bulkOpen}
                    ids={Array.from(selected)}
                    conti={conti}
                    onClose={() => { setBulkOpen(null); load(); }}
                />
            )}

            {editing && (
                <EditTitoloDialog titolo={editing} conti={conti} onClose={() => { setEditing(null); load(); }} />
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

function BulkActionDialog({ action, ids, conti, onClose }) {
    const today = new Date().toISOString().slice(0, 10);
    const [data_incasso, setDataIncasso] = useState(today);
    const [mezzo, setMezzo] = useState("bonifico");
    const [conto_id, setContoId] = useState("");
    const [coperto, setCoperto] = useState(today);  // data copertura di default = OGGI
    const [file, setFile] = useState(null);
    const [inviaCliente, setInviaCliente] = useState(false);
    const [inviaCollab, setInviaCollab] = useState(false);
    const [noteEmail, setNoteEmail] = useState("");

    const submit = async () => {
        try {
            // se c'è file o invio email, usa endpoint multipart con allegato
            if (file || inviaCliente || inviaCollab) {
                const fd = new FormData();
                if (file) fd.append("file", file);
                const qs = new URLSearchParams({
                    action,
                    ids_json: JSON.stringify(ids),
                    invia_cliente: String(inviaCliente),
                    invia_collaboratore: String(inviaCollab),
                });
                if (action === "incassa") {
                    qs.append("data_incasso", data_incasso);
                    qs.append("mezzo_pagamento", mezzo);
                    if (conto_id) qs.append("conto_cassa_id", conto_id);
                } else {
                    qs.append("data_copertura", coperto);
                }
                if (noteEmail) qs.append("note_email", noteEmail);
                const r = await api.post(`/titoli/bulk-azione-allegato?${qs}`, fd, {
                    headers: { "Content-Type": "multipart/form-data" },
                });
                const parts = [];
                if (action === "incassa") parts.push(`${r.data.incassati} incassati per ${fmtEur(r.data.totale)}`);
                else parts.push(`Copertura su ${r.data.aggiornati} titoli`);
                if (r.data.allegato_nome) parts.push(`allegato "${r.data.allegato_nome}" salvato`);
                if (r.data.email_create) parts.push(`${r.data.email_create} email in coda`);
                toast.success(parts.join(" · "));
            } else if (action === "incassa") {
                const r = await api.post("/titoli/bulk-incassa", {
                    ids, data_incasso, mezzo_pagamento: mezzo, conto_cassa_id: conto_id || null,
                });
                toast.success(`${r.data.incassati} titoli incassati per ${fmtEur(r.data.totale)}`);
            } else {
                const r = await api.post("/titoli/bulk-copertura", { ids, data_copertura: coperto });
                toast.success(`Copertura impostata su ${r.data.aggiornati} titoli`);
            }
            onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-md">
                <DialogHeader>
                    <DialogTitle>
                        {action === "incassa" ? `Incassa ${ids.length} titoli` : `Imposta copertura su ${ids.length} titoli`}
                    </DialogTitle>
                </DialogHeader>
                {action === "incassa" ? (
                    <div className="space-y-3 py-2">
                        <div><Label>Data incasso</Label><Input type="date" value={data_incasso} onChange={(e) => setDataIncasso(e.target.value)} data-testid="bulk-data" /></div>
                        <div><Label>Mezzo pagamento</Label><Input value={mezzo} onChange={(e) => setMezzo(e.target.value)} /></div>
                        <div>
                            <Label>Conto / Banca</Label>
                            <Select value={conto_id} onValueChange={setContoId}>
                                <SelectTrigger data-testid="bulk-conto"><SelectValue placeholder="-" /></SelectTrigger>
                                <SelectContent>
                                    {conti.map((c) => <SelectItem key={c.id} value={c.id}>{c.nome}</SelectItem>)}
                                </SelectContent>
                            </Select>
                        </div>
                    </div>
                ) : (
                    <div className="space-y-3 py-2">
                        <div className="bg-amber-50 border border-amber-200 rounded-md p-3 text-xs text-amber-900">
                            <strong>Copertura titolo</strong>: l&apos;agenzia anticipa il pagamento al cliente.
                            Il titolo resta &quot;da incassare&quot; finché il cliente non paga.
                            Apparirà nella sezione <strong>Sospesi</strong>.
                        </div>
                        <div>
                            <Label>Data copertura (oggi è il default)</Label>
                            <Input type="date" value={coperto} onChange={(e) => setCoperto(e.target.value)} data-testid="bulk-coperto" />
                        </div>
                    </div>
                )}

                <div className="pt-3 border-t border-slate-200 space-y-3">
                    <div className="text-xs font-semibold uppercase tracking-wider text-slate-600">Allegato e invio email</div>
                    <div>
                        <Label>Allega file (quietanza PDF, ricevuta, ecc.)</Label>
                        <Input
                            type="file" accept=".pdf,.jpg,.jpeg,.png,.doc,.docx"
                            data-testid="bulk-file"
                            onChange={(e) => setFile(e.target.files?.[0] || null)}
                        />
                        {file && <div className="text-xs text-slate-500 mt-1 truncate">{file.name} · {(file.size / 1024).toFixed(0)} KB</div>}
                    </div>
                    <div className="space-y-1.5">
                        <label className="flex items-center gap-2 text-sm cursor-pointer">
                            <input
                                type="checkbox" checked={inviaCliente}
                                onChange={(e) => setInviaCliente(e.target.checked)}
                                data-testid="bulk-invia-cliente"
                            />
                            Invia email ai clienti contraenti
                        </label>
                        <label className="flex items-center gap-2 text-sm cursor-pointer">
                            <input
                                type="checkbox" checked={inviaCollab}
                                onChange={(e) => setInviaCollab(e.target.checked)}
                                data-testid="bulk-invia-collab"
                            />
                            Notifica i collaboratori delle polizze
                        </label>
                    </div>
                    {(inviaCliente || inviaCollab) && (
                        <div>
                            <Label>Testo aggiuntivo email (opzionale)</Label>
                            <Input value={noteEmail} onChange={(e) => setNoteEmail(e.target.value)} placeholder="Verrà inserito nel corpo dell'email" />
                        </div>
                    )}
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Annulla</Button>
                    <Button onClick={submit} data-testid="bulk-confirm" className="bg-sky-700 hover:bg-sky-800">
                        Conferma
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function EditTitoloDialog({ titolo, conti, onClose }) {
    const [f, setF] = useState({ ...titolo });
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
    const save = async () => {
        try {
            await api.put(`/titoli/${titolo.id}`, {
                tipo: f.tipo, effetto: f.effetto, scadenza: f.scadenza, stato: f.stato,
                importo_lordo: parseFloat(f.importo_lordo) || 0,
                importo_netto: parseFloat(f.importo_netto) || 0,
                imposte: parseFloat(f.imposte) || 0,
                provvigioni: parseFloat(f.provvigioni) || 0,
                mezzo_pagamento: f.mezzo_pagamento || null,
                conto_cassa_id: f.conto_cassa_id || null,
                data_incasso: f.data_incasso || null,
                coperto_fino_a: f.coperto_fino_a || null,
            });
            toast.success("Titolo aggiornato"); onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-xl">
                <DialogHeader><DialogTitle>Modifica titolo</DialogTitle></DialogHeader>
                <div className="grid grid-cols-2 gap-3 py-2">
                    <div>
                        <Label>Tipo</Label>
                        <Select value={f.tipo} onValueChange={(v) => set("tipo", v)}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                                {["nuova", "rinnovo", "appendice", "regolazione", "storno"].map((t) =>
                                    <SelectItem key={t} value={t}>{t}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <Label>Stato</Label>
                        <Select value={f.stato} onValueChange={(v) => set("stato", v)}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="da_incassare">Da incassare</SelectItem>
                                <SelectItem value="incassato">Incassato</SelectItem>
                                <SelectItem value="insoluto">Insoluto</SelectItem>
                                <SelectItem value="stornato">Stornato</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div><Label>Effetto</Label><Input type="date" value={f.effetto || ""} onChange={(e) => set("effetto", e.target.value)} /></div>
                    <div><Label>Scadenza</Label><Input type="date" value={f.scadenza || ""} onChange={(e) => set("scadenza", e.target.value)} /></div>
                    <div><Label>Lordo €</Label><Input type="number" step="0.01" value={f.importo_lordo || 0} onChange={(e) => set("importo_lordo", e.target.value)} /></div>
                    <div><Label>Netto €</Label><Input type="number" step="0.01" value={f.importo_netto || 0} onChange={(e) => set("importo_netto", e.target.value)} /></div>
                    <div><Label>Imposte €</Label><Input type="number" step="0.01" value={f.imposte || 0} onChange={(e) => set("imposte", e.target.value)} /></div>
                    <div><Label>Provvigioni €</Label><Input type="number" step="0.01" value={f.provvigioni || 0} onChange={(e) => set("provvigioni", e.target.value)} /></div>
                    <div><Label>Data incasso</Label><Input type="date" value={f.data_incasso || ""} onChange={(e) => set("data_incasso", e.target.value)} /></div>
                    <div><Label>Copertura fino al</Label><Input type="date" value={f.coperto_fino_a || ""} onChange={(e) => set("coperto_fino_a", e.target.value)} /></div>
                    <div>
                        <Label>Conto / Banca</Label>
                        <Select value={f.conto_cassa_id || ""} onValueChange={(v) => set("conto_cassa_id", v)}>
                            <SelectTrigger><SelectValue placeholder="-" /></SelectTrigger>
                            <SelectContent>
                                {conti.map((c) => <SelectItem key={c.id} value={c.id}>{c.nome}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="col-span-2">
                        <Label>Mezzo pagamento</Label>
                        <Input value={f.mezzo_pagamento || ""} onChange={(e) => set("mezzo_pagamento", e.target.value)} />
                    </div>
                </div>
                <DialogFooter>
                    <Button onClick={save} data-testid="titolo-save-edit" className="bg-sky-700 hover:bg-sky-800">Salva</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
