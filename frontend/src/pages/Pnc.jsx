/**
 * PNC — Partite PNC (Rivalsa / Cassa Agenti / Fondo Pensione / Gruppo Agenti).
 * Stesso funzionamento delle Ritenute: imponibile × aliquota, totali per anno/collaboratore.
 * Il "Versa" crea un movimento in Prima Nota (colonna PNC), come la Ritenuta compagnia.
 */
import { useEffect, useMemo, useState } from "react";
import { api, fmtEur } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { Plus, Trash2, Edit, Landmark, CheckCircle2, RotateCcw } from "lucide-react";
import { toast } from "sonner";

const TIPI = [
    { key: "rivalsa", label: "Rivalsa" },
    { key: "cassa_agenti", label: "Cassa Agenti" },
    { key: "fondo_pensione", label: "Fondo Pensione" },
    { key: "gruppo_agenti", label: "Gruppo Agenti" },
];
const TIPO_LABEL = Object.fromEntries(TIPI.map((t) => [t.key, t.label]));

export default function Pnc() {
    const currentYear = new Date().getFullYear();
    const [anno, setAnno] = useState(currentYear);
    const [filtroTipo, setFiltroTipo] = useState("");
    const [items, setItems] = useState(null);
    const [totali, setTotali] = useState(null);
    const [editing, setEditing] = useState(null);
    const [open, setOpen] = useState(false);
    const [collabs, setCollabs] = useState([]);

    const load = () => {
        const params = { anno };
        if (filtroTipo) params.tipo = filtroTipo;
        api.get("/pnc", { params }).then((r) => setItems(r.data));
        api.get("/pnc/totali", { params }).then((r) => setTotali(r.data));
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [anno, filtroTipo]);
    useEffect(() => {
        api.get("/auth/users").then((r) => {
            const list = (r.data || []).filter((x) => (x.role || "") !== "cliente" && x.attivo !== false);
            setCollabs(list);
        }).catch(() => setCollabs([]));
    }, []);

    const totGen = useMemo(() => {
        const t = totali?.per_collaboratore || [];
        return {
            imponibile: t.reduce((s, x) => s + (x.imponibile_tot || 0), 0),
            importo: t.reduce((s, x) => s + (x.importo_tot || 0), 0),
            versata: t.reduce((s, x) => s + (x.versata_tot || 0), 0),
            n: t.reduce((s, x) => s + (x.n_record || 0), 0),
        };
    }, [totali]);

    const del = async (id) => {
        if (!window.confirm("Eliminare la partita PNC? (se versata rimuove anche il movimento)")) return;
        await api.delete(`/pnc/${id}`); toast.success("Eliminata"); load();
    };
    const versa = async (id) => {
        try { await api.post(`/pnc/${id}/versa`); toast.success("Versata · movimento creato in Prima Nota"); load(); }
        catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };
    const storna = async (id) => {
        if (!window.confirm("Stornare il versamento? Il movimento in Prima Nota verrà rimosso.")) return;
        try { await api.post(`/pnc/${id}/storna`); toast.success("Stornata"); load(); }
        catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <div data-testid="pnc-page">
            <PageHeader
                title={<span className="flex items-center gap-2"><Landmark className="text-fuchsia-600" size={20} /> Partite PNC</span>}
                subtitle="Rivalsa · Cassa Agenti · Fondo Pensione · Gruppo Agenti — versamento in Prima Nota"
                actions={
                    <div className="flex gap-2">
                        <Select value={String(anno)} onValueChange={(v) => setAnno(parseInt(v))}>
                            <SelectTrigger className="w-28" data-testid="pnc-anno"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                {[0, -1, -2, -3, -4].map((d) => {
                                    const y = currentYear + d;
                                    return <SelectItem key={y} value={String(y)}>{y}</SelectItem>;
                                })}
                            </SelectContent>
                        </Select>
                        <Dialog open={open} onOpenChange={setOpen}>
                            <DialogTrigger asChild>
                                <Button onClick={() => setEditing(null)} data-testid="pnc-new">
                                    <Plus size={14} className="mr-1" /> Nuova PNC
                                </Button>
                            </DialogTrigger>
                            <PncDialog editing={editing} anno={anno} collabs={collabs} filtroTipo={filtroTipo}
                                onClose={() => { setOpen(false); setEditing(null); load(); }} />
                        </Dialog>
                    </div>
                }
            />

            {/* Filtro tipo */}
            <div className="flex flex-wrap gap-2 mb-4">
                <button onClick={() => setFiltroTipo("")}
                    className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${filtroTipo === "" ? "bg-fuchsia-700 text-white border-fuchsia-700" : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"}`}
                    data-testid="pnc-filter-all">Tutti</button>
                {TIPI.map((t) => (
                    <button key={t.key} onClick={() => setFiltroTipo(t.key)}
                        className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${filtroTipo === t.key ? "bg-fuchsia-700 text-white border-fuchsia-700" : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"}`}
                        data-testid={`pnc-filter-${t.key}`}>{t.label}</button>
                ))}
            </div>

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
                <Card className="p-3 border-l-4 border-fuchsia-400 bg-white">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">Importo Totale</div>
                    <div className="text-xl font-bold font-mono">{fmtEur(totGen.importo)}</div>
                </Card>
                <Card className="p-3 border-l-4 border-emerald-400 bg-white">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">Versate</div>
                    <div className="text-xl font-bold font-mono">{fmtEur(totGen.versata)}</div>
                </Card>
            </div>

            {/* Riepilogo per tipo */}
            {totali?.per_tipo && totali.per_tipo.length > 0 && (
                <div className="flex flex-wrap gap-2 mb-4">
                    {totali.per_tipo.map((t) => (
                        <div key={t.tipo} className="text-xs bg-fuchsia-50 border border-fuchsia-200 rounded px-3 py-1.5">
                            <span className="font-semibold text-fuchsia-800">{t.tipo_label}</span>
                            <span className="text-slate-500"> · {t.n_record}</span>
                            <span className="font-mono ml-1">{fmtEur(t.importo_tot)}</span>
                        </div>
                    ))}
                </div>
            )}

            {/* Riepilogo per collaboratore */}
            {totali && totali.per_collaboratore && totali.per_collaboratore.length > 0 && (
                <Card className="mb-4 p-3">
                    <div className="text-xs font-semibold text-slate-600 mb-2">Riepilogo per collaboratore</div>
                    <table className="w-full text-xs">
                        <thead><tr className="text-slate-500 text-left border-b">
                            <th className="py-1.5">Collaboratore</th>
                            <th className="text-right">N</th>
                            <th className="text-right">Imponibile</th>
                            <th className="text-right">Importo</th>
                            <th className="text-right">Versato</th>
                            <th className="text-right">Residuo</th>
                        </tr></thead>
                        <tbody>
                            {totali.per_collaboratore.map((r) => (
                                <tr key={r.collaboratore_id} className="border-b border-slate-100">
                                    <td className="py-1.5 font-medium">{r.collaboratore_nome || "—"}</td>
                                    <td className="text-right">{r.n_record}</td>
                                    <td className="text-right font-mono">{fmtEur(r.imponibile_tot)}</td>
                                    <td className="text-right font-mono">{fmtEur(r.importo_tot)}</td>
                                    <td className="text-right font-mono text-emerald-700">{fmtEur(r.versata_tot)}</td>
                                    <td className="text-right font-mono text-rose-700">{fmtEur((r.importo_tot || 0) - (r.versata_tot || 0))}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </Card>
            )}

            {/* Dettaglio */}
            <div className="tbl-scroll">
                {items === null ? <Loading /> : items.length === 0 ? <Empty /> : (
                    <table className="tbl-compact w-full text-xs">
                        <thead><tr>
                            <th>Data</th><th>Tipo</th><th>Collaboratore</th><th>Descrizione</th>
                            <th className="text-right">Imponibile</th>
                            <th className="text-right">Aliq.</th>
                            <th className="text-right">Importo</th>
                            <th>Stato</th><th>Data Vers.</th><th className="w-24"></th>
                        </tr></thead>
                        <tbody>
                            {items.map((r) => (
                                <tr key={r.id} data-testid={`pnc-row-${r.id}`}>
                                    <td>{r.data || "—"}</td>
                                    <td><span className="inline-block px-1.5 py-0.5 rounded bg-fuchsia-100 text-fuchsia-700 text-[10px] font-medium">{TIPO_LABEL[r.tipo] || r.tipo}</span></td>
                                    <td className="font-medium">{r.collaboratore_nome || "—"}</td>
                                    <td>{r.descrizione || "—"}</td>
                                    <td className="text-right font-mono">{fmtEur(r.imponibile)}</td>
                                    <td className="text-right">{r.aliquota}%</td>
                                    <td className="text-right font-mono font-semibold">{fmtEur(r.importo)}</td>
                                    <td>{r.stato === "versata"
                                        ? <span className="text-emerald-700 font-medium">Versata</span>
                                        : <span className="text-amber-600">Da versare</span>}</td>
                                    <td>{r.data_versamento || "—"}</td>
                                    <td className="text-right space-x-1 whitespace-nowrap">
                                        {r.stato !== "versata" ? (
                                            <button onClick={() => versa(r.id)} title="Versa (crea movimento)"
                                                className="text-emerald-700 hover:bg-emerald-50 p-1 rounded" data-testid={`pnc-versa-${r.id}`}>
                                                <CheckCircle2 size={12} />
                                            </button>
                                        ) : (
                                            <button onClick={() => storna(r.id)} title="Storna versamento"
                                                className="text-amber-600 hover:bg-amber-50 p-1 rounded" data-testid={`pnc-storna-${r.id}`}>
                                                <RotateCcw size={12} />
                                            </button>
                                        )}
                                        <button onClick={() => { setEditing(r); setOpen(true); }}
                                            className="text-sky-700 hover:bg-sky-50 p-1 rounded" data-testid={`pnc-edit-${r.id}`}>
                                            <Edit size={12} />
                                        </button>
                                        <button onClick={() => del(r.id)} className="text-rose-600 hover:bg-rose-50 p-1 rounded" data-testid={`pnc-del-${r.id}`}>
                                            <Trash2 size={12} />
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

function PncDialog({ editing, anno, collabs, filtroTipo, onClose }) {
    const [f, setF] = useState(editing || {
        anno, tipo: filtroTipo || "rivalsa", collaboratore_id: "", descrizione: "",
        imponibile: 0, aliquota: 0, importo: 0, causale: "",
        data: new Date().toISOString().slice(0, 10), note: "",
    });
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
    useEffect(() => {
        if (f.imponibile && f.aliquota) {
            const r = Math.round(parseFloat(f.imponibile) * parseFloat(f.aliquota)) / 100;
            setF((p) => ({ ...p, importo: r }));
        }
    // eslint-disable-next-line
    }, [f.imponibile, f.aliquota]);
    const save = async () => {
        if (!f.tipo) { toast.error("Seleziona il tipo PNC"); return; }
        if (!f.collaboratore_id) { toast.error("Seleziona collaboratore"); return; }
        try {
            if (editing?.id) await api.put(`/pnc/${editing.id}`, f);
            else await api.post("/pnc", f);
            toast.success("Salvata"); onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };
    return (
        <DialogContent className="max-w-xl">
            <DialogHeader><DialogTitle>{editing?.id ? "Modifica PNC" : "Nuova PNC"}</DialogTitle></DialogHeader>
            <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2"><Label className="text-xs">Tipo PNC *</Label>
                    <Select value={f.tipo} onValueChange={(v) => set("tipo", v)}>
                        <SelectTrigger data-testid="pnc-tipo"><SelectValue placeholder="Seleziona tipo" /></SelectTrigger>
                        <SelectContent>
                            {TIPI.map((t) => <SelectItem key={t.key} value={t.key}>{t.label}</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
                <div><Label className="text-xs">Anno *</Label>
                    <Input type="number" value={f.anno} onChange={(e) => set("anno", parseInt(e.target.value) || anno)} /></div>
                <div><Label className="text-xs">Data</Label>
                    <Input type="date" value={f.data || ""} onChange={(e) => set("data", e.target.value)} /></div>
                <div className="col-span-2"><Label className="text-xs">Collaboratore *</Label>
                    <Select value={f.collaboratore_id} onValueChange={(v) => set("collaboratore_id", v)}>
                        <SelectTrigger data-testid="pnc-collab"><SelectValue placeholder="Seleziona" /></SelectTrigger>
                        <SelectContent>
                            {collabs.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
                <div className="col-span-2"><Label className="text-xs">Descrizione</Label>
                    <Input value={f.descrizione || ""} onChange={(e) => set("descrizione", e.target.value)} /></div>
                <div><Label className="text-xs">Causale</Label>
                    <Input value={f.causale || ""} onChange={(e) => set("causale", e.target.value)} /></div>
                <div><Label className="text-xs">Imponibile €</Label>
                    <Input type="number" step="0.01" value={f.imponibile} onChange={(e) => set("imponibile", parseFloat(e.target.value) || 0)} data-testid="pnc-imp" /></div>
                <div><Label className="text-xs">Aliquota %</Label>
                    <Input type="number" step="0.01" value={f.aliquota} onChange={(e) => set("aliquota", parseFloat(e.target.value) || 0)} /></div>
                <div><Label className="text-xs">Importo calcolato €</Label>
                    <Input type="number" step="0.01" value={f.importo} onChange={(e) => set("importo", parseFloat(e.target.value) || 0)} className="font-semibold" data-testid="pnc-importo" /></div>
            </div>
            <DialogFooter>
                <Button onClick={save} className="bg-fuchsia-700 hover:bg-fuchsia-800" data-testid="pnc-save">Salva</Button>
            </DialogFooter>
        </DialogContent>
    );
}
