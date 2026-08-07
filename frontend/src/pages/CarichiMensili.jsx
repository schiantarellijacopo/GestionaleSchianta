/**
 * Modulo "Carichi Mensili / Quietanzamento"
 *
 * - Import selettivo dei titoli in scadenza (mese corrente / successivo)
 * - Vaglio checkbox → validazione o annullamento
 * - Replica manuale da storico polizza
 * - Blocco cancellazione titoli in Prima Nota chiusa
 * - Column toggle salvato in localStorage
 */
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
    Filter, CheckCircle2, XCircle, RotateCw, Search,
    Lock, AlertTriangle, TrendingUp, TrendingDown, Plus, Columns,
} from "lucide-react";

const ALL_COLUMNS = [
    { k: "stato_carico", label: "Stato", w: 90 },
    { k: "polizza_numero", label: "N. Polizza / Quietanza", w: 160 },
    { k: "cliente_nome", label: "Cliente", w: 200 },
    { k: "compagnia_ramo", label: "Compagnia / Ramo", w: 180 },
    { k: "polizza_targa", label: "Targa / Bene", w: 110 },
    { k: "scadenza", label: "Scadenza", w: 100 },
    { k: "mezzo_pagamento", label: "Pagamento", w: 100 },
    { k: "sinistri_badge", label: "Sinistri 12m", w: 90 },
    { k: "confronto_premio", label: "Premio Vecc. vs Nuovo", w: 170 },
    { k: "importo_netto", label: "Netto (€)", w: 90 },
    { k: "provvigioni", label: "Provv. (€)", w: 90 },
    { k: "frazionamento", label: "Frazionam.", w: 100 },
    { k: "operatore_nome", label: "Operatore", w: 130 },
    { k: "note_carico", label: "Note / Motivo", w: 220 },
    { k: "azioni", label: "Azioni", w: 130 },
];
const DEFAULT_VISIBLE = ["stato_carico", "polizza_numero", "cliente_nome",
    "compagnia_ramo", "polizza_targa", "scadenza", "sinistri_badge",
    "confronto_premio", "importo_netto", "provvigioni", "note_carico", "azioni"];
const LS_COLS = "carichi_mensili.visible_cols.v1";

const MOTIVI = ["Disdettata", "Mezzo Venduto", "Cliente Trasferito", "Voltura", "Sostituita"];

export default function CarichiMensili() {
    const [rows, setRows] = useState(null);
    const [q, setQ] = useState("");
    const [range, setRange] = useState("mese_corrente");
    const [statoCarico, setStatoCarico] = useState("in_attesa");
    const [selected, setSelected] = useState(new Set());
    const [replicaOpen, setReplicaOpen] = useState(false);
    const [annullaOpen, setAnnullaOpen] = useState(false);
    const [visible, setVisible] = useState(() => {
        try { return JSON.parse(localStorage.getItem(LS_COLS)) || DEFAULT_VISIBLE; }
        catch { return DEFAULT_VISIBLE; }
    });
    const [colToggleOpen, setColToggleOpen] = useState(false);

    const load = async () => {
        try {
            const r = await api.get("/carichi-mensili", {
                params: { stato_carico: statoCarico, range_filter: range },
            });
            setRows(r.data.righe || []);
            setSelected(new Set());
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore caricamento");
            setRows([]);
        }
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [statoCarico, range]);

    useEffect(() => {
        localStorage.setItem(LS_COLS, JSON.stringify(visible));
    }, [visible]);

    const filtered = useMemo(() => {
        if (!rows) return [];
        const qq = q.toLowerCase().trim();
        if (!qq) return rows;
        return rows.filter((r) => (
            (r.cliente_nome || "").toLowerCase().includes(qq) ||
            (r.polizza_numero || "").toLowerCase().includes(qq) ||
            (r.compagnia_nome || "").toLowerCase().includes(qq) ||
            (r.polizza_targa || "").toLowerCase().includes(qq)
        ));
    }, [rows, q]);

    const toggleAll = () => {
        if (selected.size === filtered.length) setSelected(new Set());
        else setSelected(new Set(filtered.map((r) => r.id)));
    };
    const toggleOne = (id) => {
        const s = new Set(selected);
        if (s.has(id)) s.delete(id); else s.add(id);
        setSelected(s);
    };

    const valida = async () => {
        if (selected.size === 0) return;
        if (!window.confirm(`Validare e promuovere ${selected.size} titolo/i nello Scadenziario ufficiale?`)) return;
        try {
            const r = await api.post("/carichi-mensili/valida", { titoli_ids: [...selected] });
            toast.success(`Validati ${r.data.validati} titoli`);
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore validazione");
        }
    };

    const eliminaOne = async (id) => {
        if (!window.confirm("Eliminare questo titolo? L'azione è irreversibile.")) return;
        try {
            await api.delete(`/carichi-mensili/${id}`);
            toast.success("Titolo eliminato");
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore eliminazione");
        }
    };

    const isVisible = (k) => visible.includes(k);
    const toggleCol = (k) => {
        if (visible.includes(k)) setVisible(visible.filter((v) => v !== k));
        else setVisible([...visible, k]);
    };

    return (
        <div className="p-4 md:p-6 max-w-[1600px] mx-auto" data-testid="page-carichi-mensili">
            <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900">Carichi Mensili / Quietanzamento</h1>
                    <p className="text-sm text-slate-500">Import selettivo dei titoli in scadenza + vaglio operatore</p>
                </div>
                <div className="flex items-center gap-2">
                    <Button variant="outline" onClick={() => setColToggleOpen(true)} data-testid="btn-columns">
                        <Columns size={14} className="mr-1" /> Personalizza colonne
                    </Button>
                    <Button onClick={() => setReplicaOpen(true)} className="bg-sky-700 hover:bg-sky-800" data-testid="btn-replica">
                        <Plus size={14} className="mr-1" /> Replica titolo manuale
                    </Button>
                </div>
            </div>

            {/* Filtri */}
            <Card className="p-3 mb-3 flex items-center gap-2 flex-wrap">
                <div className="flex items-center gap-1">
                    <Filter size={14} className="text-slate-500" />
                    <span className="text-xs text-slate-600 uppercase font-semibold tracking-wide">Filtri</span>
                </div>
                {["mese_corrente", "mese_successivo", "tutti"].map((r) => (
                    <Button
                        key={r} size="sm" variant={range === r ? "default" : "outline"}
                        onClick={() => setRange(r)} data-testid={`filter-range-${r}`}
                        className={range === r ? "bg-violet-600 hover:bg-violet-700" : ""}
                    >
                        {r === "mese_corrente" ? "Mese corrente" : r === "mese_successivo" ? "Mese successivo" : "Tutti"}
                    </Button>
                ))}
                <div className="w-px h-6 bg-slate-200 mx-1" />
                {[
                    { k: "in_attesa", l: "🔵 In attesa" },
                    { k: "validato", l: "✅ Validati" },
                    { k: "annullato_carico", l: "❌ Annullati" },
                    { k: "tutti", l: "Tutti" },
                ].map((s) => (
                    <Button
                        key={s.k} size="sm" variant={statoCarico === s.k ? "default" : "outline"}
                        onClick={() => setStatoCarico(s.k)} data-testid={`filter-stato-${s.k}`}
                        className={statoCarico === s.k ? "bg-emerald-600 hover:bg-emerald-700" : ""}
                    >{s.l}</Button>
                ))}
                <div className="flex-1" />
                <div className="relative">
                    <Search size={14} className="absolute left-2 top-2.5 text-slate-400" />
                    <Input
                        value={q} onChange={(e) => setQ(e.target.value)}
                        placeholder="Cerca cliente/polizza/targa…"
                        className="pl-7 w-64 h-9" data-testid="search-carichi"
                    />
                </div>
            </Card>

            {/* Barra azioni bulk */}
            {selected.size > 0 && (
                <Card className="p-2.5 mb-2 bg-violet-50 border-violet-300 flex items-center gap-2" data-testid="bulk-bar">
                    <span className="text-sm font-semibold text-violet-900">
                        {selected.size} titoli selezionati
                    </span>
                    <div className="flex-1" />
                    <Button size="sm" onClick={valida} className="bg-emerald-600 hover:bg-emerald-700"
                            data-testid="btn-valida">
                        <CheckCircle2 size={14} className="mr-1" /> Valida e Importa
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => setAnnullaOpen(true)}
                            className="border-rose-300 text-rose-700 hover:bg-rose-50"
                            data-testid="btn-annulla">
                        <XCircle size={14} className="mr-1" /> Annulla (motivo)
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>
                        Deseleziona
                    </Button>
                </Card>
            )}

            {/* Tabella */}
            <Card className="overflow-hidden">
                {rows === null ? (
                    <div className="p-8 text-center text-slate-500">Caricamento…</div>
                ) : filtered.length === 0 ? (
                    <div className="p-8 text-center text-slate-500">
                        Nessun titolo per i filtri correnti.
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-xs">
                            <thead className="bg-slate-50 border-b border-slate-200">
                                <tr>
                                    <th className="w-10 p-2 text-left">
                                        <Checkbox
                                            checked={filtered.length > 0 && selected.size === filtered.length}
                                            onCheckedChange={toggleAll}
                                            data-testid="check-all"
                                        />
                                    </th>
                                    {ALL_COLUMNS.filter((c) => isVisible(c.k)).map((c) => (
                                        <th key={c.k} className="p-2 text-left font-semibold text-slate-700 uppercase tracking-wide"
                                            style={{ minWidth: c.w }}>{c.label}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {filtered.map((r) => (
                                    <TitoloRow
                                        key={r.id} r={r}
                                        checked={selected.has(r.id)}
                                        onCheck={() => toggleOne(r.id)}
                                        onDelete={() => eliminaOne(r.id)}
                                        isVisible={isVisible}
                                    />
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </Card>
            <div className="mt-2 text-xs text-slate-500 text-center">
                {filtered.length} titoli · {selected.size} selezionati
            </div>

            {/* Dialog: replica manuale */}
            {replicaOpen && (
                <ReplicaDialog onClose={() => { setReplicaOpen(false); load(); }} />
            )}
            {/* Dialog: annulla con motivo */}
            {annullaOpen && (
                <AnnullaDialog
                    ids={[...selected]}
                    onClose={() => { setAnnullaOpen(false); load(); }}
                />
            )}
            {/* Dialog: personalizza colonne */}
            {colToggleOpen && (
                <Dialog open onOpenChange={(o) => !o && setColToggleOpen(false)}>
                    <DialogContent className="max-w-md" data-testid="dialog-columns">
                        <DialogHeader><DialogTitle>Personalizza colonne</DialogTitle></DialogHeader>
                        <div className="space-y-2 max-h-96 overflow-y-auto">
                            {ALL_COLUMNS.map((c) => (
                                <label key={c.k} className="flex items-center gap-2 text-sm">
                                    <Checkbox
                                        checked={visible.includes(c.k)}
                                        onCheckedChange={() => toggleCol(c.k)}
                                        data-testid={`col-toggle-${c.k}`}
                                    />
                                    {c.label}
                                </label>
                            ))}
                        </div>
                        <DialogFooter>
                            <Button variant="outline" onClick={() => setVisible(DEFAULT_VISIBLE)}>
                                Ripristina default
                            </Button>
                            <Button onClick={() => setColToggleOpen(false)}>Chiudi</Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            )}
        </div>
    );
}

function TitoloRow({ r, checked, onCheck, onDelete, isVisible }) {
    const stato = r.stato_carico || "validato";
    const statoBadge = {
        in_attesa: "bg-sky-100 text-sky-800",
        validato: "bg-emerald-100 text-emerald-800",
        annullato_carico: "bg-slate-100 text-slate-600 line-through",
    }[stato] || "bg-slate-100";
    const prevPrem = r.premio_precedente;
    const currPrem = Number(r.importo_lordo || 0);
    const deltaEuro = prevPrem != null ? (currPrem - prevPrem) : null;
    const deltaPct = (prevPrem && prevPrem > 0) ? ((currPrem - prevPrem) / prevPrem) * 100 : null;

    return (
        <tr className={`border-b border-slate-100 hover:bg-slate-50/70 ${r.bloccato ? "bg-amber-50/30" : ""}`}
            data-testid={`row-${r.id}`}>
            <td className="p-2">
                <Checkbox checked={checked} onCheckedChange={onCheck}
                          disabled={stato !== "in_attesa"}
                          data-testid={`check-${r.id}`} />
            </td>
            {isVisible("stato_carico") && (
                <td className="p-2">
                    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded uppercase ${statoBadge}`}>
                        {stato === "in_attesa" ? "In Attesa" : stato === "validato" ? "Validato" : "Annullato"}
                    </span>
                </td>
            )}
            {isVisible("polizza_numero") && (
                <td className="p-2 font-mono text-[11px]">
                    <div className="flex items-center gap-1">
                        {r.bloccato && <Lock size={11} className="text-amber-600" title={r.motivo_blocco} />}
                        {r.polizza_numero || "-"}
                    </div>
                    {r.numero_titolo && <div className="text-slate-400 text-[10px]">Q: {r.numero_titolo}</div>}
                </td>
            )}
            {isVisible("cliente_nome") && (
                <td className="p-2 font-medium text-slate-900">{r.cliente_nome || "-"}</td>
            )}
            {isVisible("compagnia_ramo") && (
                <td className="p-2">
                    <div className="font-medium">{r.compagnia_nome || "-"}</div>
                    <div className="text-slate-400 text-[10px] uppercase">{r.polizza_ramo || "-"}</div>
                </td>
            )}
            {isVisible("polizza_targa") && (
                <td className="p-2 font-mono">{r.polizza_targa || "-"}</td>
            )}
            {isVisible("scadenza") && (
                <td className="p-2 font-mono">{fmtIt(r.scadenza)}</td>
            )}
            {isVisible("mezzo_pagamento") && (
                <td className="p-2 text-[11px]">{r.mezzo_pagamento || "-"}</td>
            )}
            {isVisible("sinistri_badge") && (
                <td className="p-2">
                    {r.sinistri_ultimi_12m > 0 ? (
                        <span className="inline-flex items-center gap-1 text-[10px] font-bold px-1.5 py-0.5 rounded bg-rose-100 text-rose-800"
                              title={`${r.sinistri_ultimi_12m} sinistri negli ultimi 12 mesi`}>
                            <AlertTriangle size={10} /> {r.sinistri_ultimi_12m}
                        </span>
                    ) : (
                        <span className="text-[10px] text-emerald-600">✅</span>
                    )}
                </td>
            )}
            {isVisible("confronto_premio") && (
                <td className="p-2">
                    {prevPrem == null ? (
                        <span className="text-slate-400 text-[11px]">— nuova —</span>
                    ) : (
                        <div className="flex items-center gap-1 text-[11px]">
                            <span className="text-slate-500 line-through">€{prevPrem.toFixed(2)}</span>
                            <span className="font-semibold">→ €{currPrem.toFixed(2)}</span>
                            {deltaPct != null && (
                                <span className={`text-[10px] font-bold flex items-center gap-0.5 ${
                                    deltaEuro > 0 ? "text-rose-700" : deltaEuro < 0 ? "text-emerald-700" : "text-slate-500"
                                }`}>
                                    {deltaEuro > 0 ? <TrendingUp size={10} /> : deltaEuro < 0 ? <TrendingDown size={10} /> : null}
                                    {deltaPct > 0 ? "+" : ""}{deltaPct.toFixed(1)}%
                                </span>
                            )}
                        </div>
                    )}
                </td>
            )}
            {isVisible("importo_netto") && (
                <td className="p-2 text-right font-mono">{Number(r.importo_netto || 0).toFixed(2)}</td>
            )}
            {isVisible("provvigioni") && (
                <td className="p-2 text-right font-mono text-violet-700">{Number(r.provvigioni || 0).toFixed(2)}</td>
            )}
            {isVisible("frazionamento") && (
                <td className="p-2 uppercase text-[10px]">{r.frazionamento || "-"}</td>
            )}
            {isVisible("operatore_nome") && (
                <td className="p-2 text-[11px]">{r.operatore_nome || "-"}</td>
            )}
            {isVisible("note_carico") && (
                <td className="p-2 text-[11px] text-slate-600 max-w-[220px] truncate"
                    title={r.note_carico || r.motivo_mancanza || ""}>
                    {r.motivo_mancanza && <span className="text-rose-700 font-semibold">{r.motivo_mancanza}: </span>}
                    {r.note_carico || "-"}
                </td>
            )}
            {isVisible("azioni") && (
                <td className="p-2">
                    <div className="flex items-center gap-1">
                        <Button size="sm" variant="ghost" className="h-6 px-2 text-[11px] text-rose-600 hover:bg-rose-50"
                                onClick={onDelete}
                                disabled={r.bloccato}
                                title={r.bloccato ? r.motivo_blocco : "Elimina titolo"}
                                data-testid={`btn-del-${r.id}`}>
                            🗑
                        </Button>
                    </div>
                </td>
            )}
        </tr>
    );
}

function ReplicaDialog({ onClose }) {
    const [polQuery, setPolQuery] = useState("");
    const [pols, setPols] = useState([]);
    const [selPol, setSelPol] = useState(null);
    const [scad, setScad] = useState("");
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        if (polQuery.length < 2) { setPols([]); return; }
        const t = setTimeout(async () => {
            try {
                const r = await api.get("/polizze", { params: { q: polQuery, limit: 20 } });
                setPols(r.data || []);
            } catch { setPols([]); }
        }, 300);
        return () => clearTimeout(t);
    }, [polQuery]);

    const salva = async () => {
        if (!selPol) { toast.error("Seleziona una polizza"); return; }
        setSaving(true);
        try {
            const r = await api.post("/carichi-mensili/replica-manuale", {
                polizza_id: selPol.id, scadenza: scad || undefined,
            });
            toast.success(`Titolo replicato · nuova scadenza ${r.data.titolo.scadenza}`);
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore replica");
        } finally { setSaving(false); }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-lg" data-testid="dialog-replica">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <RotateCw size={16} /> Replica titolo dal precedente
                    </DialogTitle>
                </DialogHeader>
                <div className="space-y-3">
                    <div>
                        <Label>Cerca polizza (numero polizza o cliente)</Label>
                        <Input value={polQuery} onChange={(e) => setPolQuery(e.target.value)}
                               placeholder="Es. Rossi Mario o POL-2026-…" autoFocus />
                        {pols.length > 0 && (
                            <div className="border rounded max-h-40 overflow-y-auto mt-1">
                                {pols.map((p) => (
                                    <button
                                        key={p.id}
                                        className={`block w-full text-left px-2 py-1.5 text-xs hover:bg-slate-50 ${selPol?.id === p.id ? "bg-violet-50" : ""}`}
                                        onClick={() => setSelPol(p)}
                                        data-testid={`repl-pick-${p.id}`}
                                    >
                                        <span className="font-mono font-semibold">{p.numero_polizza}</span>
                                        <span className="text-slate-500 ml-2">{p.ramo}</span>
                                        {p.targa && <span className="text-slate-400 ml-2">[{p.targa}]</span>}
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>
                    {selPol && (
                        <div className="bg-emerald-50 border border-emerald-200 rounded p-2 text-xs">
                            ✓ Selezionata: <strong>{selPol.numero_polizza}</strong> · {selPol.ramo} · frazionamento: {selPol.frazionamento || "annuale"}
                        </div>
                    )}
                    <div>
                        <Label>Scadenza nuovo titolo (opzionale — calcolata auto se vuota)</Label>
                        <Input type="date" value={scad} onChange={(e) => setScad(e.target.value)} />
                        <div className="text-[10px] text-slate-500 mt-1">
                            Se vuoto, il sistema aggiunge il periodo del frazionamento all'ultima scadenza.
                        </div>
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Annulla</Button>
                    <Button onClick={salva} disabled={saving || !selPol} className="bg-sky-700 hover:bg-sky-800"
                            data-testid="btn-salva-replica">
                        {saving ? "Salvo…" : "Replica titolo"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function AnnullaDialog({ ids, onClose }) {
    const [motivo, setMotivo] = useState(MOTIVI[0]);
    const [note, setNote] = useState("");
    const [saving, setSaving] = useState(false);
    const salva = async () => {
        setSaving(true);
        try {
            const r = await api.post("/carichi-mensili/annulla", {
                titoli_ids: ids, motivo_mancanza: motivo, note_carico: note || null,
            });
            toast.success(`Annullati ${r.data.annullati} titoli`);
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        } finally { setSaving(false); }
    };
    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-md" data-testid="dialog-annulla">
                <DialogHeader><DialogTitle>Annulla {ids.length} titolo/i</DialogTitle></DialogHeader>
                <div className="space-y-3">
                    <div>
                        <Label>Motivo</Label>
                        <select className="w-full border rounded h-9 px-2 text-sm"
                                value={motivo} onChange={(e) => setMotivo(e.target.value)}
                                data-testid="annulla-motivo">
                            {MOTIVI.map((m) => <option key={m} value={m}>{m}</option>)}
                        </select>
                    </div>
                    <div>
                        <Label>Note (opzionale)</Label>
                        <Input value={note} onChange={(e) => setNote(e.target.value)} />
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Annulla</Button>
                    <Button onClick={salva} disabled={saving} className="bg-rose-600 hover:bg-rose-700"
                            data-testid="btn-conferma-annulla">
                        {saving ? "…" : "Conferma"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function fmtIt(iso) {
    if (!iso || iso.length < 10) return "-";
    const [y, m, d] = iso.slice(0, 10).split("-");
    return `${d}/${m}/${y}`;
}
