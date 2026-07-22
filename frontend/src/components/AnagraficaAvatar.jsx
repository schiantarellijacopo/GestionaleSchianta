import { useRef, useState } from "react";
import { api } from "@/lib/api";
import { User, Building2, Home, Church, Camera, Trash2, Loader2 } from "lucide-react";
import { toast } from "sonner";

/**
 * Avatar riusabile per Anagrafica.
 * Mostra foto/logo con fallback icona differenziato per tipologia soggetto.
 *
 * Props:
 * - ana: oggetto anagrafica {id, tipo, sotto_tipo, avatar_url, ragione_sociale, nome, cognome}
 * - size: "sm" (32px) | "md" (64px) | "lg" (80px) | "xl" (96px)
 * - editable: se true mostra overlay camera/trash per upload/delete
 * - onUpdated(url|null): callback dopo upload/delete
 */
const SIZES = {
    sm: { px: 32, icon: 16, ring: "ring-1", overlay: 12, text: "text-[10px]" },
    md: { px: 64, icon: 26, ring: "ring-2", overlay: 14, text: "text-sm" },
    lg: { px: 80, icon: 34, ring: "ring-2", overlay: 16, text: "text-base" },
    xl: { px: 96, icon: 40, ring: "ring-2", overlay: 18, text: "text-lg" },
};

const TYPE_STYLE = {
    persona_fisica: { icon: User, bg: "bg-sky-100", color: "text-sky-700", ring: "ring-sky-200" },
    persona_giuridica: { icon: Building2, bg: "bg-violet-100", color: "text-violet-700", ring: "ring-violet-200" },
    condominio: { icon: Home, bg: "bg-amber-100", color: "text-amber-700", ring: "ring-amber-200" },
    parrocchia: { icon: Church, bg: "bg-rose-100", color: "text-rose-700", ring: "ring-rose-200" },
    onlus: { icon: Church, bg: "bg-emerald-100", color: "text-emerald-700", ring: "ring-emerald-200" },
    asd: { icon: Building2, bg: "bg-teal-100", color: "text-teal-700", ring: "ring-teal-200" },
};

function initialsOf(ana) {
    const rs = (ana?.ragione_sociale || "").trim();
    if (ana?.tipo === "persona_fisica" && (ana?.nome || ana?.cognome)) {
        return ((ana?.nome?.[0] || "") + (ana?.cognome?.[0] || "")).toUpperCase();
    }
    return (rs.split(/\s+/).map((w) => w[0] || "").join("").slice(0, 2) || "?").toUpperCase();
}

export default function AnagraficaAvatar({ ana, size = "md", editable = false, onUpdated }) {
    const s = SIZES[size] || SIZES.md;
    const key = ana?.sotto_tipo || (ana?.tipo === "persona_fisica" ? "persona_fisica" : "persona_giuridica");
    const style = TYPE_STYLE[key] || TYPE_STYLE.persona_fisica;
    const Icon = style.icon;
    const inputRef = useRef();
    const [uploading, setUploading] = useState(false);

    const doUpload = async (file) => {
        if (!file) return;
        if (file.size > 5 * 1024 * 1024) { toast.error("Max 5MB"); return; }
        const fd = new FormData();
        fd.append("file", file);
        setUploading(true);
        try {
            const r = await api.post(`/anagrafiche/${ana.id}/avatar`, fd,
                { headers: { "Content-Type": "multipart/form-data" } });
            toast.success("Avatar aggiornato");
            onUpdated && onUpdated(r.data.avatar_url);
        } catch (e) { toast.error(e?.response?.data?.detail || "Errore upload"); }
        finally { setUploading(false); }
    };

    const doDelete = async (e) => {
        e.stopPropagation();
        if (!window.confirm("Rimuovere l'immagine?")) return;
        try {
            await api.delete(`/anagrafiche/${ana.id}/avatar`);
            toast.success("Immagine rimossa");
            onUpdated && onUpdated(null);
        } catch (err) { toast.error(err?.response?.data?.detail || "Errore"); }
    };

    return (
        <div className="relative inline-block group" style={{ width: s.px, height: s.px }}
            data-testid={`anagrafica-avatar-${ana?.id || "unknown"}`}>
            {ana?.avatar_url ? (
                <img src={ana.avatar_url} alt=""
                    className={`w-full h-full object-cover rounded-full ${s.ring} ${style.ring} ring-offset-2 ring-offset-white`} />
            ) : (
                <div className={`w-full h-full rounded-full ${style.bg} ${style.color} ${s.ring} ${style.ring} ring-offset-2 ring-offset-white flex items-center justify-center font-bold`}>
                    {size === "sm" ? (
                        <span className={s.text}>{initialsOf(ana)}</span>
                    ) : (
                        <Icon size={s.icon} />
                    )}
                </div>
            )}
            {editable && (
                <>
                    <input ref={inputRef} type="file" accept="image/*" className="hidden"
                        onChange={(e) => doUpload(e.target.files?.[0])}
                        data-testid={`avatar-upload-input-${ana?.id}`} />
                    <button type="button" onClick={() => inputRef.current?.click()}
                        disabled={uploading}
                        className="absolute bottom-0 right-0 p-1.5 rounded-full bg-slate-900 text-white shadow-lg opacity-0 group-hover:opacity-100 transition-opacity"
                        title="Carica/sostituisci immagine"
                        data-testid={`avatar-upload-btn-${ana?.id}`}>
                        {uploading ? <Loader2 size={s.overlay} className="animate-spin" /> : <Camera size={s.overlay} />}
                    </button>
                    {ana?.avatar_url && (
                        <button type="button" onClick={doDelete}
                            className="absolute top-0 right-0 p-1 rounded-full bg-rose-600 text-white shadow-lg opacity-0 group-hover:opacity-100 transition-opacity"
                            title="Rimuovi immagine"
                            data-testid={`avatar-delete-btn-${ana?.id}`}>
                            <Trash2 size={s.overlay - 2} />
                        </button>
                    )}
                </>
            )}
        </div>
    );
}
