/**
 * Immagini AI — generatore di immagini marketing (Gemini Nano Banana).
 */
import { useEffect, useState } from "react";
import { api, API_BASE, formatError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Loading, PageHeader } from "@/components/Shared";
import { ImagePlus, Loader2, Download, Trash2, Sparkles } from "lucide-react";
import { toast } from "sonner";

const FORMATI = [
    { id: "quadrato", label: "Post 1:1" },
    { id: "verticale", label: "Storia/Reel 9:16" },
    { id: "orizzontale", label: "Banner 16:9" },
];
const STILI = [
    { id: null, label: "Auto" },
    { id: "fotografico", label: "Fotografico" },
    { id: "illustrazione", label: "Illustrazione" },
    { id: "minimal", label: "Minimal" },
    { id: "elegante", label: "Elegante" },
];
const ESEMPI = [
    "Post sulla protezione della casa dai danni atmosferici, famiglia serena davanti a una villetta",
    "Promo polizza auto: auto moderna su strada panoramica italiana al tramonto",
    "Campagna previdenza: coppia di pensionati felice in riva al mare",
];

export default function ImmaginiAI() {
    const [prompt, setPrompt] = useState("");
    const [formato, setFormato] = useState("quadrato");
    const [stile, setStile] = useState(null);
    const [busy, setBusy] = useState(false);
    const [items, setItems] = useState(null);

    const load = () => api.get("/immagini-ai").then((r) => setItems(r.data || []));
    useEffect(() => { load(); }, []);

    const genera = async () => {
        if (!prompt.trim() || busy) return;
        setBusy(true);
        try {
            const r = await api.post("/immagini-ai/genera", { prompt, formato, stile });
            setItems((it) => [r.data, ...(it || [])]);
            toast.success("Immagine generata");
        } catch (e) { toast.error(formatError(e)); }
        finally { setBusy(false); }
    };

    const elimina = async (i) => {
        if (!window.confirm("Eliminare questa immagine?")) return;
        await api.delete(`/immagini-ai/${i.id}`);
        setItems((it) => it.filter((x) => x.id !== i.id));
    };

    const fullUrl = (u) => (u?.startsWith("/api/") ? `${API_BASE.replace(/\/api$/, "")}${u}` : u);

    return (
        <div data-testid="immagini-ai-page" className="space-y-4">
            <PageHeader
                title={<span className="flex items-center gap-2"><ImagePlus className="text-fuchsia-600" /> Immagini AI</span>}
                subtitle="Genera immagini marketing per post, storie e banner — descrivi cosa vuoi, al resto pensa l'AI"
            />

            <Card className="p-4 space-y-3">
                <Textarea value={prompt} onChange={(e) => setPrompt(e.target.value)}
                          placeholder='Descrivi l&apos;immagine — es. "Post sulla polizza casa: famiglia serena davanti a una villetta al tramonto"'
                          rows={3} data-testid="imgai-prompt" />
                <div className="flex flex-wrap items-center gap-4">
                    <div className="flex items-center gap-1.5">
                        <span className="text-[10px] uppercase font-semibold text-slate-500">Formato</span>
                        {FORMATI.map((f) => (
                            <button key={f.id} onClick={() => setFormato(f.id)}
                                    className={`text-xs px-2.5 py-1 rounded-full border ${formato === f.id ? "bg-fuchsia-600 text-white border-fuchsia-600" : "border-slate-300 text-slate-600 hover:bg-slate-50"}`}
                                    data-testid={`imgai-formato-${f.id}`}>
                                {f.label}
                            </button>
                        ))}
                    </div>
                    <div className="flex items-center gap-1.5">
                        <span className="text-[10px] uppercase font-semibold text-slate-500">Stile</span>
                        {STILI.map((s) => (
                            <button key={s.label} onClick={() => setStile(s.id)}
                                    className={`text-xs px-2.5 py-1 rounded-full border ${stile === s.id ? "bg-slate-800 text-white border-slate-800" : "border-slate-300 text-slate-600 hover:bg-slate-50"}`}
                                    data-testid={`imgai-stile-${s.id || "auto"}`}>
                                {s.label}
                            </button>
                        ))}
                    </div>
                    <Button onClick={genera} disabled={busy || !prompt.trim()}
                            className="ml-auto bg-fuchsia-600 hover:bg-fuchsia-700" data-testid="imgai-genera-btn">
                        {busy ? <><Loader2 size={14} className="animate-spin mr-1.5" /> Generazione (10-20s)…</>
                            : <><Sparkles size={14} className="mr-1.5" /> Genera immagine</>}
                    </Button>
                </div>
                {!prompt && (
                    <div className="flex flex-wrap gap-1.5">
                        {ESEMPI.map((e, i) => (
                            <button key={i} onClick={() => setPrompt(e)}
                                    className="text-[11px] px-2 py-0.5 bg-fuchsia-50 border border-fuchsia-200 rounded-full text-fuchsia-700 hover:bg-fuchsia-100"
                                    data-testid={`imgai-esempio-${i}`}>
                                {e.slice(0, 60)}…
                            </button>
                        ))}
                    </div>
                )}
            </Card>

            {items === null ? <Loading /> : items.length === 0 ? (
                <Card className="p-10 text-center text-sm text-slate-400" data-testid="imgai-empty">
                    Nessuna immagine ancora — genera la prima!
                </Card>
            ) : (
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                    {items.map((i) => (
                        <Card key={i.id} className="overflow-hidden group" data-testid={`imgai-card-${i.id}`}>
                            <div className="relative bg-slate-100">
                                <img src={fullUrl(i.url)} alt={i.prompt}
                                     className="w-full aspect-square object-cover" loading="lazy" />
                                <div className="absolute inset-0 bg-black/0 group-hover:bg-black/40 transition-colors flex items-center justify-center gap-2 opacity-0 group-hover:opacity-100">
                                    <a href={fullUrl(i.url)} download target="_blank" rel="noreferrer"
                                       className="p-2 bg-white rounded-full text-slate-700 hover:text-fuchsia-600"
                                       data-testid={`imgai-download-${i.id}`}>
                                        <Download size={15} />
                                    </a>
                                    <button onClick={() => elimina(i)}
                                            className="p-2 bg-white rounded-full text-slate-700 hover:text-rose-600"
                                            data-testid={`imgai-delete-${i.id}`}>
                                        <Trash2 size={15} />
                                    </button>
                                </div>
                            </div>
                            <div className="p-2">
                                <div className="text-[11px] text-slate-600 line-clamp-2" title={i.prompt}>{i.prompt}</div>
                                <div className="text-[9px] text-slate-400 mt-0.5 uppercase">{i.formato}{i.stile ? ` · ${i.stile}` : ""}</div>
                            </div>
                        </Card>
                    ))}
                </div>
            )}
        </div>
    );
}
