import { useEffect, useState, useRef, useMemo, useCallback } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, fmtDate, fmtEur } from "@/lib/api";
import { formatPhone, telHref } from "@/lib/phone";
import { PageHeader, Empty, Loading } from "@/components/Shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter, DialogDescription,
} from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, Search, ScanLine, Calculator, MapPin, X, Mail, Phone, Contact, ChevronRight, Users, Home, Church, Briefcase, Settings, Trash2, Star, Heart, Flag, Award, Target, Bookmark, Tag as TagIcon, Zap } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import AddressAutocomplete from "@/components/AddressAutocomplete";

// Colori per categoria
const CAT_BADGE = {
    con_polizze: { dot: "bg-sky-500", label: "Con polizze", text: "text-sky-700" },
    senza_polizze: { dot: "bg-red-500", label: "Senza polizze", text: "text-red-700" },
    condominio: { dot: "bg-emerald-500", label: "Condominio", text: "text-emerald-700" },
};

export default function Anagrafiche() {
    const { user } = useAuth();
    const [searchParams, setSearchParams] = useSearchParams();
    const [list, setList] = useState(null);
    const [q, setQ] = useState("");
    const [open, setOpen] = useState(false);
    const [tagFilter, setTagFilter] = useState(null);
    const [catFilter, setCatFilter] = useState("all");
    const [stats, setStats] = useState(null);
    const [expanded, setExpanded] = useState({});
    const [networks, setNetworks] = useState({});
    const [kpiDialogOpen, setKpiDialogOpen] = useState(false);
    // filtri da URL (dashboard task)
    const compleannoFilter = searchParams.get("compleanno"); // "oggi" | "settimana" | "mese"
    const docFilter = searchParams.get("doc"); // "scaduti" | "in_scadenza"
    const canCreate = ["admin", "collaboratore", "dipendente"].includes(user?.role);

    const load = useCallback(() => {
        api.get("/anagrafiche", { params: { q: q || undefined, tag: tagFilter || undefined } })
            .then((r) => setList(r.data));
    }, [q, tagFilter]);

    useEffect(() => { load(); }, [load]);
    useEffect(() => { api.get("/anagrafiche/stats").then((r) => setStats(r.data)).catch(() => {}); }, []);

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

    // Tag univoci per chip filtri
    const tagsUnivoci = useMemo(() => {
        if (!list) return [];
        const all = new Set();
        list.forEach((a) => (a.tags || []).forEach((t) => all.add(t)));
        return Array.from(all).sort();
    }, [list]);

    const filtered = useMemo(() => {
        if (!list) return [];
        let out = list;
        if (catFilter !== "all") out = out.filter((a) => a.categoria_ui === catFilter);

        // FILTRO COMPLEANNO (?compleanno=oggi|settimana|mese)
        if (compleannoFilter) {
            const today = new Date();
            const md = (d) => `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
            const todayMd = md(today);
            const weekSet = new Set();
            for (let i = 0; i < 7; i++) {
                const d = new Date(today); d.setDate(today.getDate() + i); weekSet.add(md(d));
            }
            const monthMd = String(today.getMonth() + 1).padStart(2, "0");
            out = out.filter((a) => {
                const dn = (a.data_nascita || "");
                if (dn.length < 10) return false;
                const m = dn.substring(5, 10);
                if (compleannoFilter === "oggi") return m === todayMd;
                if (compleannoFilter === "settimana") return weekSet.has(m);
                if (compleannoFilter === "mese") return dn.substring(5, 7) === monthMd;
                return true;
            });
        }

        // FILTRO DOCUMENTI (?doc=scaduti|in_scadenza)
        if (docFilter) {
            const todayIso = new Date().toISOString().slice(0, 10);
            const in30 = new Date(); in30.setDate(in30.getDate() + 30);
            const in30Iso = in30.toISOString().slice(0, 10);
            out = out.filter((a) => {
                const docs = a.documenti || {};
                if (docFilter === "scaduti") {
                    return Object.values(docs).some((d) => d && d.scadenza && d.scadenza < todayIso);
                }
                if (docFilter === "in_scadenza") {
                    return Object.values(docs).some((d) => d && d.scadenza && d.scadenza >= todayIso && d.scadenza <= in30Iso);
                }
                return true;
            });
        }
        return out;
    }, [list, catFilter, compleannoFilter, docFilter]);

    const clearTaskFilter = () => {
        const p = new URLSearchParams(searchParams);
        p.delete("compleanno");
        p.delete("doc");
        setSearchParams(p);
    };

    const counts = useMemo(() => {
        if (!list) return { con: 0, senza: 0, cond: 0 };
        return {
            con: list.filter((a) => a.categoria_ui === "con_polizze").length,
            senza: list.filter((a) => a.categoria_ui === "senza_polizze").length,
            cond: list.filter((a) => a.categoria_ui === "condominio").length,
        };
    }, [list]);

    return (
        <div data-testid="anagrafiche-page">
            <PageHeader
                title="Anagrafiche clienti"
                subtitle="Persone fisiche e giuridiche presenti a portafoglio"
                actions={
                    canCreate && (
                        <Dialog open={open} onOpenChange={setOpen}>
                            <DialogTrigger asChild>
                                <Button data-testid="anagrafica-new-button" className="bg-sky-700 hover:bg-sky-800">
                                    <Plus size={16} className="mr-1" /> Nuova anagrafica
                                </Button>
                            </DialogTrigger>
                            <NuovaAnagraficaDialog onClose={() => { setOpen(false); load(); }} />
                        </Dialog>
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
                    {list ? `${filtered.length} risultati` : ""}
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
                        <span className="text-amber-700 num">— {filtered.length} risultati</span>
                    </div>
                    <Button size="sm" variant="ghost" onClick={clearTaskFilter} data-testid="anag-clear-task-filter">
                        <X size={14} className="mr-1" /> Rimuovi filtro
                    </Button>
                </div>
            )}

            {/* Chips filtri categoria */}
            <div className="flex flex-wrap items-center gap-2 mb-3">
                <CatChip active={catFilter === "all"} onClick={() => setCatFilter("all")} dot="bg-slate-300" label={`Tutte (${list?.length || 0})`} />
                <CatChip active={catFilter === "con_polizze"} onClick={() => setCatFilter("con_polizze")} dot="bg-sky-500" label={`Con polizze (${counts.con})`} />
                <CatChip active={catFilter === "senza_polizze"} onClick={() => setCatFilter("senza_polizze")} dot="bg-red-500" label={`Senza polizze (${counts.senza})`} />
                <CatChip active={catFilter === "condominio"} onClick={() => setCatFilter("condominio")} dot="bg-emerald-500" label={`Condomini (${counts.cond})`} />
                {tagFilter && (
                    <button onClick={() => setTagFilter(null)} className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full bg-amber-100 text-amber-800 hover:bg-amber-200" data-testid="anag-tag-active">
                        Tag: {tagFilter} <X size={10} />
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

            <div className="bg-white border border-slate-200 rounded-md overflow-hidden">
                {list === null ? <Loading /> : filtered.length === 0 ? <Empty /> : (
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="text-[10px] uppercase tracking-widest text-slate-500 border-b border-slate-200">
                                <th className="w-8 py-3"></th>
                                <th className="text-left py-3 pr-3">Cliente</th>
                                <th className="text-left py-3 pr-3">E-mail</th>
                                <th className="text-left py-3 pr-3">Telefono</th>
                                <th className="text-center py-3 pr-3 text-emerald-700">Polizze</th>
                                <th className="text-left py-3 pr-3">Collaboratore</th>
                                <th className="text-right py-3 pr-3">Premio totale</th>
                                <th className="text-right py-3 pr-3 text-emerald-700">Provvigioni</th>
                                <th className="text-left py-3 pr-3">Tag</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filtered.map((a) => {
                                const cat = CAT_BADGE[a.categoria_ui] || CAT_BADGE.senza_polizze;
                                const isOpen = !!expanded[a.id];
                                const net = networks[a.id];
                                return (
                                    <RigaAnagrafica
                                        key={a.id}
                                        a={a}
                                        cat={cat}
                                        isOpen={isOpen}
                                        net={net}
                                        onToggle={() => toggleExpand(a.id)}
                                        onTagClick={(t) => setTagFilter(t)}
                                    />
                                );
                            })}
                        </tbody>
                    </table>
                )}
            </div>

            <PersonalizzaKpiDialog
                open={kpiDialogOpen}
                onOpenChange={setKpiDialogOpen}
                onChanged={() => api.get("/anagrafiche/stats").then((r) => setStats(r.data)).catch(() => {})}
            />
        </div>
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
                <span className="text-[10px] uppercase tracking-wider text-slate-400">tot.</span>
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

function RigaAnagrafica({ a, cat, isOpen, net, onToggle, onTagClick }) {
    return (
        <>
            <tr className="border-b border-slate-100 hover:bg-slate-50 transition-colors" data-testid={`anagrafica-row-${a.id}`}>
                <td className="py-3 pl-2">
                    <button
                        onClick={onToggle}
                        className="text-slate-400 hover:text-sky-600 transition-colors"
                        data-testid={`anag-expand-${a.id}`}
                        aria-label="Espandi network"
                    >
                        <ChevronRight size={16} className={`transform transition-transform ${isOpen ? "rotate-90" : ""}`} />
                    </button>
                </td>
                <td className="py-3 pr-3">
                    <div className="flex items-center gap-2">
                        <Contact size={16} className="text-slate-400 shrink-0" />
                        <Link
                            to={`/anagrafiche/${a.id}`}
                            className={`hover:underline font-semibold text-[15px] tracking-wide ${cat.text}`}
                        >
                            {a.ragione_sociale}
                        </Link>
                        {a.tipo === "persona_giuridica" && <span className="ml-1 text-[9px] text-slate-400">PG</span>}
                    </div>
                    <ComplianceBadges ana={a} />
                </td>
                <td className="py-3 pr-3 text-xs">
                    {a.email
                        ? <a
                            href={`mailto:${a.email}`}
                            onClick={(e) => e.stopPropagation()}
                            className="inline-flex items-center gap-1 text-sky-700 hover:underline"
                            data-testid={`anag-email-link-${a.id}`}
                          ><Mail size={12} className="text-slate-400" />{a.email}</a>
                        : <span className="text-slate-300">—</span>}
                </td>
                <td className="py-3 pr-3 text-xs">
                    {a.cellulare || a.telefono
                        ? <a
                            href={`tel:${telHref(a.cellulare || a.telefono)}`}
                            onClick={(e) => e.stopPropagation()}
                            className="inline-flex items-center gap-1 text-sky-700 hover:underline"
                            data-testid={`anag-phone-link-${a.id}`}
                          ><Phone size={12} className="text-slate-400" />{formatPhone(a.cellulare || a.telefono)}</a>
                        : <span className="text-slate-300">—</span>}
                </td>
                <td className="py-3 pr-3 text-center text-emerald-700 font-semibold num">
                    {a.polizze_attive_count || 0}
                </td>
                <td className="py-3 pr-3 text-xs">
                    {a.collaboratore_nome
                        ? <span className="text-slate-700">{a.collaboratore_nome}</span>
                        : <span className="text-slate-300">—</span>}
                </td>
                <td className="py-3 pr-3 text-right font-bold num text-slate-900 text-base">
                    {net ? fmtEur(net.root.premio_totale || 0) : <span className="text-slate-300">—</span>}
                </td>
                <td className="py-3 pr-3 text-right font-semibold num text-emerald-700">
                    {net ? fmtEur(net.root.provvigioni_totale || 0) : <span className="text-slate-300">—</span>}
                </td>
                <td className="py-3 pr-3">
                    <div className="flex flex-wrap gap-1">
                        {(a.tags || []).slice(0, 3).map((t) => (
                            <button
                                key={t}
                                onClick={() => onTagClick(t)}
                                className="text-[9px] uppercase px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 hover:bg-sky-100 hover:text-sky-700"
                            >
                                {t}
                            </button>
                        ))}
                        {(a.tags || []).length > 3 && <span className="text-[9px] text-slate-400">+{a.tags.length - 3}</span>}
                    </div>
                </td>
            </tr>
            {isOpen && net && (
                <tr className="bg-slate-50/60 border-b border-slate-200" data-testid={`anag-network-${a.id}`}>
                    <td colSpan={9} className="px-12 py-4">
                        {net.collegati.length === 0 ? (
                            <div className="text-xs text-slate-500 italic">
                                Nessuna anagrafica collegata. Aggiungi familiari, aziende rappresentate o relazioni dalla scheda &gt; Albero genealogico.
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
    });

    useEffect(() => { api.get("/collaboratori").then((r) => setCollaboratori(r.data)); }, []);

    const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
    const setU = (k, v) => set(k, (v || "").toUpperCase());

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

    const save = async () => {
        const isPF = form.tipo === "persona_fisica";
        if (isPF && !form.nome && !form.cognome) { toast.error("Inserisci Cognome o Nome"); return; }
        if (!isPF && !form.ragione_sociale) { toast.error("Inserisci la ragione sociale"); return; }
        const { _ci_file_da_salvare, _visura_file_da_salvare, _amministratori, _dati_extra_visura, ...payload } = form;
        if (isPF && !payload.ragione_sociale) {
            payload.ragione_sociale = `${form.cognome || ""} ${form.nome || ""}`.trim();
        }
        // attacca note dalla visura (forma giuridica, REA, capitale, oggetto sociale)
        if (_dati_extra_visura) {
            const extra = Object.entries(_dati_extra_visura).filter(([, v]) => v).map(([k, v]) => `${k}: ${v}`).join(" · ");
            if (extra) payload.note = (payload.note ? payload.note + "\n" : "") + `[Da visura] ${extra}`;
        }
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
                toast.success(`Ditta + ${_amministratori.length} amministratori creati`);
            } else {
                toast.success("Anagrafica creata");
            }
            onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
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
                        <Input value={form.partita_iva} onChange={(e) => set("partita_iva", e.target.value)} />
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
                <Button data-testid="anag-save-button" onClick={save} className="bg-sky-700 hover:bg-sky-800">Salva</Button>
            </DialogFooter>
        </DialogContent>
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

