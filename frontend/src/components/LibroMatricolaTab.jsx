/** LibroMatricolaTab — gestione applicazioni veicoli su polizza RCA flotta. */
import { useEffect, useMemo, useState } from "react";
import { api, fmtDate, fmtEur } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { Link } from "react-router-dom";
import { Plus, Pencil, Trash2, Search, ArrowLeftRight, History, X, Upload, Download, Ban, Paperclip, AlertTriangle, Building2 } from "lucide-react";
import { ImportTargheStub } from "@/pages/Importazione";
import { API_BASE } from "@/lib/api";
import DocumentiSezioneSplit from "@/components/DocumentiSezioneSplit";
import TargaConflictWidget from "@/components/TargaConflictWidget";
import IntestatarioAutocomplete from "@/components/IntestatarioAutocomplete";

export default function LibroMatricolaTab({ polizzaId, polizza = null }) {
    const [list, setList] = useState([]);
    const [editing, setEditing] = useState(null);
    const [sostituendo, setSostituendo] = useState(null);
    const [annullando, setAnnullando] = useState(null);
    const [docsApp, setDocsApp] = useState(null);
    const [conflictApp, setConflictApp] = useState(null);
    const [q, setQ] = useState("");
    const [showStorico, setShowStorico] = useState(false);
    const [showImport, setShowImport] = useState(false);

    const load = () => {
        const params = { includi_storico: showStorico };
        if (q.trim()) params.q = q.trim();
        return api.get(`/polizze/${polizzaId}/applicazioni`, { params }).then((r) => setList(r.data || []));
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [polizzaId, showStorico]);
    // Debounce search
    useEffect(() => {
        const t = setTimeout(load, 350);
        return () => clearTimeout(t);
        // eslint-disable-next-line
    }, [q]);

    const onDelete = async (a) => {
        if (!window.confirm(`Eliminare applicazione ${a.numero} (${a.targa})?`)) return;
        try {
            await api.delete(`/polizze/${polizzaId}/applicazioni/${a.id}`);
            toast.success("Applicazione eliminata");
            load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    // Split attive / storico per resa
    const attive = useMemo(() => list.filter((a) => !["annullata", "sostituita"].includes(a.stato)), [list]);
    const storico = useMemo(() => list.filter((a) => ["annullata", "sostituita"].includes(a.stato)), [list]);

    return (
        <Card className="border-slate-200 mt-4 overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-200 flex flex-wrap justify-between items-center gap-3 bg-cyan-50">
                <div>
                    <div className="text-xs uppercase tracking-wider text-cyan-800 font-semibold">Libro Matricola</div>
                    <div className="text-sm text-slate-600">{attive.length} attive{showStorico ? ` · ${storico.length} storiche` : ""}</div>
                </div>
                <div className="flex gap-2 items-center flex-wrap">
                    <div className="relative">
                        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" size={13} />
                        <Input
                            className="pl-8 h-9 w-60"
                            placeholder="Cerca targa, numero, intestatario..."
                            value={q}
                            onChange={(e) => setQ(e.target.value)}
                            data-testid="lm-search"
                        />
                        {q && (
                            <button onClick={() => setQ("")} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700">
                                <X size={13} />
                            </button>
                        )}
                    </div>
                    <Button
                        size="sm" variant={showStorico ? "default" : "outline"}
                        onClick={() => setShowStorico((s) => !s)}
                        data-testid="lm-toggle-storico"
                        className={showStorico ? "bg-amber-500 hover:bg-amber-600" : ""}
                    >
                        <History size={14} className="mr-1" />Storico
                    </Button>
                    <Button
                        size="sm" variant="outline"
                        onClick={async () => {
                            try {
                                const url = `${API_BASE}/polizze/${polizzaId}/libro-matricola/export`;
                                const r = await fetch(url, {
                                    headers: { "Authorization": `Bearer ${localStorage.getItem("token") || ""}` },
                                });
                                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                                const blob = await r.blob();
                                const dl = document.createElement("a");
                                dl.href = URL.createObjectURL(blob);
                                dl.download = `LibroMatricola_${polizza?.numero_polizza || polizzaId}.xlsx`;
                                dl.click();
                                URL.revokeObjectURL(dl.href);
                            } catch (e) {
                                toast.error("Errore export: " + e.message);
                            }
                        }}
                        data-testid="lm-export-btn"
                        className="border-emerald-300 text-emerald-700 hover:bg-emerald-50"
                    >
                        <Download size={14} className="mr-1" /> Esporta Excel
                    </Button>
                    <Button
                        size="sm" variant="outline"
                        onClick={() => setShowImport(true)}
                        data-testid="lm-import-btn"
                        className="border-sky-300 text-sky-700 hover:bg-sky-50"
                    >
                        <Upload size={14} className="mr-1" /> Importa Excel/CSV
                    </Button>
                    <Button
                        size="sm" variant="outline"
                        onClick={async () => {
                            if (!window.confirm("Vuoi provare a collegare automaticamente gli intestatari alle anagrafiche? Prima verrà mostrata un'anteprima.")) return;
                            try {
                                const preview = await api.post("/libro-matricola/migra-intestatari?dry_run=true");
                                if (window.confirm(`Anteprima: ${preview.data.collegate} collegate · ${preview.data.ambigue} ambigue · ${preview.data.non_trovate} non trovate.\n\nConfermi il collegamento delle ${preview.data.collegate} univoche?`)) {
                                    const r = await api.post("/libro-matricola/migra-intestatari?dry_run=false");
                                    toast.success(`Collegate ${r.data.collegate} applicazioni`);
                                    load();
                                }
                            } catch (e) { toast.error(e.response?.data?.detail || "Errore migrazione"); }
                        }}
                        className="border-violet-300 text-violet-700 hover:bg-violet-50"
                        data-testid="lm-tab-migra-intestatari"
                    >
                        <Building2 size={14} className="mr-1" /> Migra intestatari
                    </Button>
                    <Button
                        size="sm" variant="outline"
                        onClick={async () => {
                            try {
                                const r = await api.get("/libro-matricola/intestatari-ambigui");
                                if (!r.data || r.data.length === 0) {
                                    toast.info("Nessun intestatario ambiguo da risolvere 🎉");
                                    return;
                                }
                                // Rimando l'utente alla pagina globale Libro Matricola per il wizard completo
                                if (window.confirm(`Trovati ${r.data.length} gruppi ambigui. Aprire il wizard nella pagina globale Libro Matricola?`)) {
                                    window.location.href = "/libro-matricola";
                                }
                            } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
                        }}
                        className="border-amber-300 text-amber-700 hover:bg-amber-50"
                        data-testid="lm-tab-risolvi-ambigui"
                    >
                        <AlertTriangle size={14} className="mr-1" /> Risolvi ambigui
                    </Button>
                    <Button
                        size="sm" className="bg-sky-700 hover:bg-sky-800"
                        onClick={() => setEditing({ _new: true })}
                        data-testid="lm-new-btn"
                    >
                        <Plus size={14} className="mr-1" /> Nuova applicazione
                    </Button>
                </div>
            </div>

            {/* Dialog import libro matricola pre-collegato a questa polizza */}
            <Dialog open={showImport} onOpenChange={setShowImport}>
                <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto" data-testid="lm-import-dialog">
                    <DialogHeader>
                        <DialogTitle>Importa applicazioni veicoli (Libro Matricola)</DialogTitle>
                    </DialogHeader>
                    <ImportTargheStub
                        polizzaPreselezionata={polizza || { id: polizzaId, numero_polizza: "questa polizza" }}
                        onImportComplete={() => { load(); }}
                    />
                </DialogContent>
            </Dialog>

            {list.length === 0 ? (
                <div className="p-8 text-center text-slate-500 text-sm" data-testid="lm-empty">
                    {q ? `Nessun risultato per "${q}"` : "Nessuna applicazione censita."}
                </div>
            ) : (
                <>
                    <ApplicazioniTable
                        title="Applicazioni attive"
                        items={attive}
                        onEdit={setEditing}
                        onDelete={onDelete}
                        onSostituisci={(a) => setSostituendo(a)}
                        onAnnulla={(a) => setAnnullando(a)}
                        onDocs={(a) => setDocsApp(a)}
                        onConflict={(a) => setConflictApp(a)}
                    />
                    {showStorico && storico.length > 0 && (
                        <ApplicazioniTable
                            title="Storico (annullate / sostituite)"
                            items={storico}
                            onEdit={setEditing}
                            onDelete={onDelete}
                            onDocs={(a) => setDocsApp(a)}
                            onConflict={(a) => setConflictApp(a)}
                            isStorico
                        />
                    )}
                </>
            )}

            {editing && (
                <ApplicazioneDialog
                    polizzaId={polizzaId}
                    initial={editing}
                    onClose={() => { setEditing(null); load(); }}
                />
            )}
            {sostituendo && (
                <SostituisciDialog
                    polizzaId={polizzaId}
                    applicazione={sostituendo}
                    onClose={() => { setSostituendo(null); load(); }}
                />
            )}
            {annullando && (
                <AnnullaAppDialog
                    applicazione={annullando}
                    onClose={() => { setAnnullando(null); load(); }}
                />
            )}
            {docsApp && (
                <DocsAppDialog polizzaId={polizzaId} applicazione={docsApp}
                    onClose={() => setDocsApp(null)} />
            )}
            {conflictApp && (
                <Dialog open onOpenChange={(o) => !o && setConflictApp(null)}>
                    <DialogContent className="max-w-2xl" data-testid="lm-conflict-dialog">
                        <DialogHeader>
                            <DialogTitle>
                                <AlertTriangle className="inline text-amber-600 mr-1" size={16} />
                                Altre polizze con targa <span className="font-mono">{conflictApp.targa}</span>
                            </DialogTitle>
                        </DialogHeader>
                        <TargaConflictWidget targa={conflictApp.targa} excludeId={polizzaId} compact={false} />
                    </DialogContent>
                </Dialog>
            )}
        </Card>
    );
}

export function ApplicazioniTable({ title, items, onEdit, onDelete, onSostituisci, onAnnulla, onDocs, onConflict, isStorico = false }) {
    if (!items || items.length === 0) return null;
    return (
        <div className={isStorico ? "border-t border-slate-200 bg-amber-50/30" : ""}>
            {isStorico && (
                <div className="px-4 py-2 text-xs font-semibold uppercase tracking-wider text-amber-800 bg-amber-100">
                    {title}
                </div>
            )}
            <table className="tbl-compact w-full text-xs">
                <thead>
                    <tr>
                        <th className="w-16">Numero</th>
                        <th className="w-28">Veicolo</th>
                        <th className="w-32">Marca/Modello</th>
                        <th className="w-24">Stato</th>
                        <th className="w-28">Inclusione</th>
                        <th className="w-28">Esclusione</th>
                        <th className="w-24">Valore</th>
                        <th className="w-28">Scad. leasing</th>
                        <th>Intestatario / Note</th>
                        <th className="w-32 text-center">Azioni</th>
                    </tr>
                </thead>
                <tbody>
                    {items.map((a) => (
                        <tr key={a.id} data-testid={`lm-row-${a.id}`} className={a.stato === "sostituita" ? "opacity-60" : a.stato === "annullata" ? "opacity-70" : ""}>
                            <td className="font-mono text-amber-700 font-semibold">{a.numero}</td>
                            <td className="font-mono">{a.targa}</td>
                            <td>{[a.marca, a.modello].filter(Boolean).join(" ") || "—"}</td>
                            <td>
                                <span className={`badge ${a.stato === "attiva" ? "badge-success"
                                    : a.stato === "annullata" ? "badge-danger"
                                        : a.stato === "sostituita" ? "badge-warning"
                                            : "badge-neutral"}`}>
                                    {a.stato}
                                </span>
                                {a.sostituita_da_id && (
                                    <div className="text-[9px] text-amber-700 mt-0.5">→ sostituita</div>
                                )}
                                {a.sostituisce_id && (
                                    <div className="text-[9px] text-emerald-700 mt-0.5">← da sost.</div>
                                )}
                            </td>
                            <td className="num whitespace-nowrap">{fmtDate(a.data_inclusione)}</td>
                            <td className="num whitespace-nowrap">{fmtDate(a.data_esclusione)}</td>
                            <td className="num text-right">{a.valore_veicolo ? fmtEur(a.valore_veicolo) : "—"}</td>
                            <td className="num whitespace-nowrap">{fmtDate(a.scadenza_leasing) || "—"}</td>
                            <td className="truncate max-w-[260px]">
                                {a.intestatario_anagrafica_id ? (
                                    <Link to={`/anagrafiche/${a.intestatario_anagrafica_id}`}
                                          className="text-sky-700 hover:underline"
                                          title="Apri anagrafica collegata"
                                          data-testid={`lm-anagrafica-link-${a.id}`}>
                                        {a.intestatario || a.note || "—"}
                                    </Link>
                                ) : (
                                    <span title={a.intestatario ? "Nessuna anagrafica collegata (testo libero)" : ""}>
                                        {a.intestatario || a.note || "—"}
                                    </span>
                                )}
                                {a.motivo_annullamento && (
                                    <div className="text-[10px] text-rose-700 italic">Motivo: {a.motivo_annullamento}</div>
                                )}
                            </td>
                            <td className="text-center">
                                <div className="flex gap-1 justify-center">
                                    <Button size="sm" variant="outline" className="h-7 px-2"
                                        onClick={() => onEdit(a)} data-testid={`lm-edit-${a.id}`} title="Modifica">
                                        <Pencil size={12} />
                                    </Button>
                                    {a.targa && onConflict && (
                                        <Button size="sm" variant="outline" className="h-7 px-2 text-amber-700 hover:bg-amber-50"
                                            onClick={() => onConflict(a)} data-testid={`lm-conflict-${a.id}`}
                                            title="Verifica altre polizze con stessa targa">
                                            <AlertTriangle size={12} />
                                        </Button>
                                    )}
                                    {onDocs && (
                                        <Button size="sm" variant="outline" className="h-7 px-2 text-sky-700 hover:bg-sky-50"
                                            onClick={() => onDocs(a)} data-testid={`lm-docs-${a.id}`}
                                            title="Documenti veicolo (libretto, foto, ecc.)">
                                            <Paperclip size={12} />
                                        </Button>
                                    )}
                                    {!isStorico && a.stato === "attiva" && onSostituisci && (
                                        <Button size="sm" variant="outline" className="h-7 px-2 text-violet-700 hover:bg-violet-50"
                                            onClick={() => onSostituisci(a)} data-testid={`lm-sostituisci-${a.id}`} title="Sostituisci">
                                            <ArrowLeftRight size={12} />
                                        </Button>
                                    )}
                                    {!isStorico && a.stato === "attiva" && onAnnulla && (
                                        <Button size="sm" variant="outline" className="h-7 px-2 text-orange-700 hover:bg-orange-50"
                                            onClick={() => onAnnulla(a)} data-testid={`lm-annulla-${a.id}`}
                                            title="Annulla (vendita/demolizione/…)">
                                            <Ban size={12} />
                                        </Button>
                                    )}
                                    <Button size="sm" variant="outline" className="h-7 px-2 text-rose-700 hover:bg-rose-50"
                                        onClick={() => onDelete(a)} data-testid={`lm-delete-${a.id}`} title="Elimina">
                                        <Trash2 size={12} />
                                    </Button>
                                </div>
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

function ApplicazioneDialog({ polizzaId, initial, onClose }) {
    const isNew = !!initial._new;
    const [f, setF] = useState({
        numero: initial.numero || "",
        targa: initial.targa || "",
        stato: initial.stato || "attiva",
        data_inclusione: initial.data_inclusione || new Date().toISOString().slice(0, 10),
        data_esclusione: initial.data_esclusione || "",
        marca: initial.marca || "",
        modello: initial.modello || "",
        tipo_veicolo: initial.tipo_veicolo || "Autovettura",
        tipo_alimentazione: initial.tipo_alimentazione || "",
        tipo_uso: initial.tipo_uso || "Privato",
        data_immatricolazione: initial.data_immatricolazione || "",
        cv_fiscali: initial.cv_fiscali || "",
        kw: initial.kw || "",
        cilindrata: initial.cilindrata || "",
        posti: initial.posti || "",
        leasing: initial.leasing || "Nessuna",
        data_leasing: initial.data_leasing || "",
        scadenza_leasing: initial.scadenza_leasing || "",
        valore_veicolo: initial.valore_veicolo || "",
        valore_residuo: initial.valore_residuo || "",
        valore_accessori: initial.valore_accessori || "",
        intestatario: initial.intestatario || "",
        intestatario_anagrafica_id: initial.intestatario_anagrafica_id || null,
        provincia_intestatario: initial.provincia_intestatario || "",
        note: initial.note || "",
    });
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const save = async () => {
        if (!f.targa) { toast.error("Targa obbligatoria"); return; }
        const payload = { ...f };
        ["cv_fiscali", "kw", "cilindrata", "posti", "numero",
            "valore_veicolo", "valore_residuo", "valore_accessori"].forEach((k) => {
            if (payload[k] === "" || payload[k] === null) delete payload[k];
            else payload[k] = parseFloat(payload[k]);
        });
        try {
            if (isNew) {
                await api.post(`/polizze/${polizzaId}/applicazioni`, payload);
                toast.success("Applicazione creata");
            } else {
                await api.put(`/polizze/${polizzaId}/applicazioni/${initial.id}`, payload);
                toast.success("Applicazione aggiornata");
            }
            onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <Dialog open onOpenChange={onClose}>
            <DialogContent className="max-w-3xl" data-testid="lm-dialog">
                <DialogHeader>
                    <DialogTitle>
                        {isNew ? "Nuova applicazione" : `Applicazione ${initial.numero} — ${initial.targa}`}
                    </DialogTitle>
                </DialogHeader>
                <div className="grid grid-cols-3 gap-3 py-2 max-h-[70vh] overflow-y-auto">
                    <div><Label>Numero</Label><Input type="number" value={f.numero} onChange={(e) => set("numero", e.target.value)} placeholder="auto" /></div>
                    <div><Label>Targa *</Label><Input value={f.targa} onChange={(e) => set("targa", e.target.value.toUpperCase())} data-testid="lm-targa" /></div>
                    <div>
                        <Label>Stato</Label>
                        <Select value={f.stato} onValueChange={(v) => set("stato", v)}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="attiva">Attiva</SelectItem>
                                <SelectItem value="sospesa">Sospesa</SelectItem>
                                <SelectItem value="annullata">Annullata</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div><Label>Data inclusione</Label><Input type="date" value={f.data_inclusione} onChange={(e) => set("data_inclusione", e.target.value)} /></div>
                    <div><Label>Data esclusione</Label><Input type="date" value={f.data_esclusione} onChange={(e) => set("data_esclusione", e.target.value)} /></div>
                    <div>
                        <Label>Leasing</Label>
                        <Select value={f.leasing} onValueChange={(v) => set("leasing", v)}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="Nessuna">Nessuna</SelectItem>
                                <SelectItem value="Leasys">Leasys</SelectItem>
                                <SelectItem value="Arval">Arval</SelectItem>
                                <SelectItem value="Mercedes">Mercedes Leasing</SelectItem>
                                <SelectItem value="UniCredit">UniCredit Leasing</SelectItem>
                                <SelectItem value="Altro">Altro</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div><Label>Data leasing</Label><Input type="date" value={f.data_leasing} onChange={(e) => set("data_leasing", e.target.value)} /></div>
                    <div><Label>Scadenza leasing</Label><Input type="date" value={f.scadenza_leasing} onChange={(e) => set("scadenza_leasing", e.target.value)} data-testid="lm-scad-leasing" /></div>
                    <div></div>
                    <div className="col-span-3 mt-2 text-xs uppercase tracking-wider text-slate-500 font-semibold">Valori veicolo</div>
                    <div><Label>Valore veicolo €</Label><Input type="number" step="0.01" value={f.valore_veicolo} onChange={(e) => set("valore_veicolo", e.target.value)} data-testid="lm-valore-veicolo" /></div>
                    <div><Label>Valore residuo €</Label><Input type="number" step="0.01" value={f.valore_residuo} onChange={(e) => set("valore_residuo", e.target.value)} /></div>
                    <div><Label>Valore accessori €</Label><Input type="number" step="0.01" value={f.valore_accessori} onChange={(e) => set("valore_accessori", e.target.value)} /></div>
                    <div className="col-span-3 mt-2 text-xs uppercase tracking-wider text-slate-500 font-semibold">Dati veicolo</div>
                    <div><Label>Marca</Label><Input value={f.marca} onChange={(e) => set("marca", e.target.value)} /></div>
                    <div><Label>Modello</Label><Input value={f.modello} onChange={(e) => set("modello", e.target.value)} /></div>
                    <div>
                        <Label>Tipo veicolo</Label>
                        <Select value={f.tipo_veicolo} onValueChange={(v) => set("tipo_veicolo", v)}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="Autovettura">Autovettura</SelectItem>
                                <SelectItem value="Autocarro">Autocarro</SelectItem>
                                <SelectItem value="Motociclo">Motociclo</SelectItem>
                                <SelectItem value="Ciclomotore">Ciclomotore</SelectItem>
                                <SelectItem value="Rimorchio">Rimorchio</SelectItem>
                                <SelectItem value="Altro">Altro</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div><Label>Alimentazione</Label><Input value={f.tipo_alimentazione} onChange={(e) => set("tipo_alimentazione", e.target.value)} placeholder="Benzina, Diesel, …" /></div>
                    <div><Label>Uso</Label><Input value={f.tipo_uso} onChange={(e) => set("tipo_uso", e.target.value)} placeholder="Privato, Conto terzi, …" /></div>
                    <div><Label>Immatricolazione</Label><Input type="date" value={f.data_immatricolazione} onChange={(e) => set("data_immatricolazione", e.target.value)} /></div>
                    <div><Label>CV fiscali</Label><Input type="number" value={f.cv_fiscali} onChange={(e) => set("cv_fiscali", e.target.value)} /></div>
                    <div><Label>kW</Label><Input type="number" step="0.1" value={f.kw} onChange={(e) => set("kw", e.target.value)} /></div>
                    <div><Label>Cilindrata (cc)</Label><Input type="number" value={f.cilindrata} onChange={(e) => set("cilindrata", e.target.value)} /></div>
                    <div><Label>Posti</Label><Input type="number" value={f.posti} onChange={(e) => set("posti", e.target.value)} /></div>
                    <div className="col-span-3 mt-2 text-xs uppercase tracking-wider text-slate-500 font-semibold">Contraente / Intestatario</div>
                    <div className="col-span-3">
                        <Label>Contraente · cerca anagrafica</Label>
                        <IntestatarioAutocomplete
                            value={f.intestatario}
                            anagraficaId={f.intestatario_anagrafica_id}
                            onChange={(name, anagraficaId) => {
                                set("intestatario", name);
                                set("intestatario_anagrafica_id", anagraficaId);
                            }}
                        />
                        <div className="text-[10px] text-slate-500 mt-1">
                            Se collegato ad un&apos;anagrafica, il cliente vedrà questa applicazione dal suo portale.
                        </div>
                    </div>
                    <div className="col-span-2">
                        <Label>Intestatario (testo libero)</Label>
                        <Input value={f.intestatario} onChange={(e) => set("intestatario", e.target.value)}
                               placeholder="Sincronizzato con il campo Contraente sopra" />
                    </div>
                    <div><Label>Provincia</Label><Input value={f.provincia_intestatario} onChange={(e) => set("provincia_intestatario", e.target.value)} placeholder="MI, RM, …" /></div>
                    <div className="col-span-3"><Label>Note</Label><Input value={f.note} onChange={(e) => set("note", e.target.value)} /></div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Annulla</Button>
                    <Button onClick={save} className="bg-sky-700 hover:bg-sky-800" data-testid="lm-save">
                        Salva
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function SostituisciDialog({ polizzaId, applicazione, onClose }) {
    const [f, setF] = useState({
        targa: "",
        marca: "",
        modello: "",
        valore_veicolo: "",
        scadenza_leasing: applicazione.scadenza_leasing || "",
        data_inclusione: new Date().toISOString().slice(0, 10),
        motivo: "",
        tipo_cessazione: "venduta",  // vendita | demolita | esportata | cessata_leasing
    });
    const [attoFile, setAttoFile] = useState(null);
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
    const [saving, setSaving] = useState(false);

    const targaCambia = f.targa && f.targa.toUpperCase() !== (applicazione.targa || "").toUpperCase();
    const richiedeAtto = targaCambia;

    const CATEGORIE_ATTO = {
        venduta:         "atto_vendita",
        demolita:        "certificato_demolizione",
        esportata:       "documento_esportazione",
        cessata_leasing: "cessazione_leasing",
    };

    const sostituisci = async () => {
        if (!f.targa) { toast.error("Targa nuovo veicolo obbligatoria"); return; }
        if (richiedeAtto && !f.tipo_cessazione) {
            toast.error("Scegli il motivo di cessazione del vecchio veicolo");
            return;
        }
        if (richiedeAtto && !attoFile) {
            if (!window.confirm(
                `⚠️ Non hai caricato il documento di ${f.tipo_cessazione.toUpperCase()}.\n\n` +
                `La sostituzione verrà comunque salvata e la pratica finirà tra i "Documenti Mancanti" della Dashboard.\n` +
                `Il cliente riceverà solleciti automatici via Email/WhatsApp finché non carica il documento.\n\n` +
                `Vuoi procedere senza caricare l'atto?`,
            )) return;
        }
        setSaving(true);
        try {
            const payload = { ...f };
            if (payload.valore_veicolo === "") delete payload.valore_veicolo;
            else payload.valore_veicolo = parseFloat(payload.valore_veicolo);
            const r = await api.post(
                `/polizze/${polizzaId}/applicazioni/${applicazione.id}/sostituisci`,
                payload,
            );
            // Upload atto se presente
            if (richiedeAtto && attoFile) {
                const fd = new FormData();
                fd.append("file", attoFile);
                fd.append("categoria", CATEGORIE_ATTO[f.tipo_cessazione] || "atto_vendita");
                fd.append("entita_tipo", "polizza");
                fd.append("entita_id", polizzaId);
                fd.append("applicazione_matricola_id", applicazione.id);
                fd.append("descrizione", `Atto ${f.tipo_cessazione} per targa ${applicazione.targa}`);
                fd.append("visibile_cliente", "true");
                try {
                    await api.post("/allegati", fd, {
                        headers: { "Content-Type": "multipart/form-data" },
                    });
                    toast.success("Sostituzione completata + atto caricato");
                } catch (e) {
                    toast.warning("Sostituzione salvata ma upload atto fallito. Ricaricalo dai Documenti Mancanti.");
                }
            } else if (richiedeAtto) {
                toast.warning(`Sostituzione salvata. Manca il documento di ${f.tipo_cessazione} — pratica in "Documenti Mancanti"`);
            } else {
                toast.success("Applicazione sostituita (stessa targa, libretto ereditato)");
            }
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        } finally { setSaving(false); }
    };

    return (
        <Dialog open onOpenChange={onClose}>
            <DialogContent className="max-w-2xl" data-testid="lm-sostituisci-dialog">
                <DialogHeader>
                    <DialogTitle>
                        <ArrowLeftRight className="inline mr-2 -mt-1" size={18} />
                        Sostituisci applicazione {applicazione.numero} — {applicazione.targa}
                    </DialogTitle>
                </DialogHeader>
                <div className="space-y-3 py-2">
                    <div className="text-xs bg-amber-50 border border-amber-200 rounded p-2 text-amber-900">
                        L&apos;applicazione corrente <strong>{applicazione.targa}</strong> verrà marcata come <em>sostituita</em>.
                        Se cambia la targa, è <strong>obbligatorio</strong> specificare il motivo e caricare il documento ufficiale.
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Nuova targa *</Label><Input value={f.targa} onChange={(e) => set("targa", e.target.value.toUpperCase())} data-testid="sost-targa" className="font-mono uppercase" /></div>
                        <div><Label>Data inclusione nuova</Label><Input type="date" value={f.data_inclusione} onChange={(e) => set("data_inclusione", e.target.value)} /></div>
                        <div><Label>Marca</Label><Input value={f.marca} onChange={(e) => set("marca", e.target.value)} /></div>
                        <div><Label>Modello</Label><Input value={f.modello} onChange={(e) => set("modello", e.target.value)} /></div>
                        <div><Label>Valore veicolo €</Label><Input type="number" step="0.01" value={f.valore_veicolo} onChange={(e) => set("valore_veicolo", e.target.value)} /></div>
                        <div><Label>Scadenza leasing</Label><Input type="date" value={f.scadenza_leasing} onChange={(e) => set("scadenza_leasing", e.target.value)} /></div>
                    </div>

                    {richiedeAtto && (
                        <div className="border border-rose-300 bg-rose-50 rounded p-3 space-y-3">
                            <div className="text-xs font-semibold text-rose-800 uppercase tracking-wide flex items-center gap-2">
                                <AlertTriangle size={14} /> Cambio targa — motivo cessazione e documento OBBLIGATORI
                            </div>
                            <div>
                                <Label className="text-xs font-semibold">Motivo di cessazione della vecchia targa *</Label>
                                <div className="grid grid-cols-2 gap-2 mt-1">
                                    {[
                                        { key: "venduta", label: "Vendita → Atto di Vendita" },
                                        { key: "demolita", label: "Demolizione → Certificato Demolizione" },
                                        { key: "esportata", label: "Esportazione → Doc. Esportazione" },
                                        { key: "cessata_leasing", label: "Cessazione Leasing" },
                                    ].map((opt) => (
                                        <label key={opt.key}
                                               className={`text-xs border rounded p-2 cursor-pointer transition ${f.tipo_cessazione === opt.key ? "border-rose-500 bg-white ring-2 ring-rose-200" : "border-slate-200 hover:border-slate-400"}`}>
                                            <input type="radio" name="motivo-cessazione"
                                                   checked={f.tipo_cessazione === opt.key}
                                                   onChange={() => set("tipo_cessazione", opt.key)}
                                                   className="mr-2" data-testid={`sost-motivo-${opt.key}`} />
                                            {opt.label}
                                        </label>
                                    ))}
                                </div>
                            </div>
                            <div>
                                <Label className="text-xs font-semibold">Carica documento {(CATEGORIE_ATTO[f.tipo_cessazione] || "atto").replace(/_/g, " ")} (consigliato)</Label>
                                <input type="file"
                                       accept="application/pdf,image/*"
                                       onChange={(e) => setAttoFile(e.target.files?.[0] || null)}
                                       className="w-full text-xs border border-slate-200 rounded p-2 bg-white"
                                       data-testid="sost-atto-file" />
                                {attoFile && (
                                    <div className="text-[10px] text-slate-500 mt-1">📄 {attoFile.name} · {(attoFile.size / 1024).toFixed(0)} KB</div>
                                )}
                                {!attoFile && (
                                    <div className="text-[10px] text-rose-700 mt-1">
                                        ⚠️ Se non lo carichi ora, il cliente riceverà solleciti automatici via Email/WhatsApp finché non lo invia
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    <div><Label>Note aggiuntive</Label><Input value={f.motivo} onChange={(e) => set("motivo", e.target.value)} placeholder="Note libere sulla sostituzione" data-testid="sost-motivo" /></div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Annulla</Button>
                    <Button onClick={sostituisci} disabled={saving} className="bg-violet-600 hover:bg-violet-700" data-testid="sost-conferma">
                        <ArrowLeftRight size={14} className="mr-1" />
                        {saving ? "Sostituendo…" : "Sostituisci"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}


function AnnullaAppDialog({ applicazione, onClose }) {
    const [motivo, setMotivo] = useState("");
    const [motivoPreset, setMotivoPreset] = useState("");
    const [data, setData] = useState(new Date().toISOString().slice(0, 10));
    const [saving, setSaving] = useState(false);

    const confermaAnnulla = async () => {
        const motivoFinale = motivoPreset && motivoPreset !== "Altro"
            ? (motivo ? `${motivoPreset} — ${motivo}` : motivoPreset)
            : motivo.trim();
        if (!motivoFinale) { toast.error("Motivo obbligatorio"); return; }
        setSaving(true);
        try {
            await api.post(
                `/polizze/${applicazione.polizza_id}/applicazioni/${applicazione.id}/annulla`,
                { motivo: motivoFinale, data_annullamento: data },
            );
            toast.success("Applicazione annullata");
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        } finally { setSaving(false); }
    };

    return (
        <Dialog open onOpenChange={onClose}>
            <DialogContent className="max-w-lg" data-testid="lm-annulla-dialog">
                <DialogHeader>
                    <DialogTitle>
                        <Ban className="inline mr-2 -mt-1 text-orange-600" size={18} />
                        Annulla applicazione {applicazione.numero} — {applicazione.targa}
                    </DialogTitle>
                </DialogHeader>
                <div className="space-y-3 py-2">
                    <div className="text-xs bg-orange-50 border border-orange-200 rounded p-2 text-orange-900">
                        L&apos;applicazione verrà marcata come <strong>annullata</strong> con la data di esclusione indicata.
                        Il veicolo non risulterà più coperto dalla data di annullamento.
                    </div>
                    <div>
                        <Label>Motivo *</Label>
                        <Select value={motivoPreset} onValueChange={setMotivoPreset}>
                            <SelectTrigger data-testid="lm-annulla-preset"><SelectValue placeholder="Seleziona motivo…" /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="Vendita">Vendita veicolo</SelectItem>
                                <SelectItem value="Demolizione">Demolizione</SelectItem>
                                <SelectItem value="Furto">Furto</SelectItem>
                                <SelectItem value="Restituzione leasing">Restituzione leasing</SelectItem>
                                <SelectItem value="Cessazione uso">Cessazione uso</SelectItem>
                                <SelectItem value="Errore inserimento">Errore inserimento</SelectItem>
                                <SelectItem value="Altro">Altro (specificare)</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <Label>{motivoPreset === "Altro" || !motivoPreset ? "Descrizione motivo *" : "Note aggiuntive"}</Label>
                        <Input
                            value={motivo}
                            onChange={(e) => setMotivo(e.target.value)}
                            placeholder={motivoPreset === "Altro" ? "Es. veicolo distrutto in incendio" : "Facoltativo"}
                            data-testid="lm-annulla-motivo"
                        />
                    </div>
                    <div>
                        <Label>Data annullamento</Label>
                        <Input type="date" value={data} onChange={(e) => setData(e.target.value)} data-testid="lm-annulla-data" />
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Annulla</Button>
                    <Button onClick={confermaAnnulla} disabled={saving} className="bg-orange-600 hover:bg-orange-700" data-testid="lm-annulla-conferma">
                        <Ban size={14} className="mr-1" />
                        {saving ? "Annullando…" : "Conferma annullamento"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}


function DocsAppDialog({ polizzaId, applicazione, onClose }) {
    // Categorie tipiche di documenti per veicolo/applicazione libro matricola
    const categorieVeicolo = [
        { key: "libretto", label: "Libretto di circolazione", visibile_default: true },
        { key: "certificato", label: "Certificato assicurativo", visibile_default: true },
        { key: "quietanza", label: "Quietanza / Ricevuta", visibile_default: true },
        { key: "foto", label: "Foto veicolo / danni", visibile_default: false },
        { key: "atto_vendita", label: "Atto di vendita / passaggio", visibile_default: false },
        { key: "altro", label: "Altro documento veicolo", visibile_default: false },
    ];
    return (
        <Dialog open onOpenChange={onClose}>
            <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto" data-testid="lm-docs-dialog">
                <DialogHeader>
                    <DialogTitle>
                        <Paperclip className="inline mr-2 -mt-1 text-sky-600" size={18} />
                        Documenti veicolo — {applicazione.targa} (app. {applicazione.numero})
                    </DialogTitle>
                </DialogHeader>
                <div className="text-xs bg-sky-50 border border-sky-200 rounded p-2 text-sky-900 mb-3">
                    Documenti collegati a <strong>questo specifico veicolo</strong> del libro matricola
                    (es. libretto, certificato, foto). Restano collegati alla polizza ma filtrati per targa.
                </div>
                <DocumentiSezioneSplit
                    entita_tipo="polizza"
                    entita_id={polizzaId}
                    applicazione_matricola_id={applicazione.id}
                    categorie={categorieVeicolo}
                    titolo={`Veicolo ${applicazione.targa}`}
                />
            </DialogContent>
        </Dialog>
    );
}
