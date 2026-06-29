import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { PageHeader, Empty, Loading } from "@/components/Shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
    Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import { Plus, Building2, Edit, Trash2, Link2 } from "lucide-react";
import { toast } from "sonner";

export default function Compagnie() {
    const [list, setList] = useState(null);
    const [agenzie, setAgenzie] = useState([]);
    const [open, setOpen] = useState(false);
    const [editing, setEditing] = useState(null);

    const load = () => api.get("/compagnie").then((r) => setList(r.data));
    useEffect(() => { load(); api.get("/agenzie").then((r) => setAgenzie(r.data)); }, []);

    const del = async (c) => {
        if (!window.confirm(`Eliminare compagnia ${c.ragione_sociale}?`)) return;
        try { await api.delete(`/compagnie/${c.id}`); toast.success("Eliminata"); load(); }
        catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <div data-testid="compagnie-page">
            <PageHeader
                title="Compagnie assicurative"
                subtitle="Anagrafica compagnie · tipo mandato · agenzia partner"
                actions={
                    <Dialog open={open} onOpenChange={(o) => { if (!o) setEditing(null); setOpen(o); }}>
                        <DialogTrigger asChild>
                            <Button onClick={() => setEditing(null)} data-testid="comp-new-button" className="bg-sky-700 hover:bg-sky-800">
                                <Plus size={16} className="mr-1" /> Nuova compagnia
                            </Button>
                        </DialogTrigger>
                        <CompagniaDialog editing={editing} agenzie={agenzie}
                            onClose={() => { setOpen(false); setEditing(null); load(); }} />
                    </Dialog>
                }
            />

            {list === null ? <Loading /> : list.length === 0 ? <Empty /> : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {list.map((c) => {
                        const isColl = c.tipo_mandato === "collaborazione";
                        const partner = agenzie.find((a) => a.id === c.agenzia_partner_id);
                        return (
                            <div key={c.id} className="bg-white border border-slate-200 rounded-md p-5 hover:shadow-md transition-shadow" data-testid={`comp-card-${c.id}`}>
                                <div className="flex items-center gap-3 mb-3">
                                    <div className={`w-10 h-10 rounded-md flex items-center justify-center ${isColl ? "bg-amber-50 text-amber-700" : "bg-sky-50 text-sky-700"}`}>
                                        <Building2 size={18} />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="font-medium text-slate-900 truncate">{c.ragione_sociale}</div>
                                        <div className="text-xs text-slate-500 num">Codice: {c.codice}</div>
                                    </div>
                                    <span className={`badge ${c.attiva ? "badge-success" : "badge-neutral"}`}>
                                        {c.attiva ? "attiva" : "inattiva"}
                                    </span>
                                </div>

                                {/* tipo mandato */}
                                <div className="flex items-center gap-2 mb-2">
                                    <span className={`text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded ${isColl ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800"}`}>
                                        {isColl ? "Mandato collaborazione" : "Mandato diretto"}
                                    </span>
                                    {isColl && partner && (
                                        <span className="text-xs text-slate-600 flex items-center gap-1">
                                            <Link2 size={11} className="text-amber-600" /> via <span className="font-semibold">{partner.ragione_sociale}</span>
                                        </span>
                                    )}
                                </div>

                                {c.referente && <div className="text-sm text-slate-700">Referente: <span className="font-medium">{c.referente}</span></div>}
                                {c.email && <div className="text-sm text-slate-600">{c.email}</div>}
                                {c.telefono && <div className="text-sm text-slate-600 num">{c.telefono}</div>}
                                {c.descrizione && <div className="text-xs text-slate-500 mt-2">{c.descrizione}</div>}

                                <div className="flex justify-end gap-1 mt-3 pt-3 border-t border-slate-100">
                                    <button onClick={() => { setEditing(c); setOpen(true); }}
                                        className="text-sky-700 hover:bg-sky-50 p-1.5 rounded" data-testid={`comp-edit-${c.id}`}>
                                        <Edit size={13} />
                                    </button>
                                    <button onClick={() => del(c)}
                                        className="text-rose-600 hover:bg-rose-50 p-1.5 rounded" data-testid={`comp-del-${c.id}`}>
                                        <Trash2 size={13} />
                                    </button>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

function CompagniaDialog({ editing, agenzie, onClose }) {
    const [f, setF] = useState(editing || {
        codice: "", ragione_sociale: "", referente: "",
        email: "", telefono: "", sito_web: "", descrizione: "", attiva: true,
        trattiene_provvigioni: true,
        tipo_mandato: "diretto",
        agenzia_partner_id: null,
    });
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
    const save = async () => {
        if (!f.codice || !f.ragione_sociale) { toast.error("Codice e ragione sociale obbligatori"); return; }
        if (f.tipo_mandato === "collaborazione" && !f.agenzia_partner_id) {
            toast.error("Per il mandato di collaborazione selezionare l'agenzia partner");
            return;
        }
        try {
            const payload = { ...f, agenzia_partner_id: f.tipo_mandato === "collaborazione" ? f.agenzia_partner_id : null };
            if (editing?.id) await api.put(`/compagnie/${editing.id}`, payload);
            else await api.post("/compagnie", payload);
            toast.success(editing?.id ? "Aggiornata" : "Creata"); onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const isColl = f.tipo_mandato === "collaborazione";
    return (
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader><DialogTitle>{editing?.id ? "Modifica" : "Nuova"} compagnia</DialogTitle></DialogHeader>
            <div className="space-y-3 py-2">
                <div className="grid grid-cols-2 gap-3">
                    <div><Label>Codice *</Label><Input data-testid="comp-codice-input" value={f.codice}
                        onChange={(e) => set("codice", e.target.value.toUpperCase())} /></div>
                    <div><Label>Ragione sociale *</Label><Input data-testid="comp-rs-input" value={f.ragione_sociale}
                        onChange={(e) => set("ragione_sociale", e.target.value)} /></div>
                </div>

                {/* SEZIONE MANDATO */}
                <div className="border-t pt-3 mt-3">
                    <h3 className="text-xs font-semibold text-slate-700 uppercase tracking-wider mb-2">
                        🔗 Tipo di mandato
                    </h3>
                    <div className="grid grid-cols-2 gap-3 mb-2">
                        <div>
                            <Label>Tipo mandato *</Label>
                            <Select value={f.tipo_mandato} onValueChange={(v) => set("tipo_mandato", v)}>
                                <SelectTrigger data-testid="comp-tipo-mandato"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="diretto">Mandato diretto</SelectItem>
                                    <SelectItem value="collaborazione">Mandato di collaborazione</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        {isColl && (
                            <div>
                                <Label>Agenzia partner *</Label>
                                <Select value={f.agenzia_partner_id || ""} onValueChange={(v) => set("agenzia_partner_id", v)}>
                                    <SelectTrigger data-testid="comp-agenzia-partner"><SelectValue placeholder="Seleziona agenzia" /></SelectTrigger>
                                    <SelectContent>
                                        {agenzie.filter((a) => a.tipo === "partner").map((a) => (
                                            <SelectItem key={a.id} value={a.id}>{a.ragione_sociale}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                        )}
                    </div>
                    <div className="text-[11px] text-slate-500 bg-slate-50 border border-slate-200 rounded p-2">
                        {isColl ? (
                            <>📍 <strong>Collaborazione</strong>: il mandato diretto con la compagnia è dell'agenzia
                                partner. Saldo cassa = <strong>premi interi</strong> (no detrazione provvigioni). Le nostre provvigioni le
                                fatturerà l'agenzia partner.</>
                        ) : (
                            <>📍 <strong>Diretto</strong>: rapporto diretto con la compagnia. Saldo cassa =
                                <strong> premi − provvigioni</strong> (se "tratteniamo le provvigioni"). Le ritenute compagnia sono in
                                negativo sulle provvigioni e vanno versate.</>
                        )}
                    </div>
                </div>

                {!isColl && (
                    <div className="flex items-center gap-2 mt-1">
                        <Checkbox id="trattiene" checked={!!f.trattiene_provvigioni}
                            onCheckedChange={(v) => set("trattiene_provvigioni", !!v)} />
                        <Label htmlFor="trattiene" className="text-xs cursor-pointer">
                            Tratteniamo le provvigioni dal premio (saldo = premio − provv.)
                        </Label>
                    </div>
                )}

                <div className="border-t pt-3 mt-3">
                    <h3 className="text-xs font-semibold text-slate-700 uppercase tracking-wider mb-2">Contatti</h3>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Referente</Label><Input value={f.referente || ""} onChange={(e) => set("referente", e.target.value)} /></div>
                        <div><Label>Sito web</Label><Input value={f.sito_web || ""} onChange={(e) => set("sito_web", e.target.value)} /></div>
                        <div><Label>Email</Label><Input value={f.email || ""} onChange={(e) => set("email", e.target.value)} /></div>
                        <div><Label>Telefono</Label><Input value={f.telefono || ""} onChange={(e) => set("telefono", e.target.value)} /></div>
                    </div>
                    <div className="mt-2"><Label>Descrizione</Label>
                        <Input value={f.descrizione || ""} onChange={(e) => set("descrizione", e.target.value)} /></div>
                    <div className="flex items-center gap-2 mt-2">
                        <Checkbox id="attiva" checked={!!f.attiva} onCheckedChange={(v) => set("attiva", !!v)} />
                        <Label htmlFor="attiva" className="text-xs cursor-pointer">Compagnia attiva</Label>
                    </div>
                </div>
            </div>
            <DialogFooter>
                <Button data-testid="comp-save-button" onClick={save} className="bg-sky-700 hover:bg-sky-800">
                    {editing?.id ? "Aggiorna" : "Crea compagnia"}
                </Button>
            </DialogFooter>
        </DialogContent>
    );
}
