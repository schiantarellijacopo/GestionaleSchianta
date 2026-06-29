/**
 * Ritenute Compagnia — gemella negativa del Rappel.
 * La compagnia ci trattiene importi sulle provvigioni (es. ritenute su vita).
 * Funzionalmente identica al Rappel ma in senso opposto: aumenta il saldo
 * da versare alla compagnia, va in estratto conto e in prima nota al
 * momento del versamento. Solo per compagnie con mandato diretto.
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
import { Plus, Trash2, Pencil, TrendingDown, Wallet, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { api, fmtEur, fmtDate } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";

export default function RitenuteCompagnia() {
    const [items, setItems] = useState(null);
    const [compagnie, setCompagnie] = useState([]);
    const [fComp, setFComp] = useState("__all__");
    const [editing, setEditing] = useState(null);
    const [dialogOpen, setDialogOpen] = useState(false);

    const load = useCallback(() => {
        const params = {};
        if (fComp && fComp !== "__all__") params.compagnia_id = fComp;
        api.get("/ritenute-compagnia", { params }).then((r) => setItems(r.data || []));
    }, [fComp]);

    useEffect(() => { load(); }, [load]);
    useEffect(() => {
        // mostriamo solo compagnie con mandato diretto
        api.get("/compagnie").then((r) =>
            setCompagnie((r.data || []).filter((c) => c.attiva !== false && (c.tipo_mandato || "diretto") === "diretto")));
    }, []);

    const apriNuovo = () => { setEditing(null); setDialogOpen(true); };
    const apriEdit = (r) => { setEditing(r); setDialogOpen(true); };

    const elimina = async (r) => {
        if (!window.confirm(`Eliminare la ritenuta di ${fmtEur(r.importo)}?${r.stato === "versata" ? "\n(Verrà rimosso anche il movimento in Prima Nota)" : ""}`)) return;
        try {
            await api.delete(`/ritenute-compagnia/${r.id}`);
            toast.success("Ritenuta eliminata"); load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const versa = async (r) => {
        const dataDefault = new Date().toISOString().slice(0, 10);
        const dataVers = window.prompt(
            `Registrare il versamento di ${fmtEur(r.importo)} (${r.compagnia_nome})?\nDigita la data di registrazione (YYYY-MM-DD).`,
            dataDefault,
        );
        if (!dataVers) return;
        try {
            await api.post(`/ritenute-compagnia/${r.id}/versa`, { data_versamento: dataVers });
            toast.success("Versamento registrato in Prima Nota"); load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const storna = async (r) => {
        if (!window.confirm("Annullare il versamento?\nIl movimento in Prima Nota verrà rimosso.")) return;
        try {
            await api.post(`/ritenute-compagnia/${r.id}/storna`);
            toast.success("Versamento stornato"); load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const totale = useMemo(() => (items || []).reduce((s, r) => s + (r.importo || 0), 0), [items]);
    const totDaVersare = useMemo(() => (items || []).filter((r) => r.stato !== "versata").reduce((s, r) => s + (r.importo || 0), 0), [items]);

    return (
        <div className="p-6 space-y-5" data-testid="ritenute-compagnia-page">
            <div className="flex items-start justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
                        <TrendingDown className="text-rose-600" size={26} />
                        Ritenute Compagnia
                    </h1>
                    <p className="text-sm text-slate-500 mt-1 max-w-2xl">
                        Le compagnie ci trattengono importi sulle provvigioni (es. ritenute su vita).
                        Ogni ritenuta <span className="font-medium text-rose-700">aumenta il saldo da versare</span> alla
                        compagnia e va in estratto conto. Al versamento crea un'uscita in Prima Nota.
                        <span className="text-amber-600 ml-1">Solo per compagnie con mandato diretto.</span>
                    </p>
                </div>
                <Button onClick={apriNuovo} className="bg-rose-700 hover:bg-rose-800" data-testid="ritc-new">
                    <Plus size={16} className="mr-2" /> Nuova ritenuta
                </Button>
            </div>

            {/* KPI */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <Card className="p-3 border-l-4 border-rose-400 bg-white">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">Totale ritenute</div>
                    <div className="text-2xl font-bold font-mono text-rose-700">{fmtEur(totale)}</div>
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

            {/* Filtri */}
            <Card className="p-3 flex flex-wrap gap-3 items-end">
                <div>
                    <Label className="text-xs">Compagnia</Label>
                    <Select value={fComp} onValueChange={setFComp}>
                        <SelectTrigger className="w-64" data-testid="ritc-filt-comp">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="__all__">Tutte (mandato diretto)</SelectItem>
                            {compagnie.map((c) => <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
            </Card>

            {items === null ? <Loading /> : items.length === 0 ? <Empty message="Nessuna ritenuta registrata" /> : (
                <table className="tbl-compact w-full text-xs">
                    <thead>
                        <tr>
                            <th>Data</th><th>Anno</th><th>Compagnia</th><th>Descrizione</th>
                            <th className="text-right">Importo €</th><th>Stato</th><th className="w-32"></th>
                        </tr>
                    </thead>
                    <tbody>
                        {items.map((r) => {
                            const versata = r.stato === "versata";
                            return (
                                <tr key={r.id} data-testid={`ritc-row-${r.id}`}>
                                    <td className="num">{fmtDate(r.data)}</td>
                                    <td className="num font-medium">{r.anno}</td>
                                    <td>
                                        <div className="font-medium">{r.compagnia_nome || "—"}</div>
                                        {r.compagnia_codice && <div className="text-[10px] text-slate-400 font-mono">{r.compagnia_codice}</div>}
                                    </td>
                                    <td className="text-slate-600">{r.descrizione || "—"}</td>
                                    <td className="num text-right font-semibold text-rose-700">- {fmtEur(r.importo)}</td>
                                    <td>{versata ? <span className="badge badge-success">versata</span> : <span className="badge badge-warning">da versare</span>}</td>
                                    <td className="text-right whitespace-nowrap">
                                        {versata ? (
                                            <button onClick={() => storna(r)}
                                                className="inline-flex items-center justify-center h-7 w-7 rounded border border-amber-200 hover:bg-amber-50 text-amber-700 mr-1"
                                                title="Storna versamento"
                                                data-testid={`ritc-storna-${r.id}`}>
                                                <RotateCcw size={12} />
                                            </button>
                                        ) : (
                                            <button onClick={() => versa(r)}
                                                className="inline-flex items-center justify-center h-7 w-7 rounded border border-emerald-300 hover:bg-emerald-50 text-emerald-700 mr-1"
                                                title="Registra versamento" data-testid={`ritc-versa-${r.id}`}>
                                                <Wallet size={12} />
                                            </button>
                                        )}
                                        <button onClick={() => apriEdit(r)} disabled={versata}
                                            className="inline-flex items-center justify-center h-7 w-7 rounded border border-slate-200 hover:bg-slate-100 mr-1">
                                            <Pencil size={12} />
                                        </button>
                                        <button onClick={() => elimina(r)}
                                            className="inline-flex items-center justify-center h-7 w-7 rounded border border-rose-200 hover:bg-rose-50 text-rose-600">
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
                <RitenutaCompagniaDialog
                    item={editing} compagnie={compagnie}
                    onClose={(refresh) => { setDialogOpen(false); setEditing(null); if (refresh) load(); }}
                />
            )}
        </div>
    );
}

function RitenutaCompagniaDialog({ item, compagnie, onClose }) {
    const [f, setF] = useState(() => item ? {
        compagnia_id: item.compagnia_id,
        data: item.data,
        importo: String(item.importo),
        descrizione: item.descrizione || "",
        note: item.note || "",
    } : {
        compagnia_id: "",
        data: new Date().toISOString().slice(0, 10),
        importo: "",
        descrizione: "",
        note: "",
    });
    const [saving, setSaving] = useState(false);
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const save = async () => {
        if (!f.compagnia_id) { toast.error("Seleziona la compagnia"); return; }
        if (!f.data) { toast.error("Inserisci la data"); return; }
        const imp = parseFloat(f.importo);
        if (!imp || imp <= 0) { toast.error("Importo deve essere positivo"); return; }
        setSaving(true);
        try {
            const body = {
                compagnia_id: f.compagnia_id, data: f.data, importo: imp,
                descrizione: f.descrizione || null, note: f.note || null,
                anno: parseInt(f.data.slice(0, 4), 10),
            };
            if (item) await api.put(`/ritenute-compagnia/${item.id}`, body);
            else await api.post("/ritenute-compagnia", body);
            toast.success(item ? "Ritenuta aggiornata" : "Ritenuta creata"); onClose(true);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        } finally { setSaving(false); }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose(false)}>
            <DialogContent className="max-w-md" data-testid="ritc-dialog">
                <DialogHeader>
                    <DialogTitle>{item ? "Modifica ritenuta" : "Nuova ritenuta compagnia"}</DialogTitle>
                </DialogHeader>
                <div className="space-y-3 py-2">
                    <div>
                        <Label>Compagnia (solo mandato diretto) *</Label>
                        <Select value={f.compagnia_id} onValueChange={(v) => set("compagnia_id", v)}>
                            <SelectTrigger data-testid="ritc-comp"><SelectValue placeholder="Seleziona" /></SelectTrigger>
                            <SelectContent>
                                {compagnie.map((c) => <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <Label>Data *</Label>
                            <Input type="date" value={f.data} onChange={(e) => set("data", e.target.value)} data-testid="ritc-data" />
                        </div>
                        <div>
                            <Label>Importo € *</Label>
                            <Input type="number" step="0.01" min="0"
                                value={f.importo} onChange={(e) => set("importo", e.target.value)} data-testid="ritc-importo" />
                        </div>
                    </div>
                    <div>
                        <Label>Descrizione</Label>
                        <Input placeholder="es. Ritenuta vita Q3, Storno commissioni..."
                            value={f.descrizione} onChange={(e) => set("descrizione", e.target.value)} />
                    </div>
                    <div>
                        <Label>Note</Label>
                        <Input value={f.note} onChange={(e) => set("note", e.target.value)} />
                    </div>
                    <div className="text-[11px] text-rose-700 bg-rose-50 border border-rose-200 rounded p-2">
                        La ritenuta viene registrata come <strong>dare</strong> verso la compagnia
                        (aumenta il saldo da versare). Premi "Versa" per registrare il pagamento in
                        Prima Nota.
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={() => onClose(false)}>Annulla</Button>
                    <Button onClick={save} disabled={saving} className="bg-rose-700 hover:bg-rose-800" data-testid="ritc-save">
                        {saving ? "Salvataggio…" : (item ? "Aggiorna" : "Crea ritenuta")}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
