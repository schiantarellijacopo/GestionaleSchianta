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
import { Plus, Pencil, Trash2, Search, ArrowLeftRight, History, X, Upload, Download } from "lucide-react";
import { ImportTargheStub } from "@/pages/Importazione";
import { API_BASE } from "@/lib/api";

export default function LibroMatricolaTab({ polizzaId, polizza = null }) {
    const [list, setList] = useState([]);
    const [editing, setEditing] = useState(null);
    const [sostituendo, setSostituendo] = useState(null);
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
                    />
                    {showStorico && storico.length > 0 && (
                        <ApplicazioniTable
                            title="Storico (annullate / sostituite)"
                            items={storico}
                            onEdit={setEditing}
                            onDelete={onDelete}
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
        </Card>
    );
}

function ApplicazioniTable({ title, items, onEdit, onDelete, onSostituisci, isStorico = false }) {
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
                                {a.intestatario || a.note || "—"}
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
                                    {!isStorico && a.stato === "attiva" && onSostituisci && (
                                        <Button size="sm" variant="outline" className="h-7 px-2 text-violet-700 hover:bg-violet-50"
                                            onClick={() => onSostituisci(a)} data-testid={`lm-sostituisci-${a.id}`} title="Sostituisci">
                                            <ArrowLeftRight size={12} />
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
                    <div className="col-span-3 mt-2 text-xs uppercase tracking-wider text-slate-500 font-semibold">Intestatario / Note</div>
                    <div className="col-span-2"><Label>Intestatario</Label><Input value={f.intestatario} onChange={(e) => set("intestatario", e.target.value)} /></div>
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
    });
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
    const [saving, setSaving] = useState(false);

    const sostituisci = async () => {
        if (!f.targa) { toast.error("Targa nuovo veicolo obbligatoria"); return; }
        setSaving(true);
        try {
            const payload = { ...f };
            if (payload.valore_veicolo === "") delete payload.valore_veicolo;
            else payload.valore_veicolo = parseFloat(payload.valore_veicolo);
            await api.post(`/polizze/${polizzaId}/applicazioni/${applicazione.id}/sostituisci`, payload);
            toast.success("Applicazione sostituita");
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
                        Verrà creata una nuova applicazione con i dati ereditati (tariffa, intestatario, ecc.) sovrascritti dai campi qui sotto.
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Nuova targa *</Label><Input value={f.targa} onChange={(e) => set("targa", e.target.value.toUpperCase())} data-testid="sost-targa" /></div>
                        <div><Label>Data inclusione nuova</Label><Input type="date" value={f.data_inclusione} onChange={(e) => set("data_inclusione", e.target.value)} /></div>
                        <div><Label>Marca</Label><Input value={f.marca} onChange={(e) => set("marca", e.target.value)} /></div>
                        <div><Label>Modello</Label><Input value={f.modello} onChange={(e) => set("modello", e.target.value)} /></div>
                        <div><Label>Valore veicolo €</Label><Input type="number" step="0.01" value={f.valore_veicolo} onChange={(e) => set("valore_veicolo", e.target.value)} /></div>
                        <div><Label>Scadenza leasing</Label><Input type="date" value={f.scadenza_leasing} onChange={(e) => set("scadenza_leasing", e.target.value)} /></div>
                        <div className="col-span-2"><Label>Motivo sostituzione</Label><Input value={f.motivo} onChange={(e) => set("motivo", e.target.value)} placeholder="es. Cambio veicolo, leasing nuovo, ..." data-testid="sost-motivo" /></div>
                    </div>
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
