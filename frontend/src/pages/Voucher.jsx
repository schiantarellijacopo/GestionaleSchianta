/**
 * Voucher Compagnia — gestione codici sconto forniti dalle compagnie e
 * assegnabili manualmente ai clienti dell'agenzia.
 */
import { useEffect, useState } from "react";
import { api, fmtEur } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Plus, Ticket, Trash2, Edit, Upload } from "lucide-react";
import { toast } from "sonner";

export default function Voucher() {
    const [items, setItems] = useState(null);
    const [stato, setStato] = useState("all");
    const [open, setOpen] = useState(false);
    const [bulkOpen, setBulkOpen] = useState(false);
    const [editing, setEditing] = useState(null);
    const [compagnie, setCompagnie] = useState([]);
    const [anagrafiche, setAnagrafiche] = useState([]);
    const load = () => {
        const params = stato !== "all" ? { stato } : {};
        api.get("/voucher", { params }).then((r) => setItems(r.data));
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [stato]);
    useEffect(() => {
        api.get("/compagnie").then((r) => setCompagnie(r.data));
        api.get("/anagrafiche?limit=2000").then((r) => setAnagrafiche(r.data));
    }, []);

    const del = async (id) => {
        if (!window.confirm("Eliminare?")) return;
        await api.delete(`/voucher/${id}`); toast.success("Eliminato"); load();
    };

    const assegna = async (v) => {
        const aid = window.prompt(`Assegna voucher ${v.codice} — digita ID anagrafica o lascia vuoto:`);
        if (!aid) return;
        try {
            await api.post(`/voucher/${v.id}/assegna`, { anagrafica_id: aid });
            toast.success("Assegnato"); load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const counts = (items || []).reduce((acc, v) => {
        if (v.usato) acc.usato++;
        else if (v.assegnato_a) acc.assegnato++;
        else acc.disponibile++;
        return acc;
    }, { disponibile: 0, assegnato: 0, usato: 0 });

    return (
        <div data-testid="voucher-page" className="space-y-3">
            <PageHeader
                title={<span className="flex items-center gap-2"><Ticket className="text-emerald-600" /> Voucher Compagnia</span>}
                subtitle="Codici sconto forniti dalle compagnie · assegnazione clienti"
                actions={
                    <div className="flex gap-2">
                        <Dialog open={bulkOpen} onOpenChange={setBulkOpen}>
                            <DialogTrigger asChild>
                                <Button variant="outline" data-testid="vou-bulk"><Upload size={14} className="mr-1" /> Import massivo</Button>
                            </DialogTrigger>
                            <BulkImportDialog compagnie={compagnie} onClose={() => { setBulkOpen(false); load(); }} />
                        </Dialog>
                        <Dialog open={open} onOpenChange={setOpen}>
                            <DialogTrigger asChild>
                                <Button onClick={() => setEditing(null)} className="bg-emerald-700 hover:bg-emerald-800" data-testid="vou-new">
                                    <Plus size={14} className="mr-1" /> Nuovo voucher
                                </Button>
                            </DialogTrigger>
                            <VoucherDialog editing={editing} compagnie={compagnie} anagrafiche={anagrafiche}
                                onClose={() => { setOpen(false); setEditing(null); load(); }} />
                        </Dialog>
                    </div>
                }
            />

            <div className="grid grid-cols-3 gap-3">
                <Card className="p-3 border-l-4 border-emerald-400 bg-white cursor-pointer" onClick={() => setStato("disponibile")} data-testid="vou-f-disp">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">Disponibili</div>
                    <div className="text-2xl font-bold text-emerald-700">{counts.disponibile}</div>
                </Card>
                <Card className="p-3 border-l-4 border-amber-400 bg-white cursor-pointer" onClick={() => setStato("assegnato")} data-testid="vou-f-ass">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">Assegnati (non usati)</div>
                    <div className="text-2xl font-bold text-amber-700">{counts.assegnato}</div>
                </Card>
                <Card className="p-3 border-l-4 border-slate-400 bg-white cursor-pointer" onClick={() => setStato("usato")} data-testid="vou-f-uso">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">Usati</div>
                    <div className="text-2xl font-bold text-slate-700">{counts.usato}</div>
                </Card>
            </div>
            <button onClick={() => setStato("all")} className="text-xs text-sky-600 hover:underline" data-testid="vou-f-all">
                {stato !== "all" ? `Mostra tutti (${(items || []).length})` : "Tutti i voucher"}
            </button>

            {items === null ? <Loading /> : items.length === 0 ? <Empty /> : (
                <div className="tbl-scroll">
                    <table className="tbl-compact w-full text-xs">
                        <thead><tr>
                            <th>Codice</th><th>Compagnia</th><th>Ramo</th>
                            <th className="text-right">Valore</th><th>Tipo</th>
                            <th>Validità</th><th>Assegnato a</th><th>Stato</th><th className="w-24"></th>
                        </tr></thead>
                        <tbody>
                            {items.map((v) => (
                                <tr key={v.id}>
                                    <td className="font-mono font-bold">{v.codice}</td>
                                    <td>{v.compagnia_nome || "—"}</td>
                                    <td>{v.ramo || "—"}</td>
                                    <td className="text-right font-mono">{v.tipo_valore === "percentuale" ? `${v.valore}%` : fmtEur(v.valore)}</td>
                                    <td>{v.tipo_valore}</td>
                                    <td>{v.valido_dal || ""} → {v.valido_al || "∞"}</td>
                                    <td>{v.assegnato_a_nome || <span className="text-emerald-700 font-semibold">DISPONIBILE</span>}</td>
                                    <td>{v.usato ? "✓ Usato" : (v.assegnato_a ? "Assegnato" : "—")}</td>
                                    <td className="space-x-1 text-right">
                                        {!v.assegnato_a && (
                                            <button onClick={() => assegna(v)} className="text-emerald-700 hover:bg-emerald-50 px-1.5 py-0.5 rounded text-[10px]">
                                                Assegna
                                            </button>
                                        )}
                                        <button onClick={() => { setEditing(v); setOpen(true); }} className="text-sky-700 hover:bg-sky-50 p-1 rounded">
                                            <Edit size={11} />
                                        </button>
                                        <button onClick={() => del(v.id)} className="text-rose-600 hover:bg-rose-50 p-1 rounded">
                                            <Trash2 size={11} />
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}

function VoucherDialog({ editing, compagnie, anagrafiche, onClose }) {
    const [f, setF] = useState(editing || {
        codice: "", compagnia_id: "", ramo: "", valore: 0, tipo_valore: "euro",
        valido_dal: "", valido_al: "", assegnato_a: null, descrizione: "", usato: false,
    });
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
    const save = async () => {
        if (!f.codice) { toast.error("Codice obbligatorio"); return; }
        try {
            if (editing?.id) await api.put(`/voucher/${editing.id}`, f);
            else await api.post("/voucher", f);
            toast.success("Salvato"); onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };
    return (
        <DialogContent className="max-w-xl">
            <DialogHeader><DialogTitle>{editing?.id ? "Modifica" : "Nuovo"} voucher</DialogTitle></DialogHeader>
            <div className="grid grid-cols-2 gap-3">
                <div><Label className="text-xs">Codice *</Label>
                    <Input value={f.codice} onChange={(e) => set("codice", e.target.value)} data-testid="vou-codice" /></div>
                <div><Label className="text-xs">Compagnia</Label>
                    <Select value={f.compagnia_id || ""} onValueChange={(v) => set("compagnia_id", v)}>
                        <SelectTrigger><SelectValue placeholder="—" /></SelectTrigger>
                        <SelectContent>
                            {compagnie.map((c) => <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
                <div><Label className="text-xs">Ramo</Label>
                    <Input value={f.ramo || ""} onChange={(e) => set("ramo", e.target.value)} placeholder="RC AUTO, CASA…" /></div>
                <div><Label className="text-xs">Valore</Label>
                    <Input type="number" step="0.01" value={f.valore} onChange={(e) => set("valore", parseFloat(e.target.value) || 0)} /></div>
                <div><Label className="text-xs">Tipo valore</Label>
                    <Select value={f.tipo_valore} onValueChange={(v) => set("tipo_valore", v)}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="euro">€ Euro</SelectItem>
                            <SelectItem value="percentuale">% Percentuale</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
                <div><Label className="text-xs">Valido dal</Label>
                    <Input type="date" value={f.valido_dal || ""} onChange={(e) => set("valido_dal", e.target.value)} /></div>
                <div><Label className="text-xs">Valido al</Label>
                    <Input type="date" value={f.valido_al || ""} onChange={(e) => set("valido_al", e.target.value)} /></div>
                <div className="col-span-2"><Label className="text-xs">Descrizione</Label>
                    <Textarea rows={2} value={f.descrizione || ""} onChange={(e) => set("descrizione", e.target.value)} /></div>
            </div>
            <DialogFooter>
                <Button onClick={save} className="bg-emerald-700 hover:bg-emerald-800" data-testid="vou-save">Salva</Button>
            </DialogFooter>
        </DialogContent>
    );
}

function BulkImportDialog({ compagnie, onClose }) {
    const [f, setF] = useState({
        codici_text: "", compagnia_id: "", ramo: "",
        valore: 0, tipo_valore: "euro", valido_dal: "", valido_al: "",
    });
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
    const importa = async () => {
        const codici = (f.codici_text || "").split(/[\s,\n;]+/).filter(Boolean);
        if (!codici.length) { toast.error("Inserisci almeno un codice"); return; }
        try {
            const r = await api.post("/voucher/bulk-import", { ...f, codici });
            toast.success(`Importati ${r.data.creati} voucher (${r.data.duplicati} duplicati)`); onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };
    return (
        <DialogContent className="max-w-xl">
            <DialogHeader><DialogTitle>Importa lista voucher</DialogTitle></DialogHeader>
            <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                    <div><Label className="text-xs">Compagnia</Label>
                        <Select value={f.compagnia_id || ""} onValueChange={(v) => set("compagnia_id", v)}>
                            <SelectTrigger><SelectValue placeholder="—" /></SelectTrigger>
                            <SelectContent>
                                {compagnie.map((c) => <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div><Label className="text-xs">Ramo</Label>
                        <Input value={f.ramo} onChange={(e) => set("ramo", e.target.value)} placeholder="RC AUTO" /></div>
                    <div><Label className="text-xs">Valore</Label>
                        <Input type="number" value={f.valore} onChange={(e) => set("valore", parseFloat(e.target.value) || 0)} /></div>
                    <div><Label className="text-xs">Tipo</Label>
                        <Select value={f.tipo_valore} onValueChange={(v) => set("tipo_valore", v)}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="euro">€</SelectItem><SelectItem value="percentuale">%</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                </div>
                <div><Label className="text-xs">Codici voucher (uno per riga o separati da virgola)</Label>
                    <Textarea rows={8} value={f.codici_text} onChange={(e) => set("codici_text", e.target.value)}
                        placeholder="VOUCH001&#10;VOUCH002&#10;VOUCH003"
                        data-testid="vou-bulk-codici" /></div>
            </div>
            <DialogFooter>
                <Button onClick={importa} className="bg-emerald-700 hover:bg-emerald-800" data-testid="vou-bulk-save">
                    <Upload size={14} className="mr-1" /> Importa
                </Button>
            </DialogFooter>
        </DialogContent>
    );
}
