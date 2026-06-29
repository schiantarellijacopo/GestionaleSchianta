/**
 * Agenzie — libreria delle agenzie partner. Si definisce qui l'agenzia
 * principale dello studio + le agenzie con cui collaboriamo (mandato indiretto).
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { PageHeader, Empty, Loading } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger,
} from "@/components/ui/dialog";
import { Plus, Building2, Edit, Trash2, Crown, Handshake, Link2 } from "lucide-react";
import { toast } from "sonner";

export default function Agenzie() {
    const [list, setList] = useState(null);
    const [open, setOpen] = useState(false);
    const [editing, setEditing] = useState(null);

    const load = () => api.get("/agenzie").then((r) => setList(r.data));
    useEffect(() => { load(); }, []);

    const del = async (a) => {
        if (!window.confirm(`Eliminare agenzia ${a.ragione_sociale}?`)) return;
        try { await api.delete(`/agenzie/${a.id}`); toast.success("Eliminata"); load(); }
        catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const principale = (list || []).find((a) => a.tipo === "principale");
    const partner = (list || []).filter((a) => a.tipo === "partner");

    return (
        <div data-testid="agenzie-page" className="space-y-5">
            <PageHeader
                title="Agenzie"
                subtitle="Agenzia principale e agenzie partner (collaborazioni con mandati indiretti)"
                actions={
                    <Dialog open={open} onOpenChange={(o) => { if (!o) setEditing(null); setOpen(o); }}>
                        <DialogTrigger asChild>
                            <Button onClick={() => setEditing(null)} className="bg-sky-700 hover:bg-sky-800" data-testid="age-new">
                                <Plus size={14} className="mr-1" /> Nuova agenzia
                            </Button>
                        </DialogTrigger>
                        <AgenziaDialog editing={editing} principaleExists={!!principale}
                            onClose={() => { setOpen(false); setEditing(null); load(); }} />
                    </Dialog>
                }
            />

            {list === null ? <Loading /> : (
                <>
                    {/* AGENZIA PRINCIPALE */}
                    <div>
                        <h2 className="text-sm font-semibold uppercase tracking-wider text-amber-700 mb-2 flex items-center gap-2">
                            <Crown size={16} /> Agenzia principale
                        </h2>
                        {!principale ? (
                            <Card className="p-4 border-dashed border-2 border-amber-200 bg-amber-50/30">
                                <div className="text-sm text-slate-500">
                                    Non hai ancora definito l'agenzia principale.
                                    <Button size="sm" variant="link" className="ml-1 px-0"
                                        onClick={() => { setEditing({ tipo: "principale" }); setOpen(true); }}
                                        data-testid="age-create-principale">
                                        Crea agenzia principale →
                                    </Button>
                                </div>
                            </Card>
                        ) : (
                            <AgenziaCard a={principale} onEdit={() => { setEditing(principale); setOpen(true); }}
                                onDelete={del} testid="age-principale" />
                        )}
                    </div>

                    {/* PARTNER */}
                    <div>
                        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-700 mb-2 flex items-center gap-2">
                            <Handshake size={16} /> Agenzie partner ({partner.length})
                        </h2>
                        {partner.length === 0 ? <Empty message="Nessuna agenzia partner. Aggiungine una per gestire i mandati di collaborazione." /> : (
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                                {partner.map((a) => (
                                    <AgenziaCard key={a.id} a={a}
                                        onEdit={() => { setEditing(a); setOpen(true); }}
                                        onDelete={del} testid={`age-partner-${a.id}`} />
                                ))}
                            </div>
                        )}
                    </div>
                </>
            )}
        </div>
    );
}

function AgenziaCard({ a, onEdit, onDelete, testid }) {
    const [collegaOpen, setCollegaOpen] = useState(false);
    return (
        <Card className={`p-4 ${a.tipo === "principale" ? "border-l-4 border-amber-400" : ""}`} data-testid={testid}>
            <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2 flex-1 min-w-0">
                    <div className={`w-10 h-10 rounded-md flex items-center justify-center
                        ${a.tipo === "principale" ? "bg-amber-50 text-amber-700" : "bg-slate-50 text-slate-700"}`}>
                        {a.tipo === "principale" ? <Crown size={18} /> : <Building2 size={18} />}
                    </div>
                    <div className="flex-1 min-w-0">
                        <div className="font-medium text-slate-900 truncate">{a.ragione_sociale}</div>
                        {a.codice && <div className="text-xs text-slate-400 font-mono">{a.codice}</div>}
                    </div>
                </div>
                <div className="flex gap-1">
                    <button onClick={onEdit} className="text-sky-700 hover:bg-sky-50 p-1.5 rounded"><Edit size={13} /></button>
                    <button onClick={() => onDelete(a)} className="text-rose-600 hover:bg-rose-50 p-1.5 rounded"><Trash2 size={13} /></button>
                </div>
            </div>
            <div className="mt-2 text-xs text-slate-600 space-y-0.5">
                {a.referente && <div>Referente: <span className="font-medium">{a.referente}</span></div>}
                {a.email && <div>{a.email}</div>}
                {a.telefono && <div className="font-mono">{a.telefono}</div>}
                {a.citta && <div>{a.citta} {a.provincia ? `(${a.provincia})` : ""}</div>}
                {a.partita_iva && <div>P.IVA: <span className="font-mono">{a.partita_iva}</span></div>}
                {a.perc_ritenuta_acconto > 0 && (
                    <div className="text-rose-700 font-medium">Ritenuta acconto: {a.perc_ritenuta_acconto}%</div>
                )}
            </div>
            {a.tipo === "partner" && (
                <div className="mt-2 pt-2 border-t border-slate-100 text-xs flex items-center justify-between">
                    <div>
                        <span className="text-slate-500">Compagnie collegate: </span>
                        <span className="font-bold text-sky-700">{a.n_compagnie_collegate || 0}</span>
                    </div>
                    <Button size="sm" variant="outline" onClick={() => setCollegaOpen(true)}
                        data-testid={`age-collega-${a.id}`}>
                        <Link2 size={11} className="mr-1" /> Collega compagnie
                    </Button>
                </div>
            )}
            {collegaOpen && <CollegaCompagnieDialog agenzia={a} onClose={() => setCollegaOpen(false)} />}
        </Card>
    );
}

function CollegaCompagnieDialog({ agenzia, onClose }) {
    const [comps, setComps] = useState(null);
    const [collegate, setCollegate] = useState(new Set());
    useEffect(() => {
        api.get("/compagnie").then((r) => {
            setComps(r.data);
            setCollegate(new Set((r.data || []).filter((c) => c.agenzia_partner_id === agenzia.id).map((c) => c.id)));
        });
    }, [agenzia.id]);

    const toggle = (id) => {
        setCollegate((p) => {
            const n = new Set(p);
            if (n.has(id)) n.delete(id);
            else n.add(id);
            return n;
        });
    };

    const save = async () => {
        try {
            for (const c of comps) {
                const wantLinked = collegate.has(c.id);
                const isLinked = c.agenzia_partner_id === agenzia.id;
                if (wantLinked && !isLinked) {
                    await api.put(`/compagnie/${c.id}`, { ...c, tipo_mandato: "collaborazione", agenzia_partner_id: agenzia.id });
                } else if (!wantLinked && isLinked) {
                    await api.put(`/compagnie/${c.id}`, { ...c, tipo_mandato: "diretto", agenzia_partner_id: null });
                }
            }
            toast.success("Collegamenti aggiornati"); onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-xl max-h-[80vh] overflow-y-auto">
                <DialogHeader><DialogTitle>Collega compagnie a {agenzia.ragione_sociale}</DialogTitle></DialogHeader>
                <div className="space-y-2 py-2">
                    <div className="text-xs text-slate-600 bg-amber-50 border border-amber-200 p-2 rounded">
                        Le compagnie selezionate diventano <strong>mandato di collaborazione</strong> via questa agenzia.
                        Le compagnie deselezionate tornano a mandato diretto.
                    </div>
                    {comps === null ? <Loading /> : (
                        <div className="grid grid-cols-1 gap-1 max-h-96 overflow-y-auto">
                            {comps.map((c) => (
                                <label key={c.id} className={`flex items-center gap-2 p-2 border rounded cursor-pointer text-sm
                                    ${collegate.has(c.id) ? "bg-sky-50 border-sky-400" : "border-slate-200"}`}>
                                    <Checkbox checked={collegate.has(c.id)} onCheckedChange={() => toggle(c.id)} />
                                    <div className="flex-1">
                                        <div className="font-medium">{c.ragione_sociale}</div>
                                        <div className="text-[10px] text-slate-400 font-mono">{c.codice}</div>
                                    </div>
                                    {c.agenzia_partner_id && c.agenzia_partner_id !== agenzia.id && (
                                        <span className="text-[10px] text-amber-700">⚠ già collegata ad altra agenzia</span>
                                    )}
                                </label>
                            ))}
                        </div>
                    )}
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Annulla</Button>
                    <Button onClick={save} className="bg-sky-700 hover:bg-sky-800" data-testid="age-collega-save">
                        Salva collegamenti ({collegate.size})
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function AgenziaDialog({ editing, principaleExists, onClose }) {
    const [f, setF] = useState(editing || {
        ragione_sociale: "", codice: "", tipo: "partner",
        referente: "", email: "", telefono: "", indirizzo: "", citta: "", provincia: "", cap: "",
        partita_iva: "", codice_fiscale: "", iban: "", note: "", attiva: true,
    });
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
    const save = async () => {
        if (!f.ragione_sociale.trim()) { toast.error("Ragione sociale obbligatoria"); return; }
        try {
            if (editing?.id) await api.put(`/agenzie/${editing.id}`, f);
            else await api.post("/agenzie", f);
            toast.success(editing?.id ? "Aggiornata" : "Creata"); onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };
    const canBePrincipale = !principaleExists || editing?.tipo === "principale";
    return (
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader><DialogTitle>{editing?.id ? "Modifica" : "Nuova"} agenzia</DialogTitle></DialogHeader>
            <div className="grid grid-cols-2 gap-3 py-2">
                <div className="col-span-2">
                    <Label>Tipo *</Label>
                    <Select value={f.tipo} onValueChange={(v) => set("tipo", v)}>
                        <SelectTrigger data-testid="age-tipo"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            {canBePrincipale && <SelectItem value="principale">Agenzia principale (la mia)</SelectItem>}
                            <SelectItem value="partner">Agenzia partner (collaborazione)</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
                <div className="col-span-2"><Label>Ragione sociale *</Label>
                    <Input value={f.ragione_sociale} onChange={(e) => set("ragione_sociale", e.target.value)} data-testid="age-rs" /></div>
                <div><Label>Codice</Label>
                    <Input value={f.codice || ""} onChange={(e) => set("codice", e.target.value.toUpperCase())} /></div>
                <div><Label>Referente</Label>
                    <Input value={f.referente || ""} onChange={(e) => set("referente", e.target.value)} /></div>
                <div><Label>Email</Label>
                    <Input value={f.email || ""} onChange={(e) => set("email", e.target.value)} /></div>
                <div><Label>Telefono</Label>
                    <Input value={f.telefono || ""} onChange={(e) => set("telefono", e.target.value)} /></div>
                <div><Label>Indirizzo</Label>
                    <Input value={f.indirizzo || ""} onChange={(e) => set("indirizzo", e.target.value)} /></div>
                <div><Label>CAP</Label>
                    <Input value={f.cap || ""} onChange={(e) => set("cap", e.target.value)} /></div>
                <div><Label>Città</Label>
                    <Input value={f.citta || ""} onChange={(e) => set("citta", e.target.value)} /></div>
                <div><Label>Provincia</Label>
                    <Input value={f.provincia || ""} onChange={(e) => set("provincia", e.target.value.toUpperCase())} maxLength={2} /></div>
                <div><Label>Partita IVA</Label>
                    <Input value={f.partita_iva || ""} onChange={(e) => set("partita_iva", e.target.value)} /></div>
                <div><Label>Codice fiscale</Label>
                    <Input value={f.codice_fiscale || ""} onChange={(e) => set("codice_fiscale", e.target.value.toUpperCase())} /></div>
                <div className="col-span-2"><Label>IBAN</Label>
                    <Input value={f.iban || ""} onChange={(e) => set("iban", e.target.value.toUpperCase())} /></div>
                <div className="col-span-2"><Label>Note</Label>
                    <Input value={f.note || ""} onChange={(e) => set("note", e.target.value)} /></div>
                <div className="col-span-2 flex items-center gap-2">
                    <Checkbox id="att" checked={!!f.attiva} onCheckedChange={(v) => set("attiva", !!v)} />
                    <Label htmlFor="att" className="text-xs">Attiva</Label>
                </div>
            </div>
            <DialogFooter>
                <Button onClick={save} className="bg-sky-700 hover:bg-sky-800" data-testid="age-save">
                    {editing?.id ? "Aggiorna" : "Crea"}
                </Button>
            </DialogFooter>
        </DialogContent>
    );
}
