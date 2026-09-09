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
import { api, fmtEur, fmtDate } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
    Filter, CheckCircle2, XCircle, RotateCw, Search,
    Lock, AlertTriangle, TrendingUp, TrendingDown, Plus, Columns, Upload,
} from "lucide-react";

const ALL_COLUMNS = [
    { k: "stato_carico", label: "Stato", w: 90 },
    { k: "cliente_nome", label: "Cliente", w: 200 },
    { k: "polizza_numero", label: "Polizza", w: 140 },
    { k: "compagnia_nome", label: "Compagnia", w: 140 },
    { k: "operatore_nome", label: "Operatore", w: 140 },
    { k: "polizza_ramo", label: "Ramo", w: 110 },
    { k: "data_decorrenza", label: "Data Decorrenza", w: 110 },
    { k: "scadenza", label: "Data Scadenza", w: 110 },
    { k: "premio_precedente", label: "Premio '25", w: 90 },
    { k: "importo_lordo", label: "Premio '26", w: 90 },
    { k: "tipo_rinnovo", label: "Tipo Rinnovo", w: 100 },
    { k: "mezzo_pagamento", label: "Metodo Pagamento", w: 140 },
    { k: "variazione_badge", label: "Stato / Variazione", w: 180 },
    { k: "note_carico", label: "Note", w: 180 },
    { k: "motivo_mancanza", label: "Alert", w: 140 },
    { k: "note_storiche", label: "Collaboratori (Storiche)", w: 180 },
    { k: "sinistri_badge", label: "Sinistri ultimo anno", w: 110 },
    { k: "provvigioni", label: "Provv. agenzia", w: 100 },
    { k: "provvigioni_collab", label: "Provv. collaboratore", w: 110 },
    { k: "importo_netto", label: "Premio netto", w: 100 },
    { k: "imposte", label: "Tasse", w: 90 },
    { k: "servizio_sanitario", label: "Servizio sanitario", w: 100 },
    { k: "polizza_targa", label: "Targa", w: 100 },
    { k: "frazionamento", label: "Frazionam.", w: 100 },
    { k: "confronto_premio", label: "Premio prec./attuale", w: 170 },
    { k: "azioni", label: "Azioni", w: 80 },
];
const DEFAULT_VISIBLE = ["stato_carico", "cliente_nome", "polizza_numero",
    "compagnia_nome", "operatore_nome", "polizza_ramo", "data_decorrenza", "scadenza",
    "premio_precedente", "importo_lordo", "tipo_rinnovo", "mezzo_pagamento",
    "variazione_badge", "note_carico", "polizza_targa", "azioni"];
const LS_COLS = "carichi_mensili.visible_cols.v2";
const LS_ORDER = "carichi_mensili.col_order.v1";

const MOTIVI = ["Disdettata", "Mezzo Venduto", "Cliente Trasferito", "Voltura", "Sostituita"];

export default function CarichiMensili() {
    const [rows, setRows] = useState(null);
    const [q, setQ] = useState("");
    const [range, setRange] = useState("mese_corrente");
    const [dal, setDal] = useState("");
    const [al, setAl] = useState("");
    const [statoCarico, setStatoCarico] = useState("tutti");
    // Filtri avanzati (collaboratore/compagnia/ramo/mezzo/tipo)
    const [collabId, setCollabId] = useState("");
    const [compagniaId, setCompagniaId] = useState("");
    const [ramo, setRamo] = useState("");
    const [mezzoPag, setMezzoPag] = useState("");
    const [tipoRinn, setTipoRinn] = useState("");
    const [collaboratori, setCollaboratori] = useState([]);
    const [compagnie, setCompagnie] = useState([]);
    const [rami, setRami] = useState([]);
    const [selected, setSelected] = useState(new Set());
    const [replicaOpen, setReplicaOpen] = useState(false);
    const [annullaOpen, setAnnullaOpen] = useState(false);
    const [confrontoOpen, setConfrontoOpen] = useState(false);
    const [importOpen, setImportOpen] = useState(false);
    const [visible, setVisible] = useState(() => {
        try { return JSON.parse(localStorage.getItem(LS_COLS)) || DEFAULT_VISIBLE; }
        catch { return DEFAULT_VISIBLE; }
    });
    const [columnOrder, setColumnOrder] = useState(() => {
        try {
            const saved = JSON.parse(localStorage.getItem(LS_ORDER));
            if (Array.isArray(saved) && saved.length > 0) {
                // Aggiungi colonne nuove non presenti in saved (backward compat)
                const missing = ALL_COLUMNS.map((c) => c.k).filter((k) => !saved.includes(k));
                return [...saved, ...missing];
            }
        } catch { /* fallthrough */ }
        return ALL_COLUMNS.map((c) => c.k);
    });
    const [colToggleOpen, setColToggleOpen] = useState(false);
    const [dragKey, setDragKey] = useState(null);

    const load = async () => {
        try {
            const params = { stato_carico: statoCarico };
            if (collabId) params.collaboratore_id = collabId;
            // Se ci sono date esplicite, hanno priorità sul range preset
            if (dal && al) { params.dal = dal; params.al = al; }
            else if (range !== "tutti") params.range_filter = range;
            const r = await api.get("/carichi-mensili", { params });
            setRows(r.data.righe || []);
            setSelected(new Set());
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore caricamento");
            setRows([]);
        }
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [statoCarico, range, dal, al, collabId]);

    useEffect(() => {
        api.get("/collaboratori").then((r) => setCollaboratori(r.data || [])).catch(() => {});
    }, []);

    useEffect(() => {
        localStorage.setItem(LS_COLS, JSON.stringify(visible));
    }, [visible]);
    useEffect(() => {
        localStorage.setItem(LS_ORDER, JSON.stringify(columnOrder));
    }, [columnOrder]);

    // Colonne ordinate secondo columnOrder (fallback a ordine originale)
    const orderedColumns = useMemo(() => {
        const byKey = Object.fromEntries(ALL_COLUMNS.map((c) => [c.k, c]));
        return columnOrder.map((k) => byKey[k]).filter(Boolean);
    }, [columnOrder]);

    const moveColumn = (fromKey, toKey) => {
        if (fromKey === toKey) return;
        const next = [...columnOrder];
        const fromIdx = next.indexOf(fromKey);
        const toIdx = next.indexOf(toKey);
        if (fromIdx < 0 || toIdx < 0) return;
        next.splice(fromIdx, 1);
        next.splice(toIdx, 0, fromKey);
        setColumnOrder(next);
    };

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
                    <Button variant="outline" onClick={() => setConfrontoOpen(true)} data-testid="btn-confronto-annuale"
                            className="border-amber-300 text-amber-700 hover:bg-amber-50">
                        <TrendingDown size={14} className="mr-1" /> Confronto anno prec.
                    </Button>
                    <Button variant="outline" onClick={() => setImportOpen(true)} data-testid="btn-import-excel"
                            className="border-emerald-300 text-emerald-700 hover:bg-emerald-50">
                        <Upload size={14} className="mr-1" /> Importa Excel/CSV
                    </Button>
                    <Button variant="outline" onClick={() => setColToggleOpen(true)} data-testid="btn-columns">
                        <Columns size={14} className="mr-1" /> Personalizza colonne
                    </Button>
                    <Button onClick={() => setReplicaOpen(true)} className="bg-sky-700 hover:bg-sky-800" data-testid="btn-replica">
                        <Plus size={14} className="mr-1" /> Replica titolo manuale
                    </Button>
                </div>
            </div>

            {/* Filtri */}
            <Card className="p-3 mb-3 space-y-2">
                <div className="flex items-center gap-2 flex-wrap">
                    <div className="flex items-center gap-1">
                        <Filter size={14} className="text-slate-500" />
                        <span className="text-xs text-slate-600 uppercase font-semibold tracking-wide">Filtri</span>
                    </div>
                    {["mese_corrente", "mese_successivo", "tutti"].map((r) => (
                        <Button
                            key={r} size="sm" variant={range === r && !dal ? "default" : "outline"}
                            onClick={() => { setRange(r); setDal(""); setAl(""); }} data-testid={`filter-range-${r}`}
                            className={range === r && !dal ? "bg-violet-600 hover:bg-violet-700" : ""}
                        >
                            {r === "mese_corrente" ? "Mese corrente" : r === "mese_successivo" ? "Mese successivo" : "Tutti"}
                        </Button>
                    ))}
                    <div className="w-px h-6 bg-slate-200 mx-1" />
                    <Select value={collabId || "all"} onValueChange={(v) => setCollabId(v === "all" ? "" : v)}>
                        <SelectTrigger className="w-52 h-9" data-testid="filter-collaboratore">
                            <SelectValue placeholder="Collaboratore" />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">Tutti i collaboratori</SelectItem>
                            {collaboratori.map((c) => (
                                <SelectItem key={c.id} value={c.id}>{c.name || c.email}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                    <div className="flex-1" />
                    <div className="relative">
                        <Search size={14} className="absolute left-2 top-2.5 text-slate-400" />
                        <Input
                            value={q} onChange={(e) => setQ(e.target.value)}
                            placeholder="Cerca cliente/polizza/targa…"
                            className="pl-7 w-64 h-9" data-testid="search-carichi"
                        />
                    </div>
                </div>
                {/* Range date custom (override preset) */}
                <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-[11px] text-slate-500 font-semibold uppercase tracking-wide">Range date scadenza:</span>
                    <Input type="date" value={dal} onChange={(e) => setDal(e.target.value)}
                           className="w-40 h-8 text-xs" data-testid="filter-date-dal" placeholder="Da" />
                    <span className="text-[11px] text-slate-500">→</span>
                    <Input type="date" value={al} onChange={(e) => setAl(e.target.value)}
                           className="w-40 h-8 text-xs" data-testid="filter-date-al" placeholder="A" />
                    {(dal || al) && (
                        <Button size="sm" variant="ghost" onClick={() => { setDal(""); setAl(""); }}
                                className="h-8 text-xs text-slate-600">
                            <XCircle size={12} className="mr-1" /> Reset date
                        </Button>
                    )}
                    <span className="text-[10px] text-slate-400 ml-2">
                        {(dal && al) ? "🎯 Filtro date attivo (override preset)" : "Preset mese attivo — imposta le date per il range custom"}
                    </span>
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
                                    {orderedColumns.filter((c) => isVisible(c.k)).map((c) => (
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
                                        orderedColumns={orderedColumns}
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
            {/* Dialog: import Excel/CSV con auto-mapping */}
            {importOpen && (
                <ImportExcelDialog onClose={() => { setImportOpen(false); load(); }} />
            )}
            {/* Dialog: confronto anno precedente (in base alle date selezionate) */}
            {confrontoOpen && (
                <ConfrontoAnnualeDialog dal={dal} al={al} onClose={() => setConfrontoOpen(false)} />
            )}
            {/* Dialog: personalizza colonne */}
            {colToggleOpen && (
                <Dialog open onOpenChange={(o) => !o && setColToggleOpen(false)}>
                    <DialogContent className="max-w-md" data-testid="dialog-columns">
                        <DialogHeader><DialogTitle>Personalizza colonne — trascina per riordinare</DialogTitle></DialogHeader>
                        <div className="space-y-1 max-h-96 overflow-y-auto">
                            {orderedColumns.map((c) => (
                                <div
                                    key={c.k}
                                    draggable
                                    onDragStart={() => setDragKey(c.k)}
                                    onDragOver={(e) => e.preventDefault()}
                                    onDrop={() => { if (dragKey) moveColumn(dragKey, c.k); setDragKey(null); }}
                                    className={`flex items-center gap-2 text-sm p-1.5 rounded border ${
                                        dragKey === c.k ? "opacity-50 border-violet-400 bg-violet-50" : "border-transparent hover:border-slate-200 hover:bg-slate-50"
                                    } cursor-move`}
                                    data-testid={`col-drag-${c.k}`}
                                >
                                    <span className="text-slate-400 text-xs cursor-grab select-none">⋮⋮</span>
                                    <Checkbox
                                        checked={visible.includes(c.k)}
                                        onCheckedChange={() => toggleCol(c.k)}
                                        data-testid={`col-toggle-${c.k}`}
                                    />
                                    <span className="flex-1">{c.label}</span>
                                </div>
                            ))}
                        </div>
                        <DialogFooter>
                            <Button variant="outline" onClick={() => {
                                setVisible(DEFAULT_VISIBLE);
                                setColumnOrder(ALL_COLUMNS.map((c) => c.k));
                            }}>
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

// Dizionario di renderers per ciascuna colonna: la chiave corrisponde a ALL_COLUMNS[i].k
// e la funzione ritorna il contenuto della cella. In questo modo la Row può renderizzare
// dinamicamente le celle nell'ordine di `orderedColumns` scelto dall'utente (drag&drop).
const CELL_RENDERERS = {
    stato_carico: (r) => {
        const stato = r.stato_carico || "validato";
        const cls = {
            in_attesa: "bg-sky-100 text-sky-800",
            validato: "bg-emerald-100 text-emerald-800",
            annullato_carico: "bg-slate-100 text-slate-600 line-through",
        }[stato] || "bg-slate-100";
        return (
            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded uppercase ${cls}`}>
                {stato === "in_attesa" ? "In Attesa" : stato === "validato" ? "Validato" : "Annullato"}
            </span>
        );
    },
    cliente_nome: (r) => <span className="font-medium text-slate-900">{r.cliente_nome || "-"}</span>,
    polizza_numero: (r) => (
        <div className="font-mono text-[11px]">
            <div className="flex items-center gap-1">
                {r.bloccato && <Lock size={11} className="text-amber-600" title={r.motivo_blocco} />}
                {r.polizza_numero || "-"}
            </div>
            {r.numero_titolo && <div className="text-slate-400 text-[10px]">Q: {r.numero_titolo}</div>}
        </div>
    ),
    compagnia_nome: (r) => <span className="text-[11px]">{r.compagnia_nome || "-"}</span>,
    operatore_nome: (r) => <span className="text-[11px]">{r.operatore_nome || "-"}</span>,
    polizza_ramo: (r) => <span className="text-[11px] uppercase text-slate-600">{r.polizza_ramo || "-"}</span>,
    data_decorrenza: (r) => <span className="font-mono text-[11px]">{fmtIt(r.data_decorrenza)}</span>,
    scadenza: (r) => <span className="font-mono">{fmtIt(r.scadenza)}</span>,
    premio_precedente: (r) => (
        <span className="font-mono text-[11px] text-slate-600">
            {r.premio_precedente != null ? `€${Number(r.premio_precedente).toFixed(2)}` : "-"}
        </span>
    ),
    importo_lordo: (r) => (
        <span className="font-mono text-[11px] font-semibold">
            €{Number(r.importo_lordo || 0).toFixed(2)}
        </span>
    ),
    tipo_rinnovo: (r) => (
        <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 text-[10px] font-semibold uppercase">
            {r.tipo_rinnovo === "rinnovo" ? "QR"
                : r.tipo_rinnovo === "prima_emissione" ? "PE"
                : r.tipo_rinnovo === "regolazione" ? "REG"
                : (r.tipo_rinnovo || "-")}
        </span>
    ),
    mezzo_pagamento: (r) => <span className="text-[11px]">{r.mezzo_pagamento || "-"}</span>,
    variazione_badge: (r) => (
        r.variazione_badge ? (
            <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                r.variazione_badge?.startsWith("🛑") ? "bg-rose-100 text-rose-800"
                : r.variazione_badge?.startsWith("🔻") ? "bg-emerald-100 text-emerald-800"
                : r.variazione_badge?.startsWith("🟢") ? "bg-sky-100 text-sky-800"
                : r.variazione_badge?.startsWith("🔄") ? "bg-amber-100 text-amber-800"
                : r.variazione_badge?.startsWith("⏸") ? "bg-slate-200 text-slate-800"
                : "bg-violet-100 text-violet-800"
            }`} title={r.variazione_dettaglio || ""}>{r.variazione_badge}</span>
        ) : (
            <span className="text-slate-400 text-[11px]">-</span>
        )
    ),
    note_carico: (r) => (
        <span className="text-[11px] text-slate-600 max-w-[220px] whitespace-normal break-words inline-block align-top leading-tight"
              title={r.note_carico || r.motivo_mancanza || ""}>
            {r.motivo_mancanza && <span className="text-rose-700 font-semibold">{r.motivo_mancanza}: </span>}
            {r.note_carico || "-"}
        </span>
    ),
    motivo_mancanza: (r) => (
        r.motivo_mancanza ? (
            <span className="inline-block px-1.5 py-0.5 rounded bg-rose-50 border border-rose-200 text-rose-700 text-[10px] font-semibold">
                <AlertTriangle size={9} className="inline mr-0.5" /> {r.motivo_mancanza}
            </span>
        ) : (
            <span className="text-slate-400 text-[11px]">-</span>
        )
    ),
    note_storiche: (r) => (
        <span className="text-[11px] text-slate-600 max-w-[220px] whitespace-normal break-words inline-block align-top leading-tight"
              title={r.note_storiche || ""}>
            {r.note_storiche || "-"}
        </span>
    ),
    sinistri_badge: (r) => (
        r.sinistri_ultimi_12m > 0 ? (
            <span className="inline-flex items-center gap-1 text-[10px] font-bold px-1.5 py-0.5 rounded bg-rose-100 text-rose-800"
                  title={`${r.sinistri_ultimi_12m} sinistri negli ultimi 12 mesi`}>
                <AlertTriangle size={10} /> {r.sinistri_ultimi_12m}
            </span>
        ) : (
            <span className="text-[10px] text-emerald-600">✅</span>
        )
    ),
    provvigioni: (r) => (
        <span className="font-mono text-violet-700 text-[11px]">
            {Number(r.provvigioni || 0).toFixed(2)}
        </span>
    ),
    provvigioni_collab: (r) => (
        <span className="font-mono text-fuchsia-700 text-[11px]">
            {r.provvigioni_collab != null ? Number(r.provvigioni_collab).toFixed(2) : "-"}
        </span>
    ),
    importo_netto: (r) => (
        <span className="font-mono text-[11px]">{Number(r.importo_netto || 0).toFixed(2)}</span>
    ),
    imposte: (r) => (
        <span className="font-mono text-[11px]">{Number(r.imposte || 0).toFixed(2)}</span>
    ),
    servizio_sanitario: (r) => (
        <span className="font-mono text-[11px]">
            {r.servizio_sanitario != null ? Number(r.servizio_sanitario).toFixed(2) : "-"}
        </span>
    ),
    polizza_targa: (r) => <span className="font-mono">{r.polizza_targa || "-"}</span>,
    frazionamento: (r) => <span className="uppercase text-[10px]">{r.frazionamento || "-"}</span>,
    confronto_premio: (r) => {
        const prevPrem = r.premio_precedente;
        const currPrem = Number(r.importo_lordo || 0);
        if (prevPrem == null) return <span className="text-slate-400 text-[11px]">— nuova —</span>;
        const deltaEuro = currPrem - prevPrem;
        const deltaPct = prevPrem > 0 ? (deltaEuro / prevPrem) * 100 : null;
        return (
            <div className="flex items-center gap-1 text-[11px]">
                <span className="text-slate-500 line-through">€{Number(prevPrem).toFixed(2)}</span>
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
        );
    },
    azioni: (r, { onDelete }) => (
        <div className="flex items-center gap-1">
            <Button size="sm" variant="ghost" className="h-6 px-2 text-[11px] text-rose-600 hover:bg-rose-50"
                    onClick={onDelete}
                    disabled={r.bloccato}
                    title={r.bloccato ? r.motivo_blocco : "Elimina titolo"}
                    data-testid={`btn-del-${r.id}`}>
                🗑
            </Button>
        </div>
    ),
};

function TitoloRow({ r, checked, onCheck, onDelete, orderedColumns, isVisible }) {
    const stato = r.stato_carico || "validato";
    return (
        <tr className={`border-b border-slate-100 hover:bg-slate-50/70 ${r.bloccato ? "bg-amber-50/30" : ""}`}
            data-testid={`row-${r.id}`}>
            <td className="p-2">
                <Checkbox checked={checked} onCheckedChange={onCheck}
                          disabled={stato !== "in_attesa"}
                          data-testid={`check-${r.id}`} />
            </td>
            {orderedColumns.filter((c) => isVisible(c.k)).map((c) => {
                const renderer = CELL_RENDERERS[c.k];
                return (
                    <td key={c.k} className="p-2 align-middle" data-testid={`cell-${c.k}-${r.id}`}>
                        {renderer ? renderer(r, { onDelete }) : (r[c.k] != null ? String(r[c.k]) : "-")}
                    </td>
                );
            })}
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
                            Se vuoto, il sistema aggiunge il periodo del frazionamento all&apos;ultima scadenza.
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

function ImportExcelDialog({ onClose }) {
    const [file, setFile] = useState(null);
    const [preview, setPreview] = useState(null);   // {headers, sample_rows, suggested_mapping, total_rows}
    const [mapping, setMapping] = useState({});
    const [step, setStep] = useState(1);            // 1=upload, 2=mapping, 3=risultato
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState(null);

    const doPreview = async () => {
        if (!file) { toast.error("Seleziona un file .xlsx o .csv"); return; }
        setLoading(true);
        try {
            const fd = new FormData();
            fd.append("file", file);
            const r = await api.post("/carichi-mensili/import/preview", fd, {
                headers: { "Content-Type": "multipart/form-data" },
            });
            setPreview(r.data);
            setMapping({ ...r.data.suggested_mapping });
            setStep(2);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore lettura file");
        } finally { setLoading(false); }
    };

    const doImport = async () => {
        if (!mapping.polizza_numero) {
            toast.error("Devi mappare almeno il campo 'polizza_numero'");
            return;
        }
        setLoading(true);
        try {
            const fd = new FormData();
            fd.append("file", file);
            fd.append("mapping_json", JSON.stringify(mapping));
            const r = await api.post("/carichi-mensili/import/apply", fd, {
                headers: { "Content-Type": "multipart/form-data" },
            });
            setResult(r.data);
            // Se ci sono righe orfane vai allo step 2.5 (match manuale), altrimenti step 3 finale
            if ((r.data.unmatched || []).length > 0) {
                setStep(2.5);
                // Pre-popola matches: nessuna polizza selezionata di default
                setManualMatches((r.data.unmatched || []).map((u) => ({
                    ...u, polizza_id: null,
                })));
            } else {
                setStep(3);
                toast.success(`Import completato: ${r.data.creati} titoli creati`);
            }
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore import");
        } finally { setLoading(false); }
    };

    const [manualMatches, setManualMatches] = useState([]);
    const doManualMatch = async () => {
        const scelti = manualMatches.filter((m) => m.polizza_id);
        if (scelti.length === 0) {
            // Nessun abbinamento manuale → salta e vai al risultato
            setStep(3);
            return;
        }
        setLoading(true);
        try {
            const r = await api.post("/carichi-mensili/import/match-manual", {
                batch_id: result.batch_id, matches: scelti,
            });
            toast.success(`${r.data.creati} titoli aggiuntivi creati con abbinamento manuale`);
            setResult({ ...result, creati: result.creati + r.data.creati,
                        creati_manuale: r.data.creati });
            setStep(3);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore match manuale");
        } finally { setLoading(false); }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-3xl max-h-[92vh] overflow-y-auto" data-testid="dialog-import-excel">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Upload size={16} /> Importa Titoli da Excel/CSV
                        <span className="text-xs text-slate-500 font-normal ml-2">
                            Step {step === 2.5 ? "2.5" : Math.floor(step)} · {
                                step === 1 ? "Carica file" :
                                step === 2 ? "Mappa colonne" :
                                step === 2.5 ? "Abbina polizze mancanti" :
                                "Risultato"
                            }
                        </span>
                    </DialogTitle>
                </DialogHeader>

                {step === 1 && (
                    <div className="space-y-3">
                        <div className="bg-sky-50 border border-sky-200 rounded p-2 text-xs text-sky-900">
                            📄 Carica un file <strong>.xlsx</strong>, <strong>.xls</strong> o <strong>.csv</strong> ricevuto dalla compagnia. Il sistema leggerà le intestazioni e ti proporrà un mapping automatico verso i campi CRM.
                        </div>
                        <Input
                            type="file"
                            accept=".xlsx,.xls,.csv"
                            onChange={(e) => setFile(e.target.files?.[0] || null)}
                            data-testid="import-file-input"
                        />
                        {file && <div className="text-xs text-slate-600">Selezionato: <strong>{file.name}</strong> ({(file.size / 1024).toFixed(1)} KB)</div>}
                    </div>
                )}

                {step === 2 && preview && (
                    <div className="space-y-3">
                        <div className="bg-emerald-50 border border-emerald-200 rounded p-2 text-xs text-emerald-900">
                            ✅ File letto correttamente: <strong>{preview.total_rows}</strong> righe · <strong>{preview.headers.length}</strong> colonne. Verifica il mapping suggerito qui sotto e correggi se necessario.
                        </div>
                        <div className="overflow-x-auto max-h-64">
                            <table className="w-full text-xs">
                                <thead className="bg-slate-100 sticky top-0">
                                    <tr>
                                        <th className="p-1.5 text-left font-semibold text-slate-700">Campo CRM</th>
                                        <th className="p-1.5 text-left font-semibold text-slate-700">Colonna nel file</th>
                                        <th className="p-1.5 text-left font-semibold text-slate-500 text-[10px]">Esempio (prima riga)</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {(preview.campi_crm_disponibili || []).map((campo) => (
                                        <tr key={campo} className="border-b border-slate-100">
                                            <td className="p-1.5 font-mono text-[11px] font-semibold">
                                                {campo}
                                                {campo === "polizza_numero" && <span className="text-rose-500 ml-1">*</span>}
                                            </td>
                                            <td className="p-1.5">
                                                <select
                                                    value={mapping[campo] || ""}
                                                    onChange={(e) => setMapping({ ...mapping, [campo]: e.target.value || null })}
                                                    className="w-full text-xs border rounded h-7 px-1.5"
                                                    data-testid={`mapping-${campo}`}
                                                >
                                                    <option value="">— non mappato —</option>
                                                    {preview.headers.map((h) => (
                                                        <option key={h} value={h}>{h}</option>
                                                    ))}
                                                </select>
                                            </td>
                                            <td className="p-1.5 text-[10px] text-slate-500 max-w-[200px] truncate">
                                                {mapping[campo] && preview.sample_rows[0]
                                                    ? String(preview.sample_rows[0][mapping[campo]] ?? "")
                                                    : "-"}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                        <div className="text-[10px] text-slate-500">* Il campo <code>polizza_numero</code> è obbligatorio per abbinare i titoli alle polizze del CRM.</div>
                    </div>
                )}

                {step === 2.5 && (
                    <div className="space-y-3">
                        <div className="bg-amber-50 border-2 border-amber-300 rounded p-2.5">
                            <div className="font-bold text-amber-900 text-sm">⚠️ Abbinamento manuale polizze</div>
                            <div className="text-xs text-amber-800 mt-1">
                                <strong>{manualMatches.length}</strong> righe del file hanno un numero polizza <strong>NON trovato</strong> nel CRM.
                                Scegli la polizza corretta dai suggerimenti oppure lascia &quot;— non abbinare —&quot; per scartarla.
                            </div>
                        </div>
                        <div className="max-h-96 overflow-y-auto space-y-2">
                            {manualMatches.map((u, idx) => (
                                <div key={idx} className="border border-slate-200 rounded p-2 bg-white">
                                    <div className="flex items-start justify-between gap-2 mb-1.5">
                                        <div className="text-[11px]">
                                            <span className="font-mono font-bold">{u.polizza_numero_file}</span>
                                            {u.cliente_file && <span className="text-slate-600 ml-2">· {u.cliente_file}</span>}
                                            <span className="text-slate-400 ml-2">
                                                scad. {u.scadenza ? fmtIt(u.scadenza) : "-"} · € {(u.importo_lordo || 0).toFixed(2)}
                                            </span>
                                        </div>
                                        <span className="text-[10px] text-slate-500">riga {u.riga}</span>
                                    </div>
                                    <select
                                        value={u.polizza_id || ""}
                                        onChange={(e) => {
                                            const next = [...manualMatches];
                                            next[idx] = { ...next[idx], polizza_id: e.target.value || null };
                                            setManualMatches(next);
                                        }}
                                        className="w-full text-xs border rounded h-8 px-2"
                                        data-testid={`manual-match-${idx}`}
                                    >
                                        <option value="">— non abbinare (scarta questa riga) —</option>
                                        {(u.suggerimenti || []).map((s) => (
                                            <option key={s.id} value={s.id}>
                                                {s.numero_polizza} · {s.ramo || "-"}
                                                {s.targa ? ` [${s.targa}]` : ""}
                                                {s.cliente_nome ? ` · ${s.cliente_nome}` : ""}
                                            </option>
                                        ))}
                                    </select>
                                    {(u.suggerimenti || []).length === 0 && (
                                        <div className="text-[10px] text-slate-500 mt-1 italic">
                                            Nessun suggerimento trovato. La riga verrà scartata.
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                        <div className="text-[10px] text-slate-500">
                            💡 Il sistema ha già creato <strong>{result?.creati || 0}</strong> titoli abbinati automaticamente.
                            Qui puoi recuperare le righe con polizza non trovata scegliendo manualmente.
                        </div>
                    </div>
                )}

                {step === 3 && result && (
                    <div className="space-y-3">
                        <div className="bg-emerald-50 border border-emerald-300 rounded p-3">
                            <div className="text-lg font-bold text-emerald-900">🎉 Import completato</div>
                            <div className="grid grid-cols-4 gap-2 mt-2 text-sm">
                                <div><span className="text-slate-500">Letti:</span> <strong>{result.totale_letti}</strong></div>
                                <div><span className="text-emerald-700">Creati:</span> <strong>{result.creati}</strong></div>
                                <div><span className="text-amber-700">Saltati:</span> <strong>{result.saltati}</strong></div>
                                <div><span className="text-rose-700">Orfani:</span> <strong>{(result.unmatched || []).length}</strong></div>
                            </div>
                            {result.creati_manuale > 0 && (
                                <div className="mt-2 text-xs text-emerald-800">
                                    ↳ inclusi <strong>{result.creati_manuale}</strong> abbinati manualmente
                                </div>
                            )}
                        </div>
                        {(result.errori || []).length > 0 && (
                            <div className="bg-rose-50 border border-rose-200 rounded p-2 max-h-40 overflow-y-auto">
                                <div className="text-xs font-semibold text-rose-900 mb-1">⚠ {result.errori.length} errori:</div>
                                {result.errori.slice(0, 10).map((e, i) => (
                                    <div key={i} className="text-[10px] text-rose-800">
                                        Riga {e.riga}: {e.polizza && `[${e.polizza}] `}{e.errore}
                                    </div>
                                ))}
                            </div>
                        )}
                        <div className="text-xs text-slate-600">
                            I titoli sono ora in stato <strong>&quot;In Attesa&quot;</strong>. Filtrali e valida quelli approvati per promuoverli allo scadenziario ufficiale.
                        </div>
                    </div>
                )}

                <DialogFooter>
                    {step === 1 && (
                        <>
                            <Button variant="outline" onClick={onClose}>Annulla</Button>
                            <Button onClick={doPreview} disabled={!file || loading}
                                    className="bg-sky-700 hover:bg-sky-800" data-testid="btn-import-preview">
                                {loading ? "Analisi…" : "Analizza file →"}
                            </Button>
                        </>
                    )}
                    {step === 2 && (
                        <>
                            <Button variant="outline" onClick={() => setStep(1)}>← Indietro</Button>
                            <Button onClick={doImport} disabled={loading || !mapping.polizza_numero}
                                    className="bg-emerald-600 hover:bg-emerald-700" data-testid="btn-import-apply">
                                {loading ? "Import in corso…" : `Importa ${preview?.total_rows || 0} righe`}
                            </Button>
                        </>
                    )}
                    {step === 2.5 && (
                        <>
                            <Button variant="ghost" onClick={() => setStep(3)}>Salta abbinamento →</Button>
                            <Button onClick={doManualMatch} disabled={loading}
                                    className="bg-amber-600 hover:bg-amber-700" data-testid="btn-import-manual-match">
                                {loading ? "Salvo…" : `Abbina ${manualMatches.filter((m) => m.polizza_id).length} righe →`}
                            </Button>
                        </>
                    )}
                    {step === 3 && (
                        <Button onClick={onClose} className="bg-sky-700 hover:bg-sky-800">Chiudi</Button>
                    )}
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}



// ============================================================
// Confronto anno precedente vs corrente (in base alle date selezionate)
// ============================================================
const TIPO_TONE = {
    confermato: "bg-emerald-100 text-emerald-700",
    mancante: "bg-rose-100 text-rose-700",
    nuovo: "bg-sky-100 text-sky-700",
};

function ConfrontoAnnualeDialog({ dal, al, onClose }) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const hasRange = !!(dal && al);
    const annoDefault = new Date().getFullYear();

    useEffect(() => {
        setLoading(true);
        const params = hasRange ? { dal, al } : { anno: annoDefault };
        api.get("/carichi-mensili/confronto-annuale", { params })
            .then((r) => setData(r.data))
            .catch((e) => setError(e.response?.data?.detail || "Errore nel confronto"))
            .finally(() => setLoading(false));
    }, [dal, al]); // eslint-disable-line

    const s = data?.stats;
    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-5xl max-h-[90vh] overflow-y-auto" data-testid="dialog-confronto-annuale">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <TrendingDown className="text-violet-600" size={18} />
                        Confronto {hasRange ? "per periodo selezionato" : `anno ${annoDefault}`} vs anno precedente
                    </DialogTitle>
                </DialogHeader>

                <div className="text-xs text-slate-500 -mt-2">
                    {hasRange
                        ? <>Periodo <strong>{fmtDate(dal)} – {fmtDate(al)}</strong> confrontato con lo <strong>stesso periodo dell'anno precedente</strong>, per data di decorrenza.</>
                        : <>Nessuna data selezionata: confronto sull'intero anno <strong>{annoDefault}</strong> vs <strong>{annoDefault - 1}</strong>. Imposta le date "Da/A" nella pagina per un confronto sul periodo.</>}
                </div>

                {loading ? (
                    <div className="py-10 text-center text-slate-400 text-sm">Calcolo confronto in corso…</div>
                ) : error ? (
                    <div className="py-10 text-center text-rose-600 text-sm">{error}</div>
                ) : (
                    <>
                        {s && (
                            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 my-2">
                                <StatBox label="Totale" value={s.totale} />
                                <StatBox label="Confermati" value={s.confermati} tone="text-emerald-700" />
                                <StatBox label="Mancanti" value={s.mancanti} tone="text-rose-700" />
                                <StatBox label="Nuovi" value={s.nuovi} tone="text-sky-700" />
                                <StatBox label="Δ Premio" value={`${s.delta_premio > 0 ? "+" : ""}${fmtEur(s.delta_premio)}`} tone={s.delta_premio >= 0 ? "text-emerald-700" : "text-rose-700"} />
                            </div>
                        )}
                        {s && (
                            <div className="text-xs text-slate-600 mb-2">
                                Premio anno prec.: <strong>{fmtEur(s.premio_totale_prec)}</strong> · Premio periodo: <strong>{fmtEur(s.premio_totale_corr)}</strong>
                            </div>
                        )}
                        <div className="border border-slate-200 rounded-lg overflow-x-auto">
                            <table className="w-full text-xs">
                                <thead className="bg-slate-50 uppercase tracking-wide text-slate-500">
                                    <tr>
                                        <th className="text-left px-2 py-2">Esito</th>
                                        <th className="text-left px-2 py-2">Cliente</th>
                                        <th className="text-left px-2 py-2">Polizza</th>
                                        <th className="text-left px-2 py-2">Compagnia</th>
                                        <th className="text-right px-2 py-2">Premio prec.</th>
                                        <th className="text-right px-2 py-2">Premio periodo</th>
                                        <th className="text-right px-2 py-2">Δ</th>
                                        <th className="text-left px-2 py-2">Dettaglio</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-100">
                                    {(data?.righe || []).map((r, i) => (
                                        <tr key={r.id || i} data-testid={`confronto-row-${i}`}>
                                            <td className="px-2 py-1.5">
                                                <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-medium ${TIPO_TONE[r.tipo_row] || "bg-slate-100"}`}>{r.motivo_label}</span>
                                            </td>
                                            <td className="px-2 py-1.5">{r.cliente_nome || "—"}</td>
                                            <td className="px-2 py-1.5 num">{r.polizza_numero || "—"}{r.nuova_polizza_numero && <span className="text-sky-700"> → {r.nuova_polizza_numero}</span>}</td>
                                            <td className="px-2 py-1.5">{r.compagnia_nome || "—"}</td>
                                            <td className="px-2 py-1.5 text-right num text-slate-500">{r.premio_anno_prec != null ? fmtEur(r.premio_anno_prec) : "—"}</td>
                                            <td className="px-2 py-1.5 text-right num font-medium">{r.premio_anno_corr != null ? fmtEur(r.premio_anno_corr) : "—"}</td>
                                            <td className={`px-2 py-1.5 text-right num font-semibold ${r.delta_euro > 0 ? "text-rose-700" : r.delta_euro < 0 ? "text-emerald-700" : "text-slate-400"}`}>
                                                {r.delta_euro != null ? `${r.delta_euro > 0 ? "+" : ""}${fmtEur(r.delta_euro)}` : "—"}
                                                {r.delta_pct != null && <span className="text-[10px] ml-1">({r.delta_pct > 0 ? "+" : ""}{r.delta_pct}%)</span>}
                                            </td>
                                            <td className="px-2 py-1.5 text-slate-500">{r.dettaglio}</td>
                                        </tr>
                                    ))}
                                    {(data?.righe || []).length === 0 && (
                                        <tr><td colSpan={8} className="px-2 py-6 text-center text-slate-400">Nessun titolo nel periodo selezionato.</td></tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </>
                )}

                <DialogFooter>
                    <Button variant="outline" onClick={onClose} data-testid="confronto-close">Chiudi</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function StatBox({ label, value, tone = "text-slate-800" }) {
    return (
        <div className="bg-slate-50 border border-slate-200 rounded-lg px-3 py-2">
            <div className="text-[10px] uppercase tracking-wide text-slate-400">{label}</div>
            <div className={`text-lg font-bold ${tone}`}>{value}</div>
        </div>
    );
}
