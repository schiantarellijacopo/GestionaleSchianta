/**
 * KpiBar — componente riusabile per mostrare KPI personalizzabili.
 *
 * Usage:
 *   <KpiBar sezione="polizze" />
 *   <KpiBar sezione="titoli" />
 *   <KpiBar sezione="sinistri" />
 *   <KpiBar sezione="avvisi" />
 *   <KpiBar sezione="prima_nota" />
 *
 * Le KPI predefinite vengono caricate dal backend.
 * L'utente può aggiungere/rimuovere KPI custom tramite "Personalizza KPI".
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
    Select, SelectTrigger, SelectContent, SelectItem, SelectValue,
} from "@/components/ui/select";
import {
    Settings, Plus, Trash2, FileText, Clock, Replace, XCircle, AlertTriangle,
    Layers, CheckCircle, Pause, Receipt, Mail, MessageCircle, Smartphone,
    Users, Archive, TrendingUp, TrendingDown, Wallet, Star, Tag, Shield,
    Building, BarChart3,
} from "lucide-react";
import { toast } from "sonner";

const ICON_MAP = {
    FileText, Clock, Replace, XCircle, AlertTriangle, Layers, CheckCircle,
    Pause, Receipt, Mail, MessageCircle, Smartphone, Users, Archive,
    TrendingUp, TrendingDown, Wallet, Star, Tag, Shield, Building, BarChart3,
};

const COLOR_CLASSES = {
    sky: "border-sky-400 text-sky-700",
    emerald: "border-emerald-500 text-emerald-700",
    amber: "border-amber-500 text-amber-700",
    violet: "border-violet-500 text-violet-700",
    rose: "border-rose-500 text-rose-700",
    indigo: "border-indigo-500 text-indigo-700",
    slate: "border-slate-400 text-slate-700",
};

function KpiCard({ k }) {
    const Ic = ICON_MAP[k.icon] || Star;
    const cls = COLOR_CLASSES[k.color] || COLOR_CLASSES.sky;
    return (
        <Card
            className={`p-3 border-l-4 ${cls} bg-white relative overflow-hidden flex-1 min-w-[150px]`}
            data-testid={`kpi-${k.key}`}
        >
            <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                    <div className="text-[10px] uppercase tracking-wider font-medium text-slate-500 truncate">
                        {k.label}
                    </div>
                    <div className="text-2xl font-bold mt-0.5 text-slate-900">
                        {k.value ?? "—"}
                    </div>
                    {k.sub && (
                        <div className={`text-[11px] mt-0.5 font-medium ${cls.split(" ")[1] || ""}`}>
                            {k.sub}
                        </div>
                    )}
                </div>
                <Ic size={18} className={`${cls.split(" ")[1]} opacity-50 shrink-0`} />
            </div>
        </Card>
    );
}

export default function KpiBar({ sezione, title, description }) {
    const [data, setData] = useState(null);
    const [open, setOpen] = useState(false);

    const load = async () => {
        try {
            const r = await api.get(`/kpi/${sezione}/stats`);
            setData(r.data);
        } catch (e) {
            // silent: KPI section è informativa, no toast invasivo
        }
    };
    useEffect(() => { load(); }, [sezione]);

    if (!data) return null;
    const allKpi = [...(data.default || []), ...(data.custom || [])];

    return (
        <div className="mb-5" data-testid={`kpi-bar-${sezione}`}>
            {(title || description) && (
                <div className="mb-2">
                    {title && <h2 className="text-base font-semibold text-slate-800">{title}</h2>}
                    {description && <p className="text-xs text-slate-500">{description}</p>}
                </div>
            )}
            <div className="flex flex-wrap gap-2">
                {allKpi.map((k) => <KpiCard key={k.key} k={k} />)}
                <button
                    type="button"
                    onClick={() => setOpen(true)}
                    className="px-3 py-2 text-xs border border-dashed border-slate-300 rounded text-slate-500 hover:border-violet-400 hover:text-violet-700 hover:bg-violet-50 flex items-center gap-1.5 self-stretch"
                    data-testid={`kpi-customize-${sezione}`}
                >
                    <Settings size={12} />
                    Personalizza KPI
                </button>
            </div>
            {open && (
                <KpiCustomizeDialog
                    sezione={sezione}
                    customs={(data.custom || []).map((c) => ({
                        id: c.custom_id, label: c.label, color: c.color, icon: c.icon,
                    }))}
                    onClose={(reload) => { setOpen(false); if (reload) load(); }}
                />
            )}
        </div>
    );
}

const COLORS = ["sky", "emerald", "amber", "violet", "rose", "indigo"];
const ICONS = ["Star", "Tag", "Shield", "Building", "FileText", "BarChart3", "Layers"];
const FILTRO_KIND_BY_SEZIONE = {
    polizze: [
        { v: "tag", l: "Tag anagrafica" }, { v: "stato", l: "Stato polizza" },
        { v: "ramo", l: "Ramo" }, { v: "compagnia", l: "Compagnia" },
    ],
    titoli: [
        { v: "tag", l: "Tag anagrafica" }, { v: "stato", l: "Stato titolo" },
    ],
    sinistri: [
        { v: "stato", l: "Stato sinistro" }, { v: "compagnia", l: "Compagnia" },
    ],
    avvisi: [{ v: "stato", l: "Stato titolo" }],
    prima_nota: [{ v: "tag", l: "Tag" }],
};

function KpiCustomizeDialog({ sezione, customs, onClose }) {
    const [items, setItems] = useState(customs);
    const [adding, setAdding] = useState(false);
    const [form, setForm] = useState({
        label: "", color: "sky", icon: "Star", filtro_kind: "tag", filtro_params: {},
    });

    const remove = async (id) => {
        if (!window.confirm("Rimuovere questa KPI?")) return;
        try {
            await api.delete(`/kpi/custom/${id}`);
            setItems(items.filter((i) => i.id !== id));
            toast.success("KPI rimossa");
        } catch (e) { toast.error("Errore"); }
    };

    const save = async () => {
        if (!form.label.trim()) { toast.error("Etichetta obbligatoria"); return; }
        try {
            await api.post("/kpi/custom", {
                sezione, label: form.label, color: form.color, icon: form.icon,
                ordine: items.length, filtro_kind: form.filtro_kind,
                filtro_params: form.filtro_params,
            });
            toast.success("KPI creata");
            onClose(true);
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const kinds = FILTRO_KIND_BY_SEZIONE[sezione] || [{ v: "tag", l: "Tag" }];

    return (
        <Dialog open onOpenChange={(o) => !o && onClose(false)}>
            <DialogContent className="max-w-2xl" data-testid="kpi-customize-dialog">
                <DialogHeader>
                    <DialogTitle>Personalizza KPI · {sezione}</DialogTitle>
                </DialogHeader>
                <div className="space-y-3">
                    {/* Lista custom esistenti */}
                    {items.length > 0 && (
                        <div className="space-y-1.5">
                            <Label className="text-xs uppercase tracking-wide text-slate-500">KPI custom esistenti</Label>
                            {items.map((c) => {
                                const Ic = ICON_MAP[c.icon] || Star;
                                return (
                                    <div key={c.id} className="flex items-center justify-between p-2 bg-slate-50 border border-slate-200 rounded">
                                        <div className="flex items-center gap-2">
                                            <Ic size={14} className={`text-${c.color}-600`} />
                                            <span className="text-sm">{c.label}</span>
                                            <span className="text-[10px] text-slate-400">({c.color})</span>
                                        </div>
                                        <button onClick={() => remove(c.id)} className="text-rose-500 hover:bg-rose-50 p-1 rounded">
                                            <Trash2 size={12} />
                                        </button>
                                    </div>
                                );
                            })}
                        </div>
                    )}

                    {/* Form aggiunta */}
                    {!adding && (
                        <Button onClick={() => setAdding(true)} variant="outline" className="w-full" data-testid="kpi-add-new">
                            <Plus size={14} className="mr-1" /> Aggiungi nuova KPI
                        </Button>
                    )}

                    {adding && (
                        <div className="border border-violet-200 bg-violet-50/40 rounded p-3 space-y-2">
                            <div>
                                <Label>Etichetta *</Label>
                                <Input value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })}
                                    placeholder="es. RC Auto privati" data-testid="kpi-label" />
                            </div>
                            <div className="grid grid-cols-3 gap-2">
                                <div>
                                    <Label>Colore</Label>
                                    <Select value={form.color} onValueChange={(v) => setForm({ ...form, color: v })}>
                                        <SelectTrigger><SelectValue /></SelectTrigger>
                                        <SelectContent>
                                            {COLORS.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                                        </SelectContent>
                                    </Select>
                                </div>
                                <div>
                                    <Label>Icona</Label>
                                    <Select value={form.icon} onValueChange={(v) => setForm({ ...form, icon: v })}>
                                        <SelectTrigger><SelectValue /></SelectTrigger>
                                        <SelectContent>
                                            {ICONS.map((i) => <SelectItem key={i} value={i}>{i}</SelectItem>)}
                                        </SelectContent>
                                    </Select>
                                </div>
                                <div>
                                    <Label>Filtra per</Label>
                                    <Select value={form.filtro_kind} onValueChange={(v) => setForm({ ...form, filtro_kind: v, filtro_params: {} })}>
                                        <SelectTrigger><SelectValue /></SelectTrigger>
                                        <SelectContent>
                                            {kinds.map((k) => <SelectItem key={k.v} value={k.v}>{k.l}</SelectItem>)}
                                        </SelectContent>
                                    </Select>
                                </div>
                            </div>
                            <div>
                                <Label>Valore filtro *</Label>
                                <Input
                                    placeholder={
                                        form.filtro_kind === "tag" ? "es. RC_AUTO, AGRICOLO…"
                                        : form.filtro_kind === "stato" ? "es. attiva, scaduto, aperto…"
                                        : form.filtro_kind === "ramo" ? "es. RCAUTO, INFORTUNI…"
                                        : "valore"
                                    }
                                    value={form.filtro_params[form.filtro_kind] || ""}
                                    onChange={(e) => setForm({
                                        ...form,
                                        filtro_params: { [form.filtro_kind]: e.target.value },
                                    })}
                                    data-testid="kpi-filter-value"
                                />
                            </div>
                            <div className="flex justify-end gap-1.5">
                                <Button variant="outline" size="sm" onClick={() => setAdding(false)}>Annulla</Button>
                                <Button size="sm" onClick={save} className="bg-violet-700 hover:bg-violet-800" data-testid="kpi-save">
                                    Salva KPI
                                </Button>
                            </div>
                        </div>
                    )}
                </div>
                <DialogFooter>
                    <Button onClick={() => onClose(false)}>Chiudi</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
