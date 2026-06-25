import React, { useCallback, useEffect, useMemo, useState } from "react";
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
import { Plus, Trash2, Pencil, Gift, TrendingUp, ChevronDown, ChevronRight, Wallet, Printer, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { api, fmtEur, fmtDate, API_BASE } from "@/lib/api";
import AllegatiCell from "@/components/AllegatiCell";

const Loading = () => <div className="p-6 text-sm text-slate-400">Caricamento…</div>;
const Empty = ({ message = "Nessun risultato" }) => (
    <div className="p-8 text-center text-sm text-slate-400">{message}</div>
);

export default function RappelPage() {
    const [items, setItems] = useState(null);
    const [archivio, setArchivio] = useState(null);
    const [compagnie, setCompagnie] = useState([]);
    const [filtroCompagnia, setFiltroCompagnia] = useState("__all__");
    const [filtroAnno, setFiltroAnno] = useState("__all__");
    const [editing, setEditing] = useState(null);
    const [dialogOpen, setDialogOpen] = useState(false);

    const load = useCallback(() => {
        const params = {};
        if (filtroCompagnia && filtroCompagnia !== "__all__") params.compagnia_id = filtroCompagnia;
        if (filtroAnno && filtroAnno !== "__all__") params.anno = parseInt(filtroAnno, 10);
        api.get("/rappel", { params }).then((r) => setItems(r.data || []));
        api.get("/rappel/archivio").then((r) => setArchivio(r.data || []));
    }, [filtroCompagnia, filtroAnno]);

    useEffect(() => { load(); }, [load]);
    useEffect(() => {
        api.get("/compagnie")
            .then((r) => setCompagnie((r.data || []).filter((c) => c.attiva !== false)));
    }, []);

    const apriNuovo = () => { setEditing(null); setDialogOpen(true); };
    const apriEdit = (r) => { setEditing(r); setDialogOpen(true); };
    const elimina = async (r) => {
        if (!window.confirm(`Eliminare il rappel di ${fmtEur(r.importo)} di ${r.compagnia_nome}?${r.stato === "incassato" ? "\n(Verrà rimosso anche il movimento in Prima Nota)" : ""}`)) return;
        try {
            await api.delete(`/rappel/${r.id}`);
            toast.success("Rappel eliminato");
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        }
    };

    const incassa = async (r) => {
        if (!window.confirm(`Incassare il rappel di ${fmtEur(r.importo)} (${r.compagnia_nome})?\nVerrà registrato in Prima Nota come provvigione.`)) return;
        try {
            await api.post(`/rappel/${r.id}/incassa`, {});
            toast.success("Rappel incassato e registrato in Prima Nota");
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        }
    };

    const storna = async (r) => {
        if (!window.confirm(`Annullare l'incasso del rappel?\nIl movimento in Prima Nota verrà rimosso.`)) return;
        try {
            await api.post(`/rappel/${r.id}/storna`);
            toast.success("Incasso annullato");
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        }
    };

    const anniDisponibili = useMemo(
        () => (archivio || []).map((a) => a.anno),
        [archivio],
    );
    const totaleAnno = useMemo(() => {
        if (!archivio || filtroAnno === "__all__") {
            return (archivio || []).reduce((s, a) => s + a.totale, 0);
        }
        const found = archivio.find((a) => a.anno === parseInt(filtroAnno, 10));
        return found ? found.totale : 0;
    }, [archivio, filtroAnno]);

    return (
        <div className="p-6 space-y-5" data-testid="rappel-page">
            <div className="flex items-start justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
                        <Gift className="text-fuchsia-600" size={26} />
                        Rappel — Sovraprovvigioni Compagnie
                    </h1>
                    <p className="text-sm text-slate-500 mt-1 max-w-2xl">
                        Le compagnie ti accreditano sovraprovvigioni in base al raggiungimento di obiettivi.
                        Ogni rappel <span className="font-medium">riduce il saldo da versare</span> alla compagnia
                        come una rimessa fittizia (non transita in banca).
                    </p>
                </div>
                <Button onClick={apriNuovo} className="bg-fuchsia-700 hover:bg-fuchsia-800" data-testid="rappel-new-btn">
                    <Plus size={16} className="mr-2" /> Nuovo rappel
                </Button>
            </div>

            {/* Archivio per anno */}
            <Card className="border-slate-200 p-4" data-testid="rappel-archivio">
                <div className="flex items-center gap-2 mb-3">
                    <TrendingUp size={16} className="text-fuchsia-700" />
                    <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-700">
                        Archivio per anno
                    </h2>
                </div>
                {!archivio ? <Loading /> : archivio.length === 0 ? (
                    <Empty message="Nessun rappel registrato — usa 'Nuovo rappel' per iniziare l'archivio storico" />
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                        {archivio.map((anno) => (
                            <CardAnno key={anno.anno} anno={anno} onClickAnno={() => setFiltroAnno(String(anno.anno))} />
                        ))}
                    </div>
                )}
            </Card>

            {/* Filtri + tabella movimenti */}
            <Card className="border-slate-200">
                <div className="p-4 border-b border-slate-200 flex flex-wrap items-end gap-3">
                    <div>
                        <Label className="text-xs">Compagnia</Label>
                        <Select value={filtroCompagnia} onValueChange={setFiltroCompagnia}>
                            <SelectTrigger className="w-64" data-testid="rappel-filt-comp">
                                <SelectValue placeholder="Tutte" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="__all__">Tutte le compagnie</SelectItem>
                                {compagnie.map((c) => (
                                    <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <Label className="text-xs">Anno</Label>
                        <Select value={filtroAnno} onValueChange={setFiltroAnno}>
                            <SelectTrigger className="w-32" data-testid="rappel-filt-anno">
                                <SelectValue placeholder="Tutti" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="__all__">Tutti</SelectItem>
                                {anniDisponibili.map((a) => (
                                    <SelectItem key={a} value={String(a)}>{a}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="ml-auto text-sm">
                        <span className="text-slate-500">Totale {filtroAnno !== "__all__" ? filtroAnno : "complessivo"}:</span>{" "}
                        <span className="font-bold text-fuchsia-700 num">{fmtEur(totaleAnno)}</span>
                    </div>
                </div>

                {items === null ? <Loading /> : items.length === 0 ? (
                    <Empty message="Nessun rappel con i filtri selezionati" />
                ) : (
                    <table className="tbl w-full">
                        <thead>
                            <tr>
                                <th>Data</th>
                                <th>Anno</th>
                                <th>Compagnia</th>
                                <th>Descrizione</th>
                                <th className="text-right">Importo €</th>
                                <th>Stato</th>
                                <th className="text-center">Allegati</th>
                                <th className="text-center">Stampa</th>
                                <th className="w-32"></th>
                            </tr>
                        </thead>
                        <tbody>
                            {items.map((r) => {
                                const incassato = r.stato === "incassato";
                                return (
                                    <tr key={r.id} data-testid={`rappel-row-${r.id}`}>
                                        <td className="num">{fmtDate(r.data)}</td>
                                        <td className="num font-medium">{r.anno}</td>
                                        <td>
                                            <div className="font-medium">{r.compagnia_nome || "—"}</div>
                                            {r.compagnia_codice && (
                                                <div className="text-[10px] text-slate-400 font-mono">{r.compagnia_codice}</div>
                                            )}
                                        </td>
                                        <td className="text-sm text-slate-600">{r.descrizione || "—"}</td>
                                        <td className="num text-right font-semibold text-fuchsia-700">{fmtEur(r.importo)}</td>
                                        <td>
                                            {incassato
                                                ? <span className="badge badge-success" title={`Incassato il ${fmtDate(r.data_incasso)}`}>incassato</span>
                                                : <span className="badge badge-warning">da incassare</span>}
                                        </td>
                                        <td className="text-center">
                                            <AllegatiCell
                                                entita_tipo="rappel"
                                                entita_id={r.id}
                                                count={r.n_allegati || 0}
                                                hint="Allega documento"
                                                onChange={load}
                                            />
                                        </td>
                                        <td className="text-center">
                                            <a
                                                href={`${API_BASE}/stampa/rappel/${r.id}`}
                                                target="_blank" rel="noreferrer"
                                                title="Stampa PDF rappel"
                                                data-testid={`rappel-print-${r.id}`}
                                            >
                                                <button className="inline-flex items-center justify-center h-7 w-7 rounded border border-slate-200 hover:bg-slate-100">
                                                    <Printer size={12} />
                                                </button>
                                            </a>
                                        </td>
                                        <td className="text-right whitespace-nowrap">
                                            {incassato ? (
                                                <button
                                                    onClick={() => storna(r)}
                                                    className="inline-flex items-center justify-center h-7 w-7 rounded border border-amber-200 hover:bg-amber-50 text-amber-700 mr-1"
                                                    title="Annulla incasso"
                                                    data-testid={`rappel-storna-${r.id}`}
                                                >
                                                    <RotateCcw size={12} />
                                                </button>
                                            ) : (
                                                <button
                                                    onClick={() => incassa(r)}
                                                    className="inline-flex items-center justify-center h-7 w-7 rounded border border-emerald-300 hover:bg-emerald-50 text-emerald-700 mr-1"
                                                    title="Incassa rappel"
                                                    data-testid={`rappel-incassa-${r.id}`}
                                                >
                                                    <Wallet size={12} />
                                                </button>
                                            )}
                                            <button
                                                onClick={() => apriEdit(r)}
                                                className="inline-flex items-center justify-center h-7 w-7 rounded border border-slate-200 hover:bg-slate-100 mr-1"
                                                data-testid={`rappel-edit-${r.id}`}
                                                title="Modifica"
                                                disabled={incassato}
                                            >
                                                <Pencil size={12} />
                                            </button>
                                            <button
                                                onClick={() => elimina(r)}
                                                className="inline-flex items-center justify-center h-7 w-7 rounded border border-rose-200 hover:bg-rose-50 text-rose-600"
                                                data-testid={`rappel-del-${r.id}`}
                                                title="Elimina"
                                            >
                                                <Trash2 size={12} />
                                            </button>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                )}
            </Card>

            {dialogOpen && (
                <RappelDialog
                    rappel={editing}
                    compagnie={compagnie}
                    onClose={(refresh) => {
                        setDialogOpen(false);
                        setEditing(null);
                        if (refresh) load();
                    }}
                />
            )}
        </div>
    );
}

function CardAnno({ anno, onClickAnno }) {
    const [expanded, setExpanded] = useState(false);
    return (
        <div className="border border-slate-200 rounded-lg p-3 bg-gradient-to-br from-fuchsia-50/60 to-white hover:shadow-sm transition" data-testid={`rappel-anno-${anno.anno}`}>
            <button
                className="w-full flex items-center justify-between text-left"
                onClick={() => setExpanded((p) => !p)}
            >
                <div>
                    <div className="text-xs uppercase tracking-wider text-fuchsia-700">Anno</div>
                    <div className="text-2xl font-bold text-slate-900">{anno.anno}</div>
                </div>
                <div className="text-right">
                    <div className="text-xs text-slate-500">{anno.n_movimenti} movimenti</div>
                    <div className="text-lg font-bold text-fuchsia-700 num">{fmtEur(anno.totale)}</div>
                </div>
                {expanded ? <ChevronDown size={14} className="ml-2 text-slate-400" /> : <ChevronRight size={14} className="ml-2 text-slate-400" />}
            </button>
            {expanded && (
                <div className="mt-2 pt-2 border-t border-slate-200 space-y-1">
                    {anno.compagnie.map((c) => (
                        <div key={c.compagnia_id} className="flex items-center justify-between text-xs">
                            <span className="truncate flex-1 text-slate-700">{c.compagnia_nome}</span>
                            <span className="num text-fuchsia-700 font-semibold">{fmtEur(c.totale)}</span>
                        </div>
                    ))}
                    <button
                        onClick={(e) => { e.stopPropagation(); onClickAnno(); }}
                        className="text-[11px] text-sky-700 hover:underline mt-2"
                    >
                        → Vedi solo {anno.anno}
                    </button>
                </div>
            )}
        </div>
    );
}

function RappelDialog({ rappel, compagnie, onClose }) {
    const [f, setF] = useState(() => rappel ? {
        compagnia_id: rappel.compagnia_id,
        data: rappel.data,
        importo: String(rappel.importo),
        descrizione: rappel.descrizione || "",
        note: rappel.note || "",
        anno: rappel.anno,
    } : {
        compagnia_id: "",
        data: new Date().toISOString().slice(0, 10),
        importo: "",
        descrizione: "",
        note: "",
        anno: undefined,
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
                compagnia_id: f.compagnia_id,
                data: f.data,
                importo: imp,
                descrizione: f.descrizione || null,
                note: f.note || null,
                anno: f.anno || parseInt(f.data.slice(0, 4), 10),
            };
            if (rappel) {
                await api.put(`/rappel/${rappel.id}`, body);
                toast.success("Rappel aggiornato");
            } else {
                await api.post("/rappel", body);
                toast.success("Rappel creato");
            }
            onClose(true);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        } finally { setSaving(false); }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose(false)}>
            <DialogContent className="max-w-md" data-testid="rappel-dialog">
                <DialogHeader>
                    <DialogTitle>{rappel ? "Modifica rappel" : "Nuovo rappel"}</DialogTitle>
                </DialogHeader>
                <div className="space-y-3 py-2">
                    <div>
                        <Label>Compagnia *</Label>
                        <Select value={f.compagnia_id} onValueChange={(v) => set("compagnia_id", v)}>
                            <SelectTrigger data-testid="rappel-dlg-comp"><SelectValue placeholder="Seleziona" /></SelectTrigger>
                            <SelectContent>
                                {compagnie.map((c) => (
                                    <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <Label>Data accredito *</Label>
                            <Input
                                type="date" value={f.data}
                                onChange={(e) => set("data", e.target.value)}
                                data-testid="rappel-dlg-data"
                            />
                        </div>
                        <div>
                            <Label>Importo € *</Label>
                            <Input
                                type="number" step="0.01" min="0"
                                value={f.importo}
                                onChange={(e) => set("importo", e.target.value)}
                                data-testid="rappel-dlg-importo"
                            />
                        </div>
                    </div>
                    <div>
                        <Label>Descrizione</Label>
                        <Input
                            placeholder="es. Bonus obiettivo Q1, Premio fedeltà 2026..."
                            value={f.descrizione}
                            onChange={(e) => set("descrizione", e.target.value)}
                            data-testid="rappel-dlg-desc"
                        />
                    </div>
                    <div>
                        <Label>Note (opzionali)</Label>
                        <Input
                            value={f.note}
                            onChange={(e) => set("note", e.target.value)}
                            data-testid="rappel-dlg-note"
                        />
                    </div>
                    <div className="text-[11px] text-slate-500 bg-fuchsia-50 border border-fuchsia-200 rounded p-2">
                        Il rappel viene registrato come <strong>avere</strong> verso la compagnia e
                        ridurrà il saldo da versare. Non viene creato alcun movimento in banca.
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={() => onClose(false)}>Annulla</Button>
                    <Button
                        onClick={save} disabled={saving}
                        className="bg-fuchsia-700 hover:bg-fuchsia-800"
                        data-testid="rappel-dlg-save"
                    >
                        {saving ? "Salvataggio…" : (rappel ? "Aggiorna" : "Crea rappel")}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
