/**
 * Trattative — gestione proposte commerciali / disdette in corso di acquisizione
 * (prima che si trasformino in polizze): dati cliente, compagnia di provenienza,
 * premio attuale vs proposto, stato, allegati visibili/non al cliente.
 */
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, fmtEur } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { Plus, Edit, Trash2, Briefcase, ArrowRight, Paperclip, Mail, MessageCircle, Link2, Send } from "lucide-react";
import { toast } from "sonner";
import AllegatiCell from "@/components/AllegatiCell";

const STATI = [
    { v: "aperta", l: "Aperta", color: "sky" },
    { v: "proposta_inviata", l: "Proposta inviata", color: "amber" },
    { v: "in_attesa", l: "In attesa risposta", color: "violet" },
    { v: "vinta", l: "Vinta", color: "emerald" },
    { v: "persa", l: "Persa", color: "rose" },
];

export default function Trattative() {
    const [list, setList] = useState(null);
    const [stato, setStato] = useState("all");
    const [editing, setEditing] = useState(null);
    const [open, setOpen] = useState(false);

    const load = () => {
        const params = stato !== "all" ? { stato } : {};
        api.get("/trattative", { params }).then((r) => setList(r.data));
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [stato]);

    const totali = useMemo(() => {
        const src = list || [];
        return {
            n: src.length,
            premio_corrente: src.reduce((s, x) => s + (x.premio_corrente || 0), 0),
            premio_proposto: src.reduce((s, x) => s + (x.premio_proposto || 0), 0),
            vinte: src.filter((x) => x.stato === "vinta").length,
        };
    }, [list]);

    const del = async (id) => {
        if (!window.confirm("Eliminare la trattativa?")) return;
        await api.delete(`/trattative/${id}`); toast.success("Eliminata"); load();
    };

    return (
        <div data-testid="trattative-page" className="space-y-3">
            <PageHeader
                title={<span className="flex items-center gap-2"><Briefcase className="text-sky-600" /> Trattative</span>}
                subtitle="Proposte commerciali e disdette in corso · pipeline pre-polizza"
                actions={
                    <Dialog open={open} onOpenChange={setOpen}>
                        <DialogTrigger asChild>
                            <Button onClick={() => setEditing(null)} className="bg-sky-700 hover:bg-sky-800" data-testid="tr-new">
                                <Plus size={14} className="mr-1" /> Nuova trattativa
                            </Button>
                        </DialogTrigger>
                        <TrattativaDialog key={editing?.id || "new"} editing={editing}
                            onClose={() => { setOpen(false); setEditing(null); load(); }} />
                    </Dialog>
                }
            />

            {/* KPI */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Card className="p-3 border-l-4 border-sky-400 bg-white">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">In corso</div>
                    <div className="text-2xl font-bold">{totali.n}</div>
                </Card>
                <Card className="p-3 border-l-4 border-emerald-400 bg-white">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">Vinte</div>
                    <div className="text-2xl font-bold text-emerald-700">{totali.vinte}</div>
                </Card>
                <Card className="p-3 border-l-4 border-amber-400 bg-white">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">Premio corrente concorrente</div>
                    <div className="text-xl font-bold font-mono">{fmtEur(totali.premio_corrente)}</div>
                </Card>
                <Card className="p-3 border-l-4 border-violet-400 bg-white">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">Premio proposto da noi</div>
                    <div className="text-xl font-bold font-mono">{fmtEur(totali.premio_proposto)}</div>
                </Card>
            </div>

            {/* Filtri */}
            <Card className="p-3 flex gap-2 items-center">
                <span className="text-xs text-slate-500 font-medium">Stato:</span>
                <button onClick={() => setStato("all")}
                    className={`text-xs px-2 py-1 rounded border ${stato === "all" ? "bg-sky-600 text-white border-sky-600" : "border-slate-300"}`}
                    data-testid="tr-f-all">Tutti</button>
                {STATI.map((s) => (
                    <button key={s.v} onClick={() => setStato(s.v)}
                        className={`text-xs px-2 py-1 rounded border ${stato === s.v ? `bg-${s.color}-600 text-white border-${s.color}-600` : "border-slate-300"}`}
                        data-testid={`tr-f-${s.v}`}>{s.l}</button>
                ))}
            </Card>

            {/* Tabella */}
            <div className="tbl-scroll">
                {list === null ? <Loading /> : list.length === 0 ? <Empty /> : (
                    <table className="tbl-compact w-full text-xs">
                        <thead><tr>
                            <th>Titolo</th><th>Cliente</th><th>Ramo</th>
                            <th>Compagnia provenienza</th><th>Scadenza concorrente</th>
                            <th className="text-right">Premio attuale</th>
                            <th className="text-right">Premio proposto</th>
                            <th className="text-right">Risparmio</th>
                            <th>Stato</th><th>Visibile cliente</th><th className="w-20"></th>
                        </tr></thead>
                        <tbody>
                            {list.map((t) => {
                                const risp = (t.premio_corrente || 0) - (t.premio_proposto || 0);
                                const st = STATI.find((s) => s.v === t.stato) || STATI[0];
                                return (
                                    <tr key={t.id} data-testid={`tr-row-${t.id}`}>
                                        <td className="font-medium">{t.titolo}</td>
                                        <td>{t.anagrafica_nome}</td>
                                        <td>{t.ramo || "—"}</td>
                                        <td>{t.compagnia_di_provenienza || "—"}</td>
                                        <td className="num">{t.data_scadenza_corrente || "—"}</td>
                                        <td className="text-right font-mono">{fmtEur(t.premio_corrente)}</td>
                                        <td className="text-right font-mono">{fmtEur(t.premio_proposto)}</td>
                                        <td className={`text-right font-mono font-bold ${risp >= 0 ? "text-emerald-700" : "text-rose-700"}`}>
                                            {risp >= 0 ? "" : ""}{fmtEur(risp)}
                                        </td>
                                        <td><span className={`badge badge-${st.color === "emerald" ? "success" : st.color === "rose" ? "danger" : st.color === "amber" ? "warning" : "info"}`}>{st.l}</span></td>
                                        <td>{t.visibili_cliente ? <span className="text-emerald-700">✓ sì</span> : <span className="text-slate-400">no</span>}</td>
                                        <td className="text-right space-x-1">
                                            <button onClick={() => { setEditing(t); setOpen(true); }}
                                                className="text-sky-700 hover:bg-sky-50 p-1 rounded" data-testid={`tr-edit-${t.id}`}>
                                                <Edit size={11} />
                                            </button>
                                            <button onClick={() => del(t.id)} className="text-rose-600 hover:bg-rose-50 p-1 rounded">
                                                <Trash2 size={11} />
                                            </button>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
}

function TrattativaDialog({ editing, onClose }) {
    const [anagrafiche, setAnagrafiche] = useState([]);
    const [compagnie, setCompagnie] = useState([]);
    const [polizze, setPolizze] = useState([]);
    const [invio, setInvio] = useState(null); // "email" | "whatsapp"
    const [clienteSearch, setClienteSearch] = useState("");
    const [chkTxt, setChkTxt] = useState("");
    const [f, setF] = useState(editing || {
        anagrafica_id: "", titolo: "", descrizione: "",
        ramo: "", compagnia_di_provenienza: "", compagnia_target_id: "",
        data_scadenza_corrente: "", premio_corrente: 0, premio_proposto: 0,
        stato: "aperta", note: "", polizza_id: "", visibili_cliente: false,
    });
    useEffect(() => {
        api.get("/compagnie").then((r) => setCompagnie(r.data));
    }, []);
    // Ricerca cliente server-side (debounce) — scala su migliaia di anagrafiche
    useEffect(() => {
        const term = clienteSearch.trim();
        const t = setTimeout(() => {
            api.get("/anagrafiche", { params: term ? { q: term, limit: 50 } : { limit: 50 } })
                .then((r) => setAnagrafiche(Array.isArray(r.data) ? r.data : (r.data?.items || [])))
                .catch(() => setAnagrafiche([]));
        }, 300);
        return () => clearTimeout(t);
    }, [clienteSearch]);
    useEffect(() => {
        if (f.anagrafica_id) {
            api.get("/polizze", { params: { contraente_id: f.anagrafica_id, limit: 500 } })
                .then((r) => setPolizze(Array.isArray(r.data) ? r.data : (r.data?.items || [])))
                .catch(() => setPolizze([]));
        } else { setPolizze([]); }
    }, [f.anagrafica_id]);
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
    const save = async () => {
        if (!f.anagrafica_id || !f.titolo) { toast.error("Cliente e titolo obbligatori"); return; }
        try {
            if (editing?.id) await api.put(`/trattative/${editing.id}`, f);
            else await api.post("/trattative", f);
            toast.success("Salvata"); onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };
    const invia = async (canale) => {
        const dest = canale === "email" ? editing?.anagrafica_email : editing?.anagrafica_cellulare;
        if (!dest) { toast.error(`Nessun ${canale === "email" ? "indirizzo email" : "numero cellulare"} sull'anagrafica`); return; }
        if (!window.confirm(`Inviare il preventivo via ${canale.toUpperCase()} a ${dest}?`)) return;
        setInvio(canale);
        try {
            const r = await api.post(`/trattative/${editing.id}/invia`, { canale });
            if (r.data.ok) toast.success(`Preventivo inviato via ${canale.toUpperCase()} a ${r.data.destinatario}`);
            else toast.error(`Invio non riuscito: ${r.data.esito}`);
        } catch (e) { toast.error(e.response?.data?.detail || "Errore invio"); }
        finally { setInvio(null); }
    };
    return (
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader><DialogTitle>{editing?.id ? "Modifica trattativa" : "Nuova trattativa"}</DialogTitle></DialogHeader>
            <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2">
                    <Label className="text-xs">Cliente *</Label>
                    <Select value={f.anagrafica_id} onValueChange={(v) => set("anagrafica_id", v)}>
                        <SelectTrigger data-testid="tr-cliente"><SelectValue placeholder="Seleziona cliente" /></SelectTrigger>
                        <SelectContent className="max-h-80">
                            <div className="sticky top-0 bg-white z-10 p-1.5 border-b border-slate-100">
                                <Input autoFocus placeholder="Cerca cliente (nome, CF, email…)" value={clienteSearch}
                                    onChange={(e) => setClienteSearch(e.target.value)}
                                    onKeyDown={(e) => e.stopPropagation()}
                                    className="h-8 text-sm" data-testid="tr-cliente-search" />
                            </div>
                            {editing?.anagrafica_id && !anagrafiche.some((a) => a.id === editing.anagrafica_id) && (
                                <SelectItem key={editing.anagrafica_id} value={editing.anagrafica_id}>
                                    {editing.anagrafica_nome || "Cliente selezionato"}
                                </SelectItem>
                            )}
                            {anagrafiche.length === 0 && (
                                <div className="px-3 py-2 text-xs text-slate-400">Digita per cercare…</div>
                            )}
                            {anagrafiche.map((a) => (
                                <SelectItem key={a.id} value={a.id}>
                                    {a.ragione_sociale || `${a.cognome || ""} ${a.nome || ""}`}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
                <div className="col-span-2"><Label className="text-xs">Titolo *</Label>
                    <Input value={f.titolo} onChange={(e) => set("titolo", e.target.value)}
                        placeholder="es. Preventivo Auto Tesla — disdetta UnipolSai" data-testid="tr-titolo" /></div>
                <div><Label className="text-xs">Ramo</Label>
                    <Input value={f.ramo} onChange={(e) => set("ramo", e.target.value)} placeholder="RCAUTO / CASA / INFORTUNI…" /></div>
                <div><Label className="text-xs">Stato</Label>
                    <Select value={f.stato} onValueChange={(v) => set("stato", v)}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                            {STATI.map((s) => <SelectItem key={s.v} value={s.v}>{s.l}</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
                <div><Label className="text-xs">Compagnia di provenienza</Label>
                    <Input value={f.compagnia_di_provenienza} onChange={(e) => set("compagnia_di_provenienza", e.target.value)}
                        placeholder="es. UnipolSai, Allianz, …" /></div>
                <div><Label className="text-xs">Compagnia target (interna)</Label>
                    <Select value={f.compagnia_target_id || "__none__"} onValueChange={(v) => set("compagnia_target_id", v === "__none__" ? "" : v)}>
                        <SelectTrigger><SelectValue placeholder="—" /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="__none__">—</SelectItem>
                            {compagnie.map((c) => <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
                <div><Label className="text-xs">Scadenza polizza concorrente</Label>
                    <Input type="date" value={f.data_scadenza_corrente || ""} onChange={(e) => set("data_scadenza_corrente", e.target.value)} /></div>
                <div><Label className="text-xs">Premio attuale concorrente €</Label>
                    <Input type="number" step="0.01" value={f.premio_corrente} onChange={(e) => set("premio_corrente", parseFloat(e.target.value) || 0)} /></div>
                <div><Label className="text-xs">Premio proposto da noi €</Label>
                    <Input type="number" step="0.01" value={f.premio_proposto} onChange={(e) => set("premio_proposto", parseFloat(e.target.value) || 0)} /></div>
                <div className="col-span-2">
                    <Label className="text-xs flex items-center gap-1"><Link2 size={12} /> Polizza collegata (post-vendita)</Label>
                    <Select value={f.polizza_id || "__none__"} onValueChange={(v) => set("polizza_id", v === "__none__" ? "" : v)}>
                        <SelectTrigger data-testid="tr-polizza"><SelectValue placeholder="— nessuna polizza —" /></SelectTrigger>
                        <SelectContent className="max-h-80">
                            <SelectItem value="__none__">— nessuna —</SelectItem>
                            {polizze.map((p) => (
                                <SelectItem key={p.id} value={p.id}>{p.numero_polizza} · {p.ramo || ""}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                    <p className="text-[10px] text-slate-400 mt-1">Collegando una polizza, note e documenti di questa trattativa saranno visibili nella polizza.</p>
                </div>
                <div className="col-span-2"><Label className="text-xs">Descrizione</Label>
                    <Textarea rows={2} value={f.descrizione || ""} onChange={(e) => set("descrizione", e.target.value)} /></div>
                <div className="col-span-2"><Label className="text-xs">Note interne</Label>
                    <Textarea rows={2} value={f.note || ""} onChange={(e) => set("note", e.target.value)} /></div>
                <div className="col-span-2">
                    <Label className="text-xs">Checklist</Label>
                    <div className="space-y-1 mt-1" data-testid="tr-checklist">
                        {(f.checklist || []).map((it, i) => (
                            <div key={it.id || i} className="flex items-center gap-2 text-sm group">
                                <input type="checkbox" checked={!!it.done}
                                    onChange={() => set("checklist", (f.checklist || []).map((x, j) => j === i ? { ...x, done: !x.done } : x))} />
                                <span className={`flex-1 ${it.done ? "line-through text-slate-400" : "text-slate-700"}`}>{it.testo}</span>
                                <button type="button" onClick={() => set("checklist", (f.checklist || []).filter((_, j) => j !== i))}
                                    className="text-slate-300 hover:text-rose-500 opacity-0 group-hover:opacity-100">×</button>
                            </div>
                        ))}
                        <Input value={chkTxt} onChange={(e) => setChkTxt(e.target.value)}
                            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); if (chkTxt.trim()) { set("checklist", [...(f.checklist || []), { id: `${Date.now()}`, testo: chkTxt.trim(), done: false }]); setChkTxt(""); } } }}
                            placeholder="Aggiungi voce e premi Invio…" className="h-8 text-sm" data-testid="tr-checklist-input" />
                    </div>
                </div>
                <div className="col-span-2 flex items-center gap-2 mt-2">
                    <Checkbox checked={!!f.visibili_cliente} onCheckedChange={(v) => set("visibili_cliente", !!v)} id="tr-vis" />
                    <Label htmlFor="tr-vis" className="text-xs">📂 Trattativa visibile al cliente (nel suo portale)</Label>
                </div>
                {editing?.id && (
                    <div className="col-span-2 mt-2 rounded-lg border border-slate-200 bg-slate-50 p-3 space-y-3" data-testid="tr-azioni-extra">
                        <div className="flex items-center justify-between">
                            <div className="text-xs font-semibold uppercase tracking-wide text-slate-600 flex items-center gap-1.5">
                                <Paperclip size={13} /> Documenti / Preventivo
                            </div>
                            <AllegatiCell entita_tipo="trattativa" entita_id={editing.id} compact={false} hint="Allega preventivo/doc" />
                        </div>
                        <div className="flex items-center gap-2">
                            <span className="text-xs text-slate-500">Invia preventivo:</span>
                            <Button type="button" size="sm" variant="outline" disabled={invio === "email"}
                                onClick={() => invia("email")} className="text-sky-700 border-sky-200" data-testid="tr-invia-email">
                                <Mail size={13} className="mr-1" /> {invio === "email" ? "Invio…" : "Email"}
                            </Button>
                            <Button type="button" size="sm" variant="outline" disabled={invio === "whatsapp"}
                                onClick={() => invia("whatsapp")} className="text-emerald-700 border-emerald-200" data-testid="tr-invia-whatsapp">
                                <MessageCircle size={13} className="mr-1" /> {invio === "whatsapp" ? "Invio…" : "WhatsApp"}
                            </Button>
                        </div>
                    </div>
                )}
            </div>
            <DialogFooter>
                <Button onClick={save} className="bg-sky-700 hover:bg-sky-800" data-testid="tr-save">
                    {editing?.id ? <><Edit size={14} className="mr-1" /> Aggiorna</> : <><Plus size={14} className="mr-1" /> Crea</>}
                </Button>
            </DialogFooter>
        </DialogContent>
    );
}
