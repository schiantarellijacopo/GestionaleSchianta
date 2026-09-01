/**
 * Studio Marketing — Caroselli IG, Video Reel, Siti/Landing AI, Immagini.
 */
import { useEffect, useState } from "react";
import { api, API_BASE, formatError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { PageHeader } from "@/components/Shared";
import ImmaginiAI from "@/pages/ImmaginiAI";
import {
    Megaphone, Images, Clapperboard, Globe, ImagePlus, Loader2, Sparkles,
    Download, Trash2, Copy, Pencil, ExternalLink, Eye, Presentation,
} from "lucide-react";
import { toast } from "sonner";

const fullUrl = (u) => (u?.startsWith("/api/") ? `${API_BASE.replace(/\/api$/, "")}${u}` : u);
const token = () => localStorage.getItem("token") || "";

const dlBlob = async (url, name) => {
    try {
        const r = await api.get(url, { responseType: "blob" });
        const u = URL.createObjectURL(r.data);
        const a = document.createElement("a");
        a.href = u; a.download = name; a.click();
        URL.revokeObjectURL(u);
    } catch { toast.error("Errore download"); }
};

function usePolling(path, deps = []) {
    const [items, setItems] = useState(null);
    const load = () => api.get(path).then((r) => setItems(r.data || []));
    useEffect(() => { load(); }, deps); // eslint-disable-line
    useEffect(() => {
        if (!items?.some((i) => i.stato === "generating")) return;
        const t = setInterval(load, 5000);
        return () => clearInterval(t);
    }, [items]); // eslint-disable-line
    return [items, load];
}

const StatoBadge = ({ s }) => (
    <span className={`text-[10px] uppercase font-semibold px-2 py-0.5 rounded ${
        s.stato === "ready" ? "bg-emerald-100 text-emerald-700"
            : s.stato === "errore" ? "bg-rose-100 text-rose-700" : "bg-amber-100 text-amber-700"
    }`}>
        {s.stato === "generating" ? (s.progress || "In lavorazione…") : s.stato === "ready" ? "Pronto" : "Errore"}
    </span>
);

export default function StudioMarketing() {
    return (
        <div data-testid="studio-marketing-page" className="space-y-4">
            <PageHeader
                title={<span className="flex items-center gap-2"><Megaphone className="text-fuchsia-600" /> Studio Marketing</span>}
                subtitle="Caroselli, video reel, siti web e immagini — descrivi cosa vuoi, l'AI crea tutto"
            />
            <Tabs defaultValue="caroselli">
                <TabsList>
                    <TabsTrigger value="caroselli" data-testid="tab-caroselli"><Images size={13} className="mr-1" /> Caroselli</TabsTrigger>
                    <TabsTrigger value="video" data-testid="tab-video"><Clapperboard size={13} className="mr-1" /> Video Reel</TabsTrigger>
                    <TabsTrigger value="presentazioni" data-testid="tab-presentazioni"><Presentation size={13} className="mr-1" /> Presentazioni</TabsTrigger>
                    <TabsTrigger value="siti" data-testid="tab-siti"><Globe size={13} className="mr-1" /> Siti & Landing</TabsTrigger>
                    <TabsTrigger value="immagini" data-testid="tab-immagini"><ImagePlus size={13} className="mr-1" /> Immagini</TabsTrigger>
                </TabsList>
                <TabsContent value="caroselli"><CaroselliTab /></TabsContent>
                <TabsContent value="video"><VideoTab /></TabsContent>
                <TabsContent value="presentazioni"><PresentazioniTab /></TabsContent>
                <TabsContent value="siti"><SitiTab /></TabsContent>
                <TabsContent value="immagini"><ImmaginiAI embedded /></TabsContent>
            </Tabs>
        </div>
    );
}

// ───────────────────────── CAROSELLI ─────────────────────────
function CaroselliTab() {
    const [items, load] = usePolling("/marketing/caroselli");
    const [argomento, setArgomento] = useState("");
    const [nSlides, setNSlides] = useState(6);
    const [busy, setBusy] = useState(false);

    const genera = async () => {
        if (!argomento.trim()) return;
        setBusy(true);
        try {
            await api.post("/marketing/caroselli/genera", { argomento, n_slides: nSlides });
            toast.success("Carosello in generazione (1-2 minuti)…");
            setArgomento(""); load();
        } catch (e) { toast.error(formatError(e)); }
        finally { setBusy(false); }
    };

    return (
        <div className="space-y-3 mt-3">
            <Card className="p-4 flex flex-wrap items-end gap-3">
                <div className="flex-1 min-w-[280px]">
                    <div className="text-xs font-semibold text-slate-600 mb-1">Argomento del carosello</div>
                    <Input value={argomento} onChange={(e) => setArgomento(e.target.value)}
                           placeholder='es. "5 errori da evitare quando assicuri la casa"'
                           data-testid="car-argomento" />
                </div>
                <div>
                    <div className="text-xs font-semibold text-slate-600 mb-1">Slide</div>
                    <select value={nSlides} onChange={(e) => setNSlides(Number(e.target.value))}
                            className="border border-slate-300 rounded px-2 py-2 text-sm" data-testid="car-n-slides">
                        {[4, 5, 6, 7, 8].map((n) => <option key={n} value={n}>{n}</option>)}
                    </select>
                </div>
                <Button onClick={genera} disabled={busy || !argomento.trim()}
                        className="bg-fuchsia-600 hover:bg-fuchsia-700" data-testid="car-genera-btn">
                    <Sparkles size={14} className="mr-1.5" /> Genera carosello
                </Button>
            </Card>

            {items === null ? <Loader2 className="animate-spin text-slate-400 mx-auto my-8" /> :
                items.length === 0 ? (
                    <Card className="p-10 text-center text-sm text-slate-400" data-testid="car-empty">Nessun carosello ancora.</Card>
                ) : items.map((c) => (
                    <Card key={c.id} className="p-4" data-testid={`car-card-${c.id}`}>
                        <div className="flex items-center gap-3 mb-2">
                            <span className="font-semibold text-slate-800 text-sm flex-1 truncate">{c.argomento}</span>
                            <StatoBadge s={c} />
                            {c.stato === "generating" && <Loader2 size={14} className="animate-spin text-amber-600" />}
                            {c.stato === "ready" && (
                                <>
                                    <Button size="sm" variant="outline" className="h-7 text-xs"
                                            onClick={() => dlBlob(`/marketing/caroselli/${c.id}/zip`, `carosello.zip`)}
                                            data-testid={`car-zip-${c.id}`}>
                                        <Download size={12} className="mr-1" /> ZIP
                                    </Button>
                                    <Button size="sm" variant="outline" className="h-7 text-xs"
                                            onClick={() => { navigator.clipboard.writeText(c.caption || ""); toast.success("Caption copiata"); }}>
                                        <Copy size={12} className="mr-1" /> Caption
                                    </Button>
                                </>
                            )}
                            <button onClick={async () => { if (window.confirm("Eliminare?")) { await api.delete(`/marketing/caroselli/${c.id}`); load(); } }}
                                    className="text-slate-400 hover:text-rose-600"><Trash2 size={14} /></button>
                        </div>
                        {c.stato === "errore" && <div className="text-xs text-rose-600">{c.errore}</div>}
                        {(c.slides || []).length > 0 && (
                            <div className="flex gap-2 overflow-x-auto pb-1">
                                {c.slides.map((s) => (
                                    <a key={s.n} href={fullUrl(s.url)} target="_blank" rel="noreferrer" className="shrink-0">
                                        <img src={fullUrl(s.url)} alt={s.titolo}
                                             className="h-40 w-40 object-cover rounded border border-slate-200 hover:border-fuchsia-400" loading="lazy" />
                                    </a>
                                ))}
                            </div>
                        )}
                        {c.caption && <div className="text-[11px] text-slate-500 mt-2 line-clamp-2">{c.caption}</div>}
                    </Card>
                ))}
        </div>
    );
}

// ───────────────────────── VIDEO ─────────────────────────
function VideoTab() {
    const [items, load] = usePolling("/marketing/video");
    const [argomento, setArgomento] = useState("");
    const [nScene, setNScene] = useState(4);
    const [busy, setBusy] = useState(false);

    const genera = async () => {
        if (!argomento.trim()) return;
        setBusy(true);
        try {
            await api.post("/marketing/video/genera", { argomento, n_scene: nScene });
            toast.success("Reel in generazione (2-3 minuti)…");
            setArgomento(""); load();
        } catch (e) { toast.error(formatError(e)); }
        finally { setBusy(false); }
    };

    return (
        <div className="space-y-3 mt-3">
            <Card className="p-4 flex flex-wrap items-end gap-3">
                <div className="flex-1 min-w-[280px]">
                    <div className="text-xs font-semibold text-slate-600 mb-1">Argomento del reel (formato 9:16 per Instagram/TikTok)</div>
                    <Input value={argomento} onChange={(e) => setArgomento(e.target.value)}
                           placeholder='es. "Perché serve la polizza vita a 40 anni"' data-testid="vid-argomento" />
                </div>
                <div>
                    <div className="text-xs font-semibold text-slate-600 mb-1">Scene (3s l'una)</div>
                    <select value={nScene} onChange={(e) => setNScene(Number(e.target.value))}
                            className="border border-slate-300 rounded px-2 py-2 text-sm" data-testid="vid-n-scene">
                        {[3, 4, 5, 6].map((n) => <option key={n} value={n}>{n}</option>)}
                    </select>
                </div>
                <Button onClick={genera} disabled={busy || !argomento.trim()}
                        className="bg-fuchsia-600 hover:bg-fuchsia-700" data-testid="vid-genera-btn">
                    <Sparkles size={14} className="mr-1.5" /> Genera reel
                </Button>
            </Card>

            {items === null ? <Loader2 className="animate-spin text-slate-400 mx-auto my-8" /> :
                items.length === 0 ? (
                    <Card className="p-10 text-center text-sm text-slate-400" data-testid="vid-empty">Nessun video ancora.</Card>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                        {items.map((v) => (
                            <Card key={v.id} className="p-3" data-testid={`vid-card-${v.id}`}>
                                <div className="flex items-center gap-2 mb-2">
                                    <span className="font-semibold text-slate-800 text-xs flex-1 truncate">{v.argomento}</span>
                                    <StatoBadge s={v} />
                                    <button onClick={async () => { if (window.confirm("Eliminare?")) { await api.delete(`/marketing/video/${v.id}`); load(); } }}
                                            className="text-slate-400 hover:text-rose-600"><Trash2 size={13} /></button>
                                </div>
                                {v.stato === "generating" && (
                                    <div className="aspect-[9/16] max-h-72 bg-slate-100 rounded flex items-center justify-center">
                                        <Loader2 size={22} className="animate-spin text-amber-500" />
                                    </div>
                                )}
                                {v.stato === "errore" && <div className="text-xs text-rose-600">{v.errore}</div>}
                                {v.stato === "ready" && (
                                    <>
                                        <video controls className="w-full max-h-72 rounded bg-black"
                                               src={`${API_BASE}/marketing/video/${v.id}/file?token=${encodeURIComponent(token())}`}
                                               data-testid={`vid-player-${v.id}`} />
                                        <div className="flex items-center gap-2 mt-2">
                                            <a href={`${API_BASE}/marketing/video/${v.id}/file?token=${encodeURIComponent(token())}`}
                                               download className="text-xs text-fuchsia-700 hover:underline inline-flex items-center gap-1">
                                                <Download size={11} /> Scarica MP4 ({v.durata_sec}s)
                                            </a>
                                            {v.caption && (
                                                <button onClick={() => { navigator.clipboard.writeText(v.caption); toast.success("Caption copiata"); }}
                                                        className="text-xs text-slate-500 hover:text-slate-800 inline-flex items-center gap-1">
                                                    <Copy size={11} /> Caption
                                                </button>
                                            )}
                                        </div>
                                    </>
                                )}
                            </Card>
                        ))}
                    </div>
                )}
        </div>
    );
}

// ───────────────────────── PRESENTAZIONI ─────────────────────────
function PresentazioniTab() {
    const [items, load] = usePolling("/marketing/presentazioni");
    const [modalita, setModalita] = useState("argomento");
    const [contenuto, setContenuto] = useState("");
    const [nSlides, setNSlides] = useState("");
    const [stile, setStile] = useState("brand");
    const [busy, setBusy] = useState(false);

    const genera = async () => {
        if (!contenuto.trim()) return;
        setBusy(true);
        try {
            await api.post("/marketing/presentazioni/genera", {
                modalita, contenuto, stile,
                n_slides: nSlides ? Number(nSlides) : null,
            });
            toast.success("Presentazione in generazione…");
            setContenuto(""); load();
        } catch (e) { toast.error(formatError(e)); }
        finally { setBusy(false); }
    };

    return (
        <div className="space-y-3 mt-3">
            <Card className="p-4 space-y-3">
                <div className="flex gap-2 flex-wrap">
                    {[["argomento", "✨ Argomento → l'AI crea tutto"], ["punti", "📝 I miei punti chiave"]].map(([v, l]) => (
                        <button key={v} onClick={() => setModalita(v)}
                                className={`text-xs px-3 py-1.5 rounded-full border ${modalita === v ? "bg-fuchsia-600 text-white border-fuchsia-600" : "border-slate-300 text-slate-600 hover:bg-slate-50"}`}
                                data-testid={`pres-modalita-${v}`}>{l}</button>
                    ))}
                </div>
                <Textarea value={contenuto} onChange={(e) => setContenuto(e.target.value)} rows={modalita === "punti" ? 5 : 2}
                          placeholder={modalita === "punti"
                              ? "Incolla i tuoi punti chiave (uno per riga): l'AI li impagina senza inventare contenuti"
                              : 'es. "Polizza vita per famiglie: perché conviene, garanzie, vantaggi fiscali"'}
                          data-testid="pres-contenuto" />
                <div className="flex flex-wrap items-end gap-3">
                    <div>
                        <div className="text-xs font-semibold text-slate-600 mb-1">Stile grafico</div>
                        <div className="flex gap-2">
                            {[["brand", "🎨 Template pulito"], ["ai", "🖼️ Sfondi AI"]].map(([v, l]) => (
                                <button key={v} onClick={() => setStile(v)}
                                        className={`text-xs px-3 py-1.5 rounded-full border ${stile === v ? "bg-slate-800 text-white border-slate-800" : "border-slate-300 text-slate-600 hover:bg-slate-50"}`}
                                        data-testid={`pres-stile-${v}`}>{l}</button>
                            ))}
                        </div>
                    </div>
                    <div>
                        <div className="text-xs font-semibold text-slate-600 mb-1">N. slide (vuoto = decide l&apos;AI)</div>
                        <Input type="number" min={2} max={40} value={nSlides} onChange={(e) => setNSlides(e.target.value)}
                               placeholder="auto" className="w-24" data-testid="pres-n-slides" />
                    </div>
                    <Button onClick={genera} disabled={busy || !contenuto.trim()}
                            className="bg-fuchsia-600 hover:bg-fuchsia-700 ml-auto" data-testid="pres-genera-btn">
                        <Sparkles size={14} className="mr-1.5" /> Genera presentazione
                    </Button>
                </div>
            </Card>

            {items === null ? <Loader2 className="animate-spin text-slate-400 mx-auto my-8" /> :
                items.length === 0 ? (
                    <Card className="p-10 text-center text-sm text-slate-400" data-testid="pres-empty">Nessuna presentazione ancora.</Card>
                ) : items.map((p) => (
                    <Card key={p.id} className="p-4" data-testid={`pres-card-${p.id}`}>
                        <div className="flex items-center gap-3 mb-2 flex-wrap">
                            <Presentation size={15} className="text-fuchsia-600 shrink-0" />
                            <span className="font-semibold text-slate-800 text-sm flex-1 truncate">{p.titolo}</span>
                            {p.n_slide_finali && <span className="text-[10px] text-slate-400">{p.n_slide_finali} slide</span>}
                            <StatoBadge s={p} />
                            {p.stato === "generating" && <Loader2 size={14} className="animate-spin text-amber-600" />}
                            {p.stato === "ready" && (
                                <>
                                    <Button size="sm" variant="outline" className="h-7 text-xs"
                                            onClick={() => dlBlob(`/marketing/presentazioni/${p.id}/file?fmt=pptx`, "presentazione.pptx")}
                                            data-testid={`pres-pptx-${p.id}`}>
                                        <Download size={12} className="mr-1" /> PPTX
                                    </Button>
                                    <Button size="sm" variant="outline" className="h-7 text-xs"
                                            onClick={() => dlBlob(`/marketing/presentazioni/${p.id}/file?fmt=pdf`, "presentazione.pdf")}
                                            data-testid={`pres-pdf-${p.id}`}>
                                        <Download size={12} className="mr-1" /> PDF
                                    </Button>
                                </>
                            )}
                            <button onClick={async () => { if (window.confirm("Eliminare?")) { await api.delete(`/marketing/presentazioni/${p.id}`); load(); } }}
                                    className="text-slate-400 hover:text-rose-600" data-testid={`pres-del-${p.id}`}><Trash2 size={14} /></button>
                        </div>
                        {p.stato === "errore" && <div className="text-xs text-rose-600">{p.errore}</div>}
                        {(p.slides || []).length > 0 && (
                            <div className="flex gap-2 overflow-x-auto pb-1">
                                {p.slides.map((s) => (
                                    <a key={s.n} href={fullUrl(s.url)} target="_blank" rel="noreferrer" className="shrink-0">
                                        <img src={fullUrl(s.url)} alt={s.titolo}
                                             className="h-28 aspect-video object-cover rounded border border-slate-200 hover:border-fuchsia-400" loading="lazy" />
                                    </a>
                                ))}
                            </div>
                        )}
                    </Card>
                ))}
        </div>
    );
}

// ───────────────────────── SITI ─────────────────────────
function SitiTab() {
    const [items, load] = usePolling("/marketing/siti");
    const [tipo, setTipo] = useState("landing");
    const [descrizione, setDescrizione] = useState("");
    const [busy, setBusy] = useState(false);
    const [preview, setPreview] = useState(null);

    const genera = async () => {
        if (!descrizione.trim()) return;
        setBusy(true);
        try {
            await api.post("/marketing/siti/genera", { tipo, descrizione });
            toast.success("Generazione avviata (30-60s)…");
            setDescrizione(""); load();
        } catch (e) { toast.error(formatError(e)); }
        finally { setBusy(false); }
    };

    const pubblica = async (s) => {
        await api.patch(`/marketing/siti/${s.id}`, { pubblicato: !s.pubblicato });
        toast.success(s.pubblicato ? "Sito ritirato" : "Sito pubblicato!");
        load();
    };

    const modifica = async (s) => {
        const istruzioni = window.prompt("Cosa vuoi modificare? (es. 'colori più caldi, aggiungi sezione RC Auto')");
        if (!istruzioni) return;
        await api.post(`/marketing/siti/${s.id}/modifica`, { istruzioni });
        toast.success("Modifica AI in corso…");
        load();
    };

    const apriPreview = async (s) => {
        const r = await api.get(`/marketing/siti/${s.id}`);
        setPreview(r.data);
    };

    const pubUrl = (s) => `${API_BASE}/marketing/public-sito/${s.slug}`;

    return (
        <div className="space-y-3 mt-3">
            <Card className="p-4 space-y-3">
                <div className="flex gap-2">
                    {[["landing", "Landing page"], ["sito", "Sito completo"]].map(([v, l]) => (
                        <button key={v} onClick={() => setTipo(v)}
                                className={`text-xs px-3 py-1.5 rounded-full border ${tipo === v ? "bg-fuchsia-600 text-white border-fuchsia-600" : "border-slate-300 text-slate-600 hover:bg-slate-50"}`}
                                data-testid={`sito-tipo-${v}`}>{l}</button>
                    ))}
                </div>
                <Textarea value={descrizione} onChange={(e) => setDescrizione(e.target.value)} rows={2}
                          placeholder={tipo === "landing"
                              ? 'es. "Landing per campagna polizza casa: sconto 20% fino a fine mese, obiettivo richiesta preventivo"'
                              : 'es. "Sito dell\'agenzia: chi siamo, servizi auto/casa/vita/previdenza, 3 sedi, contatti"'}
                          data-testid="sito-descrizione" />
                <div className="flex justify-end">
                    <Button onClick={genera} disabled={busy || !descrizione.trim()}
                            className="bg-fuchsia-600 hover:bg-fuchsia-700" data-testid="sito-genera-btn">
                        <Sparkles size={14} className="mr-1.5" /> Genera con AI
                    </Button>
                </div>
            </Card>

            {items === null ? <Loader2 className="animate-spin text-slate-400 mx-auto my-8" /> :
                items.length === 0 ? (
                    <Card className="p-10 text-center text-sm text-slate-400" data-testid="sito-empty">Nessun sito ancora.</Card>
                ) : items.map((s) => (
                    <Card key={s.id} className="p-4" data-testid={`sito-card-${s.id}`}>
                        <div className="flex items-center gap-2 flex-wrap">
                            <Globe size={15} className="text-fuchsia-600 shrink-0" />
                            <div className="flex-1 min-w-[200px]">
                                <div className="font-semibold text-slate-800 text-sm truncate">{s.titolo}</div>
                                <div className="text-[10px] text-slate-400 uppercase">{s.tipo} · /{s.slug}</div>
                            </div>
                            <StatoBadge s={s} />
                            {s.stato === "ready" && (
                                <>
                                    <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => apriPreview(s)}
                                            data-testid={`sito-preview-${s.id}`}>
                                        <Eye size={12} className="mr-1" /> Anteprima
                                    </Button>
                                    <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => modifica(s)}>
                                        <Pencil size={12} className="mr-1" /> Modifica AI
                                    </Button>
                                    <Button size="sm" variant="outline" className="h-7 text-xs"
                                            onClick={() => dlBlob(`/marketing/siti/${s.id}/zip`, `${s.slug}.zip`)}>
                                        <Download size={12} className="mr-1" /> ZIP
                                    </Button>
                                    <Button size="sm"
                                            className={`h-7 text-xs ${s.pubblicato ? "bg-slate-500 hover:bg-slate-600" : "bg-emerald-600 hover:bg-emerald-700"}`}
                                            onClick={() => pubblica(s)} data-testid={`sito-pubblica-${s.id}`}>
                                        {s.pubblicato ? "Ritira" : "Pubblica"}
                                    </Button>
                                </>
                            )}
                            <button onClick={async () => { if (window.confirm("Eliminare il sito?")) { await api.delete(`/marketing/siti/${s.id}`); load(); } }}
                                    className="text-slate-400 hover:text-rose-600"><Trash2 size={14} /></button>
                        </div>
                        {s.stato === "errore" && <div className="text-xs text-rose-600 mt-1">{s.errore}</div>}
                        {s.pubblicato && (
                            <div className="mt-2 flex items-center gap-2 text-xs bg-emerald-50 border border-emerald-200 rounded p-2">
                                <span className="font-mono text-emerald-800 truncate">{pubUrl(s)}</span>
                                <button onClick={() => { navigator.clipboard.writeText(pubUrl(s)); toast.success("URL copiato"); }}
                                        className="text-emerald-600"><Copy size={12} /></button>
                                <a href={pubUrl(s)} target="_blank" rel="noreferrer" className="text-emerald-600"><ExternalLink size={12} /></a>
                                <span className="text-[10px] text-slate-400 ml-auto">Per il tuo dominio: scarica lo ZIP (istruzioni incluse)</span>
                            </div>
                        )}
                    </Card>
                ))}

            {preview && (
                <Dialog open onOpenChange={(v) => !v && setPreview(null)}>
                    <DialogContent className="max-w-5xl h-[85vh] p-0 overflow-hidden" data-testid="sito-preview-dialog">
                        <DialogHeader className="px-4 pt-3 pb-1"><DialogTitle className="text-sm">{preview.titolo}</DialogTitle></DialogHeader>
                        <iframe title="preview" srcDoc={preview.html} className="w-full h-full border-0" sandbox="allow-scripts" />
                    </DialogContent>
                </Dialog>
            )}
        </div>
    );
}
