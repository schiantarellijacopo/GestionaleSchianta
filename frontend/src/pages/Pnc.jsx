/**
 * PNC — Partite PNC (Rivalsa / Cassa Agenti / Fondo Pensione / Gruppo Agenti).
 * Identica alle Ritenute Compagnia (compagnia + segno + importo + Versa in Prima Nota),
 * con in più la tendina "Tipo PNC".
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
    Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";
import { Plus, Trash2, Pencil, Landmark, Wallet, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { api, fmtEur, fmtDate } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import SortHeader, { useTableSort } from "@/components/SortHeader";

const TIPI = [
    { key: "rivalsa", label: "Rivalsa" },
    { key: "cassa_agenti", label: "Cassa Agenti" },
    { key: "fondo_pensione", label: "Fondo Pensione" },
    { key: "gruppo_agenti", label: "Gruppo Agenti" },
];
const TIPO_LABEL = Object.fromEntries(TIPI.map((t) => [t.key, t.label]));

export default function Pnc() {
    const [items, setItems] = useState(null);
    const [compagnie, setCompagnie] = useState([]);
    const [fTipo, setFTipo] = useState("");
    const [editing, setEditing] = useState(null);
    const [dialogOpen, setDialogOpen] = useState(false);

    const load = useCallback(() => {
        const params = {};
        if (fTipo) params.tipo = fTipo;
        api.get("/pnc", { params }).then((r) => setItems(r.data || []));
    }, [fTipo]);

    useEffect(() => { load(); }, [load]);
    useEffect(() => {
        api.get("/compagnie").then((r) =>
            setCompagnie((r.data || []).filter((c) => c.attiva !== false && (c.tipo_mandato || "diretto") === "diretto")));
    }, []);

    const apriNuovo = () => { setEditing(null); setDialogOpen(true); };
    const apriEdit = (r) => { setEditing(r); setDialogOpen(true); };

    const elimina = async (r) => {
        if (!window.confirm(`Eliminare la partita PNC di ${fmtEur(r.importo)}?${r.stato === "versata" ? "\n(Verrà rimosso anche il movimento in Prima Nota)" : ""}`)) return;
        try { await api.delete(`/pnc/${r.id}`); toast.success("PNC eliminata"); load(); }
        catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const versa = async (r) => {
        const dataDefault = new Date().toISOString().slice(0, 10);
        const dataVers = window.prompt(
            `Registrare il versamento di ${fmtEur(r.importo)} (${r.compagnia_nome})?\nDigita la data di registrazione (YYYY-MM-DD).`,
            dataDefault,
        );
        if (!dataVers) return;
        try { await api.post(`/pnc/${r.id}/versa`, { data_versamento: dataVers }); toast.success("Versamento registrato in Prima Nota"); load(); }
        catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const storna = async (r) => {
        if (!window.confirm("Annullare il versamento?\nIl movimento in Prima Nota verrà rimosso.")) return;
        try { await api.post(`/pnc/${r.id}/storna`); toast.success("Versamento stornato"); load(); }
        catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const totale = useMemo(() => (items || []).reduce((s, r) => s + (r.importo || 0), 0), [items]);
    const totDaVersare = useMemo(() => (items || []).filter((r) => r.stato !== "versata").reduce((s, r) => s + (r.importo || 0), 0), [items]);
    const { sorted, sortKey, dir, toggle } = useTableSort(items || [], "data", "desc");

    return (
        <div className="p-6 space-y-5" data-testid="pnc-page">
            <PageHeader
                title={<span className="flex items-center gap-2"><Landmark className="text-fuchsia-600" size={24} /> Partite PNC</span>}
                subtitle="Rivalsa · Cassa Agenti · Fondo Pensione · Gruppo Agenti — come le Ritenute Compagnia, con versamento in Prima Nota"
                actions={
                    <Button onClick={apriNuovo} className="bg-fuchsia-700 hover:bg-fuchsia-800" data-testid="pnc-new">
                        <Plus size={16} className="mr-2" /> Nuova PNC
                    </Button>
                }
            />

            {/* KPI */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <Card className="p-3 border-l-4 border-fuchsia-400 bg-white">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">Totale PNC</div>
                    <div className="text-2xl font-bold font-mono text-fuchsia-700">{fmtEur(totale)}</div>
                </Card>
                <Card className="p-3 border-l-4 border-amber-400 bg-white">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">Da versare</div>
                    <div className="text-2xl font-bold font-mono text-amber-700">{fmtEur(totDaVersare)}</div>
                </Card>
                <Card className="p-3 border-l-4 border-emerald-400 bg-white">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">Versate</div>
                    <div className="text-2xl font-bold font-mono text-emerald-700">{fmtEur(totale - totDaVersare)}</div>
                </Card>
            </div>

            {/* Filtro tipo */}
            <div className="flex flex-wrap gap-2">
                <button onClick={() => setFTipo("")}
                    className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${fTipo === "" ? "bg-fuchsia-700 text-white border-fuchsia-700" : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"}`}
                    data-testid="pnc-filter-all">Tutti</button>
                {TIPI.map((t) => (
                    <button key={t.key} onClick={() => setFTipo(t.key)}
                        className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${fTipo === t.key ? "bg-fuchsia-700 text-white border-fuchsia-700" : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"}`}
                        data-testid={`pnc-filter-${t.key}`}>{t.label}</button>
                ))}
            </div>

            {items === null ? <Loading /> : items.length === 0 ? <Empty message="Nessuna partita PNC registrata" /> : (
                <table className="tbl-compact w-full text-xs">
                    <thead>
                        <tr>
                            <th><SortHeader k="data" sortKey={sortKey} dir={dir} toggle={toggle}>Data</SortHeader></th>
                            <th><SortHeader k="tipo" sortKey={sortKey} dir={dir} toggle={toggle}>Tipo</SortHeader></th>
                            <th><SortHeader k="compagnia_nome" sortKey={sortKey} dir={dir} toggle={toggle}>Compagnia</SortHeader></th>
                            <th><SortHeader k="descrizione" sortKey={sortKey} dir={dir} toggle={toggle}>Descrizione</SortHeader></th>
                            <th className="text-right"><SortHeader k="importo" sortKey={sortKey} dir={dir} toggle={toggle}>Importo €</SortHeader></th>
                            <th><SortHeader k="stato" sortKey={sortKey} dir={dir} toggle={toggle}>Stato</SortHeader></th>
                            <th className="w-32"></th>
                        </tr>
                    </thead>
                    <tbody>
                        {sorted.map((r) => {
                            const versata = r.stato === "versata";
                            return (
                                <tr key={r.id} data-testid={`pnc-row-${r.id}`}>
                                    <td className="num">{fmtDate(r.data)}</td>
                                    <td><span className="inline-block px-1.5 py-0.5 rounded bg-fuchsia-100 text-fuchsia-700 text-[10px] font-medium">{TIPO_LABEL[r.tipo] || r.tipo}</span></td>
                                    <td>
                                        <div className="font-medium">{r.compagnia_nome || "—"}</div>
                                        {r.compagnia_codice && <div className="text-[10px] text-slate-400 font-mono">{r.compagnia_codice}</div>}
                                    </td>
                                    <td className="text-slate-600">{r.descrizione || "—"}</td>
                                    <td className="num text-right font-semibold text-fuchsia-700">{(r.importo || 0) < 0 ? "- " : "+ "}{fmtEur(Math.abs(r.importo))}</td>
                                    <td>{versata ? <span className="badge badge-success">versata</span> : <span className="badge badge-warning">da versare</span>}</td>
                                    <td className="text-right whitespace-nowrap">
                                        {versata ? (
                                            <button onClick={() => storna(r)}
                                                className="inline-flex items-center justify-center h-7 w-7 rounded border border-amber-200 hover:bg-amber-50 text-amber-700 mr-1"
                                                title="Storna versamento" data-testid={`pnc-storna-${r.id}`}>
                                                <RotateCcw size={12} />
                                            </button>
                                        ) : (
                                            <button onClick={() => versa(r)}
                                                className="inline-flex items-center justify-center h-7 w-7 rounded border border-emerald-300 hover:bg-emerald-50 text-emerald-700 mr-1"
                                                title="Registra versamento" data-testid={`pnc-versa-${r.id}`}>
                                                <Wallet size={12} />
                                            </button>
                                        )}
                                        <button onClick={() => apriEdit(r)} disabled={versata}
                                            className="inline-flex items-center justify-center h-7 w-7 rounded border border-slate-200 hover:bg-slate-100 mr-1">
                                            <Pencil size={12} />
                                        </button>
                                        <button onClick={() => elimina(r)}
                                            className="inline-flex items-center justify-center h-7 w-7 rounded border border-rose-200 hover:bg-rose-50 text-rose-600" data-testid={`pnc-del-${r.id}`}>
                                            <Trash2 size={12} />
                                        </button>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            )}

            {dialogOpen && (
                <PncDialog item={editing} compagnie={compagnie} filtroTipo={fTipo}
                    onClose={(refresh) => { setDialogOpen(false); setEditing(null); if (refresh) load(); }} />
            )}
        </div>
    );
}

function PncDialog({ item, compagnie, filtroTipo, onClose }) {
    const [f, setF] = useState(() => item ? {
        tipo: item.tipo,
        compagnia_id: item.compagnia_id,
        data: item.data,
        segno: (item.importo || 0) < 0 ? "-" : "+",
        importo: String(Math.abs(item.importo)),
        descrizione: item.descrizione || "",
        note: item.note || "",
    } : {
        tipo: filtroTipo || "rivalsa",
        compagnia_id: "",
        data: new Date().toISOString().slice(0, 10),
        segno: "+",
        importo: "",
        descrizione: "",
        note: "",
    });
    const [saving, setSaving] = useState(false);
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const save = async () => {
        if (!f.tipo) { toast.error("Seleziona il tipo PNC"); return; }
        if (!f.compagnia_id) { toast.error("Seleziona la compagnia"); return; }
        if (!f.data) { toast.error("Inserisci la data"); return; }
        const imp = Math.abs(parseFloat(f.importo));
        if (!imp) { toast.error("Importo deve essere diverso da zero"); return; }
        const firmato = f.segno === "-" ? -imp : imp;
        setSaving(true);
        try {
            const body = {
                tipo: f.tipo, compagnia_id: f.compagnia_id, data: f.data, importo: firmato,
                descrizione: f.descrizione || null, note: f.note || null,
                anno: parseInt(f.data.slice(0, 4), 10),
            };
            if (item) await api.put(`/pnc/${item.id}`, body);
            else await api.post("/pnc", body);
            toast.success(item ? "PNC aggiornata" : "PNC creata"); onClose(true);
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        finally { setSaving(false); }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose(false)}>
            <DialogContent className="max-w-md" data-testid="pnc-dialog">
                <DialogHeader>
                    <DialogTitle>{item ? "Modifica PNC" : "Nuova PNC"}</DialogTitle>
                </DialogHeader>
                <div className="space-y-3 py-2">
                    <div>
                        <Label>Tipo PNC *</Label>
                        <Select value={f.tipo} onValueChange={(v) => set("tipo", v)}>
                            <SelectTrigger data-testid="pnc-tipo"><SelectValue placeholder="Seleziona tipo" /></SelectTrigger>
                            <SelectContent>
                                {TIPI.map((t) => <SelectItem key={t.key} value={t.key}>{t.label}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <Label>Compagnia (solo mandato diretto) *</Label>
                        <Select value={f.compagnia_id} onValueChange={(v) => set("compagnia_id", v)}>
                            <SelectTrigger data-testid="pnc-comp"><SelectValue placeholder="Seleziona" /></SelectTrigger>
                            <SelectContent>
                                {compagnie.map((c) => <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="grid grid-cols-3 gap-3">
                        <div>
                            <Label>Data *</Label>
                            <Input type="date" value={f.data} onChange={(e) => set("data", e.target.value)} data-testid="pnc-data" />
                        </div>
                        <div>
                            <Label>Segno</Label>
                            <select className="w-full border rounded h-9 px-2 text-sm" value={f.segno}
                                onChange={(e) => set("segno", e.target.value)} data-testid="pnc-segno">
                                <option value="+">+ Alimenta il saldo</option>
                                <option value="-">− Riduce il saldo</option>
                            </select>
                        </div>
                        <div>
                            <Label>Importo € *</Label>
                            <Input type="number" step="0.01" min="0"
                                value={f.importo} onChange={(e) => set("importo", e.target.value)} data-testid="pnc-importo" />
                        </div>
                    </div>
                    <div>
                        <Label>Descrizione</Label>
                        <Input placeholder="es. Rivalsa Q3, Cassa agenti..."
                            value={f.descrizione} onChange={(e) => set("descrizione", e.target.value)} />
                    </div>
                    <div>
                        <Label>Note</Label>
                        <Input value={f.note} onChange={(e) => set("note", e.target.value)} />
                    </div>
                    <div className="text-[11px] text-fuchsia-700 bg-fuchsia-50 border border-fuchsia-200 rounded p-2">
                        La partita PNC viene registrata come <strong>dare</strong> verso la compagnia
                        (aumenta il saldo da versare). Premi "Versa" per registrare il pagamento in Prima Nota.
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={() => onClose(false)}>Annulla</Button>
                    <Button onClick={save} disabled={saving} className="bg-fuchsia-700 hover:bg-fuchsia-800" data-testid="pnc-save">
                        {saving ? "Salvataggio…" : (item ? "Aggiorna" : "Crea PNC")}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
