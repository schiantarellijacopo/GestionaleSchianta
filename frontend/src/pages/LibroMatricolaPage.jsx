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
import { ClipboardList, Car, Search, FileText, Paperclip, X, Ban, AlertTriangle, Plus, ChevronDown, ChevronRight, Building2 } from "lucide-react";
import { toast } from "sonner";

export default function LibroMatricolaPage() {
    const [polizze, setPolizze] = useState(null);
    const [q, setQ] = useState("");
    const [stato, setStato] = useState("all");
    const [expanded, setExpanded] = useState({});   // { polizza_id: bool }
    const [docsApp, setDocsApp] = useState(null);
    const [annullaApp, setAnnullaApp] = useState(null);
    const [conflictApp, setConflictApp] = useState(null);
    const [newAppPol, setNewAppPol] = useState(null);

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
        </div>
    );
}

function PolizzaMatricolaCard({ p, expanded, onToggle, onOpenDocs, onAnnullaApp, onConflictApp, onNewApp }) {
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
                            <Plus size={13} className="mr-1" /> Applicazione
                        </Button>
                    </div>
                </div>
            </div>

            {/* Tabella applicazioni */}
            {expanded && (
                <div className="p-0">
                    {p.applicazioni.length === 0 ? (
                        <div className="p-4 text-center text-xs text-slate-500 italic">
                            Nessuna applicazione registrata su questa polizza —{" "}
                            <button onClick={onNewApp} className="text-sky-700 hover:underline font-semibold"
                                    data-testid={`btn-first-app-${p.id}`}>
                                Aggiungi la prima
                            </button>
                        </div>
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="w-full text-xs border-collapse">
                                <thead className="bg-slate-100">
                                    <tr>
                                        <th className="px-2 py-1.5 text-left border-b border-slate-200">Inserim.</th>
                                        <th className="px-2 py-1.5 text-left border-b border-slate-200">Targa/Matr.</th>
                                        <th className="px-2 py-1.5 text-left border-b border-slate-200">Descrizione</th>
                                        <th className="px-2 py-1.5 text-left border-b border-slate-200">Telaio</th>
                                        <th className="px-2 py-1.5 text-right border-b border-slate-200">Premio</th>
                                        <th className="px-2 py-1.5 text-left border-b border-slate-200">Stato</th>
                                        <th className="px-2 py-1.5 text-left border-b border-slate-200">Cessazione</th>
                                        <th className="px-2 py-1.5 text-center border-b border-slate-200">Azioni</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {p.applicazioni.map((a) => {
                                        const isCessato = !!a.data_cessazione;
                                        // arricchisco l'app col contesto polizza (per i dialog)
                                        const aFull = { ...a, polizza_numero: p.numero_polizza, contraente_nome: p.contraente_nome };
                                        return (
                                            <tr key={a.id} data-testid={`app-row-${a.id}`}
                                                className={`border-b border-slate-100 hover:bg-sky-50/40 ${isCessato ? "bg-rose-50/30 text-slate-500" : ""}`}>
                                                <td className="px-2 py-1.5 font-mono">{a.data_inserimento || "—"}</td>
                                                <td className="px-2 py-1.5 font-mono font-semibold text-sky-700">
                                                    {a.targa || a.matricola || "—"}
                                                </td>
                                                <td className="px-2 py-1.5">{a.descrizione_veicolo || a.descrizione || "—"}</td>
                                                <td className="px-2 py-1.5 font-mono text-[10px] text-slate-500">{a.telaio || "—"}</td>
                                                <td className="px-2 py-1.5 text-right font-mono">{fmtEur(a.premio_lordo || 0)}</td>
                                                <td className="px-2 py-1.5">
                                                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                                                        isCessato ? "bg-rose-100 text-rose-700" : "bg-emerald-100 text-emerald-700"
                                                    }`}>
                                                        {isCessato ? (a.tipo_cessazione || "cessato").toUpperCase() : "ATTIVO"}
                                                    </span>
                                                </td>
                                                <td className="px-2 py-1.5 font-mono">{a.data_cessazione || "—"}</td>
                                                <td className="px-2 py-1.5 text-center">
                                                    <div className="inline-flex items-center gap-1">
                                                        <button onClick={() => onOpenDocs(aFull)}
                                                            className="inline-flex items-center gap-1 text-[10px] px-1.5 py-1 rounded border border-violet-300 text-violet-700 hover:bg-violet-50"
                                                            data-testid={`app-docs-${a.id}`} title="Documenti">
                                                            <Paperclip size={10} /> {a.n_allegati || 0}
                                                        </button>
                                                        {a.targa && (
                                                            <button onClick={() => onConflictApp(aFull)}
                                                                className="inline-flex items-center text-[10px] px-1.5 py-1 rounded border border-amber-300 text-amber-700 hover:bg-amber-50"
                                                                data-testid={`app-conflict-${a.id}`} title="Verifica altre polizze con stessa targa">
                                                                <AlertTriangle size={10} />
                                                            </button>
                                                        )}
                                                        {!isCessato && (
                                                            <button onClick={() => onAnnullaApp(aFull)}
                                                                className="inline-flex items-center text-[10px] px-1.5 py-1 rounded border border-rose-300 text-rose-700 hover:bg-rose-50"
                                                                data-testid={`app-annulla-${a.id}`} title="Annulla applicazione">
                                                                <Ban size={10} />
                                                            </button>
                                                        )}
                                                    </div>
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
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
