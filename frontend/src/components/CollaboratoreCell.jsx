/**
 * CollaboratoreCell — mostra avatar tondo (20px) + nome del collaboratore.
 * Usato nelle liste Polizze/Titoli/Sinistri per dare riconoscibilità al team.
 */
import { API_BASE } from "@/lib/api";

export default function CollaboratoreCell({ nome, avatarUrl, size = 20 }) {
    if (!nome) return <span className="text-slate-400">—</span>;
    const initials = nome.split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase();
    const fullUrl = avatarUrl
        ? (avatarUrl.startsWith("http") ? avatarUrl : `${API_BASE.replace("/api", "")}${avatarUrl}`)
        : null;
    return (
        <div className="inline-flex items-center gap-1.5">
            {fullUrl ? (
                <img src={fullUrl} alt="" width={size} height={size}
                    className="rounded-full object-cover border border-white shadow-sm shrink-0"
                    style={{ width: size, height: size }} />
            ) : (
                <span
                    className="rounded-full bg-gradient-to-br from-sky-200 to-indigo-300 text-sky-900 font-semibold flex items-center justify-center shrink-0"
                    style={{ width: size, height: size, fontSize: Math.max(9, size * 0.42) }}
                    aria-hidden
                >
                    {initials || "?"}
                </span>
            )}
            <span className="truncate">{nome}</span>
        </div>
    );
}
