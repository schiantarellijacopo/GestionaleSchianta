import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import { GraduationCap, Plus, Play, CheckCircle2 } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

export default function Corsi() {
    const { user } = useAuth();
    const [list, setList] = useState(null);
    const [sel, setSel] = useState(null);
    const [open, setOpen] = useState(false);
    const canCreate = ["admin", "collaboratore"].includes(user?.role);

    const load = () => api.get("/corsi").then((r) => setList(r.data));
    useEffect(() => { load(); }, []);

    return (
        <div data-testid="corsi-page">
            <PageHeader
                title="Corsi e formazione"
                subtitle="Video formativi assegnati al tuo ruolo"
                actions={canCreate && (
                    <Dialog open={open} onOpenChange={setOpen}>
                        <DialogTrigger asChild>
                            <Button data-testid="corso-new-button" className="bg-sky-700 hover:bg-sky-800">
                                <Plus size={14} className="mr-1" /> Nuovo corso
                            </Button>
                        </DialogTrigger>
                        <CorsoForm onClose={() => { setOpen(false); load(); }} />
                    </Dialog>
                )}
            />

            {sel ? (
                <CorsoPlayer corso={sel} onBack={() => { setSel(null); load(); }} />
            ) : list === null ? <Loading /> : list.length === 0 ? <Empty message="Nessun corso disponibile" /> : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {list.map((c) => (
                        <Card key={c.id} className="border-slate-200 hover:shadow-md transition-shadow cursor-pointer overflow-hidden"
                              onClick={() => setSel(c)} data-testid={`corso-${c.id}`}>
                            <div className="h-32 bg-gradient-to-br from-sky-700 to-slate-900 flex items-center justify-center">
                                <GraduationCap size={32} className="text-sky-200" />
                            </div>
                            <div className="p-4">
                                <div className="font-medium text-slate-900 mb-1">{c.titolo}</div>
                                {c.categoria && <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-2">{c.categoria}</div>}
                                {c.descrizione && <div className="text-xs text-slate-600 line-clamp-2 mb-3">{c.descrizione}</div>}
                                {c.progresso && (
                                    <div>
                                        <div className="w-full bg-slate-100 rounded-full h-1.5 overflow-hidden">
                                            <div className="h-full bg-sky-600" style={{ width: `${c.progresso.percentuale}%` }} />
                                        </div>
                                        <div className="flex items-center justify-between mt-1.5">
                                            <span className="text-xs text-slate-500 num">{c.progresso.percentuale}%</span>
                                            {c.progresso.completato && (
                                                <span className="badge badge-success inline-flex items-center gap-1">
                                                    <CheckCircle2 size={10} /> completato
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                )}
                            </div>
                        </Card>
                    ))}
                </div>
            )}
        </div>
    );
}

function CorsoPlayer({ corso, onBack }) {
    const [progresso, setProgresso] = useState(corso.progresso);

    // utility: estrai videoId YouTube
    const ytId = (() => {
        if (!corso.video_url) return null;
        const m = corso.video_url.match(/(?:v=|youtu\.be\/|embed\/)([\w-]+)/);
        return m ? m[1] : null;
    })();

    // tracking semplice ogni 5s mentre la pagina è aperta
    useEffect(() => {
        if (!corso.id) return;
        let secondi = (progresso?.secondi_visti || 0);
        const dur = (corso.durata_minuti || 10) * 60;
        const t = setInterval(async () => {
            secondi += 5;
            if (secondi > dur) secondi = dur;
            try {
                const r = await api.post(`/corsi/${corso.id}/progresso`, {
                    secondi_visti: secondi,
                    durata_totale_sec: dur,
                    ultima_posizione_sec: secondi,
                });
                setProgresso(r.data);
                if (r.data.completato) clearInterval(t);
        } catch (err) { console.warn("progresso corso:", err?.message || err); }
        }, 5000);
        return () => clearInterval(t);
        // eslint-disable-next-line
    }, [corso.id]);

    return (
        <div className="space-y-4" data-testid="corso-player">
            <Button variant="outline" onClick={onBack}>← Torna ai corsi</Button>

            <Card className="border-slate-200 overflow-hidden">
                <div className="aspect-video bg-black flex items-center justify-center">
                    {ytId ? (
                        <iframe
                            data-testid="corso-iframe"
                            title={corso.titolo}
                            src={`https://www.youtube.com/embed/${ytId}?rel=0`}
                            className="w-full h-full"
                            frameBorder="0"
                            allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture"
                            allowFullScreen
                        />
                    ) : corso.video_url ? (
                        <video src={corso.video_url} controls className="w-full h-full" data-testid="corso-video" />
                    ) : (
                        <div className="text-slate-400 flex items-center gap-2">
                            <Play size={28} /> Nessun video collegato
                        </div>
                    )}
                </div>
                <div className="p-5">
                    <h2 className="text-xl font-semibold text-slate-900">{corso.titolo}</h2>
                    {corso.categoria && <div className="text-xs uppercase tracking-wider text-slate-500 mt-1">{corso.categoria}</div>}
                    {corso.descrizione && <p className="text-sm text-slate-700 mt-3 whitespace-pre-line">{corso.descrizione}</p>}

                    {progresso && (
                        <div className="mt-4 pt-4 border-t border-slate-100">
                            <div className="flex items-center justify-between mb-2">
                                <div className="text-xs text-slate-500">Avanzamento visualizzazione</div>
                                <div className="text-sm font-medium num">{progresso.percentuale}%</div>
                            </div>
                            <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
                                <div className="h-full bg-sky-600 transition-all" style={{ width: `${progresso.percentuale}%` }} />
                            </div>
                        </div>
                    )}
                </div>
            </Card>
        </div>
    );
}

function CorsoForm({ onClose }) {
    const [f, setF] = useState({
        titolo: "", descrizione: "", categoria: "", video_url: "",
        durata_minuti: 10, visibile_ruoli: ["dipendente", "collaboratore"], pubblicato: true,
    });
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
    const toggleRuolo = (r) => setF((p) => ({
        ...p,
        visibile_ruoli: p.visibile_ruoli.includes(r)
            ? p.visibile_ruoli.filter((x) => x !== r)
            : [...p.visibile_ruoli, r],
    }));

    const save = async () => {
        if (!f.titolo) { toast.error("Titolo obbligatorio"); return; }
        try {
            await api.post("/corsi", { ...f, durata_minuti: parseInt(f.durata_minuti) || 10 });
            toast.success("Corso creato"); onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <DialogContent className="max-w-xl">
            <DialogHeader><DialogTitle>Nuovo corso</DialogTitle></DialogHeader>
            <div className="space-y-3 py-2">
                <div><Label>Titolo *</Label><Input data-testid="corso-titolo-input" value={f.titolo} onChange={(e) => set("titolo", e.target.value)} /></div>
                <div className="grid grid-cols-2 gap-3">
                    <div><Label>Categoria</Label><Input value={f.categoria} onChange={(e) => set("categoria", e.target.value)} /></div>
                    <div><Label>Durata (minuti)</Label><Input type="number" value={f.durata_minuti} onChange={(e) => set("durata_minuti", e.target.value)} /></div>
                </div>
                <div><Label>Link video (YouTube / Vimeo / .mp4)</Label><Input value={f.video_url} onChange={(e) => set("video_url", e.target.value)} placeholder="https://www.youtube.com/watch?v=..." /></div>
                <div><Label>Descrizione</Label><Textarea rows={3} value={f.descrizione} onChange={(e) => set("descrizione", e.target.value)} /></div>
                <div>
                    <Label>Visibile ai ruoli</Label>
                    <div className="flex gap-2 mt-1">
                        {["admin", "collaboratore", "dipendente", "cliente"].map((r) => (
                            <button
                                key={r}
                                type="button"
                                onClick={() => toggleRuolo(r)}
                                className={`px-3 py-1 rounded-md text-xs border ${f.visibile_ruoli.includes(r) ? "bg-sky-700 text-white border-sky-700" : "bg-white text-slate-700 border-slate-300"}`}
                            >
                                {r}
                            </button>
                        ))}
                    </div>
                </div>
            </div>
            <DialogFooter>
                <Button data-testid="corso-save-button" onClick={save} className="bg-sky-700 hover:bg-sky-800">Crea corso</Button>
            </DialogFooter>
        </DialogContent>
    );
}
