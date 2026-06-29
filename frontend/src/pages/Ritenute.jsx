/**
 * Ritenute — gestione ritenute d'acconto dei collaboratori (modello simile a Rappel).
 * CRUD base con totali per anno/collaboratore. Calcolo automatico ritenuta = imponibile × aliquota%.
 */
import { useEffect, useMemo, useState } from "react";
import { api, fmtEur } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { Plus, Trash2, Edit, FileText } from "lucide-react";
import { toast } from "sonner";

export default function Ritenute() {
    const currentYear = new Date().getFullYear();
    const [anno, setAnno] = useState(currentYear);
    const [items, setItems] = useState(null);
    const [totali, setTotali] = useState(null);
    const [editing, setEditing] = useState(null);
    const [open, setOpen] = useState(false);
    const [collabs, setCollabs] = useState([]);

    const load = () => {
        api.get("/ritenute", { params: { anno } }).then((r) => setItems(r.data));
        api.get("/ritenute/totali", { params: { anno } }).then((r) => setTotali(r.data));
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [anno]);
    useEffect(() => {
        api.get("/auth/users").then((r) => {
            // Mostra tutti gli utenti tranne i clienti (anche se role è vuoto)
            const list = (r.data || []).filter((x) => (x.role || "") !== "cliente");
            setCollabs(list);
        }).catch(() => setCollabs([]));
    }, []);

    const totGen = useMemo(() => {
        const t = totali?.per_collaboratore || [];
        return {
            imponibile: t.reduce((s, x) => s + (x.imponibile_tot || 0), 0),
            ritenuta: t.reduce((s, x) => s + (x.ritenuta_tot || 0), 0),
            versata: t.reduce((s, x) => s + (x.versata_tot || 0), 0),
            n: t.reduce((s, x) => s + (x.n_record || 0), 0),
        };
    }, [totali]);

    const del = async (id) => {
        if (!window.confirm("Eliminare?")) return;
        await api.delete(`/ritenute/${id}`); toast.success("Eliminata"); load();
    };

    return (
        <div data-testid="ritenute-page">
            <PageHeader
                title="Ritenute d'acconto"
                subtitle="Gestione ritenute per collaboratori (versamento F24)"
                actions={
                    <div className="flex gap-2">
                        <Select value={String(anno)} onValueChange={(v) => setAnno(parseInt(v))}>
                            <SelectTrigger className="w-28" data-testid="rit-anno"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                {[0, -1, -2, -3, -4].map((d) => {
                                    const y = currentYear + d;
                                    return <SelectItem key={y} value={String(y)}>{y}</SelectItem>;
                                })}
                            </SelectContent>
                        </Select>
                        <Dialog open={open} onOpenChange={setOpen}>
                            <DialogTrigger asChild>
                                <Button onClick={() => setEditing(null)} data-testid="rit-new">
                                    <Plus size={14} className="mr-1" /> Nuova ritenuta
                                </Button>
                            </DialogTrigger>
                            <RitenutaDialog editing={editing} anno={anno} collabs={collabs}
                                onClose={() => { setOpen(false); setEditing(null); load(); }} />
                        </Dialog>
                    </div>
                }
            />

            {/* Totali */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                <Card className="p-3 border-l-4 border-sky-400 bg-white">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">Record {anno}</div>
                    <div className="text-2xl font-bold">{totGen.n}</div>
                </Card>
                <Card className="p-3 border-l-4 border-indigo-400 bg-white">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">Imponibile</div>
                    <div className="text-xl font-bold font-mono">{fmtEur(totGen.imponibile)}</div>
                </Card>
                <Card className="p-3 border-l-4 border-amber-400 bg-white">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">Ritenute Totali</div>
                    <div className="text-xl font-bold font-mono">{fmtEur(totGen.ritenuta)}</div>
                </Card>
                <Card className="p-3 border-l-4 border-emerald-400 bg-white">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">Versate</div>
                    <div className="text-xl font-bold font-mono">{fmtEur(totGen.versata)}</div>
                </Card>
            </div>

            {/* Tabella per collaboratore */}
            {totali && totali.per_collaboratore && totali.per_collaboratore.length > 0 && (
                <Card className="mb-4 p-3">
                    <div className="text-xs font-semibold text-slate-600 mb-2">Riepilogo per collaboratore</div>
                    <table className="w-full text-xs">
                        <thead><tr className="text-slate-500 text-left border-b">
                            <th className="py-1.5">Collaboratore</th>
                            <th className="text-right">N</th>
                            <th className="text-right">Imponibile</th>
                            <th className="text-right">Ritenuta</th>
                            <th className="text-right">Versata</th>
                            <th className="text-right">Residuo</th>
                        </tr></thead>
                        <tbody>
                            {totali.per_collaboratore.map((r) => (
                                <tr key={r.collaboratore_id} className="border-b border-slate-100">
                                    <td className="py-1.5 font-medium">{r.collaboratore_nome || "—"}</td>
                                    <td className="text-right">{r.n_record}</td>
                                    <td className="text-right font-mono">{fmtEur(r.imponibile_tot)}</td>
                                    <td className="text-right font-mono">{fmtEur(r.ritenuta_tot)}</td>
                                    <td className="text-right font-mono text-emerald-700">{fmtEur(r.versata_tot)}</td>
                                    <td className="text-right font-mono text-rose-700">{fmtEur((r.ritenuta_tot || 0) - (r.versata_tot || 0))}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </Card>
            )}

            {/* Tabella dettaglio */}
            <div className="tbl-scroll">
                {items === null ? <Loading /> : items.length === 0 ? <Empty /> : (
                    <table className="tbl-compact w-full text-xs">
                        <thead><tr>
                            <th>Data</th><th>Collaboratore</th><th>Descrizione</th>
                            <th>Causale</th>
                            <th className="text-right">Imponibile</th>
                            <th className="text-right">Aliq.</th>
                            <th className="text-right">Ritenuta</th>
                            <th>Versata</th><th>Data Vers.</th><th className="w-16"></th>
                        </tr></thead>
                        <tbody>
                            {items.map((r) => (
                                <tr key={r.id} data-testid={`rit-row-${r.id}`}>
                                    <td>{r.data || "—"}</td>
                                    <td className="font-medium">{r.collaboratore_nome || "—"}</td>
                                    <td>{r.descrizione || "—"}</td>
                                    <td>{r.causale || "1040"}</td>
                                    <td className="text-right font-mono">{fmtEur(r.imponibile)}</td>
                                    <td className="text-right">{r.aliquota}%</td>
                                    <td className="text-right font-mono font-semibold">{fmtEur(r.importo_ritenuta)}</td>
                                    <td>{r.versata ? <span className="text-emerald-700">✓</span> : <span className="text-slate-400">—</span>}</td>
                                    <td>{r.data_versamento || "—"}</td>
                                    <td className="text-right space-x-1">
                                        <button onClick={() => { setEditing(r); setOpen(true); }}
                                            className="text-sky-700 hover:bg-sky-50 p-1 rounded" data-testid={`rit-edit-${r.id}`}>
                                            <Edit size={11} />
                                        </button>
                                        <button onClick={() => del(r.id)} className="text-rose-600 hover:bg-rose-50 p-1 rounded">
                                            <Trash2 size={11} />
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
}

function RitenutaDialog({ editing, anno, collabs, onClose }) {
    const [f, setF] = useState(editing || {
        anno, collaboratore_id: "", descrizione: "", imponibile: 0, aliquota: 20,
        importo_ritenuta: 0, causale: "1040", data: new Date().toISOString().slice(0, 10),
        versata: false, data_versamento: "", note: "",
    });
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
    // ricalcolo auto
    useEffect(() => {
        if (f.imponibile && f.aliquota) {
            const r = Math.round(parseFloat(f.imponibile) * parseFloat(f.aliquota)) / 100;
            setF((p) => ({ ...p, importo_ritenuta: r }));
        }
    // eslint-disable-next-line
    }, [f.imponibile, f.aliquota]);
    const save = async () => {
        if (!f.collaboratore_id) { toast.error("Seleziona collaboratore"); return; }
        try {
            if (editing?.id) await api.put(`/ritenute/${editing.id}`, f);
            else await api.post("/ritenute", f);
            toast.success("Salvata"); onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };
    return (
        <DialogContent className="max-w-xl">
            <DialogHeader><DialogTitle>{editing?.id ? "Modifica ritenuta" : "Nuova ritenuta"}</DialogTitle></DialogHeader>
            <div className="grid grid-cols-2 gap-3">
                <div><Label className="text-xs">Anno *</Label>
                    <Input type="number" value={f.anno} onChange={(e) => set("anno", parseInt(e.target.value) || anno)} /></div>
                <div><Label className="text-xs">Data</Label>
                    <Input type="date" value={f.data || ""} onChange={(e) => set("data", e.target.value)} /></div>
                <div className="col-span-2"><Label className="text-xs">Collaboratore *</Label>
                    <Select value={f.collaboratore_id} onValueChange={(v) => set("collaboratore_id", v)}>
                        <SelectTrigger data-testid="rit-collab"><SelectValue placeholder="Seleziona" /></SelectTrigger>
                        <SelectContent>
                            {collabs.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
                <div className="col-span-2"><Label className="text-xs">Descrizione</Label>
                    <Input value={f.descrizione || ""} onChange={(e) => set("descrizione", e.target.value)} /></div>
                <div><Label className="text-xs">Causale F24</Label>
                    <Input value={f.causale || ""} onChange={(e) => set("causale", e.target.value)} placeholder="1040 / 1019 / ..." /></div>
                <div><Label className="text-xs">Imponibile €</Label>
                    <Input type="number" step="0.01" value={f.imponibile} onChange={(e) => set("imponibile", parseFloat(e.target.value) || 0)} data-testid="rit-imp" /></div>
                <div><Label className="text-xs">Aliquota %</Label>
                    <Input type="number" step="0.01" value={f.aliquota} onChange={(e) => set("aliquota", parseFloat(e.target.value) || 0)} /></div>
                <div><Label className="text-xs">Ritenuta calcolata €</Label>
                    <Input type="number" step="0.01" value={f.importo_ritenuta} onChange={(e) => set("importo_ritenuta", parseFloat(e.target.value) || 0)} className="font-semibold" /></div>
                <div className="col-span-2 flex items-center gap-2 mt-2">
                    <Checkbox checked={!!f.versata} onCheckedChange={(v) => set("versata", !!v)} id="rit-versata" />
                    <Label htmlFor="rit-versata" className="text-xs">Versata</Label>
                </div>
                {f.versata && (
                    <div><Label className="text-xs">Data versamento</Label>
                        <Input type="date" value={f.data_versamento || ""} onChange={(e) => set("data_versamento", e.target.value)} /></div>
                )}
            </div>
            <DialogFooter>
                <Button onClick={save} className="bg-sky-700 hover:bg-sky-800" data-testid="rit-save">Salva</Button>
            </DialogFooter>
        </DialogContent>
    );
}
