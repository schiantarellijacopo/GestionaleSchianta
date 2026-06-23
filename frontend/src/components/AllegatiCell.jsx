import { useEffect, useRef, useState } from "react";
import { api, API_BASE } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
    Popover, PopoverContent, PopoverTrigger,
} from "@/components/ui/popover";
import { Paperclip, Upload, Trash2, Eye, Loader2 } from "lucide-react";
import { toast } from "sonner";

/**
 * Cella riutilizzabile per gestire gli allegati di un'entità contabile.
 *
 * Props:
 *  - entita_tipo: "movimento" | "titolo" | ...
 *  - entita_id:   string
 *  - count:       numero già noto (dal payload). Se non passato fa fetch.
 *  - canEdit:     bool (se può uploadare/cancellare)
 *  - onChange:    callback dopo upload/delete (per ricaricare la lista padre)
 *  - hint:        testo placeholder nel pulsante upload (es. "Allega ricevuta")
 *  - compact:     bool (icona piccola per uso inline in tabella)
 */
export default function AllegatiCell({
    entita_tipo, entita_id, count, canEdit = true, onChange, hint, compact = true,
}) {
    const [open, setOpen] = useState(false);
    const [items, setItems] = useState(null);
    const [uploading, setUploading] = useState(false);
    const inputRef = useRef(null);

    const load = async () => {
        const r = await api.get("/allegati", { params: { entita_tipo, entita_id } });
        setItems(r.data);
    };
    useEffect(() => {
        if (open) load();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, entita_id]);

    const upload = async (file) => {
        if (!file) return;
        setUploading(true);
        try {
            const fd = new FormData();
            fd.append("file", file);
            await api.post(
                `/allegati?entita_tipo=${entita_tipo}&entita_id=${entita_id}`,
                fd, { headers: { "Content-Type": "multipart/form-data" } }
            );
            toast.success("Allegato caricato");
            await load();
            onChange?.();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore upload");
        } finally {
            setUploading(false);
            if (inputRef.current) inputRef.current.value = "";
        }
    };

    const rimuovi = async (aid) => {
        if (!window.confirm("Eliminare l'allegato?")) return;
        try {
            await api.delete(`/allegati/${aid}`);
            toast.success("Allegato eliminato");
            await load();
            onChange?.();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        }
    };

    const downloadUrl = (aid) => `${API_BASE}/allegati/${aid}/download`;

    const effectiveCount = items === null ? count ?? 0 : items.filter((i) => !i.is_deleted).length;

    return (
        <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger asChild>
                <button
                    type="button"
                    className={`inline-flex items-center gap-1 ${
                        effectiveCount > 0
                            ? "text-sky-700 hover:text-sky-900"
                            : "text-slate-400 hover:text-sky-700"
                    } transition-colors`}
                    data-testid={`allegati-trigger-${entita_id}`}
                    title={effectiveCount > 0 ? `${effectiveCount} allegato/i` : "Allega documento"}
                >
                    <Paperclip size={compact ? 14 : 16} className={effectiveCount > 0 ? "fill-sky-100" : ""} />
                    {effectiveCount > 0 && <span className="text-xs font-medium">{effectiveCount}</span>}
                </button>
            </PopoverTrigger>
            <PopoverContent className="w-80 p-3" data-testid={`allegati-popover-${entita_id}`}>
                <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
                    Allegati ({effectiveCount})
                </div>
                {items === null ? (
                    <div className="py-3 text-center text-xs text-slate-400">
                        <Loader2 size={14} className="inline animate-spin mr-1" /> Caricamento...
                    </div>
                ) : items.length === 0 ? (
                    <div className="py-3 text-xs text-center text-slate-400">Nessun allegato</div>
                ) : (
                    <ul className="space-y-1 mb-2 max-h-60 overflow-y-auto">
                        {items.map((it) => (
                            <li
                                key={it.id}
                                className="flex items-center gap-2 text-xs p-1.5 rounded hover:bg-slate-50"
                                data-testid={`allegato-${it.id}`}
                            >
                                <Paperclip size={12} className="text-slate-400 shrink-0" />
                                <div className="flex-1 truncate" title={it.nome_file}>{it.nome_file}</div>
                                <a
                                    href={downloadUrl(it.id)} target="_blank" rel="noreferrer"
                                    className="text-sky-700 hover:text-sky-900" title="Apri"
                                >
                                    <Eye size={13} />
                                </a>
                                {canEdit && (
                                    <button
                                        onClick={() => rimuovi(it.id)}
                                        className="text-rose-500 hover:text-rose-700"
                                        title="Elimina"
                                        data-testid={`allegato-del-${it.id}`}
                                    >
                                        <Trash2 size={13} />
                                    </button>
                                )}
                            </li>
                        ))}
                    </ul>
                )}
                {canEdit && (
                    <>
                        <input
                            ref={inputRef} type="file" className="hidden"
                            onChange={(e) => upload(e.target.files?.[0])}
                            data-testid={`allegati-input-${entita_id}`}
                        />
                        <Button
                            type="button" size="sm" variant="outline"
                            className="w-full" disabled={uploading}
                            onClick={() => inputRef.current?.click()}
                            data-testid={`allegati-upload-${entita_id}`}
                        >
                            {uploading
                                ? <><Loader2 size={13} className="animate-spin mr-1" /> Caricamento...</>
                                : <><Upload size={13} className="mr-1" /> {hint || "Carica file"}</>
                            }
                        </Button>
                    </>
                )}
            </PopoverContent>
        </Popover>
    );
}
