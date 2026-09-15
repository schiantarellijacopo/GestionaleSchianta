import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { UserCog } from "lucide-react";
import { toast } from "sonner";

// Cache globale per non rifetch la lista a ogni mount
let _cacheUsers = null;

/**
 * Selettore inline del collaboratore responsabile.
 * Uso: <CollaboratoreInlineSelect entita="anagrafiche" id={ana.id}
 *                                  value={ana.collaboratore_id}
 *                                  onSaved={onReload} canEdit={canEdit} />
 * Salva con PUT /{entita}/{id} { collaboratore_id }.
 */
export default function CollaboratoreInlineSelect({ entita, id, value, onSaved, canEdit = true, label = "Operatore", fallbackName = null }) {
    const [users, setUsers] = useState(_cacheUsers || []);
    const [editing, setEditing] = useState(false);
    const [saving, setSaving] = useState(false);
    const [selValue, setSelValue] = useState(value || "");

    useEffect(() => { setSelValue(value || ""); }, [value]);

    useEffect(() => {
        if (_cacheUsers) return;
        api.get("/auth/users").then((r) => {
            _cacheUsers = r.data.filter((u) => ["admin", "collaboratore", "dipendente"].includes(u.role));
            setUsers(_cacheUsers);
        }).catch(() => {});
    }, []);

    const currentUser = users.find((u) => u.id === value);
    const displayName = currentUser?.name || currentUser?.email || fallbackName
        || (value ? "(operatore non trovato)" : "—");

    const save = async (newId) => {
        setSaving(true);
        try {
            await api.put(`/${entita}/${id}`, { collaboratore_id: newId || null });
            toast.success("Operatore aggiornato");
            setEditing(false);
            onSaved && onSaved();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore salvataggio operatore");
        } finally { setSaving(false); }
    };

    if (!editing) {
        return (
            <button
                type="button"
                onClick={() => canEdit && setEditing(true)}
                disabled={!canEdit || saving}
                className={`inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border transition-colors ${
                    currentUser
                        ? "bg-sky-50 border-sky-200 text-sky-800 hover:bg-sky-100"
                        : "bg-slate-100 border-slate-200 text-slate-500 hover:bg-slate-200"
                } ${canEdit ? "cursor-pointer" : "cursor-default"}`}
                data-testid="collaboratore-inline-display"
                title={canEdit ? "Click per cambiare l'operatore" : ""}
            >
                <UserCog size={12} />
                <span className="font-medium">{label}:</span>
                <span>{saving ? "salvataggio…" : displayName}</span>
                {currentUser?.attivo === false && (
                    <span className="ml-1 text-[9px] uppercase font-bold text-amber-700">(inattivo)</span>
                )}
                {canEdit && <span className="text-sky-600 text-[10px] ml-1">✏</span>}
            </button>
        );
    }

    return (
        <div className="inline-flex items-center gap-1.5">
            <select
                autoFocus
                value={selValue}
                onChange={(e) => setSelValue(e.target.value)}
                onBlur={(e) => { if (!e.relatedTarget) save(selValue); }}
                className="text-xs border border-sky-300 rounded px-2 py-1 bg-white text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-200"
                data-testid="collaboratore-inline-select"
            >
                <option value="" className="text-slate-800">— Nessuno —</option>
                {users.filter((u) => u.attivo !== false || u.id === selValue).map((u) => (
                    <option key={u.id} value={u.id} className="text-slate-800">
                        {u.name || u.email}{u.attivo === false ? " (inattivo)" : ""}
                    </option>
                ))}
            </select>
            <button
                type="button"
                onClick={() => save(selValue)}
                className="text-[11px] px-2 py-1 bg-sky-700 hover:bg-sky-800 text-white rounded"
                data-testid="collaboratore-inline-save"
            >
                Salva
            </button>
            <button
                type="button"
                onClick={() => { setEditing(false); setSelValue(value || ""); }}
                className="text-[11px] px-2 py-1 text-slate-500 hover:text-slate-800"
                data-testid="collaboratore-inline-cancel"
            >
                Annulla
            </button>
        </div>
    );
}
