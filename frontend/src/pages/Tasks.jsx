/**
 * Tasks — bacheca attività stile Google Tasks.
 * Colonne per operatore, condivisione multi-operatore, allegati, stampa.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { api, fmtEur } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { PageHeader, Loading } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
    Plus, Printer, Paperclip, Users, Trash2, Check, Calendar as CalIcon,
    Share2, Download, X, CircleAlert, Link2,
} from "lucide-react";
import { toast } from "sonner";

const PRIORITA_META = {
    alta: { label: "Alta", cls: "text-rose-700 bg-rose-50 border-rose-200" },
    normale: { label: "Normale", cls: "text-slate-600 bg-slate-50 border-slate-200" },
    bassa: { label: "Bassa", cls: "text-sky-700 bg-sky-50 border-sky-200" },
};

function fmtScad(s) {
    if (!s) return null;
    try {
        const d = new Date(s + "T00:00:00");
        const today = new Date(); today.setHours(0, 0, 0, 0);
        const diff = Math.round((d - today) / 86400000);
        const label = d.toLocaleDateString("it-IT", { day: "2-digit", month: "short" });
        let cls = "text-slate-500";
        if (diff < 0) cls = "text-rose-600 font-semibold";
        else if (diff === 0) cls = "text-amber-600 font-semibold";
        return { label: diff === 0 ? "Oggi" : (diff === -1 ? "Ieri" : (diff < 0 ? `${label} (scaduta)` : label)), cls };
    } catch { return { label: s, cls: "text-slate-500" }; }
}

export default function Tasks() {
    const { user } = useAuth();
    const [operatori, setOperatori] = useState([]);
    const [tasks, setTasks] = useState(null);
    const [includeDone, setIncludeDone] = useState(false);
    const [viewAll, setViewAll] = useState(false);
    const [editing, setEditing] = useState(null);

    const load = async () => {
        try {
            const [op, tk] = await Promise.all([
                api.get("/tasks/operatori"),
                api.get(`/tasks?include_done=${includeDone}&tutti=${viewAll}`),
            ]);
            setOperatori(op.data || []);
            setTasks(tk.data || []);
        } catch (e) { toast.error("Errore caricamento attività"); }
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [includeDone, viewAll]);

    const isAdmin = user?.role === "admin";
    // Colonne: di default SOLO la propria; l'admin con "Vedi tutti" attivo vede tutti gli operatori
    const colonne = useMemo(() => {
        if (!operatori.length) return [];
        if (isAdmin && viewAll) return operatori;
        return operatori.filter((o) => o.id === user?.id);
    }, [operatori, isAdmin, viewAll, user]);

    const nomeOp = (id) => operatori.find((o) => o.id === id)?.name || "—";

    const tasksByOwner = useMemo(() => {
        const m = {};
        (tasks || []).forEach((t) => { (m[t.owner_id] = m[t.owner_id] || []).push(t); });
        return m;
    }, [tasks]);

    // Attività condivise CON me (da altri) — mostrate in evidenza per i non-admin
    const condiviseConMe = useMemo(
        () => (tasks || []).filter((t) => t.owner_id !== user?.id && (t.assegnatari || []).includes(user?.id)),
        [tasks, user]);

    const addTask = async (ownerId, titolo) => {
        if (!titolo.trim()) return;
        try {
            await api.post("/tasks", { titolo, owner_id: ownerId });
            load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };
    const toggle = async (t) => {
        try {
            await api.post(`/tasks/${t.id}/toggle`);
            load();
        } catch (e) { toast.error("Errore"); }
    };
    const remove = async (t) => {
        if (!window.confirm("Eliminare l'attività?")) return;
        try { await api.delete(`/tasks/${t.id}`); load(); }
        catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    if (!tasks) return <Loading />;

    return (
        <div className="space-y-4" data-testid="tasks-page">
            <div className="print:hidden">
                <PageHeader title="Attività (Tasks)"
                    subtitle="La bacheca di ogni operatore. Condividi con i colleghi, allega documenti e stampa l'elenco."
                    actions={
                        <div className="flex items-center gap-3">
                            {isAdmin && (
                                <label className="flex items-center gap-1.5 text-xs text-slate-600 cursor-pointer">
                                    <input type="checkbox" checked={viewAll} onChange={(e) => setViewAll(e.target.checked)}
                                        data-testid="tasks-view-all" />
                                    Vedi tutti gli operatori
                                </label>
                            )}
                            <label className="flex items-center gap-1.5 text-xs text-slate-600 cursor-pointer">
                                <input type="checkbox" checked={includeDone} onChange={(e) => setIncludeDone(e.target.checked)}
                                    data-testid="tasks-show-done" />
                                Mostra completate
                            </label>
                            <Button variant="outline" onClick={() => window.print()} data-testid="tasks-print-btn">
                                <Printer size={15} className="mr-1" /> Stampa
                            </Button>
                        </div>
                    } />
            </div>

            {/* Intestazione stampa */}
            <div className="hidden print:block mb-4">
                <h1 className="text-xl font-bold">Elenco attività</h1>
                <div className="text-xs text-slate-500">Stampato il {new Date().toLocaleString("it-IT")}</div>
            </div>

            {!(isAdmin && viewAll) && condiviseConMe.length > 0 && (
                <Card className="p-3 border-violet-200 bg-violet-50/40 print:hidden" data-testid="tasks-shared-with-me">
                    <div className="flex items-center gap-2 mb-2 text-violet-800 font-semibold text-sm">
                        <Share2 size={15} /> Condivise con me ({condiviseConMe.length})
                    </div>
                    <div className="space-y-1.5">
                        {condiviseConMe.map((t) => (
                            <TaskRow key={t.id} t={t} onToggle={toggle} onEdit={setEditing} onDelete={remove}
                                nomeOp={nomeOp} sharedFrom={nomeOp(t.owner_id)} />
                        ))}
                    </div>
                </Card>
            )}

            <div className="flex gap-4 overflow-x-auto pb-3 print:flex-wrap print:overflow-visible">
                {colonne.map((op) => {
                    const list = (tasksByOwner[op.id] || []);
                    const aperte = list.filter((t) => t.stato !== "done");
                    const complete = list.filter((t) => t.stato === "done");
                    return (
                        <div key={op.id} className="min-w-[300px] w-[300px] shrink-0 print:w-full print:min-w-0"
                            data-testid={`tasks-col-${op.id}`}>
                            <Card className="p-3">
                                <div className="flex items-center justify-between mb-2">
                                    <div className="font-semibold text-slate-800">{op.name}</div>
                                    <span className="text-[11px] text-slate-400">{aperte.length}</span>
                                </div>
                                <AddInline onAdd={(titolo) => addTask(op.id, titolo)} testid={`tasks-add-${op.id}`} />
                                <div className="space-y-1.5 mt-2">
                                    {aperte.length === 0 && (
                                        <div className="text-[11px] text-slate-400 italic py-2">Nessuna attività</div>
                                    )}
                                    {aperte.map((t) => (
                                        <TaskRow key={t.id} t={t} onToggle={toggle} onEdit={setEditing} onDelete={remove}
                                            nomeOp={nomeOp} />
                                    ))}
                                </div>
                                {includeDone && complete.length > 0 && (
                                    <div className="mt-3 pt-2 border-t border-slate-100">
                                        <div className="text-[11px] text-slate-400 mb-1">Completate ({complete.length})</div>
                                        {complete.map((t) => (
                                            <TaskRow key={t.id} t={t} onToggle={toggle} onEdit={setEditing} onDelete={remove}
                                                nomeOp={nomeOp} />
                                        ))}
                                    </div>
                                )}
                            </Card>
                        </div>
                    );
                })}
            </div>

            {editing && (
                <TaskDialog task={editing} operatori={operatori} currentUser={user}
                    onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />
            )}
        </div>
    );
}

function AddInline({ onAdd, testid }) {
    const [text, setText] = useState("");
    return (
        <div className="flex items-center gap-1.5 print:hidden">
            <Plus size={15} className="text-sky-600 shrink-0" />
            <input
                className="flex-1 text-sm border-0 border-b border-transparent focus:border-sky-300 focus:ring-0 focus:outline-none bg-transparent py-1"
                placeholder="Aggiungi un'attività"
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { onAdd(text); setText(""); } }}
                data-testid={testid}
            />
        </div>
    );
}

function TaskRow({ t, onToggle, onEdit, onDelete, sharedFrom }) {
    const scad = fmtScad(t.data_scadenza);
    const done = t.stato === "done";
    const nAlleg = (t.allegati || []).length;
    const nCond = (t.assegnatari || []).length;
    return (
        <div className="group flex items-start gap-2 rounded-md px-1.5 py-1 hover:bg-slate-50 print:hover:bg-transparent"
            data-testid={`task-row-${t.id}`}>
            <button onClick={() => onToggle(t)} className="mt-0.5 shrink-0 print:hidden" data-testid={`task-toggle-${t.id}`}
                aria-label="Completa">
                <span className={`inline-flex items-center justify-center w-4 h-4 rounded-full border ${done ? "bg-emerald-500 border-emerald-500 text-white" : "border-slate-300 hover:border-sky-500"}`}>
                    {done && <Check size={11} />}
                </span>
            </button>
            <div className="flex-1 min-w-0 cursor-pointer" onClick={() => onEdit(t)}>
                <div className={`text-sm ${done ? "line-through text-slate-400" : "text-slate-800"}`}>{t.titolo}</div>
                <div className="flex items-center gap-2 flex-wrap mt-0.5">
                    {t.priorita === "alta" && <span className="inline-flex items-center gap-0.5 text-[10px] text-rose-600"><CircleAlert size={10} />Alta</span>}
                    {scad && <span className={`inline-flex items-center gap-0.5 text-[10px] ${scad.cls}`}><CalIcon size={10} />{scad.label}</span>}
                    {nCond > 0 && <span className="inline-flex items-center gap-0.5 text-[10px] text-violet-600"><Users size={10} />{nCond}</span>}
                    {nAlleg > 0 && <span className="inline-flex items-center gap-0.5 text-[10px] text-slate-500"><Paperclip size={10} />{nAlleg}</span>}
                    {sharedFrom && <span className="text-[10px] text-violet-500">da {sharedFrom}</span>}
                </div>
            </div>
            <button onClick={() => onDelete(t)}
                className="opacity-0 group-hover:opacity-100 text-rose-400 hover:text-rose-600 shrink-0 print:hidden"
                data-testid={`task-del-${t.id}`} aria-label="Elimina">
                <Trash2 size={13} />
            </button>
        </div>
    );
}

function TaskDialog({ task, operatori, currentUser, onClose, onSaved }) {
    const [f, setF] = useState({ ...task });
    const [saving, setSaving] = useState(false);
    const fileRef = useRef(null);
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
    const isOwner = task.owner_id === currentUser?.id || currentUser?.role === "admin";

    const save = async () => {
        setSaving(true);
        try {
            await api.put(`/tasks/${task.id}`, {
                titolo: f.titolo, note: f.note, data_scadenza: f.data_scadenza || null,
                priorita: f.priorita, assegnatari: f.assegnatari || [],
                collegamento_tipo: f.collegamento_tipo || null,
                collegamento_id: f.collegamento_id || null,
                collegamento_label: f.collegamento_label || null,
            });
            toast.success("Attività aggiornata");
            onSaved();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        finally { setSaving(false); }
    };

    const uploadFile = async (file) => {
        if (!file) return;
        const fd = new FormData();
        fd.append("file", file);
        try {
            const r = await api.post(`/tasks/${task.id}/allegati`, fd, { headers: { "Content-Type": "multipart/form-data" } });
            set("allegati", [...(f.allegati || []), r.data]);
            toast.success("Allegato caricato");
        } catch (e) { toast.error(e.response?.data?.detail || "Errore upload"); }
    };
    const delAllegato = async (aid) => {
        try {
            await api.delete(`/tasks/${task.id}/allegati/${aid}`);
            set("allegati", (f.allegati || []).filter((a) => a.id !== aid));
        } catch (e) { toast.error("Errore"); }
    };
    const download = async (a) => {
        try {
            const r = await api.get(`/tasks/${task.id}/allegati/${a.id}/download`, { responseType: "blob" });
            const url = URL.createObjectURL(r.data);
            const link = document.createElement("a");
            link.href = url; link.download = a.nome_file; link.click();
            URL.revokeObjectURL(url);
        } catch (e) { toast.error("Errore download"); }
    };
    const toggleAssegnatario = (id) => {
        const cur = f.assegnatari || [];
        set("assegnatari", cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]);
    };

    const altriOperatori = operatori.filter((o) => o.id !== task.owner_id);

    const [linkQ, setLinkQ] = useState("");
    const [linkResults, setLinkResults] = useState([]);
    const [titoloPol, setTitoloPol] = useState(null);   // polizza scelta in modalità "titolo"
    const [titoliOpts, setTitoliOpts] = useState([]);
    const cercaCollegamento = async (tipo, q) => {
        if (!tipo || !q || q.length < 2) { setLinkResults([]); return; }
        // In modalità "titolo" si cerca prima la polizza
        const searchTipo = tipo === "titolo" ? "polizza" : tipo;
        try {
            const ep = searchTipo === "polizza" ? "/polizze" : "/anagrafiche";
            const r = await api.get(ep, { params: { q, limit: 8 } });
            const data = Array.isArray(r.data) ? r.data : (r.data.items || r.data.data || []);
            setLinkResults(data.map((x) => ({
                id: x.id,
                numero_polizza: x.numero_polizza,
                label: searchTipo === "polizza"
                    ? `N. ${x.numero_polizza || "?"}${x.ramo ? " · " + x.ramo : ""}`
                    : (x.ragione_sociale || `${x.nome || ""} ${x.cognome || ""}`.trim() || "?"),
            })));
        } catch { setLinkResults([]); }
    };
    const scegliPolizzaPerTitolo = async (res) => {
        setTitoloPol(res);
        setLinkResults([]); setLinkQ("");
        try {
            const r = await api.get("/titoli", { params: { polizza_id: res.id, limit: 500 } });
            const arr = Array.isArray(r.data) ? r.data : (r.data.items || []);
            setTitoliOpts(arr.sort((a, b) => (b.scadenza || "").localeCompare(a.scadenza || "")));
        } catch { setTitoliOpts([]); }
    };
    const scegliTitolo = (t) => {
        const scad = t.scadenza || t.effetto || t.data_incasso || "";
        const lbl = `Pol. ${titoloPol?.numero_polizza || "?"} · rata ${scad ? scad.slice(0, 10) : "?"} · ${fmtEur(t.importo_lordo)} (${t.stato || t.tipo || ""})`;
        set("collegamento_id", t.id);
        set("collegamento_label", lbl);
        setTitoliOpts([]);
    };
    const resetLink = () => { set("collegamento_id", null); set("collegamento_label", null); setTitoloPol(null); setTitoliOpts([]); };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-lg" data-testid="task-dialog">
                <DialogHeader><DialogTitle>Dettaglio attività</DialogTitle></DialogHeader>
                <div className="space-y-3 max-h-[65vh] overflow-y-auto pr-1">
                    <div>
                        <Label>Titolo</Label>
                        <Input value={f.titolo || ""} onChange={(e) => set("titolo", e.target.value)} data-testid="task-edit-titolo" />
                    </div>
                    <div>
                        <Label>Note</Label>
                        <Textarea rows={3} value={f.note || ""} onChange={(e) => set("note", e.target.value)} />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <Label>Scadenza</Label>
                            <Input type="date" value={(f.data_scadenza || "").slice(0, 10)}
                                onChange={(e) => set("data_scadenza", e.target.value)} data-testid="task-edit-scadenza" />
                        </div>
                        <div>
                            <Label>Priorità</Label>
                            <select className="w-full h-10 rounded-md border border-slate-300 px-2 text-sm"
                                value={f.priorita || "normale"} onChange={(e) => set("priorita", e.target.value)}
                                data-testid="task-edit-priorita">
                                <option value="bassa">Bassa</option>
                                <option value="normale">Normale</option>
                                <option value="alta">Alta</option>
                            </select>
                        </div>
                    </div>
                    <div>
                        <Label className="flex items-center gap-1"><Link2 size={13} /> Collega a</Label>
                        <div className="flex gap-2 mt-1">
                            <select className="h-9 rounded-md border border-slate-300 px-2 text-sm w-40"
                                value={f.collegamento_tipo || ""}
                                onChange={(e) => { set("collegamento_tipo", e.target.value || null); set("collegamento_id", null); set("collegamento_label", null); setLinkResults([]); setLinkQ(""); setTitoloPol(null); setTitoliOpts([]); }}
                                data-testid="task-link-tipo">
                                <option value="">Nessun collegamento</option>
                                <option value="anagrafica">Cliente / Anagrafica</option>
                                <option value="polizza">Polizza</option>
                                <option value="titolo">Titolo / Rata</option>
                            </select>
                            {f.collegamento_tipo && f.collegamento_id ? (
                                <div className="flex-1 flex items-center gap-2 bg-emerald-50 border border-emerald-200 rounded px-2 text-sm" data-testid="task-link-selected">
                                    <span className="flex-1 truncate text-emerald-800">{f.collegamento_label}</span>
                                    <button type="button" className="text-rose-500" title="Rimuovi"
                                        onClick={resetLink}><X size={13} /></button>
                                </div>
                            ) : f.collegamento_tipo === "titolo" && titoloPol ? (
                                <div className="flex-1">
                                    <div className="flex items-center gap-2 text-xs text-slate-600 mb-1">
                                        <span className="truncate">Polizza {titoloPol.label}</span>
                                        <button type="button" className="text-sky-600 underline" onClick={() => { setTitoloPol(null); setTitoliOpts([]); }}>cambia</button>
                                    </div>
                                    {titoliOpts.length === 0 ? (
                                        <div className="text-xs text-slate-400">Nessuna rata/titolo per questa polizza</div>
                                    ) : (
                                        <div className="border border-slate-200 rounded-md max-h-48 overflow-y-auto" data-testid="task-titoli-list">
                                            {titoliOpts.map((t) => (
                                                <button key={t.id} type="button"
                                                    className="w-full text-left px-3 py-1.5 hover:bg-sky-50 text-xs border-b border-slate-100 last:border-0"
                                                    onClick={() => scegliTitolo(t)}
                                                    data-testid={`task-titolo-opt-${t.id}`}>
                                                    rata {(t.scadenza || t.effetto || t.data_incasso || "?").slice(0, 10)} · {fmtEur(t.importo_lordo)} · {t.stato || t.tipo || ""}
                                                </button>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            ) : f.collegamento_tipo ? (
                                <div className="flex-1 relative">
                                    <Input placeholder={f.collegamento_tipo === "anagrafica" ? "Cerca cliente..." : "Cerca n. polizza..."}
                                        value={linkQ} onChange={(e) => { setLinkQ(e.target.value); cercaCollegamento(f.collegamento_tipo, e.target.value); }}
                                        data-testid="task-link-search" />
                                    {linkResults.length > 0 && (
                                        <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded-md shadow-lg max-h-48 overflow-y-auto">
                                            {linkResults.map((res) => (
                                                <button key={res.id} type="button"
                                                    className="w-full text-left px-3 py-2 hover:bg-sky-50 text-sm border-b border-slate-100 last:border-0"
                                                    onClick={() => {
                                                        if (f.collegamento_tipo === "titolo") { scegliPolizzaPerTitolo(res); }
                                                        else { set("collegamento_id", res.id); set("collegamento_label", res.label); setLinkResults([]); setLinkQ(""); }
                                                    }}
                                                    data-testid={`task-link-opt-${res.id}`}>
                                                    {res.label}
                                                </button>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            ) : null}
                        </div>
                        <div className="text-[11px] text-slate-400 mt-1">Il task attivo comparirà nella scheda del cliente, della polizza o del titolo collegato.</div>
                    </div>
                    <div>
                        <Label className="flex items-center gap-1"><Share2 size={13} /> Condividi con operatori</Label>
                        <div className="flex flex-wrap gap-1.5 mt-1">
                            {altriOperatori.map((o) => {
                                const on = (f.assegnatari || []).includes(o.id);
                                return (
                                    <button key={o.id} type="button" onClick={() => toggleAssegnatario(o.id)}
                                        className={`text-xs px-2 py-1 rounded-full border transition-colors ${on ? "bg-violet-600 text-white border-violet-600" : "bg-white text-slate-600 border-slate-300 hover:border-violet-400"}`}
                                        data-testid={`task-share-${o.id}`}>
                                        {o.name}
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                    <div>
                        <div className="flex items-center justify-between">
                            <Label className="flex items-center gap-1"><Paperclip size={13} /> Allegati</Label>
                            <button type="button" onClick={() => fileRef.current?.click()}
                                className="text-xs text-sky-700 hover:underline" data-testid="task-upload-btn">
                                + Aggiungi file
                            </button>
                            <input ref={fileRef} type="file" className="hidden"
                                onChange={(e) => { uploadFile(e.target.files?.[0]); e.target.value = ""; }} />
                        </div>
                        <div className="space-y-1 mt-1">
                            {(f.allegati || []).length === 0 && <div className="text-[11px] text-slate-400 italic">Nessun allegato</div>}
                            {(f.allegati || []).map((a) => (
                                <div key={a.id} className="flex items-center gap-2 text-xs bg-slate-50 rounded px-2 py-1">
                                    <Paperclip size={11} className="text-slate-400" />
                                    <span className="flex-1 truncate">{a.nome_file}</span>
                                    <button onClick={() => download(a)} className="text-sky-600" title="Scarica"><Download size={12} /></button>
                                    <button onClick={() => delAllegato(a.id)} className="text-rose-500" title="Elimina"><X size={12} /></button>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Chiudi</Button>
                    <Button onClick={save} disabled={saving} className="bg-sky-700 hover:bg-sky-800" data-testid="task-save-btn">Salva</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
