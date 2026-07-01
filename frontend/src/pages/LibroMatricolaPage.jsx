/**
 * LibroMatricolaPage — pagina standalone del libro matricola con tabella
 * filtrabile, intestazione bloccata in alto, sezione documenti per ogni veicolo
 * (apre dropzone allegati per applicazione_matricola_id).
 */
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtEur, API_BASE } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import DocumentiSezioneSplit from "@/components/DocumentiSezioneSplit";
import TargaConflictWidget from "@/components/TargaConflictWidget";
import { ClipboardList, Car, Search, FileText, Paperclip, X, Ban, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { Dialog as Dlg2, DialogContent as DC2, DialogHeader as DH2, DialogTitle as DT2, DialogFooter as DF2 } from "@/components/ui/dialog";

export default function LibroMatricolaPage() {
    const [items, setItems] = useState(null);
    const [q, setQ] = useState("");
    const [stato, setStato] = useState("all");
    const [polFilter, setPolFilter] = useState("");
    const [docsApp, setDocsApp] = useState(null);
    const [annullaApp, setAnnullaApp] = useState(null);
    const [conflictApp, setConflictApp] = useState(null);

    const load = () => {
        const params = {};
        if (stato !== "all") params.stato = stato;
        if (polFilter) params.polizza_id = polFilter;
        api.get("/libro-matricola", { params }).then((r) => setItems(r.data || []));
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [stato, polFilter]);

    const filtered = useMemo(() => {
        if (!items) return [];
        const term = q.trim().toLowerCase();
        if (!term) return items;
        return items.filter((a) => {
            const blob = `${a.targa || ""} ${a.descrizione_veicolo || ""} ${a.matricola || ""} ${a.telaio || ""} ${a.polizza_numero || ""} ${a.contraente_nome || ""}`.toLowerCase();
            return blob.includes(term);
        });
    }, [items, q]);

    const totali = useMemo(() => {
        if (!items) return { tot: 0, attivi: 0, cessati: 0, premio: 0 };
        return items.reduce((acc, a) => {
            acc.tot++;
            if (a.data_cessazione) acc.cessati++; else acc.attivi++;
            acc.premio += a.premio_lordo || 0;
            return acc;
        }, { tot: 0, attivi: 0, cessati: 0, premio: 0 });
    }, [items]);

    return (
        <div className="space-y-4" data-testid="libro-matricola-page">
            <PageHeader
                title={<span className="flex items-center gap-2"><ClipboardList className="text-violet-600" /> Libro Matricola</span>}
                subtitle="Applicazioni matricola — veicoli/macchinari/dipendenti coperti da polizze a libro"
            />

            {/* KPI */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Kpi label="Applicazioni totali" value={totali.tot} icon={ClipboardList} color="violet" />
                <Kpi label="Attive" value={totali.attivi} icon={Car} color="emerald" />
                <Kpi label="Cessate" value={totali.cessati} icon={Car} color="rose" />
                <Kpi label="Premio lordo tot." value={fmtEur(totali.premio)} icon={FileText} color="sky" mono />
            </div>

            {/* Filtri */}
            <Card className="p-3 flex flex-wrap items-center gap-2">
                <div className="relative flex-1 min-w-[240px]">
                    <Search size={14} className="absolute left-2 top-2.5 text-slate-400" />
                    <Input value={q} onChange={(e) => setQ(e.target.value)}
                        placeholder="Cerca per targa, telaio, matricola, polizza, cliente…"
                        className="pl-8 text-sm" data-testid="lm-search" />
                </div>
                <Select value={stato} onValueChange={setStato}>
                    <SelectTrigger className="w-40" data-testid="lm-stato"><SelectValue /></SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">Tutti gli stati</SelectItem>
                        <SelectItem value="attivo">Solo attivi</SelectItem>
                        <SelectItem value="cessato">Solo cessati</SelectItem>
                    </SelectContent>
                </Select>
                <div className="text-xs text-slate-500 ml-auto font-mono">{filtered.length} / {items?.length || 0}</div>
            </Card>

            {/* Tabella con HEADER STICKY */}
            {items === null ? <Loading /> : filtered.length === 0 ? <Empty message="Nessuna applicazione registrata" /> : (
                <Card className="overflow-hidden">
                    <div className="max-h-[70vh] overflow-y-auto relative">
                        <table className="w-full text-xs border-collapse">
                            <thead className="sticky top-0 z-10 bg-slate-100 shadow-sm">
                                <tr>
                                    <th className="px-2 py-2 text-left border-b border-slate-300">Inserim.</th>
                                    <th className="px-2 py-2 text-left border-b border-slate-300">Polizza</th>
                                    <th className="px-2 py-2 text-left border-b border-slate-300">Contraente</th>
                                    <th className="px-2 py-2 text-left border-b border-slate-300">Targa/Matr.</th>
                                    <th className="px-2 py-2 text-left border-b border-slate-300">Descrizione</th>
                                    <th className="px-2 py-2 text-left border-b border-slate-300">Telaio</th>
                                    <th className="px-2 py-2 text-right border-b border-slate-300">Premio</th>
                                    <th className="px-2 py-2 text-left border-b border-slate-300">Stato</th>
                                    <th className="px-2 py-2 text-left border-b border-slate-300">Cessazione</th>
                                    <th className="px-2 py-2 text-center border-b border-slate-300">Documenti</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filtered.map((a) => {
                                    const isCessato = !!a.data_cessazione;
                                    return (
                                        <tr key={a.id} data-testid={`lm-row-${a.id}`}
                                            className={`border-b border-slate-100 hover:bg-sky-50/40 ${isCessato ? "bg-rose-50/30 text-slate-500" : ""}`}>
                                            <td className="px-2 py-1.5 font-mono">{a.data_inserimento || "—"}</td>
                                            <td className="px-2 py-1.5">
                                                <Link to={`/polizze/${a.polizza_id}`} className="text-sky-700 hover:underline font-medium">
                                                    {a.polizza_numero || a.polizza_id?.slice(0, 8)}
                                                </Link>
                                                <div className="text-[10px] text-slate-500">{a.polizza_ramo}</div>
                                            </td>
                                            <td className="px-2 py-1.5">{a.contraente_nome || "—"}</td>
                                            <td className="px-2 py-1.5 font-mono font-semibold text-sky-700">
                                                {a.targa || a.matricola || "—"}
                                            </td>
                                            <td className="px-2 py-1.5">{a.descrizione_veicolo || a.descrizione || "—"}</td>
                                            <td className="px-2 py-1.5 font-mono text-[10px] text-slate-500">{a.telaio || "—"}</td>
                                            <td className="px-2 py-1.5 num text-right font-mono">{fmtEur(a.premio_lordo || 0)}</td>
                                            <td className="px-2 py-1.5">
                                                <span className={`text-[10px] px-1.5 py-0.5 rounded ${isCessato ? "bg-rose-100 text-rose-700" : "bg-emerald-100 text-emerald-700"}`}>
                                                    {isCessato ? (a.tipo_cessazione || "cessato").toUpperCase() : "ATTIVO"}
                                                </span>
                                            </td>
                                            <td className="px-2 py-1.5 font-mono">{a.data_cessazione || "—"}</td>
                                            <td className="px-2 py-1.5 text-center">
                                                <div className="inline-flex items-center gap-1">
                                                    <button onClick={() => setDocsApp(a)}
                                                        className="inline-flex items-center gap-1 text-[10px] px-2 py-1 rounded border border-violet-300 text-violet-700 hover:bg-violet-50"
                                                        data-testid={`lm-docs-${a.id}`} title="Documenti">
                                                        <Paperclip size={11} /> {a.n_allegati || 0}
                                                    </button>
                                                    {a.targa && (
                                                        <button onClick={() => setConflictApp(a)}
                                                            className="inline-flex items-center text-[10px] px-1.5 py-1 rounded border border-amber-300 text-amber-700 hover:bg-amber-50"
                                                            data-testid={`lm-conflict-${a.id}`} title="Verifica altre polizze con stessa targa">
                                                            <AlertTriangle size={11} />
                                                        </button>
                                                    )}
                                                    {!isCessato && (
                                                        <button onClick={() => setAnnullaApp(a)}
                                                            className="inline-flex items-center text-[10px] px-1.5 py-1 rounded border border-rose-300 text-rose-700 hover:bg-rose-50"
                                                            data-testid={`lm-annulla-${a.id}`} title="Annulla applicazione (vendita/demolizione/…)">
                                                            <Ban size={11} />
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
                </Card>
            )}

            {/* Dialog documenti per applicazione */}
            {docsApp && (
                <DocsApplicazioneDialog app={docsApp} onClose={() => { setDocsApp(null); load(); }} />
            )}
            {annullaApp && (
                <AnnullaApplicazioneDialog app={annullaApp} onClose={() => { setAnnullaApp(null); load(); }} />
            )}
            {conflictApp && (
                <ConflittoTargaDialog app={conflictApp} onClose={() => setConflictApp(null)} />
            )}
        </div>
    );
}

const KPI_COLORS = {
    violet: "border-l-violet-500",
    emerald: "border-l-emerald-500",
    rose: "border-l-rose-500",
    sky: "border-l-sky-500",
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
                    sottotitolo="Allega libretto di circolazione, fotografie, autorizzazioni, certificati di proprietà. Separa visibili al cliente da interni."
                    categorie={[
                        { key: "libretto_circolazione", label: "Libretto", icon: "📕", default_visibile: true, descrizione: "Libretto di circolazione del veicolo" },
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
        <Dlg2 open onOpenChange={(o) => !o && onClose()}>
            <DC2 className="max-w-lg" data-testid="lm-annulla-dialog">
                <DH2>
                    <DT2 className="flex items-center gap-2">
                        <Ban className="text-rose-600" size={16} /> Annulla applicazione veicolo
                    </DT2>
                </DH2>
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
                            <option value="sostituita">🔄 Sostituita (nuovo veicolo)</option>
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
                    {app.targa && (
                        <div className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded p-2">
                            ⚠ <b>Attenzione</b>: verifica anche eventuali altre polizze (Infortuni Conducente, Tutela Legale, Kasko…) legate alla targa <span className="font-mono">{app.targa}</span>.
                            Puoi usare il pulsante <AlertTriangle size={11} className="inline" /> nella riga per aprirle.
                        </div>
                    )}
                </div>
                <DF2>
                    <button onClick={onClose} className="px-3 py-1.5 text-sm border border-slate-300 rounded hover:bg-slate-50">Annulla</button>
                    <button onClick={submit} disabled={busy}
                        className="px-3 py-1.5 text-sm bg-rose-600 text-white rounded hover:bg-rose-700 disabled:opacity-50"
                        data-testid="lm-annulla-conferma">
                        {busy ? "…" : "Conferma cessazione"}
                    </button>
                </DF2>
            </DC2>
        </Dlg2>
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
                <div className="text-[11px] text-slate-500">
                    💡 Ricorda: quando sostituisci/annulli un veicolo, aggiorna coerentemente TUTTE le polizze collegate alla stessa targa.
                </div>
            </DialogContent>
        </Dialog>
    );
}
