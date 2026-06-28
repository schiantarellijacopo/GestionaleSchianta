import { useEffect, useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { api, API_BASE, fmtDate, fmtEur } from "@/lib/api";
import { PageHeader, Loading } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
    Bell, Mail, MessageCircle, Smartphone, FileText, Receipt,
    ChevronRight, ChevronDown, FolderOpen, History, Send, FileDown, Filter, Search,
} from "lucide-react";
import { toast } from "sonner";

const PRESETS = [
    { v: 7, label: "7 giorni" }, { v: 15, label: "15 giorni" }, { v: 30, label: "30 giorni" },
    { v: 60, label: "60 giorni" }, { v: 90, label: "90 giorni" },
];

const CORPO_DEFAULT = `Gentile Cliente,

riteniamo opportuno ricordarLe la scadenza delle rate di premio relative alle coperture assicurative i cui termini risultano sotto evidenziati.
Per il rinnovo e per verificare insieme che tutte le garanzie corrispondano alle Sue attuali esigenze, La aspettiamo in Agenzia, dove continuerà a godere dell'attenzione e del servizio che dedichiamo ai nostri Clienti.
La ringraziamo per l'attenzione e Le inviamo i nostri migliori saluti.`;

export default function Avvisi() {
    const [giorni, setGiorni] = useState(30);
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [tab, setTab] = useState("titoli");
    const [emailTarget, setEmailTarget] = useState(null);
    const [bulkOpen, setBulkOpen] = useState(false);
    const [storicoOpen, setStoricoOpen] = useState(false);
    const [collaboratori, setCollaboratori] = useState([]);

    // Filtri avanzati
    const [showFilters, setShowFilters] = useState(false);
    const [qSearch, setQSearch] = useState("");
    const [filters, setFilters] = useState({
        dal: "", al: "", collaboratore_id: "all", mezzo_pagamento: "all",
    });

    useEffect(() => {
        api.get("/utenti").then((r) => setCollaboratori(
            (r.data || []).filter((u) => ["collaboratore", "dipendente"].includes(u.role))
        )).catch(() => {});
    }, []);

    const load = async () => {
        setLoading(true);
        try {
            const params = { giorni };
            if (filters.dal) params.dal = filters.dal;
            if (filters.al) params.al = filters.al;
            if (filters.collaboratore_id !== "all") params.collaboratore_id = filters.collaboratore_id;
            if (filters.mezzo_pagamento !== "all") params.mezzo_pagamento = filters.mezzo_pagamento;
            const r = await api.get("/avvisi-scadenze/preview", { params });
            setData(r.data);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        } finally { setLoading(false); }
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ },
        [giorni, filters.dal, filters.al, filters.collaboratore_id, filters.mezzo_pagamento]);

    const resetFilters = () => setFilters({ dal: "", al: "", collaboratore_id: "all", mezzo_pagamento: "all" });
    const hasActiveFilters = filters.dal || filters.al || filters.collaboratore_id !== "all" || filters.mezzo_pagamento !== "all";

    // Raggruppa titoli per contraente
    const grupTitoli = useMemo(() => {
        if (!data?.titoli) return [];
        const m = new Map();
        for (const t of data.titoli) {
            const k = t.contraente_id || "_";
            const cur = m.get(k) || {
                contraente_id: t.contraente_id,
                contraente_nome: t.contraente_nome,
                contraente_email: t.contraente_email,
                contraente_cellulare: t.contraente_cellulare,
                titoli: [], totale: 0,
            };
            cur.titoli.push(t);
            cur.totale += t.importo_lordo || 0;
            m.set(k, cur);
        }
        const arr = Array.from(m.values()).sort((a, b) =>
            (a.contraente_nome || "").localeCompare(b.contraente_nome || ""));
        // Filtro testo libero "qSearch" (case-insensitive)
        const q = (qSearch || "").trim().toLowerCase();
        if (!q) return arr;
        return arr.filter((g) => {
            const haystack = [
                g.contraente_nome, g.contraente_email, g.contraente_cellulare,
                ...g.titoli.map((t) => t.numero_polizza),
                ...g.titoli.map((t) => t.targa),
            ].filter(Boolean).join(" ").toLowerCase();
            return haystack.includes(q);
        });
    }, [data, qSearch]);

    const totali = useMemo(() => ({
        polizze: data?.polizze?.length || 0,
        contraenti: grupTitoli.length,
        titoli: data?.titoli?.length || 0,
        importi: grupTitoli.reduce((s, g) => s + g.totale, 0),
    }), [data, grupTitoli]);

    return (
        <div data-testid="avvisi-page">
            <PageHeader
                title={<><Bell className="inline mr-2 -mt-1" size={20} />Avvisi di scadenza</>}
                subtitle="Polizze in scadenza · titoli arretrati · invia notifiche al cliente"
                actions={(
                    <div className="flex items-center gap-2 flex-wrap">
                        <div className="relative">
                            <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400" />
                            <Input
                                placeholder="Cerca contraente, polizza, targa…"
                                value={qSearch}
                                onChange={(e) => setQSearch(e.target.value)}
                                className="pl-7 h-9 w-64 text-sm"
                                data-testid="avvisi-q"
                            />
                        </div>
                        <Button
                            variant={hasActiveFilters ? "default" : "outline"}
                            size="sm"
                            onClick={() => setShowFilters((s) => !s)}
                            data-testid="toggle-filters"
                            className={hasActiveFilters ? "bg-amber-500 hover:bg-amber-600" : ""}
                        >
                            <Filter size={14} className="mr-1" />Filtri{hasActiveFilters && " (attivi)"}
                        </Button>
                        <Button variant="outline" size="sm" onClick={() => setStoricoOpen(true)} data-testid="open-storico-btn">
                            <History size={14} className="mr-1" />Storico invii
                        </Button>
                        <Select value={String(giorni)} onValueChange={(v) => setGiorni(Number(v))}>
                            <SelectTrigger className="w-36" data-testid="periodo-select"><SelectValue /></SelectTrigger>
                            <SelectContent>{PRESETS.map((p) => <SelectItem key={p.v} value={String(p.v)}>{p.label}</SelectItem>)}</SelectContent>
                        </Select>
                    </div>
                )}
            />

            {showFilters && (
                <Card className="border-slate-200 p-4 mb-4" data-testid="filters-panel">
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-3 items-end">
                        <div>
                            <label className="text-xs font-medium text-slate-600">Dal</label>
                            <Input type="date" value={filters.dal}
                                onChange={(e) => setFilters((p) => ({ ...p, dal: e.target.value }))}
                                data-testid="filter-dal" />
                        </div>
                        <div>
                            <label className="text-xs font-medium text-slate-600">Al</label>
                            <Input type="date" value={filters.al}
                                onChange={(e) => setFilters((p) => ({ ...p, al: e.target.value }))}
                                data-testid="filter-al" />
                        </div>
                        <div>
                            <label className="text-xs font-medium text-slate-600">Collaboratore</label>
                            <Select value={filters.collaboratore_id}
                                onValueChange={(v) => setFilters((p) => ({ ...p, collaboratore_id: v }))}>
                                <SelectTrigger data-testid="filter-collab"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="all">Tutti</SelectItem>
                                    {collaboratori.map((c) => (
                                        <SelectItem key={c.id} value={c.id}>{c.name || c.email}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <div>
                            <label className="text-xs font-medium text-slate-600">Mezzo pagamento</label>
                            <Select value={filters.mezzo_pagamento}
                                onValueChange={(v) => setFilters((p) => ({ ...p, mezzo_pagamento: v }))}>
                                <SelectTrigger data-testid="filter-mezzo"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="all">Tutti</SelectItem>
                                    {["bonifico", "RID/SDD", "contanti", "assegno", "POS", "bollettino", "carta_credito", "compagnia"].map((m) => (
                                        <SelectItem key={m} value={m}>{m}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <div>
                            {hasActiveFilters && (
                                <Button variant="outline" size="sm" onClick={resetFilters} className="w-full" data-testid="filter-reset">
                                    Reset filtri
                                </Button>
                            )}
                        </div>
                    </div>
                </Card>
            )}

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                <KpiCard icon={<FileText size={16} />} label="Polizze in scadenza" value={totali.polizze} accent="sky" />
                <KpiCard icon={<Receipt size={16} />} label="Titoli arretrati" value={totali.titoli} accent="rose" />
                <KpiCard label="Contraenti coinvolti" value={totali.contraenti} accent="amber" />
                <KpiCard label="Importi arretrati" value={fmtEur(totali.importi)} accent="emerald" monetary />
            </div>

            <div className="flex gap-2 mb-3 border-b border-slate-200">
                <TabBtn active={tab === "titoli"} onClick={() => setTab("titoli")} testid="tab-avvisi-titoli">
                    Titoli arretrati per contraente ({totali.contraenti})
                </TabBtn>
                <TabBtn active={tab === "polizze"} onClick={() => setTab("polizze")} testid="tab-avvisi-polizze">
                    Polizze in scadenza ({totali.polizze})
                </TabBtn>
            </div>

            {loading || !data ? <Loading /> : (
                tab === "titoli"
                    ? <TitoliByContraente
                        gruppi={grupTitoli}
                        onBulk={(ids) => setBulkOpen({ titoli_ids: ids })}
                        onEmail={setEmailTarget}
                    />
                    : <PolizzeTable items={data.polizze || []} onEmail={setEmailTarget} />
            )}

            {emailTarget && (
                <EmailDialog item={emailTarget} onClose={() => setEmailTarget(null)} />
            )}
            {bulkOpen && (
                <BulkAvvisoDialog titoli_ids={bulkOpen.titoli_ids} onClose={() => { setBulkOpen(false); load(); }} />
            )}
            {storicoOpen && (
                <StoricoAvvisiDialog onClose={() => setStoricoOpen(false)} />
            )}
        </div>
    );
}

function KpiCard({ icon, label, value, accent = "slate", monetary }) {
    const c = { rose: "border-l-rose-500", amber: "border-l-amber-500", sky: "border-l-sky-500", emerald: "border-l-emerald-500", slate: "border-l-slate-500" };
    return (
        <Card className={`border border-slate-200 border-l-4 ${c[accent]} p-3`}>
            <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-slate-500">{icon}{label}</div>
            <div className={`mt-1 font-semibold text-xl text-slate-900 ${monetary ? "num" : ""}`}>{value}</div>
        </Card>
    );
}

function TabBtn({ active, onClick, children, testid }) {
    return (
        <button type="button" onClick={onClick} data-testid={testid}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${active ? "border-sky-600 text-sky-700" : "border-transparent text-slate-600 hover:text-slate-900"}`}>
            {children}
        </button>
    );
}

function TitoliByContraente({ gruppi, onBulk, onEmail }) {
    const [expanded, setExpanded] = useState(new Set());
    const [selTitoli, setSelTitoli] = useState(new Set());

    const toggleExp = (k) => setExpanded((p) => {
        const n = new Set(p); n.has(k) ? n.delete(k) : n.add(k); return n;
    });
    const toggleTitolo = (id) => setSelTitoli((p) => {
        const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n;
    });
    const toggleGruppo = (g) => {
        const ids = g.titoli.map((t) => t.id);
        const allSel = ids.every((i) => selTitoli.has(i));
        setSelTitoli((p) => {
            const n = new Set(p);
            ids.forEach((i) => allSel ? n.delete(i) : n.add(i));
            return n;
        });
    };
    const selectAll = () => {
        const allIds = gruppi.flatMap((g) => g.titoli.map((t) => t.id));
        if (selTitoli.size === allIds.length) setSelTitoli(new Set());
        else setSelTitoli(new Set(allIds));
    };

    if (!gruppi.length) {
        return <Card className="p-8 text-center text-slate-500 border-slate-200">Nessun titolo arretrato.</Card>;
    }

    return (
        <Card className="border-slate-200 overflow-x-auto" data-testid="avvisi-titoli-grouped">
            <div className="p-3 bg-slate-50 border-b border-slate-200 flex items-center gap-3">
                <div className="text-sm font-medium">{selTitoli.size} titoli selezionati</div>
                <Button variant="outline" size="sm" onClick={selectAll} data-testid="select-all-titoli">
                    {selTitoli.size > 0 ? "Deseleziona" : "Seleziona tutti"}
                </Button>
                <Button
                    size="sm"
                    disabled={selTitoli.size === 0}
                    onClick={() => onBulk(Array.from(selTitoli))}
                    className="bg-sky-700 hover:bg-sky-800"
                    data-testid="bulk-send-btn"
                >
                    <Send size={13} className="mr-1" />Invia avvisi ({selTitoli.size})
                </Button>
            </div>
            <div className="tbl-scroll" style={{ "--c1-w": "40px", "--c2-w": "30px" }}>
            <table className="tbl freeze-3 w-full min-w-[1100px]">
                <thead>
                    <tr>
                        <th className="w-[40px] text-center"></th>
                        <th className="w-[30px]"></th>
                        <th>Contraente</th>
                        <th>Cell</th>
                        <th>Email</th>
                        <th>Mezzi disp.</th>
                        <th className="text-center">N. titoli</th>
                        <th className="text-right">Totale</th>
                        <th className="w-[150px] text-center">Notifica</th>
                    </tr>
                </thead>
                <tbody>
                    {gruppi.map((g) => {
                        const k = g.contraente_id || "_";
                        const isExp = expanded.has(k);
                        const idsSel = g.titoli.filter((t) => selTitoli.has(t.id)).length;
                        const allSel = idsSel === g.titoli.length;
                        const hasMail = !!g.contraente_email;
                        const cell = g.contraente_cellulare?.replace(/[^\d+]/g, "");
                        const hasCell = !!cell;
                        const mezzi = [hasMail && "Email", hasCell && "WhatsApp"].filter(Boolean).join(" · ") || "—";
                        return (
                            <>
                                <tr key={k} className="bg-slate-50/40 hover:bg-sky-50/50" data-testid={`gruppo-${k}`}>
                                    <td className="text-center">
                                        <input
                                            type="checkbox"
                                            checked={allSel}
                                            ref={(el) => { if (el) el.indeterminate = idsSel > 0 && !allSel; }}
                                            onChange={() => toggleGruppo(g)}
                                            data-testid={`group-check-${k}`}
                                        />
                                    </td>
                                    <td>
                                        <button type="button" onClick={() => toggleExp(k)} className="text-slate-500 hover:text-slate-900" data-testid={`expand-${k}`}>
                                            {isExp ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                        </button>
                                    </td>
                                    <td className="font-medium">
                                        <Link to={`/anagrafiche/${g.contraente_id}`} className="text-sky-700 hover:underline">
                                            {g.contraente_nome || "—"}
                                        </Link>
                                    </td>
                                    <td className="text-xs num">{g.contraente_cellulare || "—"}</td>
                                    <td className="text-xs">{g.contraente_email || "—"}</td>
                                    <td className="text-xs text-slate-700">{mezzi}</td>
                                    <td className="text-center text-xs font-medium">{g.titoli.length}</td>
                                    <td className="num text-right font-semibold text-amber-700">{fmtEur(g.totale)}</td>
                                    <td>
                                        <div className="flex justify-center gap-1">
                                            {hasMail && (
                                                <Button size="sm" variant="outline" className="h-7 w-7 p-0" title="Email"
                                                    onClick={() => onEmail({ kind: "gruppo", gruppo: g })}
                                                    data-testid={`btn-email-${k}`}>
                                                    <Mail size={12} className="text-sky-700" />
                                                </Button>
                                            )}
                                            {hasCell && (
                                                <Button size="sm" variant="outline" className="h-7 w-7 p-0" title="WhatsApp"
                                                    onClick={() => openWA(g)}
                                                    data-testid={`btn-wa-${k}`}>
                                                    <MessageCircle size={12} className="text-emerald-600" />
                                                </Button>
                                            )}
                                            {hasCell && (
                                                <Button size="sm" variant="outline" className="h-7 w-7 p-0" title="SMS (Twilio fine progetto)"
                                                    onClick={() => toast.info("SMS via Twilio - in arrivo")}
                                                    data-testid={`btn-sms-${k}`}>
                                                    <Smartphone size={12} className="text-slate-400" />
                                                </Button>
                                            )}
                                        </div>
                                    </td>
                                </tr>
                                {isExp && g.titoli.map((t) => (
                                    <tr key={t.id} className="bg-white text-xs" data-testid={`titolo-${t.id}`}>
                                        <td className="text-center">
                                            <input
                                                type="checkbox"
                                                checked={selTitoli.has(t.id)}
                                                onChange={() => toggleTitolo(t.id)}
                                                data-testid={`titolo-check-${t.id}`}
                                            />
                                        </td>
                                        <td></td>
                                        <td colSpan={3} className="pl-10">
                                            <Link to={`/polizze/${t.polizza_id}`} className="text-amber-700 font-medium num hover:underline">
                                                {t.numero_polizza || "—"}
                                            </Link>
                                            <span className="text-slate-500 ml-2">{t.compagnia_nome} · {t.ramo}</span>
                                        </td>
                                        <td className="text-slate-700">scad. {fmtDate(t.scadenza)} ({Math.abs(t.giorni_alla_scadenza ?? 0)}gg fa)</td>
                                        <td></td>
                                        <td></td>
                                        <td className="num text-right text-rose-700 font-medium">{fmtEur(t.importo_lordo)}</td>
                                        <td></td>
                                    </tr>
                                ))}
                            </>
                        );
                    })}
                </tbody>
            </table>
            </div>
        </Card>
    );
}

function openWA(g) {
    const cell = g.contraente_cellulare?.replace(/[^\d+]/g, "");
    if (!cell) { toast.error("Nessun cellulare"); return; }
    const tot = g.titoli.reduce((s, t) => s + (t.importo_lordo || 0), 0);
    const msg = `Buongiorno ${g.contraente_nome || ""}, le segnaliamo ${g.titoli.length} titolo/i scaduti per un totale di ${tot.toFixed(2)} €. La invitiamo a contattarci.`;
    api.post("/storico-avvisi/registra", {
        canale: "whatsapp", contraente_id: g.contraente_id, contraente_nome: g.contraente_nome,
        destinatario: cell, titoli_ids: g.titoli.map((t) => t.id),
        soggetto: "Sollecito titoli scaduti",
    }).catch(() => {});
    window.open(`https://wa.me/${cell}?text=${encodeURIComponent(msg)}`, "_blank", "noopener");
}

function PolizzeTable({ items, onEmail }) {
    if (!items.length) return <Card className="p-8 text-center text-slate-500 border-slate-200">Nessuna polizza in scadenza.</Card>;
    return (
        <Card className="border-slate-200 overflow-x-auto">
            <table className="tbl w-full min-w-[900px]">
                <thead><tr>
                    <th>Contraente</th><th>Polizza</th><th>Compagnia</th><th>Scadenza</th>
                    <th className="text-center">GG</th><th className="text-right">Premio €</th><th className="text-center">Notifica</th>
                </tr></thead>
                <tbody>{items.map((p) => {
                    const cell = p.contraente_cellulare?.replace(/[^\d+]/g, "");
                    const hasMail = !!p.contraente_email;
                    return (
                        <tr key={p.id} data-testid={`row-pol-${p.id}`}>
                            <td>
                                <Link to={`/anagrafiche/${p.contraente_id}`} className="text-sky-700 hover:underline">{p.contraente_nome || "—"}</Link>
                                <div className="text-[10px] text-slate-500">{p.contraente_email || ""}{cell ? ` · ${cell}` : ""}</div>
                            </td>
                            <td><Link to={`/polizze/${p.id}`} className="text-amber-700 hover:underline num">{p.numero_polizza}</Link></td>
                            <td className="text-xs">{p.compagnia_nome}</td>
                            <td className="num">{fmtDate(p.scadenza)}</td>
                            <td className="num text-center">{p.giorni_alla_scadenza}gg</td>
                            <td className="num text-right">{fmtEur(p.premio_lordo)}</td>
                            <td className="text-center">
                                <div className="flex justify-center gap-1">
                                    {hasMail && (
                                        <Button size="sm" variant="outline" className="h-7 w-7 p-0"
                                            onClick={() => onEmail({ kind: "polizza", polizza: p })} data-testid={`btn-email-pol-${p.id}`}>
                                            <Mail size={12} className="text-sky-700" />
                                        </Button>
                                    )}
                                    {cell && (
                                        <Button size="sm" variant="outline" className="h-7 w-7 p-0"
                                            onClick={() => {
                                                const msg = `Buongiorno ${p.contraente_nome || ""}, la sua polizza ${p.numero_polizza} scade il ${fmtDate(p.scadenza)}. Premio: ${fmtEur(p.premio_lordo)}.`;
                                                api.post("/storico-avvisi/registra", { canale: "whatsapp", contraente_id: p.contraente_id, contraente_nome: p.contraente_nome, polizza_id: p.id }).catch(() => {});
                                                window.open(`https://wa.me/${cell}?text=${encodeURIComponent(msg)}`, "_blank");
                                            }} data-testid={`btn-wa-pol-${p.id}`}>
                                            <MessageCircle size={12} className="text-emerald-600" />
                                        </Button>
                                    )}
                                </div>
                            </td>
                        </tr>
                    );
                })}</tbody>
            </table>
        </Card>
    );
}

function BulkAvvisoDialog({ titoli_ids, onClose }) {
    const [soggetto, setSoggetto] = useState("Promemoria pagamento polizza/e in scadenza");
    const [corpo, setCorpo] = useState(CORPO_DEFAULT);
    const [sending, setSending] = useState(false);
    const [generatingPdf, setGeneratingPdf] = useState(false);

    const invia = async () => {
        setSending(true);
        try {
            const r = await api.post("/avvisi/invia-bulk-titoli", { titoli_ids, soggetto, corpo_lettera: corpo });
            const sk = r.data.skipped?.length || 0;
            toast.success(`Inviate ${r.data.inviate} email${sk ? ` · ${sk} skippate (email mancante)` : ""}`);
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        } finally { setSending(false); }
    };

    const scaricaPdf = async () => {
        setGeneratingPdf(true);
        try {
            const r = await api.post("/avvisi/pdf-bulk",
                { titoli_ids, soggetto, corpo_lettera: corpo },
                { responseType: "blob" }
            );
            const url = window.URL.createObjectURL(new Blob([r.data], { type: "application/pdf" }));
            const a = document.createElement("a");
            a.href = url;
            a.download = `avvisi_scadenza_${new Date().toISOString().slice(0, 10)}.pdf`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
            toast.success("PDF generato");
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore PDF");
        } finally { setGeneratingPdf(false); }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-2xl" data-testid="bulk-dialog">
                <DialogHeader><DialogTitle>Invio bulk avvisi · {titoli_ids.length} titoli</DialogTitle></DialogHeader>
                <div className="space-y-3 py-2">
                    <div className="text-xs bg-sky-50 border border-sky-200 rounded p-2 text-sky-900">
                        I {titoli_ids.length} titoli verranno raggruppati per contraente. Puoi inviare la lettera <strong>via email</strong> (1 email per cliente con tabella HTML) oppure <strong>scaricare il PDF</strong> con tutti gli avvisi pronti per la stampa/archivio.
                    </div>
                    <div>
                        <label className="text-xs font-medium">Oggetto</label>
                        <Input value={soggetto} onChange={(e) => setSoggetto(e.target.value)} data-testid="bulk-soggetto" />
                    </div>
                    <div>
                        <label className="text-xs font-medium">Corpo lettera (modificabile)</label>
                        <Textarea value={corpo} onChange={(e) => setCorpo(e.target.value)} rows={10} className="text-sm" data-testid="bulk-corpo" />
                    </div>
                </div>
                <DialogFooter className="sm:justify-between">
                    <Button variant="outline" onClick={onClose}>Annulla</Button>
                    <div className="flex gap-2">
                        <Button
                            variant="outline"
                            onClick={scaricaPdf}
                            disabled={generatingPdf || sending}
                            data-testid="bulk-pdf"
                            className="border-rose-200 text-rose-700 hover:bg-rose-50"
                        >
                            <FileDown size={14} className="mr-1" />
                            {generatingPdf ? "Genero PDF…" : "Scarica PDF"}
                        </Button>
                        <Button
                            onClick={invia}
                            disabled={sending || generatingPdf}
                            className="bg-sky-700 hover:bg-sky-800"
                            data-testid="bulk-confirm"
                        >
                            <Mail size={14} className="mr-1" />
                            {sending ? "Invio…" : "Invia email"}
                        </Button>
                    </div>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function EmailDialog({ item, onClose }) {
    const isGruppo = item.kind === "gruppo";
    const g = item.gruppo;
    const p = item.polizza;
    const [to, setTo] = useState(isGruppo ? (g.contraente_email || "") : (p.contraente_email || ""));
    const [soggetto, setSoggetto] = useState(isGruppo ? "Promemoria titoli in scadenza" : `Promemoria polizza ${p.numero_polizza}`);
    const [corpo, setCorpo] = useState(CORPO_DEFAULT);
    const [sending, setSending] = useState(false);

    const invia = async () => {
        if (!to) { toast.error("Email destinatario obbligatoria"); return; }
        setSending(true);
        try {
            if (isGruppo) {
                await api.post("/avvisi/invia-bulk-titoli", {
                    titoli_ids: g.titoli.map((t) => t.id),
                    soggetto, corpo_lettera: corpo,
                });
            } else {
                await api.post("/email/invia-singola", {
                    to, subject: soggetto, body_text: corpo,
                    body_html: `<pre style="font-family:Georgia,serif">${corpo}</pre>`,
                    contraente_id: p.contraente_id, contraente_nome: p.contraente_nome,
                    polizza_id: p.id, tipo_avviso: "email_polizza",
                });
            }
            toast.success("Email inviata");
            onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        finally { setSending(false); }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-2xl" data-testid="email-dialog">
                <DialogHeader><DialogTitle>Invia avviso email{isGruppo ? ` a ${g.contraente_nome}` : ""}</DialogTitle></DialogHeader>
                <div className="space-y-3 py-2">
                    <div>
                        <label className="text-xs font-medium">Destinatario</label>
                        <Input type="email" value={to} onChange={(e) => setTo(e.target.value)} data-testid="email-to" disabled={isGruppo} />
                    </div>
                    <div>
                        <label className="text-xs font-medium">Oggetto</label>
                        <Input value={soggetto} onChange={(e) => setSoggetto(e.target.value)} data-testid="email-soggetto" />
                    </div>
                    <div>
                        <label className="text-xs font-medium">Corpo (modificabile)</label>
                        <Textarea value={corpo} onChange={(e) => setCorpo(e.target.value)} rows={10} className="text-sm" data-testid="email-corpo" />
                    </div>
                    {isGruppo && (
                        <div className="text-[11px] text-slate-500 bg-slate-50 p-2 rounded">
                            La tabella con {g.titoli.length} titoli ({fmtEur(g.totale)}) sarà aggiunta automaticamente sotto al corpo.
                        </div>
                    )}
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Annulla</Button>
                    <Button onClick={invia} disabled={sending} className="bg-sky-700 hover:bg-sky-800" data-testid="email-send">
                        {sending ? "Invio…" : "Invia"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function StoricoAvvisiDialog({ onClose }) {
    const [list, setList] = useState(null);
    useEffect(() => { api.get("/storico-avvisi", { params: { limit: 100 } }).then((r) => setList(r.data)); }, []);
    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-4xl" data-testid="storico-dialog">
                <DialogHeader><DialogTitle><History className="inline mr-2 -mt-1" size={18} />Storico invii</DialogTitle></DialogHeader>
                {list === null ? <Loading /> : list.length === 0 ? (
                    <div className="py-8 text-center text-slate-500 text-sm">Nessun avviso ancora inviato.</div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="tbl w-full text-sm">
                            <thead><tr>
                                <th>Quando</th><th>Canale</th><th>Contraente</th><th>Destinatario</th><th>Oggetto</th>
                                <th className="text-center">N.titoli</th><th className="text-right">Importo</th><th>Stato</th>
                            </tr></thead>
                            <tbody>
                                {list.map((x) => (
                                    <tr key={x.id}>
                                        <td className="num text-xs">{x.sent_at?.slice(0, 16).replace("T", " ")}</td>
                                        <td className="text-xs uppercase">{x.canale}</td>
                                        <td>{x.contraente_nome || "—"}</td>
                                        <td className="text-xs">{x.destinatario || "—"}</td>
                                        <td className="text-xs truncate max-w-[200px]">{x.soggetto || "—"}</td>
                                        <td className="text-center text-xs">{x.n_titoli || x.titoli_ids?.length || "—"}</td>
                                        <td className="num text-right">{x.totale_importo ? fmtEur(x.totale_importo) : "—"}</td>
                                        <td>
                                            <span className={`text-[10px] px-2 py-0.5 rounded ${x.stato === "inviato" ? "bg-emerald-100 text-emerald-700" : x.stato === "errore" ? "bg-rose-100 text-rose-700" : "bg-slate-100 text-slate-600"}`}>
                                                {x.stato}
                                            </span>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
                <DialogFooter><Button variant="outline" onClick={onClose}>Chiudi</Button></DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
