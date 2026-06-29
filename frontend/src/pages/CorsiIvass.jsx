/**
 * CorsiIvass — gestione corsi IVASS per collaboratori con OCR certificati e
 * grafico 30 ore annuali (obbligo formativo IVASS).
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
import { GraduationCap, Upload, Sparkles, Trash2, Plus, TrendingUp } from "lucide-react";
import { toast } from "sonner";

export default function CorsiIvass() {
    const [collaboratori, setCollaboratori] = useState([]);
    const [selected, setSelected] = useState("");
    const [anno, setAnno] = useState(new Date().getFullYear());
    const [storico, setStorico] = useState(null);
    const [dialogOpen, setDialogOpen] = useState(false);

    useEffect(() => {
        api.get("/utenti").then((r) => {
            const arr = (r.data || []).filter((u) => ["collaboratore", "dipendente", "admin"].includes(u.role));
            setCollaboratori(arr);
            if (arr.length && !selected) setSelected(arr[0].id);
        });
    /* eslint-disable-next-line */
    }, []);

    const load = () => {
        if (!selected) return;
        api.get(`/corsi-ivass/${selected}/storico`, { params: { anno } }).then((r) => setStorico(r.data));
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [selected, anno]);

    return (
        <div data-testid="corsi-ivass-page" className="space-y-4">
            <PageHeader
                title={<span className="flex items-center gap-2"><GraduationCap className="text-emerald-600" /> Corsi IVASS</span>}
                subtitle="Obbligo formativo annuale 30 ore · OCR attestati con Gemini · grafico avanzamento"
                actions={
                    <div className="flex gap-2">
                        <Select value={selected} onValueChange={setSelected}>
                            <SelectTrigger className="w-64" data-testid="civ-coll-sel">
                                <SelectValue placeholder="Collaboratore…" />
                            </SelectTrigger>
                            <SelectContent>
                                {collaboratori.map((c) => (
                                    <SelectItem key={c.id} value={c.id}>{c.name || c.email}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                        <Select value={String(anno)} onValueChange={(v) => setAnno(parseInt(v))}>
                            <SelectTrigger className="w-28" data-testid="civ-anno-sel"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                {[0, -1, -2, -3].map((d) => {
                                    const y = new Date().getFullYear() + d;
                                    return <SelectItem key={y} value={String(y)}>{y}</SelectItem>;
                                })}
                            </SelectContent>
                        </Select>
                        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
                            <DialogTrigger asChild>
                                <Button className="bg-emerald-700 hover:bg-emerald-800" data-testid="civ-new">
                                    <Plus size={14} className="mr-1" /> Aggiungi corso
                                </Button>
                            </DialogTrigger>
                            <NuovoCorsoDialog collaboratore_id={selected}
                                onClose={() => { setDialogOpen(false); load(); }} />
                        </Dialog>
                    </div>
                }
            />

            {!storico ? <Loading /> : (
                <>
                    <Card className="p-4 border-l-4 border-emerald-500 bg-gradient-to-r from-emerald-50 to-white">
                        <div className="flex items-center justify-between flex-wrap gap-3">
                            <div>
                                <div className="text-[10px] uppercase tracking-wider text-slate-500">Ore IVASS {anno}</div>
                                <div className="text-3xl font-bold text-emerald-700">
                                    {storico.totale_ore_anno} <span className="text-base text-slate-400">/ {storico.obiettivo_annuo} h</span>
                                </div>
                            </div>
                            <div className="flex-1 max-w-md">
                                <div className="text-xs text-slate-600 mb-1 text-right font-mono">{storico.completamento_pct}%</div>
                                <div className="h-3 bg-slate-200 rounded-full overflow-hidden">
                                    <div className="h-3 bg-gradient-to-r from-emerald-400 to-emerald-600 transition-all"
                                        style={{ width: `${Math.min(100, storico.completamento_pct)}%` }} />
                                </div>
                                <div className="text-[10px] text-slate-500 mt-1">
                                    {storico.completamento_pct < 50 && "⚠ Attenzione: meno di metà del fabbisogno annuale"}
                                    {storico.completamento_pct >= 50 && storico.completamento_pct < 100 && "✓ A buon punto"}
                                    {storico.completamento_pct >= 100 && "🎉 Obbligo raggiunto!"}
                                </div>
                            </div>
                        </div>
                    </Card>

                    {/* Grafico mensile */}
                    <Card className="p-4">
                        <h4 className="font-semibold text-sm mb-3 flex items-center gap-2 text-slate-800">
                            <TrendingUp size={14} /> Andamento mensile {anno}
                        </h4>
                        <div className="flex items-end gap-1.5 h-32 border-b border-l border-slate-200 pl-2">
                            {Array.from({ length: 12 }).map((_, i) => {
                                const mese = `${anno}-${String(i + 1).padStart(2, "0")}`;
                                const found = storico.grafico_mensile?.find((g) => g.mese === mese);
                                const ore = found?.ore || 0;
                                const h = Math.min(100, (ore / 30) * 100 * 1.5);
                                return (
                                    <div key={i} className="flex-1 flex flex-col items-center justify-end h-full">
                                        <div className="text-[9px] text-slate-500 font-mono mb-0.5">{ore || ""}</div>
                                        <div className="w-full bg-emerald-400 rounded-t hover:bg-emerald-500 transition"
                                            style={{ height: `${h}%`, minHeight: ore ? "4px" : "0" }}
                                            title={`${mese}: ${ore} ore`}
                                        />
                                        <div className="text-[9px] text-slate-500 mt-0.5">{String(i + 1).padStart(2, "0")}</div>
                                    </div>
                                );
                            })}
                        </div>
                    </Card>

                    {/* Tabella corsi */}
                    <Card className="overflow-hidden">
                        {storico.corsi.length === 0 ? <Empty message="Nessun corso registrato per questo anno." /> : (
                            <table className="tbl-compact w-full text-xs">
                                <thead><tr>
                                    <th>Data</th><th>Titolo corso</th><th>Ente</th>
                                    <th className="text-right">Ore</th><th className="text-right">Crediti</th><th>Note</th><th></th>
                                </tr></thead>
                                <tbody>
                                    {storico.corsi.map((c) => (
                                        <tr key={c.id}>
                                            <td className="font-mono">{c.data_corso}</td>
                                            <td className="font-medium">{c.titolo_corso}</td>
                                            <td className="text-slate-600">{c.ente || "—"}</td>
                                            <td className="text-right font-mono font-bold text-emerald-700">{c.ore_riconosciute}h</td>
                                            <td className="text-right font-mono">{c.crediti_ivass || "—"}</td>
                                            <td className="text-slate-500 italic">{c.note || ""}</td>
                                            <td>
                                                <button onClick={async () => {
                                                    if (!window.confirm("Eliminare?")) return;
                                                    await api.delete(`/corsi-ivass/${c.id}`); toast.success("Eliminato"); load();
                                                }} className="text-rose-600 hover:bg-rose-50 p-1 rounded">
                                                    <Trash2 size={11} />
                                                </button>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </Card>
                </>
            )}
        </div>
    );
}

function NuovoCorsoDialog({ collaboratore_id, onClose }) {
    const [f, setF] = useState({ titolo_corso: "", ente: "", data_corso: "", ore_riconosciute: 0, crediti_ivass: "", note: "" });
    const [busy, setBusy] = useState(false);
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const ocrPick = async (e) => {
        const file = e.target.files?.[0]; if (!file) return;
        setBusy(true);
        try {
            const fd = new FormData(); fd.append("file", file); fd.append("collaboratore_id", collaboratore_id);
            const r = await api.post("/corsi-ivass/ocr", fd, { headers: { "Content-Type": "multipart/form-data" } });
            const d = r.data.dati || {};
            setF((p) => ({
                ...p,
                titolo_corso: d.titolo_corso || p.titolo_corso,
                ente: d.ente_erogatore || p.ente,
                data_corso: d.data_corso || p.data_corso,
                ore_riconosciute: d.ore_riconosciute || p.ore_riconosciute,
                crediti_ivass: d.crediti_ivass || p.crediti_ivass,
            }));
            toast.success(`OCR · confidenza ${d.confidenza || "n/d"}`);
        } catch (err) { toast.error(err.response?.data?.detail || "Errore OCR"); }
        finally { setBusy(false); e.target.value = ""; }
    };

    const save = async () => {
        if (!f.titolo_corso || !f.data_corso || !f.ore_riconosciute) {
            toast.error("Titolo, data e ore obbligatori"); return;
        }
        try {
            await api.post("/corsi-ivass", { ...f, collaboratore_id });
            toast.success("Corso registrato"); onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <DialogContent className="max-w-xl">
            <DialogHeader><DialogTitle>Nuovo corso IVASS</DialogTitle></DialogHeader>
            <div className="space-y-3 py-2">
                <label className="inline-flex items-center gap-2 px-3 py-2 border border-violet-300 bg-violet-50 text-violet-700 rounded text-sm cursor-pointer hover:bg-violet-100"
                    data-testid="civ-ocr-pick">
                    <Sparkles size={14} />
                    {busy ? "OCR…" : "Carica certificato (OCR auto-compila i campi)"}
                    <input type="file" hidden accept="application/pdf,image/*" onChange={ocrPick} />
                </label>
                <div className="grid grid-cols-2 gap-3">
                    <div className="col-span-2"><Label className="text-xs">Titolo corso *</Label>
                        <Input value={f.titolo_corso} onChange={(e) => set("titolo_corso", e.target.value)} data-testid="civ-titolo" /></div>
                    <div><Label className="text-xs">Ente erogatore</Label>
                        <Input value={f.ente} onChange={(e) => set("ente", e.target.value)} /></div>
                    <div><Label className="text-xs">Data *</Label>
                        <Input type="date" value={f.data_corso} onChange={(e) => set("data_corso", e.target.value)} /></div>
                    <div><Label className="text-xs">Ore riconosciute *</Label>
                        <Input type="number" step="0.5" value={f.ore_riconosciute}
                            onChange={(e) => set("ore_riconosciute", parseFloat(e.target.value) || 0)} /></div>
                    <div><Label className="text-xs">Crediti IVASS</Label>
                        <Input type="number" step="0.5" value={f.crediti_ivass}
                            onChange={(e) => set("crediti_ivass", parseFloat(e.target.value) || 0)} /></div>
                    <div className="col-span-2"><Label className="text-xs">Note</Label>
                        <Textarea rows={2} value={f.note} onChange={(e) => set("note", e.target.value)} /></div>
                </div>
            </div>
            <DialogFooter>
                <Button onClick={save} className="bg-emerald-700 hover:bg-emerald-800" data-testid="civ-save">Salva</Button>
            </DialogFooter>
        </DialogContent>
    );
}
