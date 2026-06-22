import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtDate, fmtEur } from "@/lib/api";
import { PageHeader, StatusBadge, Loading, Empty } from "@/components/Shared";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Search, Plus } from "lucide-react";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

export default function Polizze() {
    const { user } = useAuth();
    const [list, setList] = useState(null);
    const [q, setQ] = useState("");
    const [stato, setStato] = useState("all");
    const [open, setOpen] = useState(false);
    const canCreate = ["admin", "collaboratore", "dipendente"].includes(user?.role);

    const load = () => {
        const params = { q: q || undefined };
        if (stato && stato !== "all") params.stato = stato;
        api.get("/polizze", { params }).then((r) => setList(r.data));
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [stato]);
    useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); /* eslint-disable-next-line */ }, [q]);

    return (
        <div data-testid="polizze-page">
            <PageHeader
                title="Polizze"
                subtitle="Portafoglio polizze attive, sospese e annullate"
                actions={canCreate && (
                    <Dialog open={open} onOpenChange={setOpen}>
                        <DialogTrigger asChild>
                            <Button data-testid="polizza-new-button" className="bg-sky-700 hover:bg-sky-800">
                                <Plus size={16} className="mr-1" /> Nuova polizza
                            </Button>
                        </DialogTrigger>
                        <NuovaPolizzaDialog onClose={() => { setOpen(false); load(); }} />
                    </Dialog>
                )}
            />

            <div className="flex items-center gap-3 mb-4">
                <div className="relative flex-1 max-w-md">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                    <Input
                        data-testid="polizze-search"
                        placeholder="Numero polizza o targa..."
                        value={q}
                        onChange={(e) => setQ(e.target.value)}
                        className="pl-9"
                    />
                </div>
                <Select value={stato} onValueChange={setStato}>
                    <SelectTrigger className="w-40"><SelectValue placeholder="Stato" /></SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">Tutti gli stati</SelectItem>
                        <SelectItem value="attiva">Attive</SelectItem>
                        <SelectItem value="sospesa">Sospese</SelectItem>
                        <SelectItem value="scaduta">Scadute</SelectItem>
                        <SelectItem value="annullata">Annullate</SelectItem>
                    </SelectContent>
                </Select>
                <span className="text-sm text-slate-500 num ml-auto">{list ? `${list.length} polizze` : ""}</span>
            </div>

            <div className="bg-white border border-slate-200 rounded-md overflow-x-auto">
                {list === null ? <Loading /> : list.length === 0 ? <Empty /> : (
                    <table className="tbl w-full min-w-[1000px]">
                        <thead>
                            <tr>
                                <th>Numero polizza</th>
                                <th>Contraente</th>
                                <th>Compagnia</th>
                                <th>Ramo</th>
                                <th>Stato</th>
                                <th>Effetto</th>
                                <th>Scadenza</th>
                                <th className="text-right">Premio lordo</th>
                                <th className="text-right">Provvigioni</th>
                            </tr>
                        </thead>
                        <tbody>
                            {list.map((p) => (
                                <tr key={p.id} data-testid={`polizza-row-${p.id}`}>
                                    <td><Link to={`/polizze/${p.id}`} className="text-sky-700 hover:underline font-medium">{p.numero_polizza}</Link></td>
                                    <td>{p.contraente_nome || "—"}</td>
                                    <td className="text-slate-600">{p.compagnia_nome || "—"}</td>
                                    <td><span className="badge badge-neutral">{p.ramo}</span></td>
                                    <td><StatusBadge stato={p.stato} /></td>
                                    <td className="num">{fmtDate(p.effetto)}</td>
                                    <td className="num">{fmtDate(p.scadenza)}</td>
                                    <td className="num text-right font-medium">{fmtEur(p.premio_lordo)}</td>
                                    <td className="num text-right text-slate-600">{fmtEur(p.provvigioni)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
}

function NuovaPolizzaDialog({ onClose }) {
    const [ana, setAna] = useState([]);
    const [comp, setComp] = useState([]);
    const [f, setF] = useState({
        numero_polizza: "", compagnia_id: "", contraente_id: "",
        ramo: "RCA", prodotto: "", effetto: "", scadenza: "",
        premio_lordo: 0, premio_netto: 0, provvigioni: 0,
        targa: "", frazionamento: "annuale", stato: "attiva",
    });
    useEffect(() => {
        api.get("/anagrafiche").then((r) => setAna(r.data));
        api.get("/compagnie").then((r) => setComp(r.data));
    }, []);
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const save = async () => {
        if (!f.numero_polizza || !f.compagnia_id || !f.contraente_id || !f.effetto || !f.scadenza) {
            toast.error("Compila tutti i campi obbligatori");
            return;
        }
        try {
            await api.post("/polizze", {
                ...f,
                premio_lordo: parseFloat(f.premio_lordo) || 0,
                premio_netto: parseFloat(f.premio_netto) || 0,
                provvigioni: parseFloat(f.provvigioni) || 0,
                assicurato_ids: [f.contraente_id],
            });
            toast.success("Polizza creata");
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        }
    };

    return (
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader><DialogTitle>Nuova polizza</DialogTitle></DialogHeader>
            <div className="grid grid-cols-2 gap-4 py-2">
                <div><Label>Numero polizza *</Label><Input data-testid="pol-numero-input" value={f.numero_polizza} onChange={(e) => set("numero_polizza", e.target.value)} /></div>
                <div>
                    <Label>Stato</Label>
                    <Select value={f.stato} onValueChange={(v) => set("stato", v)}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="attiva">Attiva</SelectItem>
                            <SelectItem value="sospesa">Sospesa</SelectItem>
                            <SelectItem value="in_emissione">In emissione</SelectItem>
                            <SelectItem value="scaduta">Scaduta</SelectItem>
                            <SelectItem value="annullata">Annullata</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
                <div>
                    <Label>Compagnia *</Label>
                    <Select value={f.compagnia_id} onValueChange={(v) => set("compagnia_id", v)}>
                        <SelectTrigger data-testid="pol-comp-select"><SelectValue placeholder="Seleziona" /></SelectTrigger>
                        <SelectContent>
                            {comp.map((c) => <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
                <div>
                    <Label>Contraente *</Label>
                    <Select value={f.contraente_id} onValueChange={(v) => set("contraente_id", v)}>
                        <SelectTrigger data-testid="pol-contraente-select"><SelectValue placeholder="Seleziona" /></SelectTrigger>
                        <SelectContent>
                            {ana.map((a) => <SelectItem key={a.id} value={a.id}>{a.ragione_sociale}</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
                <div><Label>Ramo</Label><Input value={f.ramo} onChange={(e) => set("ramo", e.target.value)} /></div>
                <div><Label>Prodotto</Label><Input value={f.prodotto} onChange={(e) => set("prodotto", e.target.value)} /></div>
                <div><Label>Effetto *</Label><Input type="date" value={f.effetto} onChange={(e) => set("effetto", e.target.value)} /></div>
                <div><Label>Scadenza *</Label><Input type="date" value={f.scadenza} onChange={(e) => set("scadenza", e.target.value)} /></div>
                <div><Label>Premio lordo €</Label><Input type="number" step="0.01" value={f.premio_lordo} onChange={(e) => set("premio_lordo", e.target.value)} /></div>
                <div><Label>Premio netto €</Label><Input type="number" step="0.01" value={f.premio_netto} onChange={(e) => set("premio_netto", e.target.value)} /></div>
                <div><Label>Provvigioni €</Label><Input type="number" step="0.01" value={f.provvigioni} onChange={(e) => set("provvigioni", e.target.value)} /></div>
                <div><Label>Targa (se RCA)</Label><Input value={f.targa} onChange={(e) => set("targa", e.target.value.toUpperCase())} /></div>
            </div>
            <DialogFooter>
                <Button data-testid="pol-save-button" onClick={save} className="bg-sky-700 hover:bg-sky-800">Crea polizza</Button>
            </DialogFooter>
        </DialogContent>
    );
}
