/**
 * LibroMatricolaPage — vista raggruppata per POLIZZA MADRE con le sue applicazioni.
 *
 * Per ogni polizza libro matricola mostra:
 * - intestazione (numero polizza, ramo, contraente, compagnia, effetto/scadenza)
 * - conteggi (applicazioni totali, attive, cessate)
 * - tabella applicazioni collassabile con azioni (documenti, cessa, verifica conflitto targa)
 * - pulsante "Nuova applicazione"
 */
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtEur } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import DocumentiSezioneSplit from "@/components/DocumentiSezioneSplit";
import TargaConflictWidget from "@/components/TargaConflictWidget";
import IntestatarioAutocomplete from "@/components/IntestatarioAutocomplete";
import { ApplicazioniTable } from "@/components/LibroMatricolaTab";
import { ClipboardList, Car, Search, FileText, Paperclip, X, Ban, AlertTriangle, Plus, ChevronDown, ChevronRight, Building2, Trash2 } from "lucide-react";
import { toast } from "sonner";

function EditIntestatarioDialog({ app, onClose }) {
    const [nome, setNome] = useState(app.intestatario || "");
    const [anaId, setAnaId] = useState(app.intestatario_anagrafica_id || null);
    const [saving, setSaving] = useState(false);
    const salva = async () => {
        setSaving(true);
        try {
            await api.put(`/libro-matricola/applicazioni/${app.id}`, {
                intestatario: nome || null,
                intestatario_anagrafica_id: anaId || null,
            });
            toast.success("Intestatario aggiornato");
            onClose(true);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore aggiornamento intestatario");
            setSaving(false);
        }
    };
    return (
        <Dialog open onOpenChange={() => onClose(false)}>
            <DialogContent className="max-w-md" data-testid="lm-edit-intestatario-dialog">
                <DialogHeader>
                    <DialogTitle>Cambia intestatario — {app.targa || app.matricola || `#${app.numero}`}</DialogTitle>
                </DialogHeader>
                <div className="space-y-2 py-2">
                    <label className="text-xs font-medium text-slate-600">Intestatario (persona/azienda)</label>
                    <IntestatarioAutocomplete
                        value={nome}
                        anagraficaId={anaId}
                        onChange={(name, id) => { setNome(name); setAnaId(id); }}
                    />
                    <p className="text-[11px] text-slate-400">
                        Puoi digitare un nome libero oppure collegare un'anagrafica esistente.
                    </p>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={() => onClose(false)} data-testid="lm-edit-intestatario-cancel">Annulla</Button>
                    <Button onClick={salva} disabled={saving} data-testid="lm-edit-intestatario-save">
                        {saving ? "Salvataggio…" : "Salva"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

export default function LibroMatricolaPage() {
    const [polizze, setPolizze] = useState(null);
    const [q, setQ] = useState("");
    const [stato, setStato] = useState("all");
    const [showStoriche, setShowStoriche] = useState(false);   // false = solo attive (default)
    const [expanded, setExpanded] = useState({});   // { polizza_id: bool }
    const [docsApp, setDocsApp] = useState(null);
    const [annullaApp, setAnnullaApp] = useState(null);
    const [conflictApp, setConflictApp] = useState(null);
    const [newAppPol, setNewAppPol] = useState(null);
    const [migrating, setMigrating] = useState(false);
    const [migrationReport, setMigrationReport] = useState(null);
    const [ambiguousGroups, setAmbiguousGroups] = useState(null);

    const load = () => {
        const params = {};
        if (stato !== "all") params.stato = stato;
        if (q) params.q = q;
        api.get("/libro-matricola/polizze", { params })
            .then((r) => setPolizze(r.data || []))
            .catch(() => setPolizze([]));
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [stato]);
    useEffect(() => { const t = setTimeout(load, 300); return () => clearTimeout(t); /* eslint-disable-next-line */ }, [q]);

    const totali = useMemo(() => {
        if (!polizze) return { pol: 0, apps: 0, attive: 0, cessate: 0, premio: 0 };
        return polizze.reduce((acc, p) => {
            acc.pol++;
            acc.apps += p.n_applicazioni_totali;
            acc.attive += p.n_applicazioni_attive;
            acc.cessate += p.n_applicazioni_cessate;
            acc.premio += p.premio_applicazioni_totale || 0;
            return acc;
        }, { pol: 0, apps: 0, attive: 0, cessate: 0, premio: 0 });
    }, [polizze]);

    return (
        <div className="space-y-4" data-testid="libro-matricola-page">
            <PageHeader
                title={<span className="flex items-center gap-2"><ClipboardList className="text-violet-600" /> Libro Matricola</span>}
                subtitle="Polizze a libro matricola con relative applicazioni (veicoli/dipendenti coperti)"
            />

            {/* KPI */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                <Kpi label="Polizze madri" value={totali.pol} icon={FileText} color="violet" />
                <Kpi label="Applicaz. totali" value={totali.apps} icon={ClipboardList} color="sky" />
                <Kpi label="Attive" value={totali.attive} icon={Car} color="emerald" />
                <Kpi label="Cessate" value={totali.cessate} icon={Car} color="rose" />
                <Kpi label="Premio applicaz." value={fmtEur(totali.premio)} icon={FileText} color="amber" mono />
            </div>

            {/* Filtri */}
            <Card className="p-3 flex flex-wrap items-center gap-2">
                <div className="relative flex-1 min-w-[240px]">
                    <Search size={14} className="absolute left-2 top-2.5 text-slate-400" />
                    <Input value={q} onChange={(e) => setQ(e.target.value)}
                        placeholder="Cerca per polizza, ramo, prodotto…"
                        className="pl-8 text-sm" data-testid="lm-search" />
                </div>
                <Select value={stato} onValueChange={setStato}>
                    <SelectTrigger className="w-56" data-testid="lm-stato"><SelectValue /></SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">Tutte le polizze</SelectItem>
                        <SelectItem value="attivo">Con almeno 1 applicazione attiva</SelectItem>
                        <SelectItem value="cessato">Con applicazioni cessate</SelectItem>
                    </SelectContent>
                </Select>
                <Button size="sm" variant="ghost"
                        onClick={() => setExpanded(polizze?.reduce((a, p) => ({ ...a, [p.id]: true }), {}) || {})}
                        className="text-[11px]">
                    Espandi tutte
                </Button>
                <Button size="sm" variant="ghost"
                        onClick={() => setExpanded({})}
                        className="text-[11px]">
                    Comprimi tutte
                </Button>
                <Button size="sm" variant={showStoriche ? "default" : "outline"}
                        onClick={() => setShowStoriche(s => !s)}
                        className={`text-[11px] ${showStoriche ? "bg-slate-700 hover:bg-slate-800 text-white" : ""}`}
                        data-testid="lm-toggle-storiche">
                    {showStoriche ? "Nascondi storiche" : "Mostra storiche"}
                </Button>
                <Button size="sm" variant="outline"
                        onClick={async () => {
                            if (!window.confirm("Vuoi provare a collegare automaticamente gli intestatari delle applicazioni alle anagrafiche esistenti?\n\nPrima verrà mostrata un'anteprima (dry-run).")) return;
                            setMigrating(true);
                            try {
                                const preview = await api.post("/libro-matricola/migra-intestatari?dry_run=true");
                                setMigrationReport({ ...preview.data, phase: "preview" });
                            } catch (e) {
                                toast.error(e.response?.data?.detail || "Errore migrazione");
                            } finally { setMigrating(false); }
                        }}
                        disabled={migrating}
                        className="text-[11px] border-violet-300 text-violet-700 hover:bg-violet-50"
                        data-testid="lm-migra-intestatari-btn">
                    <Building2 size={11} className="mr-1" /> {migrating ? "…" : "Migra intestatari → Anagrafiche"}
                </Button>
                <Button size="sm" variant="outline"
                        onClick={async () => {
                            try {
                                const r = await api.get("/libro-matricola/intestatari-ambigui");
                                if (!r.data || r.data.length === 0) {
                                    toast.info("Nessun intestatario ambiguo da risolvere 🎉");
                                    return;
                                }
                                setAmbiguousGroups(r.data);
                            } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
                        }}
                        className="text-[11px] border-amber-300 text-amber-700 hover:bg-amber-50"
                        data-testid="lm-risolvi-ambigui-btn">
                    <AlertTriangle size={11} className="mr-1" /> Risolvi ambigui
                </Button>
                <div className="text-xs text-slate-500 ml-auto font-mono">
                    {polizze?.length || 0} polizze
                </div>
            </Card>

            {/* Lista polizze madri */}
            {polizze === null ? <Loading /> :
             polizze.length === 0 ? (
                <Empty message="Nessuna polizza a libro matricola registrata. Crea una polizza in Portafoglio con il flag 'Libro Matricola' oppure imposta il prodotto libreria con 'is_libro_matricola=true'." />
             ) : (
                <div className="space-y-3">
                    {polizze.map((p) => (
                        <PolizzaMatricolaCard
                            key={p.id}
                            p={p}
                            expanded={!!expanded[p.id]}
                            showStoriche={showStoriche}
                            setShowStoriche={setShowStoriche}
                            onToggle={() => setExpanded({ ...expanded, [p.id]: !expanded[p.id] })}
                            onOpenDocs={setDocsApp}
                            onAnnullaApp={setAnnullaApp}
                            onConflictApp={setConflictApp}
                            onNewApp={() => setNewAppPol(p)}
                        />
                    ))}
                </div>
            )}

            {/* Dialogs */}
            {docsApp && (
                <DocsApplicazioneDialog app={docsApp} onClose={() => { setDocsApp(null); load(); }} />
            )}
            {annullaApp && (
                <AnnullaApplicazioneDialog app={annullaApp} onClose={() => { setAnnullaApp(null); load(); }} />
            )}
            {conflictApp && (
                <ConflittoTargaDialog app={conflictApp} onClose={() => setConflictApp(null)} />
            )}
            {newAppPol && (
                <NuovaApplicazioneDialog polizza={newAppPol} onClose={() => { setNewAppPol(null); load(); }} />
            )}
            {migrationReport && (
                <MigrationReportDialog report={migrationReport}
                    onConfirm={async () => {
                        try {
                            setMigrating(true);
                            const r = await api.post("/libro-matricola/migra-intestatari?dry_run=false");
                            toast.success(`Collegate ${r.data.collegate} applicazioni · Ambigue ${r.data.ambigue} · Non trovate ${r.data.non_trovate}`);
                            setMigrationReport(null);
                            load();
                        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
                        finally { setMigrating(false); }
                    }}
                    onClose={() => setMigrationReport(null)}
                />
            )}
            {ambiguousGroups && (
                <AmbiguiWizardDialog
                    groups={ambiguousGroups}
                    onResolved={(remaining) => {
                        if (!remaining || remaining.length === 0) {
                            toast.success("Tutti gli intestatari ambigui risolti 🎉");
                            setAmbiguousGroups(null);
                            load();
                        } else {
                            setAmbiguousGroups(remaining);
                        }
                    }}
                    onClose={() => { setAmbiguousGroups(null); load(); }}
                />
            )}
        </div>
    );
}

function PolizzaMatricolaCard({ p, expanded, showStoriche, setShowStoriche, onToggle, onOpenDocs, onAnnullaApp, onConflictApp, onNewApp }) {
    const [innerQ, setInnerQ] = useState("");
    const [sortBy, setSortBy] = useState("numero");   // numero | targa | intestatario | data | valore | stato | esclusione
    const [sortDir, setSortDir] = useState("asc");
    const [editIntest, setEditIntest] = useState(null);
    const [showEscluse, setShowEscluse] = useState(false);
    const eliminaTutte = async () => {
        const n = (p.applicazioni || []).length;
        if (!n) { toast.info("Nessuna applicazione da eliminare"); return; }
        if (!window.confirm(`Eliminare TUTTE le ${n} applicazioni di questa polizza (${p.numero_polizza})? L'operazione non è reversibile.`)) return;
        try {
            const r = await api.delete(`/libro-matricola/polizze/${p.id}/applicazioni`);
            toast.success(`Eliminate ${r.data.eliminate} applicazioni`);
            window.location.reload();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore eliminazione"); }
    };
    const changeSort = (col) => {
        if (sortBy === col) setSortDir(d => d === "asc" ? "desc" : "asc");
        else { setSortBy(col); setSortDir("asc"); }
    };
    const sortIcon = (col) => sortBy === col ? (sortDir === "asc" ? " ▲" : " ▼") : "";
    return (
        <Card className="overflow-hidden" data-testid={`polizza-lm-${p.id}`}>
            {/* Header polizza madre */}
            <div className="bg-gradient-to-r from-violet-50 to-sky-50 border-b border-slate-200 p-3">
                <div className="flex items-start justify-between gap-3">
                    <button onClick={onToggle} className="flex items-start gap-2 flex-1 text-left"
                            data-testid={`toggle-${p.id}`}>
                        {expanded ? <ChevronDown size={16} className="mt-0.5 text-slate-600" />
                                  : <ChevronRight size={16} className="mt-0.5 text-slate-600" />}
                        <div className="flex-1">
                            <div className="flex items-baseline gap-2 flex-wrap">
                                <Link to={`/polizze/${p.id}`}
                                      onClick={(e) => e.stopPropagation()}
                                      className="text-base font-bold text-sky-800 hover:underline font-mono">
                                    {p.numero_polizza}
                                </Link>
                                <span className="text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded bg-violet-100 text-violet-800">
                                    {p.ramo}
                                </span>
                                {p.prodotto && (
                                    <span className="text-[11px] text-slate-600 italic">{p.prodotto}</span>
                                )}
                                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded uppercase ${
                                    p.stato === "attiva" ? "bg-emerald-100 text-emerald-800" :
                                    p.stato === "sospesa" ? "bg-amber-100 text-amber-800" :
                                    "bg-rose-100 text-rose-800"
                                }`}>{p.stato}</span>
                            </div>
                            <div className="text-xs text-slate-600 mt-1 flex items-center gap-3 flex-wrap">
                                <span><Building2 size={11} className="inline mr-0.5" /> {p.contraente_nome}</span>
                                <span>· {p.compagnia_nome}</span>
                                <span>· Effetto <strong>{p.effetto}</strong> → Scadenza <strong>{p.scadenza}</strong></span>
                                <span>· {p.frazionamento}</span>
                            </div>
                        </div>
                    </button>
                    <div className="flex items-center gap-4 shrink-0">
                        <MiniStat label="Totali" value={p.n_applicazioni_totali} color="text-slate-800" />
                        <MiniStat label="Attive" value={p.n_applicazioni_attive} color="text-emerald-700" />
                        <MiniStat label="Cessate" value={p.n_applicazioni_cessate} color="text-rose-700" />
                        <MiniStat label="Premio" value={fmtEur(p.premio_applicazioni_totale)} color="text-sky-800" mono />
                        <Button size="sm" onClick={onNewApp}
                                className="bg-emerald-600 hover:bg-emerald-700 text-white"
                                data-testid={`btn-new-app-${p.id}`}>
                            <Plus size={13} className="mr-1" /> Nuova applicazione
                        </Button>
                        <Button size="sm" variant="outline" onClick={eliminaTutte}
                                className="text-rose-700 border-rose-300 hover:bg-rose-50"
                                data-testid={`btn-del-all-apps-${p.id}`}
                                title="Elimina TUTTE le applicazioni di questa polizza">
                            <Trash2 size={13} className="mr-1" /> Elimina tutte
                        </Button>
                    </div>
                </div>
            </div>

            {/* Tabella applicazioni */}
            {expanded && (
                <div className="p-0">
                    {/* Barra ricerca + filtri interni */}
                    <div className="p-2 bg-slate-50 border-b border-slate-200 flex flex-wrap items-center gap-2">
                        <Input
                            value={innerQ}
                            onChange={(e) => setInnerQ(e.target.value)}
                            placeholder="Cerca targa, intestatario, veicolo, matricola…"
                            className="h-8 text-xs w-72"
                            data-testid={`lm-card-search-${p.id}`}
                        />
                        <div className="text-[10px] text-slate-500 ml-auto">
                            Ordinamento: {sortBy} {sortDir}
                        </div>
                    </div>
                    {(() => {
                        const term = innerQ.trim().toLowerCase();
                        const matchTerm = (a) => {
                            if (!term) return true;
                            const veic = [a.marca, a.modello, a.tipo_veicolo, a.descrizione_veicolo].filter(Boolean).join(" ");
                            const hay = [a.targa, a.matricola, a.intestatario, veic, a.telaio,
                                a.data_inclusione, a.data_esclusione, a.numero].filter(Boolean).join(" ").toLowerCase();
                            return hay.includes(term);
                        };
                        const isEsclusa = (a) => {
                            const st = (a.stato || "").toLowerCase();
                            return Boolean(a.data_esclusione || a.data_cessazione)
                                || ["annullata", "sostituita", "cessata", "esclusa"].includes(st);
                        };
                        const cmp = (a, b, key) => {
                            const va = a[key] ?? "", vb = b[key] ?? "";
                            if (typeof va === "number" || typeof vb === "number") return (Number(va) || 0) - (Number(vb) || 0);
                            return String(va).localeCompare(String(vb), "it", { sensitivity: "base" });
                        };
                        const keyMap = { numero: "numero", targa: "targa", intestatario: "intestatario",
                            data: "data_inclusione", esclusione: "data_esclusione", valore: "valore_veicolo", stato: "stato" };
                        const sortApps = (arr) => [...arr].sort((a, b) => {
                            const r = cmp(a, b, keyMap[sortBy] || "numero");
                            return sortDir === "asc" ? r : -r;
                        });
                        const base = p.applicazioni.filter(matchTerm);
                        const attive = sortApps(base.filter((a) => !isEsclusa(a)));
                        const escluse = sortApps(base.filter(isEsclusa));

                        if (attive.length === 0 && escluse.length === 0) {
                            return (
                                <div className="p-4 text-center text-xs text-slate-500 italic">
                                    {p.applicazioni.length === 0 ? (
                                        <>Nessuna applicazione registrata su questa polizza —{" "}
                                            <button onClick={onNewApp} className="text-sky-700 hover:underline font-semibold"
                                                    data-testid={`btn-first-app-${p.id}`}>Aggiungi la prima</button>
                                        </>
                                    ) : <>Nessun risultato per la ricerca corrente.</>}
                                </div>
                            );
                        }
                        const commonHandlers = {
                            sortBy, sortDir, onSort: changeSort,
                            onEdit: (a) => { window.location.href = `/polizze/${p.id}?applicazione=${a.id}`; },
                            onEditIntestatario: (a) => setEditIntest({ ...a, polizza_id: p.id }),
                            onDelete: async (a) => {
                                if (!window.confirm(`Eliminare l'applicazione ${a.targa || a.matricola || a.numero}?`)) return;
                                try { await api.delete(`/libro-matricola/applicazioni/${a.id}`); toast.success("Applicazione eliminata"); window.location.reload(); }
                                catch (e) { toast.error(e.response?.data?.detail || "Errore eliminazione"); }
                            },
                            onDocs: (a) => onOpenDocs({ ...a, polizza_numero: p.numero_polizza, contraente_nome: p.contraente_nome }),
                            onConflict: (a) => onConflictApp({ ...a, polizza_numero: p.numero_polizza, contraente_nome: p.contraente_nome }),
                        };
                        return (
                            <>
                                {attive.length > 0 ? (
                                    <ApplicazioniTable
                                        items={attive}
                                        {...commonHandlers}
                                        onSostituisci={(a) => { window.location.href = `/polizze/${p.id}?applicazione=${a.id}&action=sostituisci`; }}
                                        onAnnulla={(a) => onAnnullaApp({ ...a, polizza_numero: p.numero_polizza, contraente_nome: p.contraente_nome })}
                                    />
                                ) : (
                                    <div className="p-3 text-center text-xs text-slate-500 italic">Nessuna applicazione attiva.</div>
                                )}
                                {escluse.length > 0 && (
                                    <div className="border-t border-slate-200">
                                        <button onClick={() => setShowEscluse((v) => !v)}
                                            className="w-full px-4 py-2 text-left text-xs font-semibold uppercase tracking-wider text-amber-800 bg-amber-100 hover:bg-amber-200 flex items-center gap-1"
                                            data-testid={`lm-toggle-escluse-${p.id}`}>
                                            {showEscluse ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                                            Escluse ({escluse.length})
                                        </button>
                                        {showEscluse && (
                                            <ApplicazioniTable items={escluse} isStorico {...commonHandlers} />
                                        )}
                                    </div>
                                )}
                            </>
                        );
                    })()}
                </div>
            )}
            {editIntest && (
                <EditIntestatarioDialog app={editIntest}
                    onClose={(reload) => { setEditIntest(null); if (reload) window.location.reload(); }} />
            )}
        </Card>
    );
}

function MiniStat({ label, value, color, mono }) {
    return (
        <div className="text-center">
            <div className="text-[9px] uppercase tracking-wider text-slate-500">{label}</div>
            <div className={`text-sm font-bold ${color} ${mono ? "font-mono" : ""}`}>{value}</div>
        </div>
    );
}

const KPI_COLORS = {
    violet: "border-l-violet-500",
    emerald: "border-l-emerald-500",
    rose: "border-l-rose-500",
    sky: "border-l-sky-500",
    amber: "border-l-amber-500",
};

function Kpi({ label, value, icon: Icon, color, mono }) {
    return (
        <Card className={`p-3 border-l-4 ${KPI_COLORS[color]} bg-white`}>
            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-slate-500">
                <Icon size={11} /> {label}
            </div>
            <div className={`text-xl font-bold mt-0.5 ${mono ? "font-mono" : ""}`}>{value}</div>
        </Card>
    );
}

function DocsApplicazioneDialog({ app, onClose }) {
    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-3xl" data-testid="lm-docs-dialog">
                <DialogHeader>
                    <DialogTitle className="flex items-center justify-between">
                        <span>
                            <Car className="inline mr-1 text-sky-600" size={16} />
                            Documenti veicolo · <span className="font-mono">{app.targa || app.matricola || "—"}</span>
                            <span className="ml-2 text-xs text-slate-500 font-normal">
                                Pol. {app.polizza_numero} · {app.contraente_nome}
                            </span>
                        </span>
                        <button onClick={onClose}><X size={16} /></button>
                    </DialogTitle>
                </DialogHeader>
                <DocumentiSezioneSplit
                    entita_tipo="polizza"
                    entita_id={app.polizza_id}
                    applicazione_matricola_id={app.id}
                    canEdit={true}
                    titolo={`Documenti del veicolo ${app.targa || app.matricola || ""}`}
                    sottotitolo="Allega libretto, foto, certificati. Separa visibili al cliente da interni."
                    categorie={[
                        { key: "libretto_circolazione", label: "Libretto", icon: "📕", default_visibile: true },
                        { key: "foto_veicolo", label: "Foto", icon: "📸", default_visibile: true },
                        { key: "certificato_proprieta", label: "Cert. proprietà", icon: "📜", default_visibile: false },
                        { key: "preventivo_riparazione", label: "Preventivo", icon: "🔧", default_visibile: false },
                    ]}
                />
            </DialogContent>
        </Dialog>
    );
}

function AnnullaApplicazioneDialog({ app, onClose }) {
    const [tipo, setTipo] = useState("venduta");
    const [dataCess, setDataCess] = useState(new Date().toISOString().slice(0, 10));
    const [motivo, setMotivo] = useState("");
    const [busy, setBusy] = useState(false);
    const submit = async () => {
        if (!dataCess) { toast.error("Data cessazione obbligatoria"); return; }
        setBusy(true);
        try {
            await api.post(`/libro-matricola/applicazioni/${app.id}/annulla`, {
                data_cessazione: dataCess,
                tipo_cessazione: tipo,
                motivo_dettaglio: motivo || null,
            });
            toast.success(`Applicazione ${app.targa || app.matricola} annullata (${tipo})`);
            onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        finally { setBusy(false); }
    };
    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-lg" data-testid="lm-annulla-dialog">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Ban className="text-rose-600" size={16} /> Annulla applicazione veicolo
                    </DialogTitle>
                </DialogHeader>
                <div className="text-xs bg-amber-50 border border-amber-200 rounded p-2 text-amber-800 mb-2">
                    <b>Veicolo:</b> <span className="font-mono">{app.targa || app.matricola}</span> — {app.descrizione_veicolo || ""}
                    <div>Polizza {app.polizza_numero} · {app.contraente_nome}</div>
                </div>
                <div className="space-y-3">
                    <div>
                        <label className="text-xs font-medium text-slate-600 block mb-1">Motivo cessazione *</label>
                        <select value={tipo} onChange={(e) => setTipo(e.target.value)}
                            className="w-full h-9 border border-slate-300 rounded px-2 text-sm" data-testid="lm-annulla-tipo">
                            <option value="venduta">🏷 Venduta</option>
                            <option value="demolita">🔨 Demolita</option>
                            <option value="esportata">🌍 Esportata</option>
                            <option value="rubata">🚨 Rubata</option>
                            <option value="sostituita">🔄 Sostituita</option>
                            <option value="cessata_altro">📋 Altro motivo</option>
                        </select>
                    </div>
                    <div>
                        <label className="text-xs font-medium text-slate-600 block mb-1">Data cessazione *</label>
                        <input type="date" value={dataCess} onChange={(e) => setDataCess(e.target.value)}
                            className="w-full h-9 border border-slate-300 rounded px-2 text-sm" data-testid="lm-annulla-data" />
                    </div>
                    <div>
                        <label className="text-xs font-medium text-slate-600 block mb-1">Note / dettaglio</label>
                        <textarea rows={2} value={motivo} onChange={(e) => setMotivo(e.target.value)}
                            className="w-full border border-slate-300 rounded px-2 py-1 text-sm" data-testid="lm-annulla-motivo" />
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Annulla</Button>
                    <Button onClick={submit} disabled={busy}
                        className="bg-rose-600 hover:bg-rose-700 text-white"
                        data-testid="lm-annulla-conferma">
                        {busy ? "…" : "Conferma cessazione"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function ConflittoTargaDialog({ app, onClose }) {
    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-2xl" data-testid="lm-conflict-dialog">
                <DialogHeader>
                    <DialogTitle className="flex items-center justify-between">
                        <span>
                            <AlertTriangle className="inline mr-1 text-amber-600" size={16} />
                            Altre polizze con targa <span className="font-mono">{app.targa}</span>
                        </span>
                        <button onClick={onClose}><X size={16} /></button>
                    </DialogTitle>
                </DialogHeader>
                <TargaConflictWidget targa={app.targa} excludeId={app.polizza_id} compact={false} />
            </DialogContent>
        </Dialog>
    );
}

function NuovaApplicazioneDialog({ polizza, onClose }) {
    const [form, setForm] = useState({
        polizza_id: polizza.id,
        data_inserimento: new Date().toISOString().slice(0, 10),
        targa: "",
        matricola: "",
        telaio: "",
        descrizione_veicolo: "",
        premio_lordo: 0,
        intestatario: "",
        intestatario_anagrafica_id: null,
    });
    const [busy, setBusy] = useState(false);

    const submit = async () => {
        if (!form.targa && !form.matricola) {
            toast.error("Inserisci una Targa o una Matricola");
            return;
        }
        setBusy(true);
        try {
            await api.post("/libro-matricola/applicazioni", form);
            toast.success("Applicazione creata");
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore creazione");
        } finally { setBusy(false); }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-lg" data-testid="lm-new-app-dialog">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Plus className="text-emerald-600" size={16} />
                        Nuova applicazione · Polizza {polizza.numero_polizza}
                    </DialogTitle>
                </DialogHeader>
                <div className="text-xs bg-sky-50 border border-sky-200 rounded p-2 text-sky-900 mb-2">
                    {polizza.contraente_nome} · {polizza.ramo} · {polizza.compagnia_nome}
                </div>
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <label className="text-xs font-medium text-slate-600 block mb-1">Data inserimento *</label>
                        <Input type="date" value={form.data_inserimento}
                               onChange={(e) => setForm({ ...form, data_inserimento: e.target.value })}
                               data-testid="new-app-data" />
                    </div>
                    <div>
                        <label className="text-xs font-medium text-slate-600 block mb-1">Premio lordo</label>
                        <Input type="number" step="0.01" value={form.premio_lordo}
                               onChange={(e) => setForm({ ...form, premio_lordo: parseFloat(e.target.value) || 0 })}
                               data-testid="new-app-premio" />
                    </div>
                    <div>
                        <label className="text-xs font-medium text-slate-600 block mb-1">Targa</label>
                        <Input value={form.targa}
                               onChange={(e) => setForm({ ...form, targa: e.target.value.toUpperCase() })}
                               placeholder="AB123CD" className="font-mono uppercase"
                               data-testid="new-app-targa" />
                    </div>
                    <div>
                        <label className="text-xs font-medium text-slate-600 block mb-1">Matricola</label>
                        <Input value={form.matricola}
                               onChange={(e) => setForm({ ...form, matricola: e.target.value })}
                               placeholder="es. M-001"
                               data-testid="new-app-matricola" />
                    </div>
                    <div className="col-span-2">
                        <label className="text-xs font-medium text-slate-600 block mb-1">Telaio</label>
                        <Input value={form.telaio}
                               onChange={(e) => setForm({ ...form, telaio: e.target.value.toUpperCase() })}
                               placeholder="Numero telaio" className="font-mono"
                               data-testid="new-app-telaio" />
                    </div>
                    <div className="col-span-2">
                        <label className="text-xs font-medium text-slate-600 block mb-1">Descrizione (marca, modello, dipendente…)</label>
                        <Input value={form.descrizione_veicolo}
                               onChange={(e) => setForm({ ...form, descrizione_veicolo: e.target.value })}
                               placeholder="es. Fiat Panda 1.2 - blu"
                               data-testid="new-app-descrizione" />
                    </div>
                    <div className="col-span-2">
                        <label className="text-xs font-medium text-slate-600 block mb-1">
                            Intestatario · Anagrafica cliente
                        </label>
                        <IntestatarioAutocomplete
                            value={form.intestatario}
                            anagraficaId={form.intestatario_anagrafica_id}
                            onChange={(name, anagraficaId) => setForm({
                                ...form,
                                intestatario: name,
                                intestatario_anagrafica_id: anagraficaId,
                            })}
                        />
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Annulla</Button>
                    <Button onClick={submit} disabled={busy}
                            className="bg-emerald-600 hover:bg-emerald-700 text-white"
                            data-testid="new-app-submit">
                        {busy ? "…" : "Crea applicazione"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}




/** Dialog di anteprima + conferma migrazione intestatari → anagrafiche. */
function MigrationReportDialog({ report, onConfirm, onClose }) {
    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-2xl" data-testid="lm-migration-dialog">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Building2 className="text-violet-600" size={16} />
                        Anteprima migrazione intestatari → Anagrafiche
                    </DialogTitle>
                </DialogHeader>
                <div className="space-y-3 text-sm">
                    <div className="grid grid-cols-4 gap-2">
                        <div className="bg-slate-50 border border-slate-200 rounded p-2 text-center">
                            <div className="text-[10px] uppercase text-slate-500">Totali</div>
                            <div className="text-lg font-bold">{report.totali_da_migrare}</div>
                        </div>
                        <div className="bg-emerald-50 border border-emerald-200 rounded p-2 text-center">
                            <div className="text-[10px] uppercase text-emerald-700">Collegate</div>
                            <div className="text-lg font-bold text-emerald-700">{report.collegate}</div>
                        </div>
                        <div className="bg-amber-50 border border-amber-200 rounded p-2 text-center">
                            <div className="text-[10px] uppercase text-amber-700">Ambigue</div>
                            <div className="text-lg font-bold text-amber-700">{report.ambigue}</div>
                        </div>
                        <div className="bg-rose-50 border border-rose-200 rounded p-2 text-center">
                            <div className="text-[10px] uppercase text-rose-700">Non trovate</div>
                            <div className="text-lg font-bold text-rose-700">{report.non_trovate}</div>
                        </div>
                    </div>
                    {report.esempi_ambigui?.length > 0 && (
                        <div>
                            <div className="text-xs font-semibold text-amber-700 mb-1">
                                ⚠️ Ambigue (più di 1 anagrafica corrisponde — verifica manuale):
                            </div>
                            <ul className="text-[11px] text-slate-600 max-h-40 overflow-y-auto bg-amber-50/40 border border-amber-100 rounded p-2 space-y-1">
                                {report.esempi_ambigui.slice(0, 10).map((ex, i) => (
                                    <li key={i}><b>{ex.intestatario}</b> — {ex.possibili_anagrafica_ids.length} candidate</li>
                                ))}
                            </ul>
                        </div>
                    )}
                    {report.esempi_non_trovati?.length > 0 && (
                        <div>
                            <div className="text-xs font-semibold text-rose-700 mb-1">
                                ❌ Non trovate (nessuna anagrafica corrisponde):
                            </div>
                            <ul className="text-[11px] text-slate-600 max-h-32 overflow-y-auto bg-rose-50/40 border border-rose-100 rounded p-2 space-y-1">
                                {report.esempi_non_trovati.slice(0, 10).map((ex, i) => (
                                    <li key={i}>{ex.intestatario}</li>
                                ))}
                            </ul>
                        </div>
                    )}
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Annulla</Button>
                    <Button onClick={onConfirm}
                            className="bg-violet-600 hover:bg-violet-700 text-white"
                            disabled={report.collegate === 0}
                            data-testid="lm-migration-confirm">
                        Conferma e collega {report.collegate} applicazioni
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}


/** Wizard per risolvere manualmente gli intestatari ambigui (>1 anagrafica match).
 * Mostra un gruppo alla volta con:
 *  - il testo intestatario e il numero di applicazioni impattate
 *  - le anagrafiche candidate con dati distintivi (CF/PIVA/città/n° polizze già collegate)
 *  - selezione radio + "Applica a tutte" o "Salta questo gruppo"
 */
function AmbiguiWizardDialog({ groups, onResolved, onClose }) {
    const [index, setIndex] = useState(0);
    const [selectedId, setSelectedId] = useState(null);
    const [busy, setBusy] = useState(false);
    const current = groups[index];

    if (!current) return null;

    const applica = async () => {
        if (!selectedId) { toast.error("Seleziona un'anagrafica"); return; }
        setBusy(true);
        try {
            const r = await api.post("/libro-matricola/risolvi-ambiguo", {
                intestatario: current.intestatario,
                anagrafica_id: selectedId,
                applicazione_ids: current.applicazione_ids,
            });
            toast.success(`Collegate ${r.data.aggiornate} applicazioni a ${current.candidati.find(c => c.id === selectedId)?.label}`);
            // Rimuovi il gruppo appena risolto
            const remaining = groups.filter((_, i) => i !== index);
            setSelectedId(null);
            if (remaining.length === 0) {
                onResolved([]);
            } else {
                // Passa al successivo (se era l'ultimo, torna al primo)
                setIndex(i => Math.min(i, remaining.length - 1));
                onResolved(remaining);
            }
        } catch (e) { toast.error(e.response?.data?.detail || "Errore risoluzione"); }
        finally { setBusy(false); }
    };

    const salta = () => {
        setSelectedId(null);
        if (index + 1 < groups.length) {
            setIndex(index + 1);
        } else {
            toast.info("Fine gruppi da risolvere.");
            onClose();
        }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-3xl" data-testid="lm-ambigui-dialog">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <AlertTriangle className="text-amber-600" size={16} />
                        Risolvi intestatari ambigui — {index + 1} / {groups.length}
                    </DialogTitle>
                </DialogHeader>
                <div className="space-y-4">
                    <div className="bg-amber-50 border border-amber-200 rounded p-3 text-sm">
                        <div className="text-xs text-amber-700 uppercase tracking-wider mb-1">Intestatario da collegare</div>
                        <div className="text-lg font-bold text-slate-800">{current.intestatario}</div>
                        <div className="text-xs text-slate-600 mt-1">
                            <b>{current.n_applicazioni}</b> applicazioni impattate
                            {current.targhe_esempio?.length > 0 && (
                                <> · Targhe esempio: <span className="font-mono">{current.targhe_esempio.slice(0, 4).join(", ")}
                                {current.targhe_esempio.length > 4 && "…"}</span></>
                            )}
                        </div>
                    </div>
                    <div>
                        <div className="text-xs font-semibold text-slate-700 mb-2">
                            Scegli l&apos;anagrafica corretta:
                        </div>
                        <div className="space-y-2 max-h-80 overflow-y-auto">
                            {current.candidati.map((c) => {
                                const isSel = selectedId === c.id;
                                const dettagli = [c.codice_fiscale, c.partita_iva, c.comune, c.provincia]
                                    .filter(Boolean).join(" · ");
                                return (
                                    <button key={c.id}
                                        onClick={() => setSelectedId(c.id)}
                                        className={`w-full text-left border rounded p-3 transition ${
                                            isSel ? "border-sky-500 bg-sky-50 ring-2 ring-sky-200" : "border-slate-200 hover:border-slate-400"
                                        }`}
                                        data-testid={`ambiguo-candidato-${c.id}`}>
                                        <div className="flex items-start gap-2">
                                            <input type="radio" checked={isSel} onChange={() => setSelectedId(c.id)}
                                                   className="mt-1" readOnly />
                                            <div className="flex-1">
                                                <div className="font-semibold text-sm">{c.label}
                                                    <span className="ml-2 text-[10px] text-slate-500 uppercase">
                                                        {c.tipo_soggetto || "—"}
                                                    </span>
                                                </div>
                                                {dettagli && (
                                                    <div className="text-[11px] text-slate-500 mt-0.5 font-mono">{dettagli}</div>
                                                )}
                                                <div className="text-[10px] text-slate-500 mt-1 flex gap-3">
                                                    <span className="inline-flex items-center gap-1">
                                                        <FileText size={10} /> {c.n_polizze_collegate} polizze
                                                    </span>
                                                    <span className="inline-flex items-center gap-1">
                                                        <ClipboardList size={10} /> {c.n_applicazioni_collegate} applicazioni
                                                    </span>
                                                    <Link to={`/anagrafiche/${c.id}`} target="_blank"
                                                          className="text-sky-700 hover:underline ml-auto">
                                                        Apri scheda →
                                                    </Link>
                                                </div>
                                            </div>
                                        </div>
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                </div>
                <DialogFooter className="flex-wrap gap-2">
                    <Button variant="ghost" onClick={onClose}>Chiudi</Button>
                    <Button variant="outline" onClick={salta} data-testid="ambiguo-salta">
                        Salta questo →
                    </Button>
                    <Button onClick={applica} disabled={busy || !selectedId}
                            className="bg-emerald-600 hover:bg-emerald-700 text-white"
                            data-testid="ambiguo-applica">
                        {busy ? "…" : `Applica a tutte le ${current.n_applicazioni} applicazioni`}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}


