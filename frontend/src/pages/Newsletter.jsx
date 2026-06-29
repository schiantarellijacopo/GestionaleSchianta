/**
 * Newsletter — campagne email/sms/whatsapp a liste segmentate di clienti.
 * MVP: CRUD bozze + invio massivo simulato (logga su Diario cliente).
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Plus, Mail, Send, Trash2, Edit, Users } from "lucide-react";
import { toast } from "sonner";

const CANALI = [
    { v: "email", l: "📧 Email", color: "sky" },
    { v: "sms", l: "📱 SMS", color: "amber" },
    { v: "whatsapp", l: "💬 WhatsApp", color: "emerald" },
];

export default function Newsletter() {
    const [items, setItems] = useState(null);
    const [open, setOpen] = useState(false);
    const [editing, setEditing] = useState(null);
    const load = () => api.get("/newsletter").then((r) => setItems(r.data));
    useEffect(() => { load(); }, []);
    const invia = async (nl) => {
        if (!window.confirm(`Inviare la newsletter "${nl.nome}" a ${nl.destinatari_calcolati || 0} clienti?`)) return;
        try {
            const r = await api.post(`/newsletter/${nl.id}/invia`);
            toast.success(`Inviata a ${r.data.destinatari} destinatari`); load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };
    const del = async (id) => {
        if (!window.confirm("Eliminare?")) return;
        await api.delete(`/newsletter/${id}`); toast.success("Eliminata"); load();
    };
    return (
        <div data-testid="newsletter-page" className="space-y-3">
            <PageHeader
                title={<span className="flex items-center gap-2"><Mail className="text-sky-600" /> Newsletter</span>}
                subtitle="Campagne di marketing massive · email · sms · whatsapp"
                actions={
                    <Dialog open={open} onOpenChange={setOpen}>
                        <DialogTrigger asChild>
                            <Button onClick={() => setEditing(null)} className="bg-sky-700 hover:bg-sky-800" data-testid="nl-new">
                                <Plus size={14} className="mr-1" /> Nuova campagna
                            </Button>
                        </DialogTrigger>
                        <NewsletterDialog editing={editing} onClose={() => { setOpen(false); setEditing(null); load(); }} />
                    </Dialog>
                }
            />
            {items === null ? <Loading /> : items.length === 0 ? <Empty /> : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {items.map((nl) => {
                        const c = CANALI.find((x) => x.v === nl.canale) || CANALI[0];
                        return (
                            <Card key={nl.id} className="p-4" data-testid={`nl-${nl.id}`}>
                                <div className="flex items-start justify-between mb-2">
                                    <div>
                                        <h3 className="font-semibold text-slate-800">{nl.nome}</h3>
                                        <div className="text-xs text-slate-500">{nl.oggetto}</div>
                                    </div>
                                    <span className={`text-[10px] px-2 py-0.5 rounded font-bold bg-${c.color}-100 text-${c.color}-700`}>
                                        {c.l}
                                    </span>
                                </div>
                                <div className="text-xs text-slate-600 mt-2 flex items-center gap-3">
                                    <span><Users size={11} className="inline mr-1" />{nl.destinatari_calcolati || 0} destinatari</span>
                                    {nl.stato === "inviata"
                                        ? <span className="text-emerald-700 font-semibold">✓ Inviata ({nl.destinatari_inviati})</span>
                                        : <span className="text-amber-700">⏳ Bozza</span>}
                                </div>
                                <div className="mt-3 flex gap-2">
                                    {nl.stato !== "inviata" && (
                                        <Button size="sm" onClick={() => invia(nl)} className="bg-emerald-700 hover:bg-emerald-800" data-testid={`nl-send-${nl.id}`}>
                                            <Send size={12} className="mr-1" /> Invia
                                        </Button>
                                    )}
                                    <Button size="sm" variant="outline" onClick={() => { setEditing(nl); setOpen(true); }} data-testid={`nl-edit-${nl.id}`}>
                                        <Edit size={12} className="mr-1" /> Modifica
                                    </Button>
                                    <Button size="sm" variant="outline" onClick={() => del(nl.id)} className="text-rose-600">
                                        <Trash2 size={12} />
                                    </Button>
                                </div>
                            </Card>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

function NewsletterDialog({ editing, onClose }) {
    const [f, setF] = useState(editing || {
        nome: "", oggetto: "", contenuto: "", canale: "email",
        target_filtro: {}, stato: "bozza",
    });
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
    const setTarget = (k, v) => setF((p) => ({ ...p, target_filtro: { ...(p.target_filtro || {}), [k]: v } }));
    const save = async () => {
        if (!f.nome || !f.oggetto || !f.contenuto) { toast.error("Compila i campi obbligatori"); return; }
        try {
            if (editing?.id) await api.put(`/newsletter/${editing.id}`, f);
            else await api.post("/newsletter", f);
            toast.success("Salvata"); onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };
    return (
        <DialogContent className="max-w-2xl">
            <DialogHeader><DialogTitle>{editing?.id ? "Modifica" : "Nuova"} newsletter</DialogTitle></DialogHeader>
            <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                    <div className="col-span-2"><Label className="text-xs">Nome interno *</Label>
                        <Input value={f.nome} onChange={(e) => set("nome", e.target.value)} data-testid="nl-nome" /></div>
                    <div className="col-span-2"><Label className="text-xs">Oggetto *</Label>
                        <Input value={f.oggetto} onChange={(e) => set("oggetto", e.target.value)} data-testid="nl-oggetto" /></div>
                    <div><Label className="text-xs">Canale *</Label>
                        <Select value={f.canale} onValueChange={(v) => set("canale", v)}>
                            <SelectTrigger data-testid="nl-canale"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                {CANALI.map((c) => <SelectItem key={c.v} value={c.v}>{c.l}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div><Label className="text-xs">Tipo cliente</Label>
                        <Select value={f.target_filtro?.tipo || "all"} onValueChange={(v) => setTarget("tipo", v === "all" ? null : v)}>
                            <SelectTrigger><SelectValue placeholder="Tutti" /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Tutti</SelectItem>
                                <SelectItem value="persona_fisica">Solo privati</SelectItem>
                                <SelectItem value="persona_giuridica">Solo aziende</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="col-span-2"><Label className="text-xs">Tag clienti (separati da virgola)</Label>
                        <Input
                            value={(f.target_filtro?.tags || []).join(", ")}
                            onChange={(e) => setTarget("tags", e.target.value.split(",").map((t) => t.trim()).filter(Boolean))}
                            placeholder="es. VIP, AGRICOLO" />
                    </div>
                </div>
                <div><Label className="text-xs">Contenuto messaggio *</Label>
                    <Textarea rows={8} value={f.contenuto} onChange={(e) => set("contenuto", e.target.value)}
                        placeholder="Ciao {nome}, …" data-testid="nl-content" />
                    <div className="text-[10px] text-slate-500 mt-1">Placeholder supportati: {"{nome}"} {"{cognome}"} {"{ragione_sociale}"}</div>
                </div>
                <div className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded p-2">
                    📋 Verrà inviata solo ai clienti con <b>consenso commerciale</b> attivo.
                </div>
            </div>
            <DialogFooter>
                <Button onClick={save} className="bg-sky-700 hover:bg-sky-800" data-testid="nl-save">Salva</Button>
            </DialogFooter>
        </DialogContent>
    );
}
