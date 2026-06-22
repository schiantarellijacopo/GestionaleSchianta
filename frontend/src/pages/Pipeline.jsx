import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import {
    GripVertical, Lock, Plus, Settings, Trash2, Edit2, Megaphone,
    HeartHandshake, Headphones, ShoppingBag, X,
} from "lucide-react";

const BUILTIN = [
    { key: "polizze", label: "Polizze", editable: true, builtin: true },
    { key: "sinistri", label: "Sinistri", editable: true, builtin: true },
    { key: "titoli", label: "Titoli", editable: true, builtin: true },
    { key: "clienti", label: "Clienti", editable: false, builtin: true },
];

const COL_COLORS_BUILTIN = {
    in_emissione: "#0EA5E9", attiva: "#10B981", sospesa: "#F59E0B",
    scaduta: "#EF4444", annullata: "#94A3B8",
    aperto: "#0EA5E9", in_istruttoria: "#F59E0B", liquidato: "#10B981",
    chiuso_senza_seguito: "#94A3B8", respinto: "#EF4444",
    da_incassare: "#F59E0B", insoluto: "#EF4444", incassato: "#10B981", stornato: "#94A3B8",
    prospect: "#94A3B8", nuovo: "#0EA5E9", attivo: "#10B981", top: "#7C3AED",
};

const TIPO_ICON = {
    marketing: <Megaphone size={12} />,
    vendita: <ShoppingBag size={12} />,
    onboarding: <HeartHandshake size={12} />,
    supporto: <Headphones size={12} />,
    generico: null,
};

export default function Pipeline() {
    const [custom, setCustom] = useState([]);
    const [active, setActive] = useState("polizze");
    const [showCreate, setShowCreate] = useState(false);

    const loadCustom = useCallback(() => {
        api.get("/pipelines").then((r) => setCustom(r.data));
    }, []);

    useEffect(() => { loadCustom(); }, [loadCustom]);

    const all = [...BUILTIN, ...custom.map((p) => ({
        key: p.id, label: p.nome, editable: true, builtin: false, tipo: p.tipo, cards_count: p.cards_count,
    }))];

    return (
        <div data-testid="pipeline-page">
            <PageHeader
                title="Pipeline"
                subtitle="Vista kanban. Trascina le card tra colonne per cambiare stato. Crea pipeline custom (marketing, vendita, onboarding, supporto)."
                actions={
                    <Dialog open={showCreate} onOpenChange={setShowCreate}>
                        <DialogTrigger asChild>
                            <Button className="bg-sky-700 hover:bg-sky-800" data-testid="pipeline-new-btn">
                                <Plus size={14} className="mr-1" /> Nuova pipeline
                            </Button>
                        </DialogTrigger>
                        <NuovaPipelineDialog onClose={() => { setShowCreate(false); loadCustom(); }} onCreated={(p) => setActive(p.id)} />
                    </Dialog>
                }
            />

            <Tabs value={active} onValueChange={setActive}>
                <TabsList className="bg-slate-100 flex-wrap h-auto">
                    {all.map((e) => (
                        <TabsTrigger key={e.key} value={e.key} data-testid={`pipeline-tab-${e.key}`}>
                            {TIPO_ICON[e.tipo] || null}
                            <span className={TIPO_ICON[e.tipo] ? "ml-1.5" : ""}>{e.label}</span>
                            {!e.editable && <Lock size={10} className="ml-1 text-slate-400" />}
                            {!e.builtin && typeof e.cards_count === "number" && (
                                <span className="ml-1.5 text-[10px] bg-slate-200 px-1.5 rounded-full">{e.cards_count}</span>
                            )}
                        </TabsTrigger>
                    ))}
                </TabsList>
                {all.map((e) => (
                    <TabsContent key={e.key} value={e.key} className="mt-4">
                        <PipelineBoard
                            entita={e.key}
                            editable={e.editable}
                            builtin={e.builtin}
                            onPipelineChange={loadCustom}
                        />
                    </TabsContent>
                ))}
            </Tabs>
        </div>
    );
}

function PipelineBoard({ entita, editable, builtin, onPipelineChange }) {
    const [data, setData] = useState(null);
    const [draggedCard, setDraggedCard] = useState(null);
    const [dragOverCol, setDragOverCol] = useState(null);
    const [showSettings, setShowSettings] = useState(false);
    const [newCardCol, setNewCardCol] = useState(null);
    const [editingCard, setEditingCard] = useState(null);
    const nav = useNavigate();

    const load = useCallback(() => {
        setData(null);
        api.get(`/pipeline/${entita}`).then((r) => setData(r.data));
    }, [entita]);

    useEffect(() => { load(); }, [load]);

    const onDragStart = (card, fromCol, ev) => {
        if (!editable) return;
        setDraggedCard({ id: card.id, fromCol, title: card.title });
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", card.id);
    };

    const onDragOver = (colKey, ev) => {
        if (!editable || !draggedCard || draggedCard.fromCol === colKey) return;
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "move";
        setDragOverCol(colKey);
    };

    const onDrop = async (toCol, ev) => {
        ev.preventDefault();
        setDragOverCol(null);
        if (!editable || !draggedCard || draggedCard.fromCol === toCol) {
            setDraggedCard(null);
            return;
        }
        // Optimistic UI
        setData((prev) => {
            if (!prev) return prev;
            let moved = null;
            const c1 = prev.colonne.map((c) => {
                if (c.key === draggedCard.fromCol) {
                    const idx = c.cards.findIndex((x) => x.id === draggedCard.id);
                    if (idx >= 0) moved = c.cards[idx];
                    return { ...c, cards: c.cards.filter((x) => x.id !== draggedCard.id), count: c.count - 1 };
                }
                return c;
            });
            const out = c1.map((c) => (c.key === toCol && moved
                ? { ...c, cards: [moved, ...c.cards], count: c.count + 1 } : c));
            return { ...prev, colonne: out };
        });
        try {
            await api.post(`/pipeline/${entita}/${draggedCard.id}/move`, { nuovo_stato: toCol });
            toast.success(`Spostato in "${toCol.replace(/_/g, " ")}"`);
        } catch (err) {
            toast.error(err.response?.data?.detail || "Errore spostamento");
            load();
        }
        setDraggedCard(null);
    };

    if (!data) return <Loading />;
    const isCustom = !builtin && data.pipeline;

    return (
        <div data-testid={`board-${entita}`}>
            {/* Header pipeline custom */}
            {isCustom && (
                <div className="flex items-center justify-between bg-slate-50 border border-slate-200 rounded-md px-4 py-2 mb-3">
                    <div>
                        <div className="font-semibold text-slate-800 text-sm">{data.pipeline.nome}</div>
                        {data.pipeline.descrizione && (
                            <div className="text-xs text-slate-500">{data.pipeline.descrizione}</div>
                        )}
                    </div>
                    <Button size="sm" variant="outline" onClick={() => setShowSettings(true)} data-testid="pipeline-settings-btn">
                        <Settings size={13} className="mr-1" /> Gestisci colonne
                    </Button>
                </div>
            )}

            <div className="flex gap-4 overflow-x-auto pb-4">
                {data.colonne.map((col) => {
                    const isDropTarget = dragOverCol === col.key && draggedCard && draggedCard.fromCol !== col.key;
                    const colColor = col.colore || COL_COLORS_BUILTIN[col.key] || "#64748B";
                    return (
                        <div
                            key={col.key}
                            className="w-72 shrink-0"
                            onDragOver={(e) => onDragOver(col.key, e)}
                            onDragLeave={() => setDragOverCol(null)}
                            onDrop={(e) => onDrop(col.key, e)}
                        >
                            <div
                                className="rounded-md px-3 py-2 mb-3 flex items-center justify-between group"
                                style={{
                                    background: `${colColor}15`,
                                    borderLeft: `3px solid ${colColor}`,
                                }}
                            >
                                <div className="font-medium text-sm text-slate-800">{col.label}</div>
                                <div className="flex items-center gap-1">
                                    {isCustom && (
                                        <button
                                            onClick={() => setNewCardCol(col.key)}
                                            className="opacity-0 group-hover:opacity-100 transition-opacity text-slate-500 hover:text-sky-700 p-0.5"
                                            title="Aggiungi card"
                                            data-testid={`add-card-${col.key}`}
                                        >
                                            <Plus size={12} />
                                        </button>
                                    )}
                                    <div className="text-xs font-semibold text-slate-600 num bg-white border border-slate-200 rounded-full px-2 py-0.5">
                                        {col.count}
                                    </div>
                                </div>
                            </div>
                            <div className={`space-y-2 min-h-[60px] rounded-md p-1 transition-colors ${
                                isDropTarget ? "bg-sky-100 ring-2 ring-sky-400 ring-dashed" : ""
                            }`}>
                                {col.cards.length === 0 ? (
                                    <div className="text-xs text-slate-400 text-center py-4">
                                        {isDropTarget ? "Rilascia qui" : (isCustom ? (
                                            <button onClick={() => setNewCardCol(col.key)} className="text-sky-700 hover:underline">
                                                + Aggiungi
                                            </button>
                                        ) : "Vuoto")}
                                    </div>
                                ) : col.cards.map((c) => (
                                    <Card
                                        key={c.id}
                                        draggable={editable}
                                        onDragStart={(e) => onDragStart(c, col.key, e)}
                                        onClick={() => isCustom ? setEditingCard(c) : (c.link && nav(c.link))}
                                        className={`p-3 hover:border-sky-400 hover:shadow-md transition-all border-slate-200 ${
                                            editable ? "cursor-grab active:cursor-grabbing" : "cursor-pointer"
                                        } ${draggedCard?.id === c.id ? "opacity-40" : ""}`}
                                        data-testid={`card-${c.id}`}
                                    >
                                        <div className="flex items-start gap-1.5">
                                            {editable && <GripVertical size={12} className="text-slate-300 mt-0.5 shrink-0" />}
                                            <div className="flex-1 min-w-0">
                                                <div className="font-medium text-sm text-slate-900 truncate">{c.title}</div>
                                                {c.subtitle && <div className="text-xs text-slate-600 truncate mt-0.5">{c.subtitle}</div>}
                                                {c.footer && <div className="text-xs text-slate-500 truncate mt-1">{c.footer}</div>}
                                                {c.tags && c.tags.length > 0 && (
                                                    <div className="flex flex-wrap gap-1 mt-1">
                                                        {c.tags.slice(0, 3).map((t) => (
                                                            <span key={t} className="text-[9px] uppercase bg-slate-100 text-slate-600 px-1 py-0.5 rounded">{t}</span>
                                                        ))}
                                                    </div>
                                                )}
                                                <div className="flex items-center justify-between mt-2 pt-2 border-t border-slate-100">
                                                    {c.extra && <span className="text-[11px] text-slate-600 num">{c.extra}</span>}
                                                    {c.date && <span className="text-[10px] text-slate-400 num">{c.date}</span>}
                                                </div>
                                            </div>
                                        </div>
                                    </Card>
                                ))}
                                {col.cards.length === 50 && col.count > 50 && (
                                    <div className="text-[10px] text-center text-slate-400">+ {col.count - 50} altri...</div>
                                )}
                            </div>
                        </div>
                    );
                })}
                {data.colonne.length === 0 && (
                    <div className="flex-1">
                        <Empty />
                        {isCustom && (
                            <div className="text-center mt-2">
                                <Button onClick={() => setShowSettings(true)} size="sm" variant="outline">
                                    <Plus size={12} className="mr-1" /> Aggiungi prima colonna
                                </Button>
                            </div>
                        )}
                    </div>
                )}
            </div>

            {!editable && (
                <div className="text-xs text-slate-500 bg-amber-50 border border-amber-200 px-3 py-2 rounded-md inline-block">
                    <Lock size={11} className="inline mr-1" /> Lo stato dei clienti è calcolato dal numero di polizze.
                </div>
            )}

            {isCustom && showSettings && (
                <Dialog open onOpenChange={setShowSettings}>
                    <SettingsColonne pipeline={data.pipeline} colonne={data.colonne}
                                     onClose={() => { setShowSettings(false); load(); onPipelineChange?.(); }} />
                </Dialog>
            )}

            {isCustom && newCardCol && (
                <Dialog open onOpenChange={() => setNewCardCol(null)}>
                    <NuovaCardDialog pipeline={data.pipeline} colonna_key={newCardCol}
                                     onClose={() => { setNewCardCol(null); load(); }} />
                </Dialog>
            )}

            {isCustom && editingCard && (
                <Dialog open onOpenChange={() => setEditingCard(null)}>
                    <EditCardDialog pipeline={data.pipeline} card={editingCard} colonne={data.colonne}
                                    onClose={() => { setEditingCard(null); load(); }} />
                </Dialog>
            )}
        </div>
    );
}

// ============== NUOVA PIPELINE ==============
function NuovaPipelineDialog({ onClose, onCreated }) {
    const [f, setF] = useState({ nome: "", descrizione: "", tipo: "marketing" });
    const salva = async () => {
        if (!f.nome) { toast.error("Inserisci un nome"); return; }
        try {
            const r = await api.post("/pipelines", f);
            toast.success("Pipeline creata");
            onCreated?.(r.data);
            onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };
    return (
        <DialogContent className="max-w-md">
            <DialogHeader><DialogTitle>Nuova pipeline custom</DialogTitle></DialogHeader>
            <div className="space-y-3 py-2">
                <div>
                    <Label>Nome *</Label>
                    <Input value={f.nome} onChange={(e) => setF({ ...f, nome: e.target.value })}
                           placeholder="Es: Campagna estate 2026" data-testid="pipeline-nome" />
                </div>
                <div>
                    <Label>Tipo (genera template colonne)</Label>
                    <Select value={f.tipo} onValueChange={(v) => setF({ ...f, tipo: v })}>
                        <SelectTrigger data-testid="pipeline-tipo"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="marketing">Marketing (Lead → Vinto/Perso)</SelectItem>
                            <SelectItem value="vendita">Vendita (Qualificazione → Negoziazione → Chiuso)</SelectItem>
                            <SelectItem value="onboarding">Onboarding (Documenti → Verifica → Completato)</SelectItem>
                            <SelectItem value="supporto">Supporto / Ticket (Aperto → In lavorazione → Risolto)</SelectItem>
                            <SelectItem value="generico">Generico (Da fare / In corso / Fatto)</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
                <div>
                    <Label>Descrizione</Label>
                    <Input value={f.descrizione} onChange={(e) => setF({ ...f, descrizione: e.target.value })} />
                </div>
                <div className="text-xs text-slate-500 bg-slate-50 border border-slate-200 rounded-md p-2">
                    Le colonne verranno create automaticamente in base al tipo. Potrai aggiungere/modificare/rimuovere
                    colonne in qualsiasi momento dal pannello &quot;Gestisci colonne&quot;.
                </div>
            </div>
            <DialogFooter>
                <Button onClick={salva} className="bg-sky-700 hover:bg-sky-800" data-testid="pipeline-crea">Crea pipeline</Button>
            </DialogFooter>
        </DialogContent>
    );
}

// ============== GESTIONE COLONNE ==============
function SettingsColonne({ pipeline, colonne, onClose }) {
    const [list, setList] = useState(colonne);
    const [busy, setBusy] = useState(false);

    const reload = async () => {
        const r = await api.get(`/pipelines/${pipeline.id}`);
        setList(r.data.colonne || []);
    };

    const aggiungi = async () => {
        const label = window.prompt("Nome della nuova colonna:");
        if (!label) return;
        setBusy(true);
        try {
            await api.post(`/pipelines/${pipeline.id}/colonne`, { label });
            await reload();
            toast.success("Colonna aggiunta");
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        finally { setBusy(false); }
    };
    const rinomina = async (col) => {
        const label = window.prompt("Nuovo nome:", col.label);
        if (!label || label === col.label) return;
        try {
            await api.put(`/pipelines/${pipeline.id}/colonne/${col.key}`, { label });
            await reload();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };
    const cambiaColore = async (col, colore) => {
        try {
            await api.put(`/pipelines/${pipeline.id}/colonne/${col.key}`, { colore });
            await reload();
        } catch (e) { toast.error("Errore"); }
    };
    const elimina = async (col) => {
        if (col.count > 0) {
            const altre = list.filter((c) => c.key !== col.key);
            if (altre.length === 0) {
                toast.error("Non puoi eliminare l'ultima colonna se contiene card");
                return;
            }
            const labels = altre.map((c) => `${c.key} (${c.label})`).join("\n");
            const dest = window.prompt(`La colonna contiene ${col.count} card. Sposta in quale colonna?\n\n${labels}\n\nInserisci la 'key':`, altre[0].key);
            if (!dest) return;
            try {
                await api.delete(`/pipelines/${pipeline.id}/colonne/${col.key}?sposta_in=${dest}`);
                await reload();
                toast.success("Colonna eliminata, card spostate");
            } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        } else {
            if (!window.confirm(`Eliminare la colonna "${col.label}"?`)) return;
            try {
                await api.delete(`/pipelines/${pipeline.id}/colonne/${col.key}`);
                await reload();
                toast.success("Colonna eliminata");
            } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        }
    };

    const PALETTE = ["#94A3B8", "#0EA5E9", "#10B981", "#F59E0B", "#EF4444", "#7C3AED", "#EC4899"];

    return (
        <DialogContent className="max-w-2xl">
            <DialogHeader>
                <DialogTitle>Gestisci colonne — {pipeline.nome}</DialogTitle>
            </DialogHeader>

            <div className="space-y-2 py-2 max-h-[60vh] overflow-y-auto">
                {list.map((col, i) => (
                    <div key={col.key} className="flex items-center gap-2 p-2 border border-slate-200 rounded-md bg-white">
                        <span className="text-xs text-slate-400 num w-6">{i + 1}.</span>
                        <span className="w-3 h-3 rounded-full" style={{ background: col.colore || "#64748B" }} />
                        <div className="flex-1">
                            <div className="text-sm font-medium">{col.label}</div>
                            <div className="text-[10px] text-slate-400 font-mono">{col.key} · {col.count || 0} card</div>
                        </div>
                        <div className="flex gap-0.5">
                            {PALETTE.map((c) => (
                                <button
                                    key={c}
                                    onClick={() => cambiaColore(col, c)}
                                    className="w-4 h-4 rounded-full border border-white ring-1 ring-slate-200 hover:scale-110 transition"
                                    style={{ background: c }}
                                    title={c}
                                />
                            ))}
                        </div>
                        <button onClick={() => rinomina(col)} className="text-slate-500 hover:text-sky-700 p-1.5" title="Rinomina" data-testid={`col-rename-${col.key}`}>
                            <Edit2 size={13} />
                        </button>
                        <button onClick={() => elimina(col)} className="text-red-500 hover:bg-red-50 p-1.5 rounded" title="Elimina" data-testid={`col-delete-${col.key}`}>
                            <Trash2 size={13} />
                        </button>
                    </div>
                ))}
            </div>
            <DialogFooter>
                <Button variant="outline" onClick={aggiungi} disabled={busy} data-testid="col-add">
                    <Plus size={13} className="mr-1" /> Aggiungi colonna
                </Button>
                <Button onClick={onClose}>Chiudi</Button>
            </DialogFooter>
        </DialogContent>
    );
}

// ============== CARDS ==============
function NuovaCardDialog({ pipeline, colonna_key, onClose }) {
    const [anagrafiche, setAnagrafiche] = useState([]);
    const [operatori, setOperatori] = useState([]);
    const [f, setF] = useState({
        titolo: "", descrizione: "",
        colonna_key, anagrafica_id: "", operatore_id: "",
        valore_stimato: 0, priorita: "media", scadenza: "",
    });
    useEffect(() => {
        api.get("/anagrafiche").then((r) => setAnagrafiche(r.data));
        api.get("/collaboratori").then((r) => setOperatori(r.data));
    }, []);

    const salva = async () => {
        if (!f.titolo) { toast.error("Titolo richiesto"); return; }
        try {
            await api.post(`/pipelines/${pipeline.id}/cards`, {
                ...f,
                anagrafica_id: f.anagrafica_id || null,
                operatore_id: f.operatore_id || null,
                scadenza: f.scadenza || null,
            });
            toast.success("Card creata");
            onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };
    return (
        <DialogContent className="max-w-lg">
            <DialogHeader><DialogTitle>Nuova card</DialogTitle></DialogHeader>
            <CardFields f={f} setF={setF} anagrafiche={anagrafiche} operatori={operatori} />
            <DialogFooter>
                <Button onClick={salva} className="bg-sky-700 hover:bg-sky-800" data-testid="card-salva">Crea</Button>
            </DialogFooter>
        </DialogContent>
    );
}

function EditCardDialog({ pipeline, card, colonne, onClose }) {
    const [anagrafiche, setAnagrafiche] = useState([]);
    const [operatori, setOperatori] = useState([]);
    const [f, setF] = useState(null);

    useEffect(() => {
        api.get("/anagrafiche").then((r) => setAnagrafiche(r.data));
        api.get("/collaboratori").then((r) => setOperatori(r.data));
        // ricarica i campi completi dalla card
        api.get(`/pipelines/${pipeline.id}`).then(() => {
            // i dati base ci sono già nella card semplificata; usa quelli
            setF({
                titolo: card.title, descrizione: card.subtitle || "",
                colonna_key: colonne.find((c) => c.cards.some((x) => x.id === card.id))?.key || colonne[0]?.key,
                valore_stimato: parseFloat((card.extra || "0").replace(/[^\d.]/g, "")) || 0,
                priorita: card.priorita || "media",
                scadenza: card.date || "",
                anagrafica_id: "", operatore_id: "",
            });
        });
    }, [card.id, pipeline.id, colonne]); // eslint-disable-line

    if (!f) return <DialogContent className="max-w-lg"><Loading /></DialogContent>;

    const salva = async () => {
        try {
            await api.put(`/pipelines/${pipeline.id}/cards/${card.id}`, {
                titolo: f.titolo, descrizione: f.descrizione,
                colonna_key: f.colonna_key,
                anagrafica_id: f.anagrafica_id || null,
                operatore_id: f.operatore_id || null,
                valore_stimato: parseFloat(f.valore_stimato) || 0,
                priorita: f.priorita,
                scadenza: f.scadenza || null,
            });
            toast.success("Card aggiornata");
            onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };
    const elimina = async () => {
        if (!window.confirm("Eliminare la card?")) return;
        try {
            await api.delete(`/pipelines/${pipeline.id}/cards/${card.id}`);
            toast.success("Card eliminata");
            onClose();
        } catch (e) { toast.error("Errore"); }
    };
    return (
        <DialogContent className="max-w-lg">
            <DialogHeader><DialogTitle>Modifica card</DialogTitle></DialogHeader>
            <CardFields f={f} setF={setF} anagrafiche={anagrafiche} operatori={operatori} colonne={colonne} />
            <DialogFooter>
                <Button variant="outline" onClick={elimina} className="text-red-600 mr-auto" data-testid="card-elimina">
                    <Trash2 size={13} className="mr-1" /> Elimina
                </Button>
                <Button onClick={salva} className="bg-sky-700 hover:bg-sky-800" data-testid="card-aggiorna">Aggiorna</Button>
            </DialogFooter>
        </DialogContent>
    );
}

function CardFields({ f, setF, anagrafiche, operatori, colonne }) {
    const set = (k, v) => setF({ ...f, [k]: v });
    return (
        <div className="space-y-3 py-2">
            <div>
                <Label>Titolo *</Label>
                <Input value={f.titolo} onChange={(e) => set("titolo", e.target.value)} data-testid="card-titolo" />
            </div>
            <div>
                <Label>Descrizione</Label>
                <textarea
                    className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm"
                    rows={2}
                    value={f.descrizione || ""}
                    onChange={(e) => set("descrizione", e.target.value)}
                />
            </div>
            {colonne && (
                <div>
                    <Label>Colonna</Label>
                    <Select value={f.colonna_key} onValueChange={(v) => set("colonna_key", v)}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                            {colonne.map((c) => <SelectItem key={c.key} value={c.key}>{c.label}</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
            )}
            <div className="grid grid-cols-2 gap-3">
                <div>
                    <Label>Valore stimato €</Label>
                    <Input type="number" step="0.01" value={f.valore_stimato || 0}
                           onChange={(e) => set("valore_stimato", e.target.value)} />
                </div>
                <div>
                    <Label>Priorità</Label>
                    <Select value={f.priorita || "media"} onValueChange={(v) => set("priorita", v)}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="bassa">Bassa</SelectItem>
                            <SelectItem value="media">Media</SelectItem>
                            <SelectItem value="alta">Alta</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
            </div>
            <div>
                <Label>Scadenza</Label>
                <Input type="date" value={f.scadenza || ""} onChange={(e) => set("scadenza", e.target.value)} />
            </div>
            <div>
                <Label>Cliente collegato</Label>
                <Select value={f.anagrafica_id || "__none__"} onValueChange={(v) => set("anagrafica_id", v === "__none__" ? "" : v)}>
                    <SelectTrigger data-testid="card-anag"><SelectValue /></SelectTrigger>
                    <SelectContent>
                        <SelectItem value="__none__">— nessuno —</SelectItem>
                        {anagrafiche.map((a) => <SelectItem key={a.id} value={a.id}>{a.ragione_sociale}</SelectItem>)}
                    </SelectContent>
                </Select>
            </div>
            <div>
                <Label>Operatore assegnato</Label>
                <Select value={f.operatore_id || "__none__"} onValueChange={(v) => set("operatore_id", v === "__none__" ? "" : v)}>
                    <SelectTrigger data-testid="card-op"><SelectValue /></SelectTrigger>
                    <SelectContent>
                        <SelectItem value="__none__">— nessuno —</SelectItem>
                        {operatori.map((o) => <SelectItem key={o.id} value={o.id}>{o.name}</SelectItem>)}
                    </SelectContent>
                </Select>
            </div>
        </div>
    );
}
