import { useEffect, useState } from "react";
import { api, fmtDate } from "@/lib/api";
import { PageHeader, StatusBadge, Loading, Empty } from "@/components/Shared";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import { Mail, Bell, Send, Plus } from "lucide-react";
import { toast } from "sonner";

export default function EmailPage() {
    const [list, setList] = useState(null);
    const [open, setOpen] = useState(false);

    const load = () => api.get("/email").then((r) => setList(r.data));
    useEffect(() => { load(); }, []);

    const inviaTutti = async (id) => {
        try {
            await api.post(`/email/${id}/invia`);
            toast.success("Email inviata (simulato)");
            load();
        } catch { toast.error("Errore"); }
    };

    const generaAvvisi = async () => {
        try {
            const res = await api.post("/email/avvisi-scadenze?giorni=60");
            toast.success(`Generati ${res.data.avvisi_creati} avvisi di scadenza`);
            load();
        } catch (e) { toast.error("Errore: " + e.message); }
    };

    return (
        <div data-testid="email-page">
            <PageHeader
                title="Pipeline Email"
                subtitle="Avvisi clienti, scadenze, comunicazioni programmate"
                actions={
                    <div className="flex gap-2">
                        <Button onClick={generaAvvisi} variant="outline" data-testid="genera-avvisi-button">
                            <Bell size={14} className="mr-1" /> Genera avvisi scadenze
                        </Button>
                        <Dialog open={open} onOpenChange={setOpen}>
                            <DialogTrigger asChild>
                                <Button className="bg-sky-700 hover:bg-sky-800" data-testid="email-new-button">
                                    <Plus size={14} className="mr-1" /> Nuova email
                                </Button>
                            </DialogTrigger>
                            <NuovaEmailDialog onClose={() => { setOpen(false); load(); }} />
                        </Dialog>
                    </div>
                }
            />

            <Card className="p-4 border-sky-200 bg-sky-50 mb-6 flex gap-3 items-start">
                <Mail size={16} className="text-sky-700 mt-0.5" />
                <div className="text-xs text-sky-900">
                    {"L'invio email è attualmente in "}<b>modalit&agrave; simulata</b>{". Per abilitare l'invio reale collega un provider SMTP (es. SendGrid, Resend) nelle impostazioni."}
                </div>
            </Card>

            <div className="bg-white border border-slate-200 rounded-md overflow-hidden">
                {list === null ? <Loading /> : list.length === 0 ? <Empty message="Nessuna email in coda" /> : (
                    <table className="tbl w-full">
                        <thead>
                            <tr>
                                <th>Stato</th>
                                <th>Destinatario</th>
                                <th>Oggetto</th>
                                <th>Template</th>
                                <th>Creata</th>
                                <th>Inviata</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody>
                            {list.map((e) => (
                                <tr key={e.id} data-testid={`email-row-${e.id}`}>
                                    <td><StatusBadge stato={e.stato} /></td>
                                    <td className="text-xs">{e.destinatario_email}</td>
                                    <td>{e.oggetto}</td>
                                    <td className="text-xs text-slate-500">{e.template || "-"}</td>
                                    <td className="num text-xs">{fmtDate(e.created_at)}</td>
                                    <td className="num text-xs">{fmtDate(e.data_invio)}</td>
                                    <td>
                                        {(e.stato === "bozza" || e.stato === "in_coda") && (
                                            <Button size="sm" onClick={() => inviaTutti(e.id)} variant="outline" data-testid={`invia-${e.id}`}>
                                                <Send size={12} className="mr-1" /> Invia
                                            </Button>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
}

function NuovaEmailDialog({ onClose }) {
    const [anagrafiche, setAnagrafiche] = useState([]);
    const [f, setF] = useState({
        destinatario_email: "", destinatario_anagrafica_id: "",
        oggetto: "", corpo: "", stato: "bozza",
    });
    useEffect(() => { api.get("/anagrafiche").then((r) => setAnagrafiche(r.data)); }, []);
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const pickAna = (id) => {
        const a = anagrafiche.find((x) => x.id === id);
        setF((p) => ({ ...p, destinatario_anagrafica_id: id, destinatario_email: a?.email || p.destinatario_email }));
    };

    const save = async (stato) => {
        if (!f.destinatario_email || !f.oggetto || !f.corpo) { toast.error("Compila i campi"); return; }
        try {
            await api.post("/email", { ...f, stato });
            toast.success("Email creata"); onClose();
        } catch (err) { toast.error(err.response?.data?.detail || "Errore"); }
    };

    return (
        <DialogContent className="max-w-xl">
            <DialogHeader><DialogTitle>Nuova email</DialogTitle></DialogHeader>
            <div className="space-y-3 py-2">
                <div>
                    <Label>Anagrafica (opzionale)</Label>
                    <select className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm"
                        value={f.destinatario_anagrafica_id} onChange={(e) => pickAna(e.target.value)}>
                        <option value="">- Seleziona -</option>
                        {anagrafiche.map((a) => (
                            <option key={a.id} value={a.id}>{a.ragione_sociale} {a.email ? `(${a.email})` : ""}</option>
                        ))}
                    </select>
                </div>
                <div><Label>Destinatario *</Label><Input data-testid="email-to-input" value={f.destinatario_email} onChange={(e) => set("destinatario_email", e.target.value)} /></div>
                <div><Label>Oggetto *</Label><Input data-testid="email-subject-input" value={f.oggetto} onChange={(e) => set("oggetto", e.target.value)} /></div>
                <div><Label>Corpo *</Label><Textarea rows={6} value={f.corpo} onChange={(e) => set("corpo", e.target.value)} /></div>
            </div>
            <DialogFooter>
                <Button variant="outline" onClick={() => save("bozza")}>Salva bozza</Button>
                <Button onClick={() => save("in_coda")} className="bg-sky-700 hover:bg-sky-800" data-testid="email-queue-button">
                    Metti in coda
                </Button>
            </DialogFooter>
        </DialogContent>
    );
}
