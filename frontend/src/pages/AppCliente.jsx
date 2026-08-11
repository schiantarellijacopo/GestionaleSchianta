/**
 * App Cliente — configurazione del Portale Cliente dal CRM.
 * Orari, team, numeri assistenza per compagnia, link utili, video, slogan.
 */
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { PageHeader, Loading } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
    Clock, Users, Phone, Link2, Video, Save, Plus, Trash2, Upload,
    Loader2, MessageSquareQuote,
} from "lucide-react";
import { toast } from "sonner";

export default function AppCliente() {
    const [cfg, setCfg] = useState(null);
    const [saving, setSaving] = useState(false);

    const load = async () => {
        const r = await api.get("/app-cliente/config");
        setCfg(r.data);
    };
    useEffect(() => { load().catch((e) => toast.error("Errore: " + e.message)); }, []);

    const set = (k, v) => setCfg((c) => ({ ...c, [k]: v }));
    const setContatto = (k, v) => setCfg((c) => ({ ...c, contatti: { ...c.contatti, [k]: v } }));

    const salva = async () => {
        setSaving(true);
        try {
            await api.put("/app-cliente/config", {
                contatti: cfg.contatti,
                slogan_portale: cfg.slogan_portale || "",
                orari: cfg.orari,
                team: cfg.team,
                assistenza_compagnie: cfg.assistenza_compagnie,
                servizi: cfg.servizi,
            });
            toast.success("Configurazione App Cliente salvata");
        } catch (e) { toast.error("Errore salvataggio: " + (e.response?.data?.detail || e.message)); }
        finally { setSaving(false); }
    };

    if (!cfg) return <Loading />;

    return (
        <div className="space-y-4" data-testid="app-cliente-page">
            <div className="flex items-start justify-between flex-wrap gap-2">
                <PageHeader title="App Cliente"
                    subtitle="Personalizza i dati mostrati nel Portale Cliente: orari, team, numeri assistenza, link e video" />
                <Button onClick={salva} disabled={saving} className="bg-sky-700 hover:bg-sky-800"
                        data-testid="app-cliente-salva">
                    {saving ? <Loader2 size={14} className="animate-spin mr-1" /> : <Save size={14} className="mr-1" />}
                    Salva tutto
                </Button>
            </div>

            {/* Contatti + slogan */}
            <Card className="p-5 border-slate-200">
                <SecTitle icon={<Phone size={15} />} title="Contatti agenzia (card blu nel portale)" />
                <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                    <Field label="Telefono" value={cfg.contatti?.telefono} onChange={(v) => setContatto("telefono", v)} testid="contatti-telefono" />
                    <Field label="Email" value={cfg.contatti?.email} onChange={(v) => setContatto("email", v)} testid="contatti-email" />
                    <Field label="Sito web" value={cfg.contatti?.sito_web} onChange={(v) => setContatto("sito_web", v)} testid="contatti-sito" />
                    <Field label="Indirizzo" value={cfg.contatti?.indirizzo} onChange={(v) => setContatto("indirizzo", v)} testid="contatti-indirizzo" />
                    <Field label="Comune" value={cfg.contatti?.comune} onChange={(v) => setContatto("comune", v)} testid="contatti-comune" />
                    <Field label="Provincia" value={cfg.contatti?.provincia} onChange={(v) => setContatto("provincia", v)} testid="contatti-provincia" />
                </div>
                <div className="mt-2">
                    <div className="text-[11px] font-semibold text-slate-500 uppercase mb-1 flex items-center gap-1">
                        <MessageSquareQuote size={12} /> Slogan (mostrato sotto il nome agenzia)
                    </div>
                    <Input value={cfg.slogan_portale || ""} onChange={(e) => set("slogan_portale", e.target.value)}
                           placeholder='Es: "Futuro senza sorprese — dal 1970 al tuo fianco"'
                           data-testid="slogan-input" />
                </div>
            </Card>

            {/* Orari */}
            <Card className="p-5 border-slate-200">
                <SecTitle icon={<Clock size={15} />} title="Orari di apertura"
                    onAdd={() => set("orari", [...(cfg.orari || []), { giorni: "", orario: "" }])}
                    addTestid="orari-add" />
                {(cfg.orari || []).length === 0 && <EmptyHint testo='Nessun orario. Es: "Lun-Ven" → "8:30-12:30 / 14:30-18:30"' />}
                {(cfg.orari || []).map((r, i) => (
                    <div key={i} className="flex gap-2 mb-1.5 items-center">
                        <Input value={r.giorni || ""} placeholder="Lun-Ven" className="w-44 h-8 text-xs"
                               onChange={(e) => set("orari", cfg.orari.map((x, j) => j === i ? { ...x, giorni: e.target.value } : x))}
                               data-testid={`orari-giorni-${i}`} />
                        <Input value={r.orario || ""} placeholder="8:30-12:30 / 14:30-18:30" className="flex-1 h-8 text-xs"
                               onChange={(e) => set("orari", cfg.orari.map((x, j) => j === i ? { ...x, orario: e.target.value } : x))}
                               data-testid={`orari-orario-${i}`} />
                        <RemoveBtn onClick={() => set("orari", cfg.orari.filter((_, j) => j !== i))} testid={`orari-remove-${i}`} />
                    </div>
                ))}
            </Card>

            {/* Team */}
            <Card className="p-5 border-slate-200">
                <SecTitle icon={<Users size={15} />} title="Il nostro team"
                    onAdd={() => set("team", [...(cfg.team || []), { nome: "", ruolo: "", telefono: "", email: "" }])}
                    addTestid="team-add" />
                {(cfg.team || []).length === 0 && <EmptyHint testo="Aggiungi i membri del team visibili al cliente." />}
                {(cfg.team || []).map((r, i) => (
                    <div key={i} className="grid grid-cols-2 md:grid-cols-[1fr_1fr_1fr_1fr_auto] gap-2 mb-1.5 items-center">
                        <Input value={r.nome || ""} placeholder="Nome e cognome" className="h-8 text-xs"
                               onChange={(e) => set("team", cfg.team.map((x, j) => j === i ? { ...x, nome: e.target.value } : x))}
                               data-testid={`team-nome-${i}`} />
                        <Input value={r.ruolo || ""} placeholder="Ruolo (es. Titolare, Sinistri)" className="h-8 text-xs"
                               onChange={(e) => set("team", cfg.team.map((x, j) => j === i ? { ...x, ruolo: e.target.value } : x))}
                               data-testid={`team-ruolo-${i}`} />
                        <Input value={r.telefono || ""} placeholder="Telefono" className="h-8 text-xs"
                               onChange={(e) => set("team", cfg.team.map((x, j) => j === i ? { ...x, telefono: e.target.value } : x))}
                               data-testid={`team-telefono-${i}`} />
                        <Input value={r.email || ""} placeholder="Email" className="h-8 text-xs"
                               onChange={(e) => set("team", cfg.team.map((x, j) => j === i ? { ...x, email: e.target.value } : x))}
                               data-testid={`team-email-${i}`} />
                        <RemoveBtn onClick={() => set("team", cfg.team.filter((_, j) => j !== i))} testid={`team-remove-${i}`} />
                    </div>
                ))}
            </Card>

            {/* Numeri assistenza per compagnia */}
            <Card className="p-5 border-slate-200">
                <SecTitle icon={<Phone size={15} />} title="Numeri assistenza per compagnia"
                    onAdd={() => set("assistenza_compagnie", [...(cfg.assistenza_compagnie || []), { compagnia: "", numero: "", note: "" }])}
                    addTestid="assistenza-add" />
                {(cfg.assistenza_compagnie || []).length === 0 && <EmptyHint testo='Es: "Allianz" → "800 686 868" — "Assistenza stradale H24"' />}
                {(cfg.assistenza_compagnie || []).map((r, i) => (
                    <div key={i} className="grid grid-cols-2 md:grid-cols-[1fr_1fr_2fr_auto] gap-2 mb-1.5 items-center">
                        <Input value={r.compagnia || ""} placeholder="Compagnia" className="h-8 text-xs"
                               onChange={(e) => set("assistenza_compagnie", cfg.assistenza_compagnie.map((x, j) => j === i ? { ...x, compagnia: e.target.value } : x))}
                               data-testid={`assistenza-compagnia-${i}`} />
                        <Input value={r.numero || ""} placeholder="Numero verde" className="h-8 text-xs"
                               onChange={(e) => set("assistenza_compagnie", cfg.assistenza_compagnie.map((x, j) => j === i ? { ...x, numero: e.target.value } : x))}
                               data-testid={`assistenza-numero-${i}`} />
                        <Input value={r.note || ""} placeholder="Note (es. assistenza stradale, sinistri...)" className="h-8 text-xs"
                               onChange={(e) => set("assistenza_compagnie", cfg.assistenza_compagnie.map((x, j) => j === i ? { ...x, note: e.target.value } : x))}
                               data-testid={`assistenza-note-${i}`} />
                        <RemoveBtn onClick={() => set("assistenza_compagnie", cfg.assistenza_compagnie.filter((_, j) => j !== i))} testid={`assistenza-remove-${i}`} />
                    </div>
                ))}
            </Card>

            {/* Link utili */}
            <Card className="p-5 border-slate-200">
                <SecTitle icon={<Link2 size={15} />} title="Link utili (card nella sezione Servizi)"
                    onAdd={() => set("servizi", [...(cfg.servizi || []), { nome: "", descrizione: "", url: "" }])}
                    addTestid="servizi-add" />
                {(cfg.servizi || []).length === 0 && <EmptyHint testo="Se vuoto il portale mostra i link di default. Aggiungi link personalizzati (tel:..., https://..., wa.me/...)." />}
                {(cfg.servizi || []).map((r, i) => (
                    <div key={i} className="grid grid-cols-2 md:grid-cols-[1fr_1.5fr_1.5fr_auto] gap-2 mb-1.5 items-center">
                        <Input value={r.nome || ""} placeholder="Nome (es. Denuncia Sinistro)" className="h-8 text-xs"
                               onChange={(e) => set("servizi", cfg.servizi.map((x, j) => j === i ? { ...x, nome: e.target.value } : x))}
                               data-testid={`servizi-nome-${i}`} />
                        <Input value={r.descrizione || ""} placeholder="Descrizione breve" className="h-8 text-xs"
                               onChange={(e) => set("servizi", cfg.servizi.map((x, j) => j === i ? { ...x, descrizione: e.target.value } : x))}
                               data-testid={`servizi-descrizione-${i}`} />
                        <Input value={r.url || ""} placeholder="tel:+39... / https://..." className="h-8 text-xs"
                               onChange={(e) => set("servizi", cfg.servizi.map((x, j) => j === i ? { ...x, url: e.target.value } : x))}
                               data-testid={`servizi-url-${i}`} />
                        <RemoveBtn onClick={() => set("servizi", cfg.servizi.filter((_, j) => j !== i))} testid={`servizi-remove-${i}`} />
                    </div>
                ))}
            </Card>

            {/* Video motivazionale */}
            <VideoSection video={cfg.video} onReload={load} />

            <div className="flex justify-end">
                <Button onClick={salva} disabled={saving} className="bg-sky-700 hover:bg-sky-800"
                        data-testid="app-cliente-salva-bottom">
                    {saving ? <Loader2 size={14} className="animate-spin mr-1" /> : <Save size={14} className="mr-1" />}
                    Salva tutto
                </Button>
            </div>
        </div>
    );
}

function VideoSection({ video, onReload }) {
    const fileRef = useRef(null);
    const [uploading, setUploading] = useState(false);
    const [url, setUrl] = useState(video?.url || "");
    useEffect(() => { setUrl(video?.url || ""); }, [video?.url]);

    const uploadVideo = async (f) => {
        if (!f) return;
        setUploading(true);
        try {
            const fd = new FormData();
            fd.append("file", f);
            await api.post("/librerie/azienda/video-analisi", fd, { headers: { "Content-Type": "multipart/form-data" } });
            toast.success("Video caricato — visibile nel portale in Analisi Personalizzata");
            onReload();
        } catch (e) { toast.error("Errore upload video: " + (e.response?.data?.detail || e.message)); }
        finally { setUploading(false); }
    };
    const salvaUrl = async () => {
        try {
            await api.put("/librerie/azienda", { video_analisi_url: url.trim() });
            toast.success(url.trim() ? "Link video salvato" : "Link video rimosso");
            onReload();
        } catch (e) { toast.error("Errore: " + (e.response?.data?.detail || e.message)); }
    };
    const rimuoviFile = async () => {
        try {
            await api.delete("/librerie/azienda/video-analisi");
            toast.success("Video eliminato");
            onReload();
        } catch (e) { toast.error("Errore: " + (e.response?.data?.detail || e.message)); }
    };

    return (
        <Card className="p-5 border-slate-200">
            <SecTitle icon={<Video size={15} />} title="Video motivazionale (Analisi Personalizzata nel portale)" />
            <div className="flex flex-col md:flex-row gap-2 items-start md:items-center">
                <Input value={url} onChange={(e) => setUrl(e.target.value)}
                       placeholder="Link YouTube o URL video (in alternativa carica un MP4)"
                       className="flex-1 h-9 text-xs" data-testid="video-url-input" />
                <Button size="sm" variant="outline" onClick={salvaUrl} data-testid="video-url-salva">Salva link</Button>
                <input ref={fileRef} type="file" accept="video/mp4,video/webm" className="hidden"
                       onChange={(e) => { uploadVideo(e.target.files?.[0]); e.target.value = ""; }}
                       data-testid="video-file-input" />
                <Button size="sm" variant="outline" disabled={uploading} onClick={() => fileRef.current?.click()}
                        data-testid="video-upload-btn">
                    {uploading ? <Loader2 size={13} className="animate-spin mr-1" /> : <Upload size={13} className="mr-1" />}
                    Carica MP4
                </Button>
            </div>
            {video?.has_file && (
                <div className="mt-2 flex items-center gap-2 text-xs text-slate-600" data-testid="video-file-row">
                    <Video size={13} className="text-emerald-600" />
                    File caricato: <strong>{video.filename || "video.mp4"}</strong>
                    <Button size="sm" variant="ghost" onClick={rimuoviFile} data-testid="video-file-delete">
                        <Trash2 size={13} className="text-rose-600" />
                    </Button>
                </div>
            )}
            {!video?.has_file && !video?.url && (
                <div className="mt-2 text-[11px] text-slate-400 italic">Nessun video configurato: la sezione video non appare nel portale.</div>
            )}
        </Card>
    );
}

function SecTitle({ icon, title, onAdd, addTestid }) {
    return (
        <div className="flex items-center justify-between mb-3">
            <div className="text-sm font-semibold text-slate-800 flex items-center gap-2">{icon} {title}</div>
            {onAdd && (
                <Button size="sm" variant="outline" className="h-7 text-xs" onClick={onAdd} data-testid={addTestid}>
                    <Plus size={13} className="mr-1" /> Aggiungi
                </Button>
            )}
        </div>
    );
}

function Field({ label, value, onChange, testid }) {
    return (
        <div>
            <div className="text-[11px] font-semibold text-slate-500 uppercase mb-1">{label}</div>
            <Input value={value || ""} onChange={(e) => onChange(e.target.value)} className="h-8 text-xs" data-testid={testid} />
        </div>
    );
}

function RemoveBtn({ onClick, testid }) {
    return (
        <Button size="sm" variant="ghost" onClick={onClick} data-testid={testid}>
            <Trash2 size={13} className="text-rose-600" />
        </Button>
    );
}

function EmptyHint({ testo }) {
    return <div className="text-[11px] text-slate-400 italic mb-1">{testo}</div>;
}
