import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { PageHeader, Empty, Loading } from "@/components/Shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import { Plus, Building2 } from "lucide-react";
import { toast } from "sonner";

export default function Compagnie() {
    const [list, setList] = useState(null);
    const [open, setOpen] = useState(false);

    const load = () => api.get("/compagnie").then((r) => setList(r.data));
    useEffect(() => { load(); }, []);

    return (
        <div data-testid="compagnie-page">
            <PageHeader
                title="Compagnie assicurative"
                subtitle="Anagrafica compagnie a portafoglio"
                actions={
                    <Dialog open={open} onOpenChange={setOpen}>
                        <DialogTrigger asChild>
                            <Button data-testid="comp-new-button" className="bg-sky-700 hover:bg-sky-800">
                                <Plus size={16} className="mr-1" /> Nuova compagnia
                            </Button>
                        </DialogTrigger>
                        <NuovaCompagniaDialog onClose={() => { setOpen(false); load(); }} />
                    </Dialog>
                }
            />

            {list === null ? <Loading /> : list.length === 0 ? <Empty /> : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {list.map((c) => (
                        <div key={c.id} className="bg-white border border-slate-200 rounded-md p-5 hover:shadow-md transition-shadow" data-testid={`comp-card-${c.id}`}>
                            <div className="flex items-center gap-3 mb-3">
                                <div className="w-10 h-10 bg-sky-50 text-sky-700 rounded-md flex items-center justify-center">
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
                            {c.referente && <div className="text-sm text-slate-700">Referente: <span className="font-medium">{c.referente}</span></div>}
                            {c.email && <div className="text-sm text-slate-600">{c.email}</div>}
                            {c.telefono && <div className="text-sm text-slate-600 num">{c.telefono}</div>}
                            {c.descrizione && <div className="text-xs text-slate-500 mt-2">{c.descrizione}</div>}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

function NuovaCompagniaDialog({ onClose }) {
    const [f, setF] = useState({
        codice: "", ragione_sociale: "", referente: "",
        email: "", telefono: "", sito_web: "", descrizione: "", attiva: true,
    });
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
    const save = async () => {
        if (!f.codice || !f.ragione_sociale) { toast.error("Codice e ragione sociale obbligatori"); return; }
        try {
            await api.post("/compagnie", f);
            toast.success("Compagnia creata"); onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <DialogContent>
            <DialogHeader><DialogTitle>Nuova compagnia</DialogTitle></DialogHeader>
            <div className="space-y-3 py-2">
                <div><Label>Codice *</Label><Input data-testid="comp-codice-input" value={f.codice} onChange={(e) => set("codice", e.target.value.toUpperCase())} /></div>
                <div><Label>Ragione sociale *</Label><Input data-testid="comp-rs-input" value={f.ragione_sociale} onChange={(e) => set("ragione_sociale", e.target.value)} /></div>
                <div><Label>Referente</Label><Input value={f.referente} onChange={(e) => set("referente", e.target.value)} /></div>
                <div className="grid grid-cols-2 gap-3">
                    <div><Label>Email</Label><Input value={f.email} onChange={(e) => set("email", e.target.value)} /></div>
                    <div><Label>Telefono</Label><Input value={f.telefono} onChange={(e) => set("telefono", e.target.value)} /></div>
                </div>
                <div><Label>Descrizione</Label><Input value={f.descrizione} onChange={(e) => set("descrizione", e.target.value)} /></div>
            </div>
            <DialogFooter>
                <Button data-testid="comp-save-button" onClick={save} className="bg-sky-700 hover:bg-sky-800">Salva</Button>
            </DialogFooter>
        </DialogContent>
    );
}
