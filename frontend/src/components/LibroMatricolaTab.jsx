/** LibroMatricolaTab — gestione applicazioni veicoli su polizza RCA flotta. */
import { useEffect, useState } from "react";
import { api, fmtDate } from "@/lib/api";
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
import { Plus, Pencil, Trash2 } from "lucide-react";

export default function LibroMatricolaTab({ polizzaId }) {
    const [list, setList] = useState([]);
    const [editing, setEditing] = useState(null);

    const load = () => api.get(`/polizze/${polizzaId}/applicazioni`).then((r) => setList(r.data || []));
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [polizzaId]);

    const onDelete = async (a) => {
        if (!window.confirm(`Eliminare applicazione ${a.numero} (${a.targa})?`)) return;
        try {
            await api.delete(`/polizze/${polizzaId}/applicazioni/${a.id}`);
            toast.success("Applicazione eliminata");
            load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <Card className="border-slate-200 mt-4 overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-200 flex justify-between items-center bg-cyan-50">
                <div>
                    <div className="text-xs uppercase tracking-wider text-cyan-800 font-semibold">Libro Matricola</div>
                    <div className="text-sm text-slate-600">{list.length} applicazioni · veicoli censiti</div>
                </div>
                <Button
                    size="sm" className="bg-sky-700 hover:bg-sky-800"
                    onClick={() => setEditing({ _new: true })}
                    data-testid="lm-new-btn"
                >
                    <Plus size={14} className="mr-1" /> Nuova applicazione
                </Button>
            </div>
            {list.length === 0 ? (
                <div className="p-8 text-center text-slate-500 text-sm">Nessuna applicazione censita.</div>
            ) : (
                <table className="tbl-compact w-full text-xs">
                    <thead>
                        <tr>
                            <th className="w-20">Numero</th>
                            <th className="w-28">Veicolo</th>
                            <th className="w-24">Stato</th>
                            <th className="w-28">Data inclusione</th>
                            <th className="w-28">Data esclusione</th>
                            <th>Note / Intestatario</th>
                            <th className="w-24 text-center">Azioni</th>
                        </tr>
                    </thead>
                    <tbody>
                        {list.map((a) => (
                            <tr key={a.id} data-testid={`lm-row-${a.id}`}>
                                <td className="font-mono text-amber-700 font-semibold">{a.numero}</td>
                                <td className="font-mono">{a.targa}</td>
                                <td>
                                    <span className={`badge ${a.stato === "attiva" ? "badge-emerald" : a.stato === "annullata" ? "badge-rose" : "badge-neutral"}`}>
                                        {a.stato}
                                    </span>
                                </td>
                                <td className="num whitespace-nowrap">{fmtDate(a.data_inclusione)}</td>
                                <td className="num whitespace-nowrap">{fmtDate(a.data_esclusione)}</td>
                                <td className="truncate max-w-[280px]">{a.intestatario || a.note || "—"}</td>
                                <td className="text-center">
                                    <div className="flex gap-1 justify-center">
                                        <Button size="sm" variant="outline" className="h-7 px-2"
                                            onClick={() => setEditing(a)} data-testid={`lm-edit-${a.id}`}>
                                            <Pencil size={12} />
                                        </Button>
                                        <Button size="sm" variant="outline" className="h-7 px-2 text-rose-700 hover:bg-rose-50"
                                            onClick={() => onDelete(a)} data-testid={`lm-delete-${a.id}`}>
                                            <Trash2 size={12} />
                                        </Button>
                                    </div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}

            {editing && (
                <ApplicazioneDialog
                    polizzaId={polizzaId}
                    initial={editing}
                    onClose={() => { setEditing(null); load(); }}
                />
            )}
        </Card>
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
        intestatario: initial.intestatario || "",
        provincia_intestatario: initial.provincia_intestatario || "",
        note: initial.note || "",
    });
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const save = async () => {
        if (!f.targa) { toast.error("Targa obbligatoria"); return; }
        const payload = { ...f };
        ["cv_fiscali", "kw", "cilindrata", "posti", "numero"].forEach((k) => {
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
                                <SelectItem value="annullata">Annullata</SelectItem>
                                <SelectItem value="sospesa">Sospesa</SelectItem>
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
                                <SelectItem value="Altro">Altro</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
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
