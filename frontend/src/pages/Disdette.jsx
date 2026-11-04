/**
 * Disdette — registro delle disdette da inviare alle altre compagnie,
 * con avviso/promemoria di scadenza (termine ultimo per l'invio).
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { Plus, Edit, Trash2, TrendingDown, AlertTriangle, Send } from "lucide-react";
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

    return (
        <div data-testid="disdette-page" className="space-y-3">
            <PageHeader
                title={<span className="flex items-center gap-2"><TrendingDown className="text-rose-600" /> Disdette</span>}
                subtitle="Disdette da inviare alle altre compagnie · promemoria scadenza invio"
                actions={
                    <Dialog open={open} onOpenChange={setOpen}>
                        <DialogTrigger asChild>
                            <Button onClick={() => setEditing(null)} className="bg-rose-700 hover:bg-rose-800" data-testid="dis-new">
                                <Plus size={14} className="mr-1" /> Nuova disdetta
                            </Button>
                        </DialogTrigger>
                        <DisdettaDialog editing={editing} onClose={() => { setOpen(false); setEditing(null); load(); }} />
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
                            <th>Scadenza invio</th><th>Modalità</th><th>Stato</th><th className="w-20"></th>
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
                                        <td className="uppercase">{d.modalita_invio || "—"}</td>
                                        <td><span className={`badge ${badgeClass(st.color)}`}>{st.l}</span></td>
                                        <td className="text-right space-x-1">
                                            <button onClick={() => { setEditing(d); setOpen(true); }}
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
    const [f, setF] = useState(editing || {
        anagrafica_id: "", compagnia_da_disdire: "", polizza_id: "", numero_polizza: "",
        ramo: "", data_scadenza: "", data_invio: "", modalita_invio: "pec",
        stato: "da_inviare", note: "",
    });
    useEffect(() => { api.get("/anagrafiche?limit=2000").then((r) => setAnagrafiche(r.data)); }, []);
    useEffect(() => {
        if (f.anagrafica_id) {
            api.get("/polizze", { params: { contraente_id: f.anagrafica_id, limit: 500 } })
                .then((r) => setPolizze(Array.isArray(r.data) ? r.data : (r.data?.items || [])))
                .catch(() => setPolizze([]));
        } else setPolizze([]);
    }, [f.anagrafica_id]);
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
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
                        setF((prev) => ({ ...prev, polizza_id: v, numero_polizza: p?.numero_polizza || prev.numero_polizza, ramo: p?.ramo || prev.ramo }));
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
                <div className="col-span-2"><Label className="text-xs">Note</Label>
                    <Textarea rows={2} value={f.note || ""} onChange={(e) => set("note", e.target.value)} /></div>
            </div>
            <DialogFooter>
                <Button onClick={save} className="bg-rose-700 hover:bg-rose-800" data-testid="dis-save">
                    {editing?.id ? <><Edit size={14} className="mr-1" /> Aggiorna</> : <><Send size={14} className="mr-1" /> Crea</>}
                </Button>
            </DialogFooter>
        </DialogContent>
    );
}
