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
import { Video, Plus, Play, CheckCircle2, Send, Mail, MessageCircle,
         Smartphone, Loader2, Trash2 } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

export default function Corsi() {
    const { user } = useAuth();
    const [list, setList] = useState(null);
    const [sel, setSel] = useState(null);
    const [open, setOpen] = useState(false);
    const [inviaVideo, setInviaVideo] = useState(null);
    const canCreate = ["admin", "collaboratore"].includes(user?.role);

    const load = () => api.get("/corsi").then((r) => setList(r.data));
    useEffect(() => { load(); }, []);

    const togglePubblicaCliente = async (c) => {
        const nuoviRuoli = (c.visibile_ruoli || []).includes("cliente")
            ? (c.visibile_ruoli || []).filter((r) => r !== "cliente")
            : [...(c.visibile_ruoli || []), "cliente"];
        try {
            await api.put(`/corsi/${c.id}`, { visibile_ruoli: nuoviRuoli });
            toast.success(nuoviRuoli.includes("cliente")
                ? "Pubblicato sull'App Cliente"
                : "Rimosso dall'App Cliente");
            await load();
        } catch (e) { toast.error(e.response?.data?.detail || e.message); }
    };

    const elimina = async (c) => {
        if (!window.confirm(`Eliminare il video «${c.titolo}»?`)) return;
        try {
            await api.delete(`/corsi/${c.id}`);
            toast.success("Video eliminato");
            await load();
        } catch (e) { toast.error(e.response?.data?.detail || e.message); }
    };

    return (
        <div data-testid="corsi-page">
            <PageHeader
                title="Video"
                subtitle="Video formativi e informativi da mostrare al team o inviare ai clienti (App / Email / WhatsApp)"
                actions={canCreate && (
                    <Dialog open={open} onOpenChange={setOpen}>
                        <DialogTrigger asChild>
                            <Button data-testid="corso-new-button" className="bg-sky-700 hover:bg-sky-800">
                                <Plus size={14} className="mr-1" /> Nuovo video
                            </Button>
                        </DialogTrigger>
                        <CorsoForm onClose={() => { setOpen(false); load(); }} />
                    </Dialog>
                )}
            />

            {sel ? (
                <CorsoPlayer corso={sel} onBack={() => { setSel(null); load(); }} />
            ) : list === null ? <Loading /> : list.length === 0 ? <Empty message="Nessun video disponibile" /> : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {list.map((c) => {
                        const suApp = (c.visibile_ruoli || []).includes("cliente");
                        return (
                            <Card key={c.id} className="border-slate-200 hover:shadow-md transition-shadow overflow-hidden group"
                                  data-testid={`corso-${c.id}`}>
                                <div className="h-32 bg-gradient-to-br from-sky-700 to-slate-900 flex items-center justify-center cursor-pointer relative"
                                     onClick={() => setSel(c)}>
                                    <Video size={32} className="text-sky-200" />
                                    {suApp && (
                                        <span className="absolute top-2 right-2 bg-emerald-500 text-white text-[9px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wide"
                                              data-testid={`corso-badge-app-${c.id}`}>
                                            <Smartphone size={9} className="inline mr-0.5" /> Su App
                                        </span>
                                    )}
                                </div>
                                <div className="p-4">
                                    <div className="font-medium text-slate-900 mb-1 cursor-pointer hover:text-sky-700"
                                         onClick={() => setSel(c)}>{c.titolo}</div>
                                    {c.categoria && <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-2">{c.categoria}</div>}
                                    {c.descrizione && <div className="text-xs text-slate-600 line-clamp-2 mb-3">{c.descrizione}</div>}
                                    {c.progresso && (
                                        <div className="mb-3">
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
                                    {/* AZIONI: pubblica sull'App / invia via email/WhatsApp */}
                                    {canCreate && (
                                        <div className="flex flex-wrap gap-1.5 pt-2 border-t border-slate-100">
                                            <button
                                                onClick={() => togglePubblicaCliente(c)}
                                                title={suApp ? "Rimuovi dall'App Cliente" : "Pubblica sull'App Cliente"}
                                                className={`flex items-center gap-1 text-[10px] font-semibold px-2 py-1 rounded border transition ${suApp
                                                    ? "bg-emerald-50 border-emerald-300 text-emerald-700 hover:bg-emerald-100"
                                                    : "bg-white border-slate-300 text-slate-600 hover:bg-slate-50"}`}
                                                data-testid={`corso-pubblica-${c.id}`}>
                                                <Smartphone size={11} /> {suApp ? "Su App" : "Pubblica App"}
                                            </button>
                                            <button
                                                onClick={() => setInviaVideo({ ...c, canale: "email" })}
                                                title="Invia questo video a un cliente via email"
                                                className="flex items-center gap-1 text-[10px] font-semibold px-2 py-1 rounded border bg-white border-slate-300 text-slate-600 hover:bg-blue-50 hover:border-blue-300 hover:text-blue-700 transition"
                                                data-testid={`corso-email-${c.id}`}>
                                                <Mail size={11} /> Email
                                            </button>
                                            <button
                                                onClick={() => setInviaVideo({ ...c, canale: "whatsapp" })}
                                                title="Invia questo video a un cliente via WhatsApp"
                                                className="flex items-center gap-1 text-[10px] font-semibold px-2 py-1 rounded border bg-white border-slate-300 text-slate-600 hover:bg-emerald-50 hover:border-emerald-300 hover:text-emerald-700 transition"
                                                data-testid={`corso-whatsapp-${c.id}`}>
                                                <MessageCircle size={11} /> WhatsApp
                                            </button>
                                            <button
                                                onClick={() => elimina(c)}
                                                title="Elimina video"
                                                className="ml-auto flex items-center gap-1 text-[10px] font-semibold px-2 py-1 rounded border bg-white border-slate-200 text-slate-400 hover:bg-rose-50 hover:border-rose-300 hover:text-rose-600 transition"
                                                data-testid={`corso-delete-${c.id}`}>
                                                <Trash2 size={11} />
                                            </button>
                                        </div>
                                    )}
                                </div>
                            </Card>
                        );
                    })}
                </div>
            )}

            {inviaVideo && (
                <InviaVideoDialog
                    corso={inviaVideo}
                    canaleIniziale={inviaVideo.canale}
                    onClose={() => setInviaVideo(null)}
                />
            )}
        </div>
    );
}

/**
 * Dialog di invio video a un cliente via email o WhatsApp.
 * Ricerca cliente con autocomplete + selezione canale + messaggio custom.
 */
function InviaVideoDialog({ corso, canaleIniziale, onClose }) {
    const [canale, setCanale] = useState(canaleIniziale || "email");
    const [q, setQ] = useState("");
    const [clienti, setClienti] = useState([]);
    const [sel, setSel] = useState(null);
    const [messaggio, setMessaggio] = useState("");
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        if (!q || q.length < 2) { setClienti([]); return; }
        const t = setTimeout(async () => {
            try {
                const r = await api.get(`/anagrafiche`, { params: { q, limit: 8 } });
                const items = Array.isArray(r.data) ? r.data : (r.data?.items || []);
                setClienti(items);
            } catch (err) { console.warn("search:", err); }
        }, 300);
        return () => clearTimeout(t);
    }, [q]);

    useEffect(() => {
        if (sel) {
            const nome = sel.ragione_sociale || sel.cognome_nome ||
                        `${sel.cognome || ""} ${sel.nome || ""}`.trim() || "cliente";
            setMessaggio(
                `Ciao ${nome},\n\nti condividiamo il video «${corso.titolo}» che potrebbe interessarti:\n\n${corso.video_url || ""}\n\n`
                + (corso.descrizione ? corso.descrizione + "\n\n" : "")
                + "A presto!"
            );
        }
    }, [sel, corso]);

    const invia = async () => {
        if (!sel) { toast.error("Seleziona un cliente"); return; }
        setBusy(true);
        try {
            const r = await api.post(`/corsi/${corso.id}/invia-cliente`, {
                anagrafica_id: sel.id, canale, messaggio,
            });
            toast.success(`Inviato a ${r.data.cliente} via ${r.data.canale}`);
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || e.message);
        } finally { setBusy(false); }
    };

    return (
        <Dialog open onOpenChange={(o) => { if (!o) onClose(); }}>
            <DialogContent className="max-w-lg" data-testid="invia-video-dialog">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2 text-base">
                        <Send size={16} /> Invia video «{corso.titolo}»
                    </DialogTitle>
                </DialogHeader>
                <div className="space-y-3 py-2">
                    {/* Canale */}
                    <div>
                        <Label className="text-xs">Canale</Label>
                        <div className="flex gap-2 mt-1">
                            <button type="button" onClick={() => setCanale("email")}
                                    className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded border text-xs font-semibold transition ${canale === "email"
                                        ? "bg-blue-600 text-white border-blue-600"
                                        : "bg-white text-slate-600 border-slate-300 hover:bg-slate-50"}`}
                                    data-testid="invia-canale-email">
                                <Mail size={13} /> Email
                            </button>
                            <button type="button" onClick={() => setCanale("whatsapp")}
                                    className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded border text-xs font-semibold transition ${canale === "whatsapp"
                                        ? "bg-emerald-600 text-white border-emerald-600"
                                        : "bg-white text-slate-600 border-slate-300 hover:bg-slate-50"}`}
                                    data-testid="invia-canale-whatsapp">
                                <MessageCircle size={13} /> WhatsApp
                            </button>
                        </div>
                    </div>

                    {/* Ricerca cliente */}
                    <div>
                        <Label className="text-xs">Cliente destinatario *</Label>
                        {sel ? (
                            <div className="bg-sky-50 border border-sky-200 rounded p-2 flex items-center justify-between mt-1">
                                <div>
                                    <div className="text-sm font-semibold text-slate-800">
                                        {sel.ragione_sociale || sel.cognome_nome || `${sel.cognome || ""} ${sel.nome || ""}`}
                                    </div>
                                    <div className="text-[11px] text-slate-500">
                                        {canale === "email"
                                            ? (sel.email || sel.pec || "⚠ Nessuna email")
                                            : (sel.cellulare || sel.telefono || "⚠ Nessun cellulare")}
                                    </div>
                                </div>
                                <Button size="sm" variant="ghost" onClick={() => { setSel(null); setQ(""); }}
                                        className="text-xs">Cambia</Button>
                            </div>
                        ) : (
                            <>
                                <Input value={q} onChange={(e) => setQ(e.target.value)}
                                       placeholder="Cerca per nome, cognome, ragione sociale, CF..."
                                       className="text-sm mt-1" data-testid="invia-cliente-search" />
                                {clienti.length > 0 && (
                                    <div className="border border-slate-200 rounded mt-1 max-h-48 overflow-auto bg-white">
                                        {clienti.map((a) => (
                                            <button key={a.id} type="button"
                                                    onClick={() => { setSel(a); setQ(""); setClienti([]); }}
                                                    className="w-full text-left px-3 py-2 text-xs hover:bg-slate-50 border-b border-slate-100 last:border-0"
                                                    data-testid={`invia-cliente-opt-${a.id}`}>
                                                <div className="font-semibold text-slate-800">
                                                    {a.ragione_sociale || a.cognome_nome ||
                                                     `${a.cognome || ""} ${a.nome || ""}`}
                                                </div>
                                                <div className="text-[10px] text-slate-500">
                                                    {a.codice_fiscale || a.partita_iva || ""} · {a.email || a.cellulare || ""}
                                                </div>
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </>
                        )}
                    </div>

                    {/* Messaggio */}
                    <div>
                        <Label className="text-xs">Messaggio</Label>
                        <Textarea rows={6} value={messaggio} onChange={(e) => setMessaggio(e.target.value)}
                                  className="text-xs mt-1" data-testid="invia-messaggio" />
                        <div className="text-[10px] text-slate-500 mt-1">
                            Il link del video è già incluso nel testo.
                        </div>
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose} disabled={busy}>Annulla</Button>
                    <Button onClick={invia} disabled={busy || !sel}
                            className={canale === "whatsapp" ? "bg-emerald-600 hover:bg-emerald-700" : "bg-blue-600 hover:bg-blue-700"}
                            data-testid="invia-submit">
                        {busy ? <Loader2 size={13} className="animate-spin mr-1" /> : <Send size={13} className="mr-1" />}
                        Invia
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
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
    }, [corso.id]);

    return (
        <div className="space-y-4" data-testid="corso-player">
            <Button variant="outline" onClick={onBack}>← Torna ai video</Button>

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
            toast.success("Video creato"); onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <DialogContent className="max-w-xl">
            <DialogHeader><DialogTitle>Nuovo video</DialogTitle></DialogHeader>
            <div className="space-y-3 py-2">
                <div><Label>Titolo *</Label><Input data-testid="corso-titolo-input" value={f.titolo} onChange={(e) => set("titolo", e.target.value)} /></div>
                <div className="grid grid-cols-2 gap-3">
                    <div><Label>Categoria</Label><Input value={f.categoria} onChange={(e) => set("categoria", e.target.value)} /></div>
                    <div><Label>Durata (minuti)</Label><Input type="number" value={f.durata_minuti} onChange={(e) => set("durata_minuti", e.target.value)} /></div>
                </div>
                <div><Label>Link video (YouTube / Vimeo / .mp4)</Label><Input value={f.video_url} onChange={(e) => set("video_url", e.target.value)} placeholder="https://www.youtube.com/watch?v=..." /></div>
                <div><Label>Descrizione</Label><Textarea rows={3} value={f.descrizione} onChange={(e) => set("descrizione", e.target.value)} /></div>
                <div>
                    <Label>Visibile ai ruoli (spunta &quot;cliente&quot; per pubblicarlo sull&apos;App Cliente)</Label>
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
                <Button data-testid="corso-save-button" onClick={save} className="bg-sky-700 hover:bg-sky-800">Crea video</Button>
            </DialogFooter>
        </DialogContent>
    );
}
