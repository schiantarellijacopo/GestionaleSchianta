import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, fmtDate, fmtEur } from "@/lib/api";
import { PageHeader, StatusBadge, Loading, Empty } from "@/components/Shared";
import KpiBar from "@/components/KpiBar";
import SortHeader, { useTableSort } from "@/components/SortHeader";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import { Plus } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

export default function Sinistri() {
    const { user } = useAuth();
    const [searchParams] = useSearchParams();
    const polizzaIdFilter = searchParams.get("polizza_id");
    const focusId = searchParams.get("focus");
    const [list, setList] = useState(null);
    const [stato, setStato] = useState("all");
    const [open, setOpen] = useState(false);
    const canCreate = ["admin", "collaboratore", "dipendente"].includes(user?.role);

    const load = () => {
        const params = {};
        if (stato !== "all") params.stato = stato;
        if (polizzaIdFilter) params.polizza_id = polizzaIdFilter;
        api.get("/sinistri", { params }).then((r) => setList(r.data));
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [stato, polizzaIdFilter]);

    // Scroll/highlight sul sinistro indicato in query
    useEffect(() => {
        if (focusId && list) {
            const el = document.querySelector(`[data-testid="sinistro-row-${focusId}"]`);
            if (el) {
                el.scrollIntoView({ behavior: "smooth", block: "center" });
                el.classList.add("ring-2", "ring-amber-400");
                setTimeout(() => el.classList.remove("ring-2", "ring-amber-400"), 2500);
            }
        }
    }, [focusId, list]);

    const { sorted: sortedList, sortKey, dir, toggle } = useTableSort(
        list || [], "data_avvenimento", "desc",
    );

    return (
        <div data-testid="sinistri-page">
            <PageHeader
                title="Sinistri"
                subtitle="Denunce di sinistro e relative liquidazioni"
                actions={canCreate && (
                    <Dialog open={open} onOpenChange={setOpen}>
                        <DialogTrigger asChild>
                            <Button data-testid="sinistro-new-button" className="bg-sky-700 hover:bg-sky-800">
                                <Plus size={16} className="mr-1" /> Nuova denuncia
                            </Button>
                        </DialogTrigger>
                        <NuovoSinistroDialog onClose={() => { setOpen(false); load(); }} />
                    </Dialog>
                )}
            />

            <KpiBar sezione="sinistri" />

            <div className="flex items-center gap-3 mb-4">
                <Select value={stato} onValueChange={setStato}>
                    <SelectTrigger className="w-48"><SelectValue /></SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">Tutti gli stati</SelectItem>
                        <SelectItem value="aperto">Aperti</SelectItem>
                        <SelectItem value="in_istruttoria">In istruttoria</SelectItem>
                        <SelectItem value="liquidato">Liquidati</SelectItem>
                        <SelectItem value="chiuso_senza_seguito">Chiusi</SelectItem>
                        <SelectItem value="respinto">Respinti</SelectItem>
                    </SelectContent>
                </Select>
                <span className="text-sm text-slate-500 num ml-auto">{list ? `${list.length} sinistri` : ""}</span>
            </div>

            {polizzaIdFilter && (
                <div className="mb-3 flex items-center gap-2 text-xs bg-amber-50 border border-amber-200 text-amber-900 rounded px-3 py-2" data-testid="filter-polizza-banner">
                    <span>Filtrato per polizza specifica.</span>
                    <Link to="/sinistri" className="underline hover:text-amber-700">Rimuovi filtro</Link>
                </div>
            )}

            <div className="tbl-scroll" style={{ "--c1-w": "100px", "--c2-w": "140px" }}>
                {list === null ? <Loading /> : list.length === 0 ? <Empty /> : (
                    <table className="tbl freeze-3 w-full min-w-[900px]">
                        <thead>
                            <tr>
                                <th><SortHeader k="numero_sinistro" sortKey={sortKey} dir={dir} toggle={toggle}>Numero</SortHeader></th>
                                <th><SortHeader k="numero_polizza" sortKey={sortKey} dir={dir} toggle={toggle}>Polizza</SortHeader></th>
                                <th><SortHeader k="data_avvenimento" sortKey={sortKey} dir={dir} toggle={toggle}>Avvenimento</SortHeader></th>
                                <th><SortHeader k="data_denuncia" sortKey={sortKey} dir={dir} toggle={toggle}>Denuncia</SortHeader></th>
                                <th><SortHeader k="luogo" sortKey={sortKey} dir={dir} toggle={toggle}>Luogo</SortHeader></th>
                                <th><SortHeader k="ramo" sortKey={sortKey} dir={dir} toggle={toggle}>Ramo</SortHeader></th>
                                <th><SortHeader k="stato" sortKey={sortKey} dir={dir} toggle={toggle}>Stato</SortHeader></th>
                                <th className="text-right"><SortHeader k="riserva" sortKey={sortKey} dir={dir} toggle={toggle}>Riserva</SortHeader></th>
                                <th className="text-right"><SortHeader k="liquidazione" sortKey={sortKey} dir={dir} toggle={toggle}>Liquidazione</SortHeader></th>
                            </tr>
                        </thead>
                        <tbody>
                            {sortedList.map((s) => (
                                <tr key={s.id} data-testid={`sinistro-row-${s.id}`}>
                                    <td className="num font-medium">{s.numero_sinistro}</td>
                                    <td><Link to={`/polizze/${s.polizza_id}`} className="text-sky-700 hover:underline">{s.numero_polizza || s.polizza_id.slice(0, 8)}</Link></td>
                                    <td className="num">{fmtDate(s.data_avvenimento)}</td>
                                    <td className="num">{fmtDate(s.data_denuncia)}</td>
                                    <td>{s.luogo}</td>
                                    <td><span className="badge badge-neutral">{s.ramo || "-"}</span></td>
                                    <td><StatusBadge stato={s.stato} /></td>
                                    <td className="num text-right">{fmtEur(s.riserva)}</td>
                                    <td className="num text-right">{fmtEur(s.liquidazione)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
}

function NuovoSinistroDialog({ onClose }) {
    const [polizze, setPolizze] = useState([]);
    const [f, setF] = useState({
        numero_sinistro: "", polizza_id: "",
        data_avvenimento: "", data_denuncia: "",
        luogo: "", descrizione: "", riserva: 0, stato: "aperto",
    });
    useEffect(() => { api.get("/polizze").then((r) => setPolizze(r.data)); }, []);
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const save = async () => {
        if (!f.numero_sinistro || !f.polizza_id || !f.data_avvenimento) {
            toast.error("Compila i campi obbligatori"); return;
        }
        const pol = polizze.find((p) => p.id === f.polizza_id);
        try {
            await api.post("/sinistri", {
                ...f,
                compagnia_id: pol?.compagnia_id || "",
                contraente_id: pol?.contraente_id || "",
                ramo: pol?.ramo,
                riserva: parseFloat(f.riserva) || 0,
            });
            toast.success("Sinistro creato"); onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <DialogContent className="max-w-xl">
            <DialogHeader><DialogTitle>Nuova denuncia sinistro</DialogTitle></DialogHeader>
            <div className="grid grid-cols-2 gap-4 py-2">
                <div><Label>Numero sinistro *</Label><Input value={f.numero_sinistro} onChange={(e) => set("numero_sinistro", e.target.value)} data-testid="sin-numero-input" /></div>
                <div>
                    <Label>Polizza *</Label>
                    <Select value={f.polizza_id} onValueChange={(v) => set("polizza_id", v)}>
                        <SelectTrigger data-testid="sin-polizza-select"><SelectValue placeholder="Seleziona" /></SelectTrigger>
                        <SelectContent>
                            {polizze.map((p) => <SelectItem key={p.id} value={p.id}>{p.numero_polizza} — {p.contraente_nome}</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
                <div><Label>Data avvenimento *</Label><Input type="date" value={f.data_avvenimento} onChange={(e) => set("data_avvenimento", e.target.value)} /></div>
                <div><Label>Data denuncia</Label><Input type="date" value={f.data_denuncia} onChange={(e) => set("data_denuncia", e.target.value)} /></div>
                <div className="col-span-2"><Label>Luogo</Label><Input value={f.luogo} onChange={(e) => set("luogo", e.target.value)} /></div>
                <div className="col-span-2"><Label>Descrizione</Label><Textarea rows={3} value={f.descrizione} onChange={(e) => set("descrizione", e.target.value)} /></div>
                <div><Label>Riserva €</Label><Input type="number" step="0.01" value={f.riserva} onChange={(e) => set("riserva", e.target.value)} /></div>
                <div>
                    <Label>Stato</Label>
                    <Select value={f.stato} onValueChange={(v) => set("stato", v)}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="aperto">Aperto</SelectItem>
                            <SelectItem value="in_istruttoria">In istruttoria</SelectItem>
                            <SelectItem value="liquidato">Liquidato</SelectItem>
                            <SelectItem value="chiuso_senza_seguito">Chiuso senza seguito</SelectItem>
                            <SelectItem value="respinto">Respinto</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
            </div>
            <DialogFooter>
                <Button onClick={save} data-testid="sin-save-button" className="bg-sky-700 hover:bg-sky-800">Crea</Button>
            </DialogFooter>
        </DialogContent>
    );
}
