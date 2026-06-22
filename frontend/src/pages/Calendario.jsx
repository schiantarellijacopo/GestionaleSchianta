import { useEffect, useState, useMemo } from "react";
import { api, fmtDate } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Plus, ChevronLeft, ChevronRight, Calendar as CalIcon, X, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

const TIPO_COLOR = {
    appuntamento: "bg-sky-500 border-sky-600",
    scadenza_polizza: "bg-red-500 border-red-600",
    scadenza_titolo: "bg-amber-500 border-amber-600",
    sinistro: "bg-orange-600 border-orange-700",
    promemoria: "bg-emerald-500 border-emerald-600",
    altro: "bg-slate-500 border-slate-600",
};

function pad(n) { return String(n).padStart(2, "0"); }
function ymd(d) { return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; }
function startOfMonth(d) { return new Date(d.getFullYear(), d.getMonth(), 1); }
function endOfMonth(d) { return new Date(d.getFullYear(), d.getMonth() + 1, 0); }

export default function Calendario() {
    const { user } = useAuth();
    const [mese, setMese] = useState(new Date());
    const [eventi, setEventi] = useState([]);
    const [loading, setLoading] = useState(true);
    const [operatori, setOperatori] = useState([]);
    const [filtroOp, setFiltroOp] = useState("all");
    const [dialog, setDialog] = useState(null);  // event being edited or { new: true, date }

    const dal = ymd(startOfMonth(mese));
    const al = ymd(endOfMonth(mese));

    useEffect(() => { api.get("/collaboratori").then((r) => setOperatori(r.data)); }, []);

    const load = () => {
        setLoading(true);
        const params = { dal, al };
        if (filtroOp !== "all") params.operatore_id = filtroOp;
        api.get("/calendario", { params }).then((r) => setEventi(r.data)).finally(() => setLoading(false));
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [dal, al, filtroOp]);

    const griglia = useMemo(() => {
        // genera 6 settimane partendo dal lunedì della prima settimana
        const first = startOfMonth(mese);
        const offset = (first.getDay() + 6) % 7;  // lunedì = 0
        const start = new Date(first);
        start.setDate(start.getDate() - offset);
        const days = [];
        for (let i = 0; i < 42; i++) {
            const d = new Date(start);
            d.setDate(start.getDate() + i);
            days.push(d);
        }
        return days;
    }, [mese]);

    const eventiPerGiorno = useMemo(() => {
        const map = {};
        eventi.forEach((e) => {
            const day = (e.inizio || "").slice(0, 10);
            if (!day) return;
            if (!map[day]) map[day] = [];
            map[day].push(e);
        });
        return map;
    }, [eventi]);

    return (
        <div data-testid="calendario-page">
            <PageHeader
                title="Calendario agenzia"
                subtitle="Appuntamenti, scadenze polizze e promemoria — per operatore o intera agenzia"
                actions={
                    <Button onClick={() => setDialog({ new: true, date: ymd(new Date()) })}
                            className="bg-sky-700 hover:bg-sky-800" data-testid="cal-new-event">
                        <Plus size={14} className="mr-1" /> Nuovo evento
                    </Button>
                }
            />

            <Card className="border-slate-200 p-3 mb-4 flex items-center gap-3 flex-wrap">
                <Button variant="outline" size="sm" onClick={() => setMese(new Date(mese.getFullYear(), mese.getMonth() - 1, 1))} data-testid="cal-prev">
                    <ChevronLeft size={14} />
                </Button>
                <div className="text-base font-semibold capitalize min-w-[180px] text-center">
                    {mese.toLocaleDateString("it-IT", { month: "long", year: "numeric" })}
                </div>
                <Button variant="outline" size="sm" onClick={() => setMese(new Date(mese.getFullYear(), mese.getMonth() + 1, 1))} data-testid="cal-next">
                    <ChevronRight size={14} />
                </Button>
                <Button variant="outline" size="sm" onClick={() => setMese(new Date())} data-testid="cal-today">Oggi</Button>

                <div className="ml-auto flex items-center gap-2">
                    <Label className="text-xs">Operatore:</Label>
                    <Select value={filtroOp} onValueChange={setFiltroOp}>
                        <SelectTrigger className="w-[200px]" data-testid="cal-filter-op"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">Tutta l&apos;agenzia</SelectItem>
                            {operatori.map((o) => <SelectItem key={o.id} value={o.id}>{o.name}</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
            </Card>

            {/* legenda */}
            <div className="flex flex-wrap gap-3 text-xs mb-3 px-1">
                {Object.entries(TIPO_COLOR).map(([k, c]) => (
                    <div key={k} className="flex items-center gap-1.5">
                        <span className={`inline-block w-2.5 h-2.5 rounded-sm ${c.split(" ")[0]}`} />
                        <span className="text-slate-600 capitalize">{k.replace("_", " ")}</span>
                    </div>
                ))}
            </div>

            {/* griglia mensile */}
            <Card className="border-slate-200 overflow-hidden">
                {loading ? <Loading /> : (
                    <>
                        <div className="grid grid-cols-7 bg-slate-100 text-[10px] uppercase tracking-wider text-slate-500 border-b border-slate-200">
                            {["Lun","Mar","Mer","Gio","Ven","Sab","Dom"].map((d) => (
                                <div key={d} className="p-2 text-center font-semibold">{d}</div>
                            ))}
                        </div>
                        <div className="grid grid-cols-7">
                            {griglia.map((d, i) => {
                                const dayStr = ymd(d);
                                const isCurrent = d.getMonth() === mese.getMonth();
                                const isToday = dayStr === ymd(new Date());
                                const dayEvents = eventiPerGiorno[dayStr] || [];
                                return (
                                    <div
                                        key={i}
                                        className={`border-b border-r border-slate-100 min-h-[100px] p-1.5 ${
                                            isCurrent ? "bg-white" : "bg-slate-50/50"
                                        } ${isToday ? "ring-2 ring-inset ring-sky-300" : ""}`}
                                        onDoubleClick={() => setDialog({ new: true, date: dayStr })}
                                        data-testid={`cal-day-${dayStr}`}
                                    >
                                        <div className={`text-xs font-medium mb-1 ${isCurrent ? "text-slate-700" : "text-slate-400"} ${isToday ? "text-sky-700" : ""}`}>
                                            {d.getDate()}
                                        </div>
                                        <div className="space-y-0.5">
                                            {dayEvents.slice(0, 4).map((e) => (
                                                <button
                                                    key={e.id}
                                                    onClick={() => !e._auto && setDialog(e)}
                                                    className={`w-full text-left text-[10px] px-1.5 py-0.5 rounded text-white truncate ${TIPO_COLOR[e.tipo]?.split(" ")[0] || "bg-slate-500"} hover:opacity-80`}
                                                    title={`${e.titolo}${e.operatore_nome ? ` · ${e.operatore_nome}` : ""}`}
                                                >
                                                    {e.titolo}
                                                </button>
                                            ))}
                                            {dayEvents.length > 4 && (
                                                <div className="text-[10px] text-slate-500 px-1">+{dayEvents.length - 4} altri</div>
                                            )}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </>
                )}
            </Card>

            <div className="mt-3 text-xs text-slate-500 flex items-center gap-4 px-1">
                <CalIcon size={12} /> Doppio click su un giorno per creare un evento
                <span className="ml-auto bg-amber-50 border border-amber-200 px-2 py-1 rounded text-[11px] text-amber-800">
                    Sync Google/Microsoft 365: configurazione OAuth richiesta — vedi Librerie
                </span>
            </div>

            {dialog && (
                <Dialog open onOpenChange={() => setDialog(null)}>
                    <EventoDialog
                        evento={dialog}
                        operatori={operatori}
                        currentUser={user}
                        onClose={() => { setDialog(null); load(); }}
                    />
                </Dialog>
            )}
        </div>
    );
}

function EventoDialog({ evento, operatori, currentUser, onClose }) {
    const isNew = evento.new === true;
    const init = isNew
        ? {
            titolo: "", descrizione: "",
            inizio: `${evento.date}T09:00`,
            fine: `${evento.date}T10:00`,
            tipo: "appuntamento", luogo: "",
            operatore_id: currentUser?.id || "",
        }
        : { ...evento };

    const [f, setF] = useState(init);
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const salva = async () => {
        if (!f.titolo) { toast.error("Inserisci un titolo"); return; }
        try {
            if (isNew) {
                await api.post("/calendario", f);
                toast.success("Evento creato");
            } else {
                await api.put(`/calendario/${f.id}`, f);
                toast.success("Evento aggiornato");
            }
            onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };
    const elimina = async () => {
        if (!window.confirm("Eliminare l'evento?")) return;
        try {
            await api.delete(`/calendario/${f.id}`);
            toast.success("Eliminato");
            onClose();
        } catch (e) { toast.error("Errore"); }
    };

    return (
        <DialogContent className="max-w-lg">
            <DialogHeader>
                <DialogTitle>{isNew ? "Nuovo evento" : "Modifica evento"}</DialogTitle>
            </DialogHeader>
            <div className="space-y-3 py-2">
                <div>
                    <Label>Titolo *</Label>
                    <Input value={f.titolo} onChange={(e) => set("titolo", e.target.value)} data-testid="ev-titolo" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <Label>Tipo</Label>
                        <Select value={f.tipo || "appuntamento"} onValueChange={(v) => set("tipo", v)}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="appuntamento">Appuntamento</SelectItem>
                                <SelectItem value="promemoria">Promemoria</SelectItem>
                                <SelectItem value="scadenza_polizza">Scadenza polizza</SelectItem>
                                <SelectItem value="scadenza_titolo">Scadenza titolo</SelectItem>
                                <SelectItem value="sinistro">Sinistro</SelectItem>
                                <SelectItem value="altro">Altro</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <Label>Operatore</Label>
                        <Select value={f.operatore_id || "__none__"} onValueChange={(v) => set("operatore_id", v === "__none__" ? null : v)}>
                            <SelectTrigger data-testid="ev-operatore"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="__none__">— nessuno —</SelectItem>
                                {operatori.map((o) => <SelectItem key={o.id} value={o.id}>{o.name}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <Label>Inizio</Label>
                        <Input type="datetime-local" value={(f.inizio || "").slice(0, 16)}
                               onChange={(e) => set("inizio", e.target.value)} />
                    </div>
                    <div>
                        <Label>Fine</Label>
                        <Input type="datetime-local" value={(f.fine || "").slice(0, 16)}
                               onChange={(e) => set("fine", e.target.value)} />
                    </div>
                </div>
                <div><Label>Luogo</Label><Input value={f.luogo || ""} onChange={(e) => set("luogo", e.target.value)} /></div>
                <div><Label>Descrizione</Label>
                    <textarea className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm" rows={3}
                              value={f.descrizione || ""} onChange={(e) => set("descrizione", e.target.value)} />
                </div>
            </div>
            <DialogFooter>
                {!isNew && (
                    <Button variant="outline" onClick={elimina} className="text-red-600 mr-auto" data-testid="ev-elimina">
                        <Trash2 size={13} className="mr-1" /> Elimina
                    </Button>
                )}
                <Button onClick={salva} className="bg-sky-700 hover:bg-sky-800" data-testid="ev-salva">
                    {isNew ? "Crea" : "Aggiorna"}
                </Button>
            </DialogFooter>
        </DialogContent>
    );
}
