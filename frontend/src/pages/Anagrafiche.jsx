import { useEffect, useState, useRef, useCallback } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, fmtDate, fmtEur } from "@/lib/api";
import { formatPhone, telHref } from "@/lib/phone";
import { PageHeader, Empty, Loading } from "@/components/Shared";
import AnagraficaAvatar from "@/components/AnagraficaAvatar";
import SortHeader from "@/components/SortHeader";
import { useTableColumns } from "@/components/ColumnManager";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter, DialogDescription,
} from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, Search, ScanLine, Calculator, MapPin, X, Mail, Phone, Contact, ChevronRight, Users, Home, Church, Briefcase, Settings, Trash2, Star, Heart, Flag, Award, Target, Bookmark, Tag as TagIcon, Zap, Upload, Send, GitMerge, Loader2 } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import AddressAutocomplete from "@/components/AddressAutocomplete";
import ImportExcelDialog from "@/components/ImportExcelDialog";

// Colori per categoria
const CAT_BADGE = {
    con_polizze: { dot: "bg-sky-500", label: "Con polizze", text: "text-sky-700" },
    senza_polizze: { dot: "bg-red-500", label: "Senza polizze", text: "text-red-700" },
    condominio: { dot: "bg-emerald-500", label: "Condominio", text: "text-emerald-700" },
};

// Colonne tabella Anagrafiche — selezionabili/riordinabili per utente (render(a, ctx))
const ANAG_COLS = [
    {
        key: "expand", label: "Espandi network", locked: true, thClass: "w-7 py-1.5", tdClass: "py-1.5 pl-2",
        render: (a, ctx) => (
            <button onClick={ctx.onToggle}
                    className="text-slate-400 hover:text-sky-600 transition-colors"
                    data-testid={`anag-expand-${a.id}`} aria-label="Espandi network">
                <ChevronRight size={15} className={`transform transition-transform ${ctx.isOpen ? "rotate-90" : ""}`} />
            </button>
        ),
    },
    {
        key: "cliente", label: "Cliente", sort: "ragione_sociale", thClass: "text-left py-1.5 pr-3 min-w-[260px]", tdClass: "py-1.5 pr-3",
        render: (a, ctx) => (
            <div className="flex items-center gap-2">
                <AnagraficaAvatar ana={a} size="sm" />
                <Link to={`/anagrafiche/${a.id}`}
                      className={`hover:underline font-semibold text-[13px] tracking-wide truncate max-w-[340px] ${ctx.cat.text}`}>
                    {a.ragione_sociale}
                </Link>
                {a.tipo === "persona_giuridica" && <span className="text-[9px] text-slate-400 shrink-0">PG</span>}
                <ComplianceBadges ana={a} />
            </div>
        ),
    },
    {
        key: "email", label: "E-mail", sort: "email", thClass: "text-left py-1.5 pr-3", tdClass: "py-1.5 pr-3 text-xs",
        render: (a) => a.email
            ? <a href={`mailto:${a.email}`} onClick={(e) => e.stopPropagation()}
                 className="inline-flex items-center gap-1 text-sky-700 hover:underline max-w-[210px]"
                 data-testid={`anag-email-link-${a.id}`}><Mail size={12} className="text-slate-400 shrink-0" /><span className="truncate">{a.email}</span></a>
            : <span className="text-slate-300">—</span>,
    },
    {
        key: "telefono", label: "Telefono", sort: "telefono", thClass: "text-left py-1.5 pr-3 w-36", tdClass: "py-1.5 pr-3 text-xs whitespace-nowrap",
        render: (a) => (a.cellulare || a.telefono)
            ? <a href={`tel:${telHref(a.cellulare || a.telefono)}`} onClick={(e) => e.stopPropagation()}
                 className="inline-flex items-center gap-1 text-sky-700 hover:underline"
                 data-testid={`anag-phone-link-${a.id}`}><Phone size={12} className="text-slate-400" />{formatPhone(a.cellulare || a.telefono)}</a>
            : <span className="text-slate-300">—</span>,
    },
    {
        key: "indirizzo", label: "Indirizzo", sort: "indirizzo", thClass: "text-left py-1.5 pr-3", tdClass: "py-1.5 pr-3 text-xs",
        render: (a) => a.indirizzo
            ? <span className="text-slate-600 truncate block max-w-[170px]" title={a.indirizzo}>{a.indirizzo}</span>
            : <span className="text-slate-300">—</span>,
    },
    {
        key: "comune", label: "Comune", sort: "comune", thClass: "text-left py-1.5 pr-3 w-28", tdClass: "py-1.5 pr-3 text-xs",
        render: (a) => a.comune
            ? <span className="text-slate-600 truncate block max-w-[110px]" title={`${a.comune}${a.provincia ? ` (${a.provincia})` : ""}`}>
                {a.comune}{a.provincia ? <span className="text-slate-400"> ({a.provincia})</span> : ""}
              </span>
            : <span className="text-slate-300">—</span>,
    },
    {
        key: "polizze", label: "Polizze", sort: "num_polizze", thClass: "text-center py-1.5 pr-2 w-14 text-emerald-700",
        tdClass: "py-1.5 pr-2 text-center text-emerald-700 font-semibold num w-14",
        render: (a) => a.polizze_attive_count || 0,
    },
    {
        key: "collaboratore", label: "Collaboratore", sort: "collaboratore_nome", thClass: "text-left py-1.5 pr-3 w-32", tdClass: "py-1.5 pr-3 text-xs",
        render: (a) => a.collaboratore_nome
            ? <span className="text-slate-700 truncate block max-w-[130px]" title={a.collaboratore_nome}>{a.collaboratore_nome}</span>
            : <span className="text-slate-300">—</span>,
    },
    {
        key: "premio_totale", label: "Premio tot.", sort: "premio_totale", thClass: "text-right py-1.5 pr-2 w-24",
        tdClass: "py-1.5 pr-2 text-right font-bold num text-slate-900 text-[13px] w-24 whitespace-nowrap",
        render: (a, ctx) => ctx.net ? fmtEur(ctx.net.root.premio_totale || 0) : <span className="text-slate-300">—</span>,
    },
    {
        key: "provvigioni", label: "Provvigioni", sort: "provvigioni", thClass: "text-right py-1.5 pr-2 w-24 text-emerald-700",
        tdClass: "py-1.5 pr-2 text-right font-semibold num text-emerald-700 w-24 whitespace-nowrap",
        render: (a, ctx) => ctx.net ? fmtEur(ctx.net.root.provvigioni_totale || 0) : <span className="text-slate-300">—</span>,
    },
    {
        key: "tag", label: "Tag", thClass: "text-left py-1.5 pr-2 w-24", tdClass: "py-1.5 pr-2 w-24",
        render: (a, ctx) => (
            <div className="flex items-center gap-1 overflow-hidden whitespace-nowrap">
                {(a.tags || []).slice(0, 2).map((t) => (
                    <button key={t} onClick={() => ctx.onTagClick(t)}
                            title={t}
                            className="text-[8px] uppercase px-1 py-0.5 rounded bg-slate-100 text-slate-600 hover:bg-sky-100 hover:text-sky-700 truncate max-w-[68px]">
                        {t}
                    </button>
                ))}
                {(a.tags || []).length > 2 && (
                    <span className="text-[9px] text-slate-400 shrink-0" title={(a.tags || []).join(", ")}>
                        +{a.tags.length - 2}
                    </span>
                )}
            </div>
        ),
    },
];

const ANAG_DELETE_COL = {
    key: "elimina", label: "Elimina", locked: true, thClass: "w-8 py-1.5", tdClass: "py-1.5 pr-2 text-right",
    render: (a, ctx) => (
        <button onClick={(e) => { e.stopPropagation(); ctx.onDelete(a); }}
                className="text-slate-300 hover:text-rose-600 p-1 rounded transition-colors"
                data-testid={`anag-delete-${a.id}`} title="Elimina anagrafica" aria-label="Elimina anagrafica">
            <Trash2 size={14} />
        </button>
    ),
};

export default function Anagrafiche() {
    const { user } = useAuth();
    const [searchParams, setSearchParams] = useSearchParams();
    const [list, setList] = useState(null);
    const [total, setTotal] = useState(0);
    const [pages, setPages] = useState(1);
    const [page, setPage] = useState(1);
    const [pageSize] = useState(50);
    const [catCounts, setCatCounts] = useState({ tutte: 0, con_polizze: 0, senza_polizze: 0, condominio: 0 });
    const [allTags, setAllTags] = useState([]);
    const [srt, setSrt] = useState({ key: "ragione_sociale", dir: "asc" });
    const [q, setQ] = useState("");
    const [qDeb, setQDeb] = useState("");
    const [open, setOpen] = useState(false);
    const [tagFilter, setTagFilter] = useState(null);
    const [collabFilter, setCollabFilter] = useState("");
    const [profFilter, setProfFilter] = useState("");
    const [comuneFilter, setComuneFilter] = useState("");
    const [conFigliFilter, setConFigliFilter] = useState(false);
    const [etaMinFilter, setEtaMinFilter] = useState("");
    const [etaMaxFilter, setEtaMaxFilter] = useState("");
    const [collaboratoriList, setCollaboratoriList] = useState([]);
    const [catFilter, setCatFilter] = useState("con_polizze");
    const [stats, setStats] = useState(null);
    const [expanded, setExpanded] = useState({});
    const [networks, setNetworks] = useState({});
    const [kpiDialogOpen, setKpiDialogOpen] = useState(false);
    const [deleteTarget, setDeleteTarget] = useState(null); // anagrafica da eliminare
    const [importOpen, setImportOpen] = useState(false);
    const [credMassivoOpen, setCredMassivoOpen] = useState(false);
    // filtri da URL (dashboard task)
    const compleannoFilter = searchParams.get("compleanno"); // "oggi" | "settimana" | "mese"
    const docFilter = searchParams.get("doc"); // "scaduti" | "in_scadenza"
    const canCreate = ["admin", "collaboratore", "dipendente"].includes(user?.role);
    const canDelete = user?.role === "admin";

    // debounce: la lista viene ricaricata max 1 volta ogni 300ms mentre si digita
    useEffect(() => {
        const t = setTimeout(() => setQDeb(q), 300);
        return () => clearTimeout(t);
    }, [q]);

    const load = useCallback(() => {
        const params = {
            paged: true, page, page_size: pageSize,
            q: qDeb || undefined, tag: tagFilter || undefined,
            collaboratore_id: collabFilter || undefined,
            professione: profFilter || undefined,
            comune: comuneFilter || undefined,
            con_figli: conFigliFilter || undefined,
            eta_min: etaMinFilter || undefined,
            eta_max: etaMaxFilter || undefined,
            categoria: catFilter !== "all" ? catFilter : undefined,
            compleanno: compleannoFilter || undefined,
            doc: docFilter || undefined,
            sort: srt.key, dir: srt.dir,
        };
        api.get("/anagrafiche", { params }).then((r) => {
            setList(r.data.items || []);
            setTotal(r.data.total || 0);
            setPages(r.data.pages || 1);
            if (r.data.conteggi) setCatCounts(r.data.conteggi);
        });
    }, [qDeb, tagFilter, catFilter, compleannoFilter, docFilter, page, pageSize, srt, collabFilter, profFilter, comuneFilter, conFigliFilter, etaMinFilter, etaMaxFilter]);

    useEffect(() => { load(); }, [load]);
    // reset alla pagina 1 quando cambiano ricerca o filtri
    useEffect(() => { setPage(1); /* eslint-disable-next-line */ }, [qDeb, tagFilter, catFilter, compleannoFilter, docFilter, collabFilter, profFilter, comuneFilter, conFigliFilter, etaMinFilter, etaMaxFilter]);
    useEffect(() => { api.get("/collaboratori").then((r) => setCollaboratoriList(r.data || [])).catch(() => {}); }, []);
    useEffect(() => { api.get("/anagrafiche/stats").then((r) => setStats(r.data)).catch(() => {}); }, []);
    useEffect(() => { api.get("/anagrafiche/tags").then((r) => setAllTags(r.data || [])).catch(() => {}); }, []);

    const toggleExpand = async (aid) => {
        const next = !expanded[aid];
        setExpanded((p) => ({ ...p, [aid]: next }));
        if (next && !networks[aid]) {
            try {
                const r = await api.get(`/anagrafiche/${aid}/network`);
                setNetworks((p) => ({ ...p, [aid]: r.data }));
            } catch { /* ignore */ }
        }
    };

    // Tag univoci per chip filtri (dal server: tutti i tag esistenti)
    const tagsUnivoci = allTags;

    // La lista arriva già filtrata e ordinata dal server (paginata)
    const sortedFiltered = list || [];
    const sortKey = srt.key;
    const dir = srt.dir;
    const toggle = (k) => setSrt((s) => ({ key: k, dir: s.key === k && s.dir === "asc" ? "desc" : "asc" }));
    const { cols: anagCols, picker: colsPicker } = useTableColumns(
        "anagrafiche", canDelete ? [...ANAG_COLS, ANAG_DELETE_COL] : ANAG_COLS,
    );
    const [dedupOpen, setDedupOpen] = useState(false);

    const clearTaskFilter = () => {
        const p = new URLSearchParams(searchParams);
        p.delete("compleanno");
        p.delete("doc");
        setSearchParams(p);
    };

    const counts = { con: catCounts.con_polizze, senza: catCounts.senza_polizze, cond: catCounts.condominio };

    return (
        <div data-testid="anagrafiche-page">
            <PageHeader
                title="Anagrafiche clienti"
                subtitle="Persone fisiche e giuridiche presenti a portafoglio"
                actions={
                    canCreate && (
                        <div className="flex items-center gap-2">
                            <Button variant="outline"
                                    onClick={() => setDedupOpen(true)}
                                    data-testid="anagrafica-unisci-doppioni-btn"
                                    className="border-amber-300 text-amber-700 hover:bg-amber-50">
                                <GitMerge size={16} className="mr-1" /> Unisci doppioni
                            </Button>
                            <Button variant="outline"
                                    onClick={() => setCredMassivoOpen(true)}
                                    data-testid="anagrafica-invia-credenziali-massivo"
                                    className="border-violet-300 text-violet-700 hover:bg-violet-50">
                                <Send size={16} className="mr-1" /> Invia credenziali Portale
                            </Button>
                            <Button variant="outline"
                                    onClick={() => setImportOpen(true)}
                                    data-testid="anagrafica-import-button"
                                    className="border-emerald-300 text-emerald-700 hover:bg-emerald-50">
                                <Upload size={16} className="mr-1" /> Importa Excel/CSV
                            </Button>
                            <Dialog open={open} onOpenChange={setOpen}>
                                <DialogTrigger asChild>
                                    <Button data-testid="anagrafica-new-button" className="bg-sky-700 hover:bg-sky-800">
                                        <Plus size={16} className="mr-1" /> Nuova anagrafica
                                    </Button>
                                </DialogTrigger>
                                <NuovaAnagraficaDialog onClose={() => { setOpen(false); load(); }} />
                            </Dialog>
                        </div>
                    )
                }
            />

            {/* 4 KPI per categoria + KPI custom */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-2">
                <KpiCard
                    icon={<Users size={18} />} color="sky"
                    label="Clienti privati" testid="kpi-privati"
                    n={stats?.privati?.n ?? "—"}
                    premio={stats?.privati?.premio_totale}
                />
                <KpiCard
                    icon={<Briefcase size={18} />} color="emerald"
                    label="Aziende" testid="kpi-aziende"
                    n={stats?.aziende?.n ?? "—"}
                    premio={stats?.aziende?.premio_totale}
                />
                <KpiCard
                    icon={<Home size={18} />} color="amber"
                    label="Condomini" testid="kpi-condomini"
                    n={stats?.condomini?.n ?? "—"}
                    premio={stats?.condomini?.premio_totale}
                />
                <KpiCard
                    icon={<Church size={18} />} color="violet"
                    label="Parrocchie" testid="kpi-parrocchie"
                    n={stats?.parrocchie?.n ?? "—"}
                    premio={stats?.parrocchie?.premio_totale}
                />
                {(stats?.custom || []).map((k) => (
                    <KpiCard
                        key={k.id}
                        icon={<CustomKpiIcon name={k.icon} />}
                        color={k.color || "sky"}
                        label={k.label} testid={`kpi-custom-${k.id}`}
                        n={k.n}
                        premio={k.premio_totale}
                        onClick={() => setTagFilter(k.tag)}
                    />
                ))}
            </div>
            {canCreate && (
                <div className="flex justify-end mb-4">
                    <Button
                        variant="outline" size="sm"
                        data-testid="btn-personalizza-kpi"
                        onClick={() => setKpiDialogOpen(true)}
                        className="text-xs"
                    >
                        <Settings size={14} className="mr-1" /> Personalizza KPI
                    </Button>
                </div>
            )}

            <div className="flex items-center gap-2 mb-3">
                <div className="relative flex-1 max-w-md">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                    <Input
                        data-testid="anagrafiche-search"
                        placeholder="Cerca per nome, codice fiscale, email..."
                        value={q}
                        onChange={(e) => setQ(e.target.value)}
                        className="pl-9"
                    />
                </div>
                <span className="text-sm text-slate-500 num">
                    {list ? `${total} risultati` : ""}
                </span>
            </div>

            {(compleannoFilter || docFilter) && (
                <div
                    className="flex items-center justify-between gap-3 mb-3 px-4 py-2 rounded-md border border-amber-300 bg-amber-50"
                    data-testid="anag-active-task-filter"
                >
                    <div className="flex items-center gap-2 text-sm text-amber-900">
                        <span className="font-semibold">Filtro attivo:</span>
                        {compleannoFilter === "oggi" && <span>Compleanni di oggi</span>}
                        {compleannoFilter === "settimana" && <span>Compleanni nei prossimi 7 giorni</span>}
                        {compleannoFilter === "mese" && <span>Compleanni nel mese in corso</span>}
                        {docFilter === "scaduti" && <span>Documenti di riconoscimento scaduti</span>}
                        {docFilter === "in_scadenza" && <span>Documenti in scadenza (30gg)</span>}
                        <span className="text-amber-700 num">— {total} risultati</span>
                    </div>
                    <Button size="sm" variant="ghost" onClick={clearTaskFilter} data-testid="anag-clear-task-filter">
                        <X size={14} className="mr-1" /> Rimuovi filtro
                    </Button>
                </div>
            )}

            {/* Chips filtri categoria */}
            <div className="flex flex-wrap items-center gap-2 mb-3">
                <CatChip active={catFilter === "all"} onClick={() => setCatFilter("all")} dot="bg-slate-300" label={`Tutte (${catCounts.tutte})`} />
                <CatChip active={catFilter === "con_polizze"} onClick={() => setCatFilter("con_polizze")} dot="bg-sky-500" label={`Con polizze (${counts.con})`} />
                <CatChip active={catFilter === "senza_polizze"} onClick={() => setCatFilter("senza_polizze")} dot="bg-red-500" label={`Senza polizze (${counts.senza})`} />
                <CatChip active={catFilter === "condominio"} onClick={() => setCatFilter("condominio")} dot="bg-emerald-500" label={`Condomini (${counts.cond})`} />
                {tagFilter && (
                    <button onClick={() => setTagFilter(null)} className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full bg-amber-100 text-amber-800 hover:bg-amber-200" data-testid="anag-tag-active">
                        Tag: {tagFilter} <X size={10} />
                    </button>
                )}
                <div className="ml-auto">
                    <Select value={collabFilter || "all"} onValueChange={(v) => setCollabFilter(v === "all" ? "" : v)}>
                        <SelectTrigger className="w-56 h-9" data-testid="anag-filter-collaboratore">
                            <SelectValue placeholder="Collaboratore" />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">Tutti i collaboratori</SelectItem>
                            {collaboratoriList.map((c) => (
                                <SelectItem key={c.id} value={c.id}>{c.name || c.email}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
            </div>

            {/* Filtri demografici avanzati */}
            <div className="flex flex-wrap items-center gap-2 mb-3" data-testid="anag-filtri-demografici">
                <Input value={profFilter} onChange={(e) => setProfFilter(e.target.value)}
                    placeholder="Professione" className="h-9 w-40" data-testid="anag-filter-professione" />
                <Input value={comuneFilter} onChange={(e) => setComuneFilter(e.target.value)}
                    placeholder="Comune" className="h-9 w-40" data-testid="anag-filter-comune" />
                <Input type="number" value={etaMinFilter} onChange={(e) => setEtaMinFilter(e.target.value)}
                    placeholder="Età min" className="h-9 w-24" data-testid="anag-filter-eta-min" />
                <Input type="number" value={etaMaxFilter} onChange={(e) => setEtaMaxFilter(e.target.value)}
                    placeholder="Età max" className="h-9 w-24" data-testid="anag-filter-eta-max" />
                <button type="button" onClick={() => setConFigliFilter((v) => !v)}
                    className={`inline-flex items-center gap-1 text-xs px-3 h-9 rounded-md border transition-colors ${conFigliFilter ? "bg-sky-700 text-white border-sky-700" : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"}`}
                    data-testid="anag-filter-con-figli">
                    Genitori con figli
                </button>
                {(profFilter || comuneFilter || etaMinFilter || etaMaxFilter || conFigliFilter) && (
                    <button type="button" onClick={() => { setProfFilter(""); setComuneFilter(""); setEtaMinFilter(""); setEtaMaxFilter(""); setConFigliFilter(false); }}
                        className="text-xs text-slate-400 hover:text-rose-600 underline" data-testid="anag-filter-reset">
                        Azzera filtri
                    </button>
                )}
            </div>

            {/* Chips tag univoci */}
            {tagsUnivoci.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5 mb-3">
                    <span className="text-xs text-slate-500 mr-1">Tag:</span>
                    {tagsUnivoci.slice(0, 30).map((t) => (
                        <button
                            key={t}
                            onClick={() => setTagFilter(tagFilter === t ? null : t)}
                            data-testid={`anag-tag-chip-${t}`}
                            className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full border ${
                                tagFilter === t
                                    ? "bg-sky-600 text-white border-sky-600"
                                    : "bg-white text-slate-600 border-slate-300 hover:bg-slate-100"
                            }`}
                        >
                            {t}
                        </button>
                    ))}
                </div>
            )}

            <div className="flex justify-end mb-2">{colsPicker}</div>
            <div className="tbl-scroll bg-white"
                 style={{ "--c1-w": "32px", "--c2-w": "340px", "--c3-w": "220px", "--c4-w": "150px", "--c5-w": "180px" }}>
                {list === null ? <Loading /> : sortedFiltered.length === 0 ? <Empty /> : (
                    <table className="freeze-5 w-full min-w-[1500px] text-sm">
                        <thead>
                            <tr className="text-[10px] uppercase tracking-widest text-slate-500 border-b border-slate-200">
                                {anagCols.map((c) => (
                                    <th key={c.key} className={c.thClass}>
                                        {c.sort
                                            ? <SortHeader k={c.sort} sortKey={sortKey} dir={dir} toggle={toggle}>{c.label}</SortHeader>
                                            : (c.key === "expand" || c.key === "elimina" ? "" : c.label)}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {sortedFiltered.map((a) => {
                                const cat = CAT_BADGE[a.categoria_ui] || CAT_BADGE.senza_polizze;
                                const isOpen = !!expanded[a.id];
                                const net = networks[a.id];
                                return (
                                    <RigaAnagrafica
                                        key={a.id}
                                        a={a}
                                        cols={anagCols}
                                        cat={cat}
                                        isOpen={isOpen}
                                        net={net}
                                        onToggle={() => toggleExpand(a.id)}
                                        onTagClick={(t) => setTagFilter(t)}
                                        canDelete={canDelete}
                                        onDelete={setDeleteTarget}
                                    />
                                );
                            })}
                        </tbody>
                    </table>
                )}
            </div>

            {/* Paginazione */}
            {list && pages > 1 && (
                <div className="flex items-center justify-between mt-3 flex-wrap gap-2" data-testid="anag-pagination">
                    <span className="text-xs text-slate-500">
                        Pagina {page} di {pages} · {total} anagrafiche
                    </span>
                    <div className="flex items-center gap-1">
                        <Button size="sm" variant="outline" disabled={page <= 1}
                            onClick={() => setPage(1)} data-testid="anag-page-first">«</Button>
                        <Button size="sm" variant="outline" disabled={page <= 1}
                            onClick={() => setPage((p) => Math.max(1, p - 1))} data-testid="anag-page-prev">‹ Prec</Button>
                        <span className="px-3 text-sm text-slate-600 num">{page}</span>
                        <Button size="sm" variant="outline" disabled={page >= pages}
                            onClick={() => setPage((p) => Math.min(pages, p + 1))} data-testid="anag-page-next">Succ ›</Button>
                        <Button size="sm" variant="outline" disabled={page >= pages}
                            onClick={() => setPage(pages)} data-testid="anag-page-last">»</Button>
                    </div>
                </div>
            )}

            <PersonalizzaKpiDialog
                open={kpiDialogOpen}
                onOpenChange={setKpiDialogOpen}
                onChanged={() => api.get("/anagrafiche/stats").then((r) => setStats(r.data)).catch(() => {})}
            />

            <DeleteAnagraficaDialog
                target={deleteTarget}
                onClose={() => setDeleteTarget(null)}
                onDeleted={() => { setDeleteTarget(null); load(); }}
            />
            <ImportExcelDialog
                open={importOpen}
                onClose={() => setImportOpen(false)}
                onSuccess={() => load()}
                entity="anagrafiche"
                title="Importa Anagrafiche da Excel/CSV"
                required={[]}
            />
            <InviaCredenzialiPortaleDialog
                open={credMassivoOpen}
                onClose={() => setCredMassivoOpen(false)}
            />
        </div>
    );
}

// ─────────────────────────────────────────────────────────────────────
// UnisciDoppioniDialog — rileva e unisce anagrafiche con stesso CF/P.IVA
// ─────────────────────────────────────────────────────────────────────
function UnisciDoppioniDialog({ open, onClose, onMerged }) {
    const [groups, setGroups] = useState(null);
    const [principali, setPrincipali] = useState({});
    const [merging, setMerging] = useState(null);

    useEffect(() => {
        if (!open) return;
        setGroups(null);
        api.get("/anagrafiche-duplicati").then((r) => {
            setGroups(r.data || []);
            const init = {};
            (r.data || []).forEach((g, i) => {
                const best = [...g.anagrafiche].sort((a, b) => (b.n_polizze || 0) - (a.n_polizze || 0))[0];
                init[i] = best?.id;
            });
            setPrincipali(init);
        }).catch((e) => {
            toast.error(e.response?.data?.detail || "Errore ricerca doppioni");
            setGroups([]);
        });
    }, [open]);

    const unisci = async (gIdx) => {
        const g = groups[gIdx];
        const principale = principali[gIdx];
        const dupIds = g.anagrafiche.map((a) => a.id).filter((id) => id !== principale);
        if (!principale || dupIds.length === 0) return;
        if (!window.confirm(`Unire ${dupIds.length} doppion${dupIds.length === 1 ? "e" : "i"} nell'anagrafica principale? Le polizze e tutti i dati collegati verranno riassegnati. Operazione NON reversibile.`)) return;
        setMerging(gIdx);
        try {
            const r = await api.post("/anagrafiche-unisci", { principale_id: principale, duplicati_ids: dupIds });
            toast.success(`Unite: ${r.data.anagrafiche_eliminate} anagrafiche · ${r.data.polizze_riassegnate} polizze riassegnate`);
            setGroups((gs) => gs.filter((_, i) => i !== gIdx));
            onMerged();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore unione");
        } finally { setMerging(null); }
    };

    return (
        <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
            <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto" data-testid="dialog-unisci-doppioni">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <GitMerge size={17} className="text-amber-600" /> Anagrafiche doppie (stesso CF / P.IVA)
                    </DialogTitle>
                </DialogHeader>
                {groups === null ? (
                    <div className="py-8 text-center text-slate-500 text-sm">
                        <Loader2 size={20} className="animate-spin mx-auto mb-2" /> Ricerca doppioni in corso…
                    </div>
                ) : groups.length === 0 ? (
                    <div className="py-8 text-center text-slate-500 text-sm" data-testid="doppioni-vuoto">
                        Nessun doppione trovato. Tutte le anagrafiche hanno CF/P.IVA univoci.
                    </div>
                ) : (
                    <div className="space-y-3">
                        <div className="text-xs text-slate-500">
                            {groups.length} grupp{groups.length === 1 ? "o" : "i"} di doppioni.
                            Scegli l'anagrafica <strong>principale</strong> (le altre verranno unite ed eliminate,
                            polizze e dati collegati riassegnati).
                        </div>
                        {groups.map((g, gIdx) => (
                            <div key={`${g.tipo}-${g.valore}`} className="border border-slate-200 rounded p-3"
                                 data-testid={`doppioni-gruppo-${gIdx}`}>
                                <div className="flex items-center justify-between mb-2">
                                    <span className="text-xs font-semibold text-slate-700">
                                        {g.tipo === "cf" ? "Codice fiscale" : "Partita IVA"}:{" "}
                                        <span className="font-mono text-amber-700">{g.valore}</span>
                                    </span>
                                    <Button size="sm" className="h-7 text-xs bg-amber-600 hover:bg-amber-700"
                                            disabled={merging !== null}
                                            onClick={() => unisci(gIdx)}
                                            data-testid={`doppioni-unisci-${gIdx}`}>
                                        {merging === gIdx ? <Loader2 size={12} className="animate-spin mr-1" /> : <GitMerge size={12} className="mr-1" />}
                                        Unisci gruppo
                                    </Button>
                                </div>
                                <div className="space-y-1">
                                    {g.anagrafiche.map((a) => (
                                        <label key={a.id}
                                               className={`flex items-center gap-2 text-xs p-1.5 rounded cursor-pointer border ${
                                                   principali[gIdx] === a.id ? "border-emerald-300 bg-emerald-50/60" : "border-transparent hover:bg-slate-50"
                                               }`}
                                               data-testid={`doppioni-record-${a.id}`}>
                                            <input type="radio" name={`gruppo-${gIdx}`}
                                                   checked={principali[gIdx] === a.id}
                                                   onChange={() => setPrincipali((s) => ({ ...s, [gIdx]: a.id }))} />
                                            <Link to={`/anagrafiche/${a.id}`} target="_blank" onClick={(e) => e.stopPropagation()}
                                                  className="font-semibold text-sky-700 hover:underline truncate max-w-[220px]">
                                                {a.ragione_sociale || "(senza nome)"}
                                            </Link>
                                            <span className="text-slate-400">{a.email || "no email"}</span>
                                            <span className="ml-auto flex items-center gap-2 shrink-0">
                                                <span className={`px-1.5 py-0.5 rounded font-semibold ${a.n_polizze > 0 ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
                                                    {a.n_polizze} polizze
                                                </span>
                                                {principali[gIdx] === a.id && (
                                                    <span className="text-[10px] uppercase font-bold text-emerald-700">Principale</span>
                                                )}
                                            </span>
                                        </label>
                                    ))}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </DialogContent>
        </Dialog>
    );
}

// ─────────────────────────────────────────────────────────────────────
// InviaCredenzialiPortaleDialog — Invio massivo credenziali Portale Cliente
// ─────────────────────────────────────────────────────────────────────
function InviaCredenzialiPortaleDialog({ open, onClose }) {
    const [filtri, setFiltri] = useState({
        tipo_soggetto: "",
        solo_con_polizze: true,
        escludi_gia_invitati: true,
    });
    const [anteprima, setAnteprima] = useState(null);
    const [esito, setEsito] = useState(null);
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        if (!open) { setAnteprima(null); setEsito(null); }
    }, [open]);

    const body = () => ({
        tipo_soggetto: filtri.tipo_soggetto || null,
        solo_con_polizze: filtri.solo_con_polizze,
        escludi_gia_invitati: filtri.escludi_gia_invitati,
    });

    const anteprimaCount = async () => {
        setBusy(true);
        try {
            const r = await api.post("/anagrafiche/invia-credenziali-portale-massivo",
                { ...body(), dry_run: true });
            setAnteprima(r.data);
            setEsito(null);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore anteprima");
        } finally { setBusy(false); }
    };

    const invia = async () => {
        if (!anteprima) return;
        if (!window.confirm(`Confermi l'invio delle credenziali a ${anteprima.totale} clienti?`)) return;
        setBusy(true);
        try {
            const r = await api.post("/anagrafiche/invia-credenziali-portale-massivo", body());
            setEsito(r.data);
            toast.success(`Inviate: ${r.data.inviate_ok} / ${r.data.totale}`);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore invio massivo");
        } finally { setBusy(false); }
    };

    return (
        <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
            <DialogContent className="max-w-2xl" data-testid="dialog-invio-cred-massivo">
                <DialogHeader>
                    <DialogTitle>Invia credenziali Portale Cliente</DialogTitle>
                    <DialogDescription>
                        Invia in blocco email + WhatsApp con link di accesso al Portale.
                        Il testo è quello del preset <b>&quot;Benvenuto Portale Cliente&quot;</b> in Alert & Automazioni.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <Label className="text-xs">Tipo cliente</Label>
                            <Select value={filtri.tipo_soggetto || "all"} onValueChange={(v) => setFiltri((f) => ({ ...f, tipo_soggetto: v === "all" ? "" : v }))}>
                                <SelectTrigger data-testid="cred-filter-tipo"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="all">Tutti</SelectItem>
                                    <SelectItem value="fisico">Persone fisiche</SelectItem>
                                    <SelectItem value="giuridico">Aziende</SelectItem>
                                    <SelectItem value="condominio">Condomini</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="space-y-2 pt-5">
                            <label className="flex items-center gap-2 text-sm">
                                <input type="checkbox" checked={filtri.solo_con_polizze}
                                       onChange={(e) => setFiltri((f) => ({ ...f, solo_con_polizze: e.target.checked }))}
                                       data-testid="cred-filter-conpolizze" />
                                <span>Solo con polizze attive/sospese</span>
                            </label>
                            <label className="flex items-center gap-2 text-sm">
                                <input type="checkbox" checked={filtri.escludi_gia_invitati}
                                       onChange={(e) => setFiltri((f) => ({ ...f, escludi_gia_invitati: e.target.checked }))}
                                       data-testid="cred-filter-escludi" />
                                <span>Escludi chi ha già ricevuto la welcome</span>
                            </label>
                        </div>
                    </div>

                    <div className="flex gap-2 pt-2">
                        <Button variant="outline" onClick={anteprimaCount} disabled={busy}
                                data-testid="cred-anteprima-btn">
                            <Search size={14} className="mr-1" /> Anteprima destinatari
                        </Button>
                        {anteprima && (
                            <Button onClick={invia} disabled={busy || anteprima.totale === 0}
                                    className="bg-violet-700 hover:bg-violet-800"
                                    data-testid="cred-invio-btn">
                                <Send size={14} className="mr-1" /> Invia a {anteprima.totale} clienti
                            </Button>
                        )}
                    </div>

                    {anteprima && !esito && (
                        <div className="bg-violet-50 border border-violet-200 rounded p-3 text-sm" data-testid="cred-anteprima-box">
                            <div className="font-medium text-violet-900">
                                Trovati {anteprima.totale} clienti con email valida
                            </div>
                            {anteprima.esempi?.length > 0 && (
                                <div className="mt-2 text-xs text-slate-700">
                                    Esempi:{" "}
                                    {anteprima.esempi.slice(0, 5).map((x) => x.nome).join(", ")}
                                    {anteprima.totale > 5 && `, +${anteprima.totale - 5} altri…`}
                                </div>
                            )}
                        </div>
                    )}

                    {esito && (
                        <div className="bg-emerald-50 border border-emerald-200 rounded p-3 text-sm space-y-1" data-testid="cred-esito-box">
                            <div className="font-medium text-emerald-900">
                                ✓ Inviate: {esito.inviate_ok} · ✗ Errori: {esito.inviate_ko} · Totale: {esito.totale}
                            </div>
                            {esito.inviate_ko > 0 && (
                                <div className="text-xs text-slate-600">
                                    Alcune anagrafiche hanno errori (email non valida, SMTP/WA irraggiungibile…).
                                    Vedi log in <Link to="/richieste-cliente" className="underline">Notifiche portale</Link>.
                                </div>
                            )}
                        </div>
                    )}
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Chiudi</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}


function KpiCard({ icon, color, label, n, premio, testid, onClick }) {
    const palettes = {
        sky:     { bg: "bg-white",  border: "border-l-4 border-l-sky-500 border border-slate-200",     ic: "text-sky-600",     hint: "text-sky-700" },
        emerald: { bg: "bg-white",  border: "border-l-4 border-l-emerald-500 border border-slate-200", ic: "text-emerald-600", hint: "text-emerald-700" },
        amber:   { bg: "bg-white",  border: "border-l-4 border-l-amber-500 border border-slate-200",   ic: "text-amber-600",   hint: "text-amber-700" },
        violet:  { bg: "bg-white",  border: "border-l-4 border-l-violet-500 border border-slate-200",  ic: "text-violet-600",  hint: "text-violet-700" },
        rose:    { bg: "bg-white",  border: "border-l-4 border-l-rose-500 border border-slate-200",    ic: "text-rose-600",    hint: "text-rose-700" },
        pink:    { bg: "bg-white",  border: "border-l-4 border-l-pink-500 border border-slate-200",    ic: "text-pink-600",    hint: "text-pink-700" },
        orange:  { bg: "bg-white",  border: "border-l-4 border-l-orange-500 border border-slate-200",  ic: "text-orange-600",  hint: "text-orange-700" },
        slate:   { bg: "bg-white",  border: "border-l-4 border-l-slate-500 border border-slate-200",   ic: "text-slate-600",   hint: "text-slate-700" },
    };
    const p = palettes[color] || palettes.sky;
    const isClickable = typeof onClick === "function";
    return (
        <div
            className={`${p.bg} ${p.border} rounded-md p-4 hover:shadow-md transition-shadow ${isClickable ? "cursor-pointer" : ""}`}
            onClick={onClick}
            role={isClickable ? "button" : undefined}
            data-testid={testid}
        >
            <div className="flex items-start justify-between">
                <div className="text-[10px] uppercase tracking-widest font-semibold text-slate-500">{label}</div>
                <div className={p.ic}>{icon}</div>
            </div>
            <div className="mt-1 flex items-baseline gap-2">
                <span className="text-3xl font-bold num text-slate-900">{n}</span>
                <span className="text-[10px] uppercase tracking-wider text-slate-400">con pol.</span>
            </div>
            <div className="mt-1 text-xs text-slate-600">
                Premi: <span className={`font-semibold num ${p.hint}`}>{fmtEur(premio || 0)}</span>
            </div>
        </div>
    );
}

const KPI_ICON_OPTS = {
    Star: Star, Heart: Heart, Flag: Flag, Award: Award, Target: Target,
    Bookmark: Bookmark, Tag: TagIcon, Zap: Zap, Users: Users,
    Briefcase: Briefcase, Home: Home, Church: Church,
};
const KPI_COLOR_OPTS = ["sky", "emerald", "amber", "violet", "rose", "pink", "orange", "slate"];

function CustomKpiIcon({ name }) {
    const Cmp = KPI_ICON_OPTS[name] || Star;
    return <Cmp size={18} />;
}

function PersonalizzaKpiDialog({ open, onOpenChange, onChanged }) {
    const [items, setItems] = useState([]);
    const [tagsAvailable, setTagsAvailable] = useState([]);
    const [loading, setLoading] = useState(false);
    const [draft, setDraft] = useState({ label: "", tag: "", color: "sky", icon: "Star" });

    const load = useCallback(async () => {
        const [r1, r2] = await Promise.all([
            api.get("/anagrafiche/kpi-custom"),
            api.get("/anagrafiche/tags"),
        ]);
        setItems(r1.data || []);
        setTagsAvailable(r2.data || []);
    }, []);

    useEffect(() => { if (open) load(); }, [open, load]);

    const handleAdd = async () => {
        if (!draft.label.trim() || !draft.tag.trim()) {
            toast.error("Inserisci etichetta e tag");
            return;
        }
        if (items.length >= 8) {
            toast.error("Massimo 8 KPI custom");
            return;
        }
        setLoading(true);
        try {
            await api.post("/anagrafiche/kpi-custom", draft);
            setDraft({ label: "", tag: "", color: "sky", icon: "Star" });
            await load();
            onChanged?.();
            toast.success("KPI aggiunta");
        } catch (e) {
            toast.error("Errore: " + (e.response?.data?.detail || e.message));
        } finally {
            setLoading(false);
        }
    };

    const handleRemove = async (kid) => {
        if (!window.confirm("Rimuovere questa KPI?")) return;
        setLoading(true);
        try {
            await api.delete(`/anagrafiche/kpi-custom/${kid}`);
            await load();
            onChanged?.();
            toast.success("KPI rimossa");
        } catch {
            toast.error("Errore");
        } finally {
            setLoading(false);
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-2xl" data-testid="dialog-personalizza-kpi">
                <DialogHeader>
                    <DialogTitle>Personalizza KPI Anagrafiche</DialogTitle>
                    <DialogDescription>
                        Crea KPI personalizzate basate sui tag delle anagrafiche.
                    </DialogDescription>
                </DialogHeader>
                <div className="space-y-4">
                    <div className="text-xs text-slate-500">
                        Crea KPI personalizzate basate sui <b>tag</b> delle anagrafiche.
                        Vengono mostrate accanto alle 4 KPI standard. Max 8.
                    </div>

                    {/* Lista esistenti */}
                    {items.length > 0 && (
                        <div className="space-y-2">
                            <Label className="text-xs uppercase tracking-wider text-slate-500">KPI attive</Label>
                            <div className="border rounded-md divide-y">
                                {items.map((k) => {
                                    const Icon = KPI_ICON_OPTS[k.icon] || Star;
                                    return (
                                        <div key={k.id} className="flex items-center justify-between px-3 py-2 text-sm" data-testid={`kpi-row-${k.id}`}>
                                            <div className="flex items-center gap-3">
                                                <Icon size={16} className={`text-${k.color}-600`} />
                                                <div>
                                                    <div className="font-medium">{k.label}</div>
                                                    <div className="text-xs text-slate-500">tag: <span className="font-mono">{k.tag}</span></div>
                                                </div>
                                            </div>
                                            <Button
                                                size="sm" variant="ghost"
                                                onClick={() => handleRemove(k.id)}
                                                disabled={loading}
                                                data-testid={`btn-remove-kpi-${k.id}`}
                                            >
                                                <Trash2 size={14} className="text-red-500" />
                                            </Button>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    )}

                    {/* Form nuova KPI */}
                    <div className="border-t pt-3 space-y-3">
                        <Label className="text-xs uppercase tracking-wider text-slate-500">Aggiungi nuova KPI</Label>
                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <Label className="text-xs">Etichetta</Label>
                                <Input
                                    value={draft.label}
                                    onChange={(e) => setDraft((d) => ({ ...d, label: e.target.value }))}
                                    placeholder="Es. Clienti Premium"
                                    data-testid="input-kpi-label"
                                />
                            </div>
                            <div>
                                <Label className="text-xs">Tag (dovrà esistere su anagrafiche)</Label>
                                <Input
                                    list="kpi-tags-datalist"
                                    value={draft.tag}
                                    onChange={(e) => setDraft((d) => ({ ...d, tag: e.target.value.toLowerCase().trim() }))}
                                    placeholder="es. vip, partner, fornitore..."
                                    data-testid="input-kpi-tag"
                                />
                                <datalist id="kpi-tags-datalist">
                                    {tagsAvailable.map((t) => <option key={t} value={t} />)}
                                </datalist>
                            </div>
                            <div>
                                <Label className="text-xs">Colore</Label>
                                <Select value={draft.color} onValueChange={(v) => setDraft((d) => ({ ...d, color: v }))}>
                                    <SelectTrigger data-testid="select-kpi-color"><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        {KPI_COLOR_OPTS.map((c) => (
                                            <SelectItem key={c} value={c}>
                                                <span className="flex items-center gap-2">
                                                    <span className={`inline-block w-3 h-3 rounded-full bg-${c}-500`} />
                                                    {c}
                                                </span>
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div>
                                <Label className="text-xs">Icona</Label>
                                <Select value={draft.icon} onValueChange={(v) => setDraft((d) => ({ ...d, icon: v }))}>
                                    <SelectTrigger data-testid="select-kpi-icon"><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        {Object.keys(KPI_ICON_OPTS).map((ic) => (
                                            <SelectItem key={ic} value={ic}>{ic}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>
                        <Button onClick={handleAdd} disabled={loading} data-testid="btn-add-kpi" className="w-full">
                            <Plus size={14} className="mr-1" /> Aggiungi KPI
                        </Button>
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)}>Chiudi</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function RigaAnagrafica({ a, cols, cat, isOpen, net, onToggle, onTagClick, onDelete, canDelete }) {
    const ctx = { cat, isOpen, net, onToggle, onTagClick, onDelete, canDelete };
    return (
        <>
            <tr className="border-b border-slate-100 hover:bg-slate-50 transition-colors" data-testid={`anagrafica-row-${a.id}`}>
                {cols.map((c) => (
                    <td key={c.key} className={c.tdClass}>{c.render(a, ctx)}</td>
                ))}
            </tr>
            {isOpen && net && (
                <tr className="bg-slate-50/60 border-b border-slate-200" data-testid={`anag-network-${a.id}`}>
                    <td colSpan={cols.length} className="px-12 py-4">
                        {net.collegati.length === 0 ? (
                            <div className="text-xs text-slate-500 italic">
                                Nessuna anagrafica collegata. Aggiungi familiari, aziende rappresentate o relazioni dalla scheda &gt; Relazione.
                            </div>
                        ) : (
                            <>
                                <div className="text-[10px] uppercase font-semibold tracking-widest text-slate-500 mb-2 flex items-center gap-1">
                                    <Users size={11} /> Collegati ({net.collegati.length})
                                </div>
                                <table className="w-full text-xs">
                                    <thead>
                                        <tr className="text-[10px] uppercase tracking-wider text-slate-500 border-b">
                                            <th className="text-left py-1.5 pr-2">Anagrafica</th>
                                            <th className="text-left py-1.5 pr-2">Relazione</th>
                                            <th className="text-center py-1.5 pr-2">Polizze</th>
                                            <th className="text-center py-1.5 pr-2">Preventivi</th>
                                            <th className="text-right py-1.5 pr-2">Premio</th>
                                            <th className="text-right py-1.5 pr-2">Provvigioni</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {net.collegati.map((c) => (
                                            <tr key={c.id} className="border-b border-slate-100 hover:bg-white">
                                                <td className="py-1.5 pr-2">
                                                    <Link to={`/anagrafiche/${c.id}`} className="text-sky-700 hover:underline font-medium">{c.ragione_sociale}</Link>
                                                </td>
                                                <td className="py-1.5 pr-2 text-slate-600 capitalize">{(c.relazione || "—").replace(/_/g, " ")}</td>
                                                <td className="text-center py-1.5 pr-2 num text-emerald-700 font-semibold">{c.n_polizze_attive}</td>
                                                <td className="text-center py-1.5 pr-2 num text-slate-500">{c.n_preventivi}</td>
                                                <td className="text-right py-1.5 pr-2 num font-semibold">{fmtEur(c.premio_totale || 0)}</td>
                                                <td className="text-right py-1.5 pr-2 num text-emerald-700">{fmtEur(c.provvigioni_totale || 0)}</td>
                                            </tr>
                                        ))}
                                        <tr className="border-t-2 border-slate-300 font-bold">
                                            <td colSpan={2} className="py-1.5 pr-2 text-right uppercase text-[10px] tracking-widest">Totale network</td>
                                            <td className="text-center py-1.5 pr-2 num">{net.totali.n_polizze_attive}</td>
                                            <td className="text-center py-1.5 pr-2 num">{net.totali.n_preventivi}</td>
                                            <td className="text-right py-1.5 pr-2 num">{fmtEur(net.totali.premio_totale)}</td>
                                            <td className="text-right py-1.5 pr-2 num text-emerald-700">{fmtEur(net.totali.provvigioni_totale)}</td>
                                        </tr>
                                    </tbody>
                                </table>
                            </>
                        )}
                    </td>
                </tr>
            )}
        </>
    );
}

function CatChip({ active, onClick, dot, label }) {
    return (
        <button
            onClick={onClick}
            className={`inline-flex items-center gap-2 text-xs px-3 py-1 rounded-full border transition ${
                active ? "bg-slate-900 text-white border-slate-900" : "bg-white text-slate-600 border-slate-300 hover:bg-slate-50"
            }`}
        >
            <span className={`w-2 h-2 rounded-full ${dot}`} />
            {label}
        </button>
    );
}

// ============================================================
// DIALOG NUOVA ANAGRAFICA con OCR CI + Calcolo CF + Geocoding auto
// ============================================================
function NuovaAnagraficaDialog({ onClose }) {
    const ciFileRef = useRef(null);
    const [collaboratori, setCollaboratori] = useState([]);
    const [ocrLoading, setOcrLoading] = useState(false);
    const [geoLoading, setGeoLoading] = useState(false);
    const [importAziendaLoading, setImportAziendaLoading] = useState(false);
    // Duplicato rilevato: {existing:{id,ragione_sociale,...}, match_on, fonte}
    // Se fonte === "auto" viene proposto dopo OCR; se "save" viene proposto al salvataggio.
    const [duplicate, setDuplicate] = useState(null);
    const [form, setForm] = useState({
        tipo: "persona_fisica",
        ragione_sociale: "", nome: "", cognome: "",
        codice_fiscale: "", partita_iva: "",
        data_nascita: "", sesso: "",
        comune_nascita: "", provincia_nascita: "",
        email: "", cellulare: "", telefono: "",
        indirizzo: "", comune: "", provincia: "", cap: "",
        numero_documento: "", data_rilascio: "", data_scadenza: "",
        comune_emissione: "",
        collaboratore_id: "",
        tipologia_lavoratore: null,
        professione: "",
        lat: null, lng: null,
        _overwrite_id: null,  // se != null il save farà PUT sull'esistente
    });

    useEffect(() => { api.get("/collaboratori").then((r) => setCollaboratori(r.data)); }, []);

    const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
    const setU = (k, v) => set(k, (v || "").toUpperCase());

    // Verifica esistenza duplicato via /api/anagrafiche/check-duplicate.
    // Ritorna existing?: {id, ragione_sociale, ...} | null.
    const checkDup = async ({ codice_fiscale, partita_iva, tipo }) => {
        try {
            const r = await api.get("/anagrafiche/check-duplicate", {
                params: {
                    codice_fiscale: codice_fiscale || undefined,
                    partita_iva: partita_iva || undefined,
                    tipo: tipo || undefined,
                },
            });
            return r.data;
        } catch { return { existing: null, match_on: null }; }
    };

    // --- Calcolo CF ---
    const calcolaCF = async () => {
        if (!form.nome || !form.cognome || !form.sesso || !form.data_nascita || !form.comune_nascita) {
            toast.error("Servono Nome, Cognome, Sesso, Data nascita, Comune nascita");
            return;
        }
        try {
            const r = await api.post("/utility/codice-fiscale/calcola", {
                nome: form.nome, cognome: form.cognome, sesso: form.sesso,
                data_nascita: form.data_nascita, comune_nascita: form.comune_nascita,
            });
            set("codice_fiscale", r.data.codice_fiscale);
            toast.success("CF calcolato: " + r.data.codice_fiscale);
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    // --- Decodifica CF (compila campi anagrafici) ---
    const decodificaCF = async () => {
        if (!form.codice_fiscale || form.codice_fiscale.length !== 16) {
            toast.error("Inserisci un CF valido (16 caratteri)");
            return;
        }
        try {
            const r = await api.post("/utility/codice-fiscale/decodifica", {
                codice_fiscale: form.codice_fiscale,
            });
            setForm((f) => ({
                ...f,
                sesso: r.data.sesso || f.sesso,
                data_nascita: r.data.data_nascita || f.data_nascita,
                comune_nascita: (r.data.comune_nascita || f.comune_nascita || "").toUpperCase(),
                provincia_nascita: r.data.provincia_nascita || f.provincia_nascita,
            }));
            toast.success("Dati estratti dal CF");
        } catch (e) { toast.error(e.response?.data?.detail || "CF non valido"); }
    };

    // --- Importa Dati Azienda da OpenAPI.it (Camerale) ---
    // Chiama /api/openapi-it/company?piva=... e pre-compila il form.
    const importaAzienda = async () => {
        const piva = (form.partita_iva || "").trim();
        if (!piva || piva.length !== 11) { toast.error("P.IVA non valida (11 cifre richieste)"); return; }
        setImportAziendaLoading(true);
        try {
            const r = await api.get("/openapi-it/company", { params: { piva } });
            const d = r.data;
            setForm((p) => ({
                ...p,
                tipo: "persona_giuridica",
                ragione_sociale: (d.ragione_sociale || p.ragione_sociale || "").toUpperCase(),
                codice_fiscale: (d.cf || p.codice_fiscale || "").toUpperCase(),
                indirizzo: (d.indirizzo_completo || p.indirizzo || "").toUpperCase(),
                comune: (d.comune || p.comune || "").toUpperCase(),
                provincia: d.provincia || p.provincia,
                cap: d.cap || p.cap,
                email: d.pec || p.email,
                _dati_extra_visura: {
                    forma_giuridica: d.forma_giuridica, rea: d.rea,
                    pec: d.pec, codice_ateco: d.ateco, ateco_descrizione: d.ateco_descrizione,
                    stato_attivita: d.attiva ? "ATTIVA" : "CESSATA",
                    cciaa: d.cciaa,
                },
            }));
            const src = (d.provider || "").includes("MOCK") ? "MOCK" : "LIVE";
            toast.success(`Dati azienda importati (${src}): ${d.ragione_sociale || piva}`);
        } catch (e) {
            toast.error("Import fallito: " + (e.response?.data?.detail || e.message));
        } finally {
            setImportAziendaLoading(false);
        }
    };

    // --- OCR Carta Identità ---
    const onOcrCI = async (file) => {
        if (!file) return;
        setOcrLoading(true);
        const fd = new FormData();
        fd.append("file", file);
        try {
            const r = await api.post("/utility/ocr-carta-identita", fd,
                { headers: { "Content-Type": "multipart/form-data" }, timeout: 60000 });
            const d = r.data;
            setForm((p) => ({
                ...p,
                tipo: "persona_fisica",
                cognome: (d.cognome || p.cognome || "").toUpperCase(),
                nome: (d.nome || p.nome || "").toUpperCase(),
                sesso: d.sesso || p.sesso,
                data_nascita: d.data_nascita || p.data_nascita,
                comune_nascita: (d.comune_nascita || p.comune_nascita || "").toUpperCase(),
                provincia_nascita: d.provincia_nascita || p.provincia_nascita,
                codice_fiscale: (d.codice_fiscale || p.codice_fiscale || "").toUpperCase(),
                numero_documento: (d.numero_documento || p.numero_documento || "").toUpperCase(),
                data_rilascio: d.data_rilascio || p.data_rilascio,
                data_scadenza: d.data_scadenza || p.data_scadenza,
                comune_emissione: (d.comune_emissione || p.comune_emissione || "").toUpperCase(),
                indirizzo: (d.indirizzo_residenza || p.indirizzo || "").toUpperCase(),
                comune: (d.comune_residenza || p.comune || "").toUpperCase(),
                _ci_file_da_salvare: file,  // verrà ricaricato dopo create anagrafica per salvare in documenti
            }));
            toast.success("Carta d'identità riconosciuta — verifica i campi");
            // Controllo duplicato immediato dopo OCR (persona fisica → CF)
            const cf = (d.codice_fiscale || "").toUpperCase();
            if (cf && cf.length === 16) {
                const dup = await checkDup({ codice_fiscale: cf, tipo: "persona_fisica" });
                if (dup?.existing) setDuplicate({ ...dup, fonte: "auto" });
            }
        } catch (e) { toast.error("OCR fallito: " + (e.response?.data?.detail || e.message)); }
        finally { setOcrLoading(false); }
    };

    // --- OCR Visura camerale ---
    const onOcrVisura = async (file) => {
        if (!file) return;
        setOcrLoading(true);
        const fd = new FormData();
        fd.append("file", file);
        try {
            const r = await api.post("/utility/ocr-visura-camerale", fd,
                { headers: { "Content-Type": "multipart/form-data" }, timeout: 90000 });
            const d = r.data;
            setForm((p) => ({
                ...p,
                tipo: "persona_giuridica",
                ragione_sociale: (d.ragione_sociale || p.ragione_sociale || "").toUpperCase(),
                partita_iva: d.partita_iva || p.partita_iva,
                codice_fiscale: (d.codice_fiscale_ditta || p.codice_fiscale || "").toUpperCase(),
                indirizzo: (d.indirizzo_sede || p.indirizzo || "").toUpperCase(),
                comune: (d.comune_sede || p.comune || "").toUpperCase(),
                provincia: d.provincia_sede || p.provincia,
                cap: d.cap_sede || p.cap,
                telefono: d.telefono || p.telefono,
                email: d.email || p.email,
                _visura_file_da_salvare: file,
                _amministratori: d.amministratori || [],
                _dati_extra_visura: {
                    forma_giuridica: d.forma_giuridica, rea: d.rea,
                    capitale_sociale: d.capitale_sociale, pec: d.pec,
                    oggetto_sociale: d.oggetto_sociale, codice_ateco: d.codice_ateco,
                    stato_attivita: d.stato_attivita, data_inizio_attivita: d.data_inizio_attivita,
                    data_costituzione: d.data_costituzione,
                },
            }));
            const nAmm = (d.amministratori || []).length;
            toast.success(`Visura riconosciuta: ${d.ragione_sociale}${nAmm ? ` + ${nAmm} amministratori` : ""}`);
            // Controllo duplicato immediato dopo OCR (persona giuridica → P.IVA)
            const piva = d.partita_iva || "";
            if (piva && piva.length >= 11) {
                const dup = await checkDup({ partita_iva: piva, tipo: "persona_giuridica" });
                if (dup?.existing) setDuplicate({ ...dup, fonte: "auto" });
            }
        } catch (e) { toast.error("OCR visura fallito: " + (e.response?.data?.detail || e.message)); }
        finally { setOcrLoading(false); }
    };

    // --- Geocoding automatico al blur dell'indirizzo o comune ---
    const geocoda = async () => {
        if (!form.indirizzo && !form.comune) return;
        setGeoLoading(true);
        try {
            const r = await api.post("/utility/geocoding", {
                indirizzo: form.indirizzo, comune: form.comune, cap: form.cap, provincia: form.provincia,
            });
            if (r.data?.trovato) {
                setForm((f) => ({ ...f, lat: r.data.lat, lng: r.data.lng }));
                toast.success(`Geo: ${r.data.lat.toFixed(4)}, ${r.data.lng.toFixed(4)}`);
            }
        } catch (e) { console.warn("geocoding:", e?.message || e); }
        finally { setGeoLoading(false); }
    };

    const save = async (overrideOverwriteId = null) => {
        const isPF = form.tipo === "persona_fisica";
        if (isPF && !form.nome && !form.cognome) { toast.error("Inserisci Cognome o Nome"); return; }
        if (!isPF && !form.ragione_sociale) { toast.error("Inserisci la ragione sociale"); return; }

        // Effective overwrite id: se passato esplicitamente (da onConfirmOverwrite)
        // ha priorità sullo state form._overwrite_id (evita stale-closure).
        const effectiveOverwriteId = overrideOverwriteId || form._overwrite_id;

        // Safety net: se non è stato ancora rilevato un duplicato via OCR ma
        // l'utente ha inserito CF/P.IVA a mano, controlla ADESSO prima di creare.
        if (!effectiveOverwriteId) {
            const dup = await checkDup({
                codice_fiscale: isPF ? form.codice_fiscale : null,
                partita_iva: !isPF ? form.partita_iva : (form.partita_iva || null),
                tipo: form.tipo,
            });
            if (dup?.existing) {
                setDuplicate({ ...dup, fonte: "save" });
                return;  // aspetta la decisione dell'utente sulla modale
            }
        }

        const { _ci_file_da_salvare, _visura_file_da_salvare, _amministratori, _dati_extra_visura, _overwrite_id, ...payload } = form;
        if (isPF && !payload.ragione_sociale) {
            payload.ragione_sociale = `${form.cognome || ""} ${form.nome || ""}`.trim();
        }
        // attacca note dalla visura (forma giuridica, REA, capitale, oggetto sociale)
        if (_dati_extra_visura) {
            const extra = Object.entries(_dati_extra_visura).filter(([, v]) => v).map(([k, v]) => `${k}: ${v}`).join(" · ");
            if (extra) payload.note = (payload.note ? payload.note + "\n" : "") + `[Da visura] ${extra}`;
        }
        // Se l'utente ha confermato la sovrascrittura, aggancia overwrite_id
        if (effectiveOverwriteId) payload.overwrite_id = effectiveOverwriteId;

        try {
            const created = await api.post("/anagrafiche", payload);
            const newId = created.data.id;
            // Salva la CI come documento, se caricata
            if (_ci_file_da_salvare) {
                const fd = new FormData();
                fd.append("file", _ci_file_da_salvare);
                api.post(`/anagrafiche/${newId}/documenti/carta_identita`, fd,
                    { headers: { "Content-Type": "multipart/form-data" } }).catch(() => {});
            }
            // Salva visura come documento
            if (_visura_file_da_salvare) {
                const fd = new FormData();
                fd.append("file", _visura_file_da_salvare);
                api.post(`/anagrafiche/${newId}/documenti/visura_camerale`, fd,
                    { headers: { "Content-Type": "multipart/form-data" } }).catch(() => {});
            }
            // Crea anagrafiche per amministratori
            if (_amministratori?.length) {
                for (const a of _amministratori) {
                    if (!a.cognome && !a.nome) continue;
                    const amm = {
                        tipo: "persona_fisica",
                        ragione_sociale: `${a.cognome || ""} ${a.nome || ""}`.trim(),
                        cognome: (a.cognome || "").toUpperCase(),
                        nome: (a.nome || "").toUpperCase(),
                        codice_fiscale: (a.codice_fiscale || "").toUpperCase(),
                        data_nascita: a.data_nascita,
                        comune_nascita: (a.comune_nascita || "").toUpperCase(),
                        provincia_nascita: a.provincia_nascita,
                        indirizzo: (a.indirizzo_residenza || "").toUpperCase(),
                        comune: (a.comune_residenza || "").toUpperCase(),
                        note: `Ruolo nella ditta ${payload.ragione_sociale}: ${a.ruolo || "amministratore"}`
                              + (a.poteri ? ` - ${a.poteri}` : ""),
                        tags: ["amministratore", "da_visura"],
                    };
                    try { await api.post("/anagrafiche", amm); } catch (err) { /* skip */ }
                }
                toast.success(`Ditta + ${_amministratori.length} amministratori ${effectiveOverwriteId ? "aggiornata" : "creati"}`);
            } else {
                toast.success(effectiveOverwriteId ? "Anagrafica sovrascritta con successo" : "Anagrafica creata");
            }
            onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    // Callback modale duplicato: conferma sovrascrittura.
    // Passa l'id esplicitamente a save() per evitare stale-closure sul form state.
    const onConfirmOverwrite = () => {
        if (!duplicate?.existing) return;
        const ovId = duplicate.existing.id;
        setForm((f) => ({ ...f, _overwrite_id: ovId }));
        setDuplicate(null);
        save(ovId);  // esplicito → nessun setTimeout, nessuna closure stale
    };
    const onCancelOverwrite = () => {
        // Se veniva da un save aborto -> chiudi. Se veniva da OCR (fonte=auto) -> tieni aperto.
        setDuplicate(null);
    };

    const isPF = form.tipo === "persona_fisica";

    return (
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
                <DialogTitle>Nuova anagrafica</DialogTitle>
            </DialogHeader>

            {/* Toolbar OCR */}
            <div className="bg-sky-50 border border-sky-200 rounded-md p-3 flex items-center gap-3 flex-wrap" data-testid="ocr-toolbar">
                <div className="text-xs text-sky-900 flex-1">
                    <strong>Auto-compila</strong> caricando {isPF ? "la carta d'identità" : "la visura camerale"} (PDF/JPG/PNG).
                    {!isPF && " Verranno create anche le anagrafiche degli amministratori."}
                </div>
                <input
                    ref={ciFileRef}
                    type="file"
                    accept=".pdf,image/*"
                    className="hidden"
                    onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (isPF) onOcrCI(f); else onOcrVisura(f);
                    }}
                    data-testid="anag-ocr-input"
                />
                <Button
                    type="button" variant="outline" size="sm"
                    onClick={() => ciFileRef.current?.click()}
                    disabled={ocrLoading}
                    data-testid="anag-ocr-button"
                >
                    <ScanLine size={13} className="mr-1" />
                    {ocrLoading ? "Riconosco..." : (isPF ? "Carica CI" : "Carica visura camerale")}
                </Button>
            </div>

            <div className="grid grid-cols-2 gap-3 py-2">
                <div className="col-span-2">
                    <Label>Tipo *</Label>
                    <Select value={form.tipo} onValueChange={(v) => set("tipo", v)}>
                        <SelectTrigger data-testid="anag-tipo-select"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="persona_fisica">Persona fisica</SelectItem>
                            <SelectItem value="persona_giuridica">Azienda / Persona giuridica</SelectItem>
                        </SelectContent>
                    </Select>
                </div>

                {isPF ? (
                    <>
                        <div>
                            <Label>Cognome *</Label>
                            <Input data-testid="anag-cognome-input" className="uc"
                                value={form.cognome} onChange={(e) => setU("cognome", e.target.value)} />
                        </div>
                        <div>
                            <Label>Nome *</Label>
                            <Input data-testid="anag-nome-input" className="uc"
                                value={form.nome} onChange={(e) => setU("nome", e.target.value)} />
                        </div>
                    </>
                ) : (
                    <div className="col-span-2">
                        <Label>Ragione sociale *</Label>
                        <Input data-testid="anag-rs-input" className="uc"
                            value={form.ragione_sociale} onChange={(e) => setU("ragione_sociale", e.target.value)} />
                    </div>
                )}

                {isPF && (
                    <>
                        <div className="col-span-2 flex items-end gap-2">
                            <div className="flex-1">
                                <Label>Codice fiscale</Label>
                                <Input data-testid="anag-cf-input" className="uc"
                                    value={form.codice_fiscale} maxLength={16}
                                    onChange={(e) => setU("codice_fiscale", e.target.value)} />
                            </div>
                            <Button type="button" size="sm" variant="outline" onClick={calcolaCF} title="Calcola CF da dati anagrafici" data-testid="anag-cf-calcola">
                                <Calculator size={13} className="mr-1" /> Calcola
                            </Button>
                            <Button type="button" size="sm" variant="outline" onClick={decodificaCF} title="Estrai dati dal CF" data-testid="anag-cf-decodifica">
                                ← Compila da CF
                            </Button>
                        </div>
                        <div>
                            <Label>Data nascita</Label>
                            <Input type="date" value={form.data_nascita} onChange={(e) => set("data_nascita", e.target.value)} />
                        </div>
                        <div>
                            <Label>Sesso</Label>
                            <Select value={form.sesso || undefined} onValueChange={(v) => set("sesso", v)}>
                                <SelectTrigger><SelectValue placeholder="-" /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="M">Maschio</SelectItem>
                                    <SelectItem value="F">Femmina</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <div>
                            <Label>Comune di nascita</Label>
                            <Input className="uc" value={form.comune_nascita} onChange={(e) => setU("comune_nascita", e.target.value)} />
                        </div>
                        <div>
                            <Label>Provincia nascita</Label>
                            <Input className="uc" maxLength={2} value={form.provincia_nascita} onChange={(e) => setU("provincia_nascita", e.target.value)} />
                        </div>
                    </>
                )}

                {!isPF && (
                    <div className="col-span-2">
                        <Label>Partita IVA</Label>
                        <div className="flex items-center gap-2 mt-1">
                            <Input value={form.partita_iva} onChange={(e) => set("partita_iva", e.target.value)}
                                placeholder="Inserisci la P.IVA (11 cifre)" className="flex-1" data-testid="anag-piva-input" />
                            <button
                                type="button"
                                onClick={importaAzienda}
                                disabled={importAziendaLoading || (form.partita_iva || "").trim().length !== 11}
                                className="whitespace-nowrap bg-emerald-600 text-white hover:bg-emerald-700 px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                                data-testid="anag-importa-azienda-btn"
                                title="Autocompila i dati dell'azienda da OpenAPI.it (Camerale)"
                            >
                                {importAziendaLoading ? "⏳ Estraggo…" : "⚡ Estrai dati"}
                            </button>
                        </div>
                        <div className="text-[11px] text-slate-500 mt-1">
                            Inserisci la Partita IVA e clicca <b>Estrai dati</b> per compilare automaticamente ragione sociale, indirizzo, PEC e ATECO.
                        </div>
                    </div>
                )}

                <div className="col-span-2 text-xs uppercase tracking-widest font-semibold text-slate-500 pt-3 border-t border-slate-100">Documento</div>
                {isPF && (
                    <>
                        <div><Label>Numero documento</Label><Input className="uc" value={form.numero_documento} onChange={(e) => setU("numero_documento", e.target.value)} /></div>
                        <div><Label>Comune emissione</Label><Input className="uc" value={form.comune_emissione} onChange={(e) => setU("comune_emissione", e.target.value)} /></div>
                        <div><Label>Data rilascio</Label><Input type="date" value={form.data_rilascio || ""} onChange={(e) => set("data_rilascio", e.target.value)} /></div>
                        <div><Label>Data scadenza</Label><Input type="date" value={form.data_scadenza || ""} onChange={(e) => set("data_scadenza", e.target.value)} /></div>
                    </>
                )}

                <div className="col-span-2 text-xs uppercase tracking-widest font-semibold text-slate-500 pt-3 border-t border-slate-100">Contatti</div>
                <div>
                    <Label>Email</Label>
                    <Input type="email" data-testid="anag-email-input"
                        value={form.email} onChange={(e) => set("email", e.target.value.toLowerCase())} />
                </div>
                <div><Label>Cellulare</Label><Input value={form.cellulare} onChange={(e) => set("cellulare", e.target.value)} /></div>
                <div><Label>Telefono</Label><Input value={form.telefono} onChange={(e) => set("telefono", e.target.value)} /></div>

                <div className="col-span-2 text-xs uppercase tracking-widest font-semibold text-slate-500 pt-3 border-t border-slate-100 flex items-center gap-2">
                    Residenza
                    {form.lat && form.lng && (
                        <span className="text-emerald-600 normal-case flex items-center gap-1 text-[10px] font-medium" data-testid="anag-geo-ok">
                            <MapPin size={11} /> {form.lat.toFixed(4)}, {form.lng.toFixed(4)}
                        </span>
                    )}
                </div>
                <div className="col-span-2">
                    <Label>Indirizzo</Label>
                    <AddressAutocomplete
                        value={form.indirizzo}
                        onChange={(v) => setU("indirizzo", v)}
                        onSelect={(p) => {
                            setForm((prev) => ({
                                ...prev,
                                indirizzo: (p.indirizzo || prev.indirizzo).toUpperCase(),
                                comune: (p.comune || prev.comune).toUpperCase(),
                                cap: p.cap || prev.cap,
                                provincia: (p.provincia || prev.provincia || "").slice(0, 2).toUpperCase(),
                                lat: p.lat,
                                lng: p.lng,
                                indirizzo_geocoded: p.display_name,
                            }));
                            toast.success("Indirizzo geolocalizzato automaticamente");
                        }}
                        testid="new-anag-indirizzo-autocomplete"
                    />
                </div>
                <div>
                    <Label>Comune</Label>
                    <Input className="uc" value={form.comune} onBlur={geocoda}
                        onChange={(e) => setU("comune", e.target.value)} />
                </div>
                <div>
                    <Label>Provincia</Label>
                    <Input className="uc" maxLength={2} value={form.provincia}
                        onChange={(e) => setU("provincia", e.target.value)} />
                </div>
                <div>
                    <Label>CAP</Label>
                    <Input value={form.cap} onChange={(e) => set("cap", e.target.value)} onBlur={geocoda} />
                </div>

                <div className="col-span-2 text-xs uppercase tracking-widest font-semibold text-slate-500 pt-3 border-t border-slate-100">Operatore assegnato</div>
                <div className="col-span-2">
                    <Label>Collaboratore / Sub-agente</Label>
                    <Select value={form.collaboratore_id || "__none__"} onValueChange={(v) => set("collaboratore_id", v === "__none__" ? "" : v)}>
                        <SelectTrigger data-testid="anag-collab-select"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="__none__">— nessuno —</SelectItem>
                            {collaboratori.map((c) => <SelectItem key={c.id} value={c.id}>{c.name} ({c.role})</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>

                {isPF && (
                    <>
                        <div className="col-span-2 text-xs uppercase tracking-widest font-semibold text-slate-500 pt-3 border-t border-slate-100">Lavoro</div>
                        <div>
                            <Label>Tipologia lavoratore</Label>
                            <Select value={form.tipologia_lavoratore || "__none__"} onValueChange={(v) => set("tipologia_lavoratore", v === "__none__" ? null : v)}>
                                <SelectTrigger data-testid="anag-tipo-lavoro"><SelectValue placeholder="—" /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="__none__">— non specificato —</SelectItem>
                                    <SelectItem value="dipendente">Dipendente</SelectItem>
                                    <SelectItem value="autonomo">Autonomo / P.IVA</SelectItem>
                                    <SelectItem value="professionista">Professionista (albo)</SelectItem>
                                    <SelectItem value="imprenditore">Imprenditore</SelectItem>
                                    <SelectItem value="pensionato">Pensionato</SelectItem>
                                    <SelectItem value="disoccupato">Disoccupato</SelectItem>
                                    <SelectItem value="studente">Studente</SelectItem>
                                    <SelectItem value="casalinga">Casalinga / Casalingo</SelectItem>
                                    <SelectItem value="altro">Altro</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <div>
                            <Label>Professione</Label>
                            <Input value={form.professione || ""}
                                   onChange={(e) => set("professione", e.target.value)}
                                   placeholder="Es: medico, impiegato" />
                        </div>
                    </>
                )}
            </div>

            <DialogFooter>
                {geoLoading && <span className="text-xs text-slate-500 mr-auto">Geolocalizzo...</span>}
                {form._overwrite_id && (
                    <span className="text-xs text-amber-700 bg-amber-100 border border-amber-300 rounded px-2 py-1 mr-auto" data-testid="anag-overwrite-hint">
                        ⚠ Sovrascriverà l&apos;anagrafica esistente
                    </span>
                )}
                <Button data-testid="anag-save-button" onClick={() => save()} className="bg-sky-700 hover:bg-sky-800">
                    {form._overwrite_id ? "Sovrascrivi" : "Salva"}
                </Button>
            </DialogFooter>

            {/* Modale di conferma sovrascrittura duplicato (OCR o Excel) */}
            <DuplicateOverwriteDialog
                open={!!duplicate}
                existing={duplicate?.existing}
                matchOn={duplicate?.match_on}
                fonte={duplicate?.fonte}
                onConfirm={onConfirmOverwrite}
                onCancel={onCancelOverwrite}
            />
        </DialogContent>
    );
}

// ============================================================
// Dialog di conferma sovrascrittura per duplicati (OCR/Excel)
// ============================================================
function DuplicateOverwriteDialog({ open, existing, matchOn, fonte, onConfirm, onCancel }) {
    if (!existing) return null;
    const label = matchOn === "partita_iva" ? "Partita IVA" : "Codice Fiscale";
    const value = matchOn === "partita_iva" ? existing.partita_iva : existing.codice_fiscale;
    return (
        <Dialog open={open} onOpenChange={(v) => !v && onCancel()}>
            <DialogContent className="max-w-md" data-testid="dup-overwrite-dialog">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2 text-amber-800">
                        ⚠ Anagrafica già esistente
                    </DialogTitle>
                    <DialogDescription>
                        {fonte === "auto"
                            ? "L\u2019OCR ha rilevato un\u2019anagrafica con lo stesso identificativo già presente in archivio."
                            : "È già presente un\u2019anagrafica con lo stesso identificativo."}
                    </DialogDescription>
                </DialogHeader>
                <div className="bg-slate-50 border border-slate-200 rounded p-3 text-sm space-y-1">
                    <div><span className="text-slate-500 text-xs uppercase tracking-wider">Ragione sociale</span><br /><b>{existing.ragione_sociale || "—"}</b></div>
                    <div><span className="text-slate-500 text-xs uppercase tracking-wider">{label}</span><br /><span className="font-mono">{value || "—"}</span></div>
                    <div><span className="text-slate-500 text-xs uppercase tracking-wider">Tipo</span><br />{existing.tipo === "persona_giuridica" ? "Azienda / P.G." : "Persona fisica"}</div>
                    {existing.updated_at && (
                        <div className="text-xs text-slate-500">Ultimo aggiornamento: {existing.updated_at.slice(0, 10)}</div>
                    )}
                </div>
                <div className="text-xs text-slate-600">
                    Vuoi <b>sovrascrivere</b> l&apos;anagrafica esistente con i nuovi dati?<br />
                    <span className="text-slate-500">In caso contrario puoi annullare e modificare i dati manualmente prima di salvare.</span>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onCancel} data-testid="dup-cancel-btn">Annulla</Button>
                    <Button onClick={onConfirm} className="bg-amber-600 hover:bg-amber-700" data-testid="dup-overwrite-btn">
                        Sovrascrivi l&apos;esistente
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

// === Badge compliance: Privacy firmata + Documento di riconoscimento ===
function ComplianceBadges({ ana }) {
    const docs = ana?.documenti || {};
    const hasPrivacy = !!(ana?.privacy_firmata_url || docs.privacy_firmata?.url || ana?.consenso_privacy);
    const hasDocId = !!(
        docs.carta_identita?.url || docs.carta_identita ||
        docs.patente?.url || docs.patente ||
        docs.passaporto?.url || docs.passaporto
    );
    return (
        <span className="inline-flex gap-1 ml-2 align-middle">
            <span
                title={hasPrivacy ? "✓ Privacy firmata" : "⚠ Privacy NON firmata"}
                className={`inline-flex items-center justify-center w-4 h-4 rounded-full text-[9px] font-bold cursor-help ${
                    hasPrivacy ? "bg-emerald-100 text-emerald-700 border border-emerald-300" : "bg-amber-100 text-amber-700 border border-amber-300"
                }`}
                data-testid={`badge-privacy-${ana.id}`}
            >
                P
            </span>
            <span
                title={hasDocId ? "✓ Documento di riconoscimento presente (CI/Patente/Passaporto)" : "⚠ Documento di riconoscimento MANCANTE (CI/Patente/Passaporto)"}
                className={`inline-flex items-center justify-center w-4 h-4 rounded-full text-[9px] font-bold cursor-help ${
                    hasDocId ? "bg-emerald-100 text-emerald-700 border border-emerald-300" : "bg-amber-100 text-amber-700 border border-amber-300"
                }`}
                data-testid={`badge-docid-${ana.id}`}
            >
                D
            </span>
        </span>
    );
}


// ============================================================
// Dialog conferma eliminazione anagrafica (con cascade su polizze/sinistri)
// ============================================================
function DeleteAnagraficaDialog({ target, onClose, onDeleted }) {
    const [busy, setBusy] = useState(false);
    const [conflict, setConflict] = useState(null); // {collegati:{polizze,sinistri,allegati}}
    const [confirmText, setConfirmText] = useState("");

    // reset stato quando cambia target
    useEffect(() => {
        setConflict(null);
        setConfirmText("");
    }, [target?.id]);

    if (!target) return null;

    const doDelete = async (force = false) => {
        setBusy(true);
        try {
            const r = await api.delete(`/anagrafiche/${target.id}${force ? "?force=true" : ""}`);
            const cs = r.data?.cascade || {};
            const msg = force && (cs.polizze || cs.sinistri)
                ? `Anagrafica eliminata (cascade: ${cs.polizze} polizze, ${cs.sinistri} sinistri, ${cs.allegati} allegati)`
                : "Anagrafica eliminata";
            toast.success(msg);
            onDeleted();
        } catch (e) {
            if (e.response?.status === 409) {
                setConflict(e.response.data?.detail || {});
            } else {
                toast.error(e.response?.data?.detail || "Errore eliminazione");
            }
        } finally {
            setBusy(false);
        }
    };

    const nome = target.ragione_sociale || `${target.cognome || ""} ${target.nome || ""}`.trim();
    const collegati = conflict?.collegati || {};
    const nCollegati = (collegati.polizze || 0) + (collegati.sinistri || 0);

    return (
        <Dialog open={!!target} onOpenChange={(v) => !v && onClose()}>
            <DialogContent className="max-w-md" data-testid="delete-anag-dialog">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2 text-rose-800">
                        <Trash2 size={18} /> Elimina anagrafica
                    </DialogTitle>
                </DialogHeader>

                {!conflict ? (
                    <>
                        <div className="text-sm text-slate-700">
                            Sei sicuro di voler eliminare <b>{nome}</b>?
                        </div>
                        <div className="text-xs text-slate-500 bg-slate-50 border border-slate-200 rounded p-2">
                            L&apos;operazione è irreversibile. Verrà controllato se esistono polizze o sinistri collegati.
                        </div>
                        <DialogFooter>
                            <Button variant="outline" onClick={onClose} disabled={busy} data-testid="delete-cancel-btn">Annulla</Button>
                            <Button onClick={() => doDelete(false)} disabled={busy} className="bg-rose-600 hover:bg-rose-700" data-testid="delete-confirm-btn">
                                {busy ? "Eliminazione..." : "Elimina"}
                            </Button>
                        </DialogFooter>
                    </>
                ) : (
                    <>
                        <div className="bg-amber-50 border border-amber-300 rounded p-3 text-sm space-y-2">
                            <div className="font-medium text-amber-900 flex items-center gap-1">
                                ⚠ Attenzione: <b>{nCollegati} record collegati</b>
                            </div>
                            <div className="text-amber-800">
                                Eliminando <b>{nome}</b> verranno cancellati IN CASCATA anche:
                            </div>
                            <ul className="text-xs list-disc ml-5 text-amber-900 space-y-0.5">
                                {collegati.polizze > 0 && <li><b>{collegati.polizze}</b> polizze (con relativi titoli e ricevute)</li>}
                                {collegati.sinistri > 0 && <li><b>{collegati.sinistri}</b> sinistri</li>}
                                {collegati.allegati > 0 && <li><b>{collegati.allegati}</b> allegati/documenti</li>}
                                <li>Diario, interviste, avvisi, raccolta dati</li>
                            </ul>
                        </div>
                        <div>
                            <Label className="text-xs">Per confermare, scrivi <b>ELIMINA</b>:</Label>
                            <Input
                                value={confirmText}
                                onChange={(e) => setConfirmText(e.target.value)}
                                placeholder="ELIMINA"
                                data-testid="delete-confirm-text"
                                autoFocus
                            />
                        </div>
                        <DialogFooter>
                            <Button variant="outline" onClick={onClose} disabled={busy} data-testid="delete-force-cancel">Annulla</Button>
                            <Button
                                onClick={() => doDelete(true)}
                                disabled={busy || confirmText !== "ELIMINA"}
                                className="bg-rose-700 hover:bg-rose-800"
                                data-testid="delete-force-btn"
                            >
                                {busy ? "Eliminazione in corso..." : `Elimina TUTTO (${nCollegati + 1} record)`}
                            </Button>
                        </DialogFooter>
                    </>
                )}
            </DialogContent>
        </Dialog>
    );
}

