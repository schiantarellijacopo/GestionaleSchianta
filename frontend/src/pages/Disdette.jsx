/**
 * Disdette — registro delle disdette da inviare alle altre compagnie,
 * con avviso/promemoria di scadenza (termine ultimo per l'invio).
 */
import { useEffect, useMemo, useState } from "react";
import { api, API_BASE, imgUrl } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { Plus, Edit, Trash2, TrendingDown, AlertTriangle, Send, FileText, Paperclip, BookUser, Download, Upload, X, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

const STATI = [
    { v: "da_inviare", l: "Da inviare", color: "amber" },
    { v: "inviata", l: "Inviata", color: "sky" },
    { v: "confermata", l: "Confermata", color: "emerald" },
    { v: "annullata", l: "Annullata", color: "slate" },
];
const badgeClass = (c) => c === "emerald" ? "badge-success" : c === "amber" ? "badge-warning" : c === "slate" ? "badge-neutral" : "badge-info";

const daysTo = (iso) => {
    if (!iso) return null;
    try {
        const d = new Date(iso); const now = new Date(); now.setHours(0, 0, 0, 0);
        return Math.round((d - now) / 86400000);
    } catch { return null; }
};

export default function Disdette() {
    const [list, setList] = useState(null);
    const [stato, setStato] = useState("all");
    const [editing, setEditing] = useState(null);
    const [open, setOpen] = useState(false);
    const [seq, setSeq] = useState(0);

    const load = () => {
        const params = stato !== "all" ? { stato } : {};
        api.get("/disdette", { params }).then((r) => setList(r.data));
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [stato]);

    const kpi = useMemo(() => {
        const src = list || [];
        const daInv = src.filter((x) => x.stato === "da_inviare");
        return {
            n: src.length,
            da_inviare: daInv.length,
            in_scadenza: daInv.filter((x) => { const d = daysTo(x.data_scadenza); return d !== null && d <= 15; }).length,
            inviate: src.filter((x) => x.stato === "inviata" || x.stato === "confermata").length,
        };
    }, [list]);

    const del = async (id) => {
        if (!window.confirm("Eliminare la disdetta?")) return;
        await api.delete(`/disdette/${id}`); toast.success("Eliminata"); load();
    };
    const markEmessa = async (id) => {
        await api.post(`/disdette/${id}/collega-polizza`, {});
        toast.success("Polizza segnata come emessa — promemoria chiuso"); load();
    };

    return (
        <div data-testid="disdette-page" className="space-y-3">
            <PageHeader
                title={<span className="flex items-center gap-2"><TrendingDown className="text-rose-600" /> Disdette</span>}
                subtitle="Disdette da inviare alle altre compagnie · promemoria scadenza invio"
                actions={
                    <Dialog open={open} onOpenChange={setOpen}>
                        <DialogTrigger asChild>
                            <Button onClick={() => { setEditing(null); setSeq((s) => s + 1); }} className="bg-rose-700 hover:bg-rose-800" data-testid="dis-new">
                                <Plus size={14} className="mr-1" /> Nuova disdetta
                            </Button>
                        </DialogTrigger>
                        {open && <DisdettaDialog key={`${editing?.id || "new"}-${seq}`} editing={editing} onClose={() => { setOpen(false); setEditing(null); load(); }} />}
                    </Dialog>
                }
            />

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Card className="p-3 border-l-4 border-slate-400 bg-white">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">Totale</div>
                    <div className="text-2xl font-bold">{kpi.n}</div>
                </Card>
                <Card className="p-3 border-l-4 border-amber-400 bg-white">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">Da inviare</div>
                    <div className="text-2xl font-bold text-amber-700">{kpi.da_inviare}</div>
                </Card>
                <Card className="p-3 border-l-4 border-rose-500 bg-white" data-testid="dis-kpi-scadenza">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">In scadenza (≤15gg)</div>
                    <div className="text-2xl font-bold text-rose-700">{kpi.in_scadenza}</div>
                </Card>
                <Card className="p-3 border-l-4 border-emerald-400 bg-white">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">Inviate / Confermate</div>
                    <div className="text-2xl font-bold text-emerald-700">{kpi.inviate}</div>
                </Card>
            </div>

            <Card className="p-3 flex gap-2 items-center flex-wrap">
                <span className="text-xs text-slate-500 font-medium">Stato:</span>
                <button onClick={() => setStato("all")}
                    className={`text-xs px-2 py-1 rounded border ${stato === "all" ? "bg-rose-600 text-white border-rose-600" : "border-slate-300"}`}
                    data-testid="dis-f-all">Tutte</button>
                {STATI.map((s) => (
                    <button key={s.v} onClick={() => setStato(s.v)}
                        className={`text-xs px-2 py-1 rounded border ${stato === s.v ? "bg-rose-600 text-white border-rose-600" : "border-slate-300"}`}
                        data-testid={`dis-f-${s.v}`}>{s.l}</button>
                ))}
            </Card>

            <div className="tbl-scroll">
                {list === null ? <Loading /> : list.length === 0 ? <Empty message="Nessuna disdetta registrata" /> : (
                    <table className="tbl-compact w-full text-xs">
                        <thead><tr>
                            <th>Compagnia da disdire</th><th>Cliente</th><th>N. polizza</th><th>Ramo</th>
                            <th>Scadenza invio</th><th>Scad. polizza</th><th>Modalità</th><th>Stato</th><th className="w-20"></th>
                        </tr></thead>
                        <tbody>
                            {list.map((d) => {
                                const st = STATI.find((s) => s.v === d.stato) || STATI[0];
                                const dd = daysTo(d.data_scadenza);
                                const urgente = d.stato === "da_inviare" && dd !== null && dd <= 15;
                                const scaduta = d.stato === "da_inviare" && dd !== null && dd < 0;
                                return (
                                    <tr key={d.id} data-testid={`dis-row-${d.id}`}>
                                        <td className="font-medium">{d.compagnia_da_disdire}</td>
                                        <td>{d.anagrafica_nome || "—"}</td>
                                        <td className="num">{d.numero_polizza || "—"}</td>
                                        <td>{d.ramo || "—"}</td>
                                        <td className="num">
                                            {d.data_scadenza || "—"}
                                            {urgente && (
                                                <span className={`ml-1 inline-flex items-center gap-0.5 text-[10px] font-bold px-1 py-0.5 rounded ${scaduta ? "bg-rose-100 text-rose-700" : "bg-amber-100 text-amber-800"}`} data-testid={`dis-avviso-${d.id}`}>
                                                    <AlertTriangle size={9} /> {scaduta ? "scaduta" : `${dd}gg`}
                                                </span>
                                            )}
                                        </td>
                                        <td className="num">{d.data_scadenza_polizza || "—"}</td>
                                        <td className="uppercase">{d.modalita_invio || "—"}</td>
                                        <td><span className={`badge ${badgeClass(st.color)}`}>{st.l}</span></td>
                                        <td className="text-right space-x-1">
                                            {d.polizza_emessa ? (
                                                <span className="inline-flex items-center gap-0.5 text-[10px] font-bold px-1 py-0.5 rounded bg-emerald-100 text-emerald-700" title={d.polizza_nuova_numero ? `Polizza sostitutiva: ${d.polizza_nuova_numero}` : "Nuova polizza emessa"} data-testid={`dis-emessa-${d.id}`}>
                                                    <CheckCircle2 size={10} /> emessa
                                                </span>
                                            ) : (
                                                <button onClick={() => markEmessa(d.id)} className="text-emerald-700 hover:bg-emerald-50 p-1 rounded" title="Segna nuova polizza emessa (chiude il promemoria)" data-testid={`dis-emessa-btn-${d.id}`}>
                                                    <CheckCircle2 size={11} />
                                                </button>
                                            )}
                                            <button onClick={() => { setEditing(d); setSeq((s) => s + 1); setOpen(true); }}
                                                className="text-sky-700 hover:bg-sky-50 p-1 rounded" data-testid={`dis-edit-${d.id}`}>
                                                <Edit size={11} />
                                            </button>
                                            <button onClick={() => del(d.id)} className="text-rose-600 hover:bg-rose-50 p-1 rounded" data-testid={`dis-del-${d.id}`}>
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

function DisdettaDialog({ editing, onClose }) {
    const [anagrafiche, setAnagrafiche] = useState([]);
    const [polizze, setPolizze] = useState([]);
    const [rubrica, setRubrica] = useState([]);
    const [rubricaOpen, setRubricaOpen] = useState(false);
    const [f, setF] = useState(editing || {
        anagrafica_id: "", compagnia_da_disdire: "", polizza_id: "", numero_polizza: "",
        ramo: "", data_scadenza: "", data_scadenza_polizza: "", data_invio: "", modalita_invio: "pec",
        stato: "da_inviare", note: "", polizza_emessa: false,
        destinatario_id: "", destinatario_nome: "", destinatario_indirizzo: "", destinatario_pec: "",
    });
    const loadRubrica = () => api.get("/disdette-destinatari").then((r) => setRubrica(r.data || []));
    useEffect(() => { api.get("/anagrafiche?limit=2000").then((r) => setAnagrafiche(r.data)); loadRubrica(); }, []);
    useEffect(() => {
        if (f.anagrafica_id) {
            api.get("/polizze", { params: { contraente_id: f.anagrafica_id, limit: 500 } })
                .then((r) => setPolizze(Array.isArray(r.data) ? r.data : (r.data?.items || [])))
                .catch(() => setPolizze([]));
        } else setPolizze([]);
    }, [f.anagrafica_id]);
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
    const pickDestinatario = (rid) => {
        if (rid === "__none__") { setF((p) => ({ ...p, destinatario_id: "", destinatario_nome: "", destinatario_indirizzo: "", destinatario_pec: "" })); return; }
        const r = rubrica.find((x) => x.id === rid);
        if (r) setF((p) => ({ ...p, destinatario_id: r.id, destinatario_nome: r.nome || "", destinatario_indirizzo: r.indirizzo || "", destinatario_pec: r.pec || "" }));
    };
    const save = async () => {
        if (!f.compagnia_da_disdire) { toast.error("Compagnia da disdire obbligatoria"); return; }
        try {
            if (editing?.id) await api.put(`/disdette/${editing.id}`, f);
            else await api.post("/disdette", f);
            toast.success("Salvata"); onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };
    return (
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader><DialogTitle>{editing?.id ? "Modifica disdetta" : "Nuova disdetta"}</DialogTitle></DialogHeader>
            <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2">
                    <Label className="text-xs">Compagnia da disdire *</Label>
                    <Input value={f.compagnia_da_disdire} onChange={(e) => set("compagnia_da_disdire", e.target.value)}
                        placeholder="es. UnipolSai, Allianz, Generali…" data-testid="dis-compagnia" />
                </div>

                {/* ---- Destinatario (agenzia/assicurazione) ---- */}
                <div className="col-span-2 border border-slate-200 rounded-md p-3 bg-slate-50/60">
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-[11px] uppercase tracking-wide font-semibold text-slate-600 flex items-center gap-1"><BookUser size={13} /> Destinatario disdetta</span>
                        <Button type="button" variant="outline" size="sm" className="h-7 text-xs" onClick={() => setRubricaOpen(true)} data-testid="dis-gestisci-rubrica">
                            <BookUser size={12} className="mr-1" /> Gestisci rubrica
                        </Button>
                    </div>
                    <div className="mb-2">
                        <Label className="text-xs">Scegli dalla rubrica</Label>
                        <Select value={f.destinatario_id || "__none__"} onValueChange={pickDestinatario}>
                            <SelectTrigger data-testid="dis-rubrica-select"><SelectValue placeholder="— seleziona —" /></SelectTrigger>
                            <SelectContent className="max-h-80">
                                <SelectItem value="__none__">— nessuno —</SelectItem>
                                {rubrica.map((r) => <SelectItem key={r.id} value={r.id}>{r.nome}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                        <div className="col-span-2"><Label className="text-xs">Nome assicurazione / agenzia</Label>
                            <Input value={f.destinatario_nome || ""} onChange={(e) => set("destinatario_nome", e.target.value)} data-testid="dis-dest-nome" /></div>
                        <div className="col-span-2"><Label className="text-xs">Indirizzo</Label>
                            <Input value={f.destinatario_indirizzo || ""} onChange={(e) => set("destinatario_indirizzo", e.target.value)} data-testid="dis-dest-indirizzo" /></div>
                        <div className="col-span-2"><Label className="text-xs">PEC destinatario</Label>
                            <Input value={f.destinatario_pec || ""} onChange={(e) => set("destinatario_pec", e.target.value)} placeholder="pec@esempio.it" data-testid="dis-dest-pec" /></div>
                    </div>
                </div>

                <div className="col-span-2">
                    <Label className="text-xs">Cliente</Label>
                    <Select value={f.anagrafica_id || "__none__"} onValueChange={(v) => set("anagrafica_id", v === "__none__" ? "" : v)}>
                        <SelectTrigger data-testid="dis-cliente"><SelectValue placeholder="— nessuno —" /></SelectTrigger>
                        <SelectContent className="max-h-80">
                            <SelectItem value="__none__">— nessuno —</SelectItem>
                            {anagrafiche.map((a) => (
                                <SelectItem key={a.id} value={a.id}>{a.ragione_sociale || `${a.cognome || ""} ${a.nome || ""}`}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
                <div>
                    <Label className="text-xs">Polizza collegata</Label>
                    <Select value={f.polizza_id || "__none__"} onValueChange={(v) => {
                        if (v === "__none__") { set("polizza_id", ""); return; }
                        const p = polizze.find((x) => x.id === v);
                        setF((prev) => ({ ...prev, polizza_id: v, numero_polizza: p?.numero_polizza || prev.numero_polizza, ramo: p?.ramo || prev.ramo, data_scadenza_polizza: p?.scadenza || p?.data_scadenza || prev.data_scadenza_polizza }));
                    }}>
                        <SelectTrigger data-testid="dis-polizza"><SelectValue placeholder="— nessuna —" /></SelectTrigger>
                        <SelectContent className="max-h-80">
                            <SelectItem value="__none__">— nessuna —</SelectItem>
                            {polizze.map((p) => <SelectItem key={p.id} value={p.id}>{p.numero_polizza} · {p.ramo || ""}</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
                <div><Label className="text-xs">N. polizza</Label>
                    <Input value={f.numero_polizza || ""} onChange={(e) => set("numero_polizza", e.target.value)} /></div>
                <div><Label className="text-xs">Ramo</Label>
                    <Input value={f.ramo || ""} onChange={(e) => set("ramo", e.target.value)} placeholder="RCAUTO / CASA…" /></div>
                <div><Label className="text-xs">Stato</Label>
                    <Select value={f.stato} onValueChange={(v) => set("stato", v)}>
                        <SelectTrigger data-testid="dis-stato"><SelectValue /></SelectTrigger>
                        <SelectContent>{STATI.map((s) => <SelectItem key={s.v} value={s.v}>{s.l}</SelectItem>)}</SelectContent>
                    </Select>
                </div>
                <div>
                    <Label className="text-xs flex items-center gap-1"><AlertTriangle size={11} className="text-amber-500" /> Scadenza invio (promemoria)</Label>
                    <Input type="date" value={f.data_scadenza || ""} onChange={(e) => set("data_scadenza", e.target.value)} data-testid="dis-scadenza" />
                </div>
                <div>
                    <Label className="text-xs flex items-center gap-1"><AlertTriangle size={11} className="text-rose-500" /> Scadenza polizza</Label>
                    <Input type="date" value={f.data_scadenza_polizza || ""} onChange={(e) => set("data_scadenza_polizza", e.target.value)} data-testid="dis-scadenza-polizza" />
                </div>
                <div><Label className="text-xs">Data invio effettivo</Label>
                    <Input type="date" value={f.data_invio || ""} onChange={(e) => set("data_invio", e.target.value)} /></div>
                <div>
                    <Label className="text-xs">Modalità invio</Label>
                    <Select value={f.modalita_invio || "pec"} onValueChange={(v) => set("modalita_invio", v)}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="pec">PEC</SelectItem>
                            <SelectItem value="raccomandata">Raccomandata A/R</SelectItem>
                            <SelectItem value="email">Email</SelectItem>
                            <SelectItem value="fax">Fax</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
                <div className="col-span-2 border border-slate-200 rounded-md p-3 bg-emerald-50/40">
                    <div className="text-[11px] uppercase tracking-wide font-semibold text-slate-600 flex items-center gap-1 mb-2"><CheckCircle2 size={13} className="text-emerald-600" /> Polizza sostitutiva emessa</div>
                    <div className="grid grid-cols-2 gap-2">
                        <div>
                            <Label className="text-xs">Collega polizza del cliente</Label>
                            <Select value={f.polizza_nuova_id || "__none__"} onValueChange={(v) => {
                                if (v === "__none__") { setF((p) => ({ ...p, polizza_nuova_id: "", polizza_nuova_numero: "" })); return; }
                                const p = polizze.find((x) => x.id === v);
                                setF((prev) => ({ ...prev, polizza_nuova_id: v, polizza_nuova_numero: p?.numero_polizza || "", polizza_emessa: true }));
                            }}>
                                <SelectTrigger data-testid="dis-polizza-nuova"><SelectValue placeholder={f.anagrafica_id ? "— scegli —" : "seleziona prima il cliente"} /></SelectTrigger>
                                <SelectContent className="max-h-80">
                                    <SelectItem value="__none__">— nessuna —</SelectItem>
                                    {polizze.map((p) => <SelectItem key={p.id} value={p.id}>{p.numero_polizza} · {p.ramo || ""}</SelectItem>)}
                                </SelectContent>
                            </Select>
                        </div>
                        <div><Label className="text-xs">Oppure n. polizza</Label>
                            <Input value={f.polizza_nuova_numero || ""} onChange={(e) => set("polizza_nuova_numero", e.target.value)} placeholder="numero polizza" data-testid="dis-polizza-nuova-num" /></div>
                    </div>
                    <label className="flex items-center gap-2 text-xs text-slate-700 mt-2 cursor-pointer" data-testid="dis-polizza-emessa">
                        <input type="checkbox" checked={!!f.polizza_emessa} onChange={(e) => set("polizza_emessa", e.target.checked)} />
                        Nuova polizza emessa (chiude il promemoria di emissione)
                    </label>
                </div>
                <div className="col-span-2"><Label className="text-xs">Note</Label>
                    <Textarea rows={2} value={f.note || ""} onChange={(e) => set("note", e.target.value)} /></div>

                {/* ---- Allegati + PDF (solo su disdetta esistente) ---- */}
                {editing?.id && (
                    <div className="col-span-2 border-t border-slate-200 pt-3 mt-1">
                        <div className="flex items-center justify-between mb-2">
                            <span className="text-[11px] uppercase tracking-wide font-semibold text-slate-600 flex items-center gap-1"><Paperclip size={13} /> Allegati & modulo</span>
                            <a href={imgUrl(`${API_BASE}/disdette/${editing.id}/pdf`)} target="_blank" rel="noreferrer" data-testid="dis-pdf-link">
                                <Button type="button" variant="outline" size="sm" className="h-7 text-xs"><FileText size={12} className="mr-1" /> Scarica PDF disdetta</Button>
                            </a>
                        </div>
                        <AllegatiDisdetta disdettaId={editing.id} />
                    </div>
                )}
            </div>
            <DialogFooter>
                <Button onClick={save} className="bg-rose-700 hover:bg-rose-800" data-testid="dis-save">
                    {editing?.id ? <><Edit size={14} className="mr-1" /> Aggiorna</> : <><Send size={14} className="mr-1" /> Crea</>}
                </Button>
            </DialogFooter>

            <Dialog open={rubricaOpen} onOpenChange={setRubricaOpen}>
                <RubricaManager rubrica={rubrica} onChanged={loadRubrica} />
            </Dialog>
        </DialogContent>
    );
}

function AllegatiDisdetta({ disdettaId }) {
    const [items, setItems] = useState(null);
    const [busy, setBusy] = useState(false);
    const load = () => api.get("/allegati", { params: { entita_tipo: "disdetta", entita_id: disdettaId } })
        .then((r) => setItems(r.data || [])).catch(() => setItems([]));
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [disdettaId]);
    const upload = async (file) => {
        if (!file) return;
        setBusy(true);
        const fd = new FormData(); fd.append("file", file);
        try {
            await api.post(`/allegati?entita_tipo=disdetta&entita_id=${disdettaId}`, fd, { headers: { "Content-Type": "multipart/form-data" } });
            toast.success("Allegato caricato"); load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore upload"); }
        finally { setBusy(false); }
    };
    const del = async (id) => { await api.delete(`/allegati/${id}`); toast.success("Rimosso"); load(); };
    return (
        <div>
            <label className="inline-flex items-center gap-2 text-xs text-sky-700 border border-dashed border-sky-300 rounded px-3 py-2 cursor-pointer hover:bg-sky-50" data-testid="dis-upload">
                <Upload size={13} /> {busy ? "Caricamento…" : "Carica documento"}
                <input type="file" hidden disabled={busy} onChange={(e) => upload(e.target.files?.[0])} />
            </label>
            <div className="mt-2 space-y-1">
                {items === null ? <span className="text-xs text-slate-400">…</span>
                    : items.length === 0 ? <span className="text-xs text-slate-400">Nessun allegato</span>
                        : items.map((a) => (
                            <div key={a.id} className="flex items-center justify-between text-xs border border-slate-200 rounded px-2 py-1" data-testid={`dis-alleg-${a.id}`}>
                                <a href={imgUrl(`${API_BASE}/allegati/${a.id}/download`)} target="_blank" rel="noreferrer" className="text-sky-700 hover:underline flex items-center gap-1 truncate">
                                    <Download size={11} /> {a.nome_file}
                                </a>
                                <button onClick={() => del(a.id)} className="text-rose-600 hover:bg-rose-50 p-1 rounded" data-testid={`dis-alleg-del-${a.id}`}><Trash2 size={11} /></button>
                            </div>
                        ))}
            </div>
        </div>
    );
}

function RubricaManager({ rubrica, onChanged }) {
    const empty = { nome: "", indirizzo: "", pec: "", email: "", note: "" };
    const [form, setForm] = useState(empty);
    const [editId, setEditId] = useState(null);
    const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));
    const save = async () => {
        if (!form.nome.trim()) { toast.error("Nome obbligatorio"); return; }
        try {
            if (editId) await api.put(`/disdette-destinatari/${editId}`, form);
            else await api.post("/disdette-destinatari", form);
            toast.success("Salvato"); setForm(empty); setEditId(null); onChanged();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };
    const edit = (r) => { setEditId(r.id); setForm({ nome: r.nome || "", indirizzo: r.indirizzo || "", pec: r.pec || "", email: r.email || "", note: r.note || "" }); };
    const del = async (id) => { if (!window.confirm("Eliminare la voce?")) return; await api.delete(`/disdette-destinatari/${id}`); toast.success("Eliminata"); if (editId === id) { setEditId(null); setForm(empty); } onChanged(); };
    return (
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto" data-testid="dis-rubrica-dialog">
            <DialogHeader><DialogTitle className="flex items-center gap-2"><BookUser size={18} /> Rubrica destinatari</DialogTitle></DialogHeader>
            <div className="space-y-2">
                <Input placeholder="Nome assicurazione / agenzia *" value={form.nome} onChange={(e) => set("nome", e.target.value)} data-testid="rub-nome" />
                <Input placeholder="Indirizzo" value={form.indirizzo} onChange={(e) => set("indirizzo", e.target.value)} data-testid="rub-indirizzo" />
                <Input placeholder="PEC" value={form.pec} onChange={(e) => set("pec", e.target.value)} data-testid="rub-pec" />
                <Input placeholder="Email (facoltativa)" value={form.email} onChange={(e) => set("email", e.target.value)} />
                <div className="flex gap-2">
                    <Button onClick={save} size="sm" className="bg-rose-700 hover:bg-rose-800" data-testid="rub-save">{editId ? "Aggiorna" : "Aggiungi"}</Button>
                    {editId && <Button onClick={() => { setEditId(null); setForm(empty); }} size="sm" variant="outline">Annulla</Button>}
                </div>
            </div>
            <div className="mt-3 border-t pt-2 space-y-1">
                {(rubrica || []).length === 0 ? <span className="text-xs text-slate-400">Rubrica vuota</span>
                    : rubrica.map((r) => (
                        <div key={r.id} className="flex items-center justify-between text-xs border border-slate-200 rounded px-2 py-1" data-testid={`rub-row-${r.id}`}>
                            <div className="truncate"><span className="font-medium">{r.nome}</span>{r.pec ? <span className="text-slate-400"> · {r.pec}</span> : null}</div>
                            <div className="flex gap-1 shrink-0">
                                <button onClick={() => edit(r)} className="text-sky-700 hover:bg-sky-50 p-1 rounded" data-testid={`rub-edit-${r.id}`}><Edit size={11} /></button>
                                <button onClick={() => del(r.id)} className="text-rose-600 hover:bg-rose-50 p-1 rounded" data-testid={`rub-del-${r.id}`}><Trash2 size={11} /></button>
                            </div>
                        </div>
                    ))}
            </div>
        </DialogContent>
    );
}
