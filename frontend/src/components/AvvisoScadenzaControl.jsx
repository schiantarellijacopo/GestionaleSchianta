import { useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Bell, BellOff, Check, X } from "lucide-react";

/**
 * Controllo opt-in "Attiva avviso" di scadenza (app + email) per un singolo
 * documento aziendale (compagnia | agenzia_partner | azienda).
 * Si mostra solo quando il documento ha una data di scadenza.
 *
 * props:
 *  - entita: "compagnia" | "agenzia_partner" | "azienda"
 *  - entitaId: id del record (per azienda può essere null/omesso)
 *  - item: documento { id, data_scadenza, avviso_attivo, avviso_giorni }
 *  - onChange(itemId, { avviso_attivo, avviso_giorni }): aggiorna lo stato locale
 */
export default function AvvisoScadenzaControl({ entita, entitaId, item, onChange }) {
    const attivo = !!item.avviso_attivo;
    const [editing, setEditing] = useState(false);
    const [giorni, setGiorni] = useState(item.avviso_giorni || 15);
    const [saving, setSaving] = useState(false);

    if (!item.data_scadenza) return null;

    const salva = async (attiva) => {
        const g = Math.max(1, Math.min(365, parseInt(giorni, 10) || 15));
        setSaving(true);
        try {
            await api.put("/documenti/avviso", {
                entita, entita_id: entitaId, item_id: item.id, attivo: attiva, giorni: g,
            });
            onChange?.(item.id, { avviso_attivo: attiva, avviso_giorni: g });
            setEditing(false);
            toast.success(attiva ? `Avviso attivo: ${g} giorni prima` : "Avviso disattivato");
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore avviso");
        } finally { setSaving(false); }
    };

    if (editing) {
        return (
            <span className="inline-flex items-center gap-1" data-testid={`avviso-edit-${item.id}`}>
                <input
                    type="number" min="1" max="365" value={giorni}
                    onChange={(e) => setGiorni(e.target.value)}
                    className="w-14 h-6 px-1 text-[11px] border border-slate-300 rounded text-center"
                    data-testid={`avviso-giorni-${item.id}`} />
                <span className="text-[10px] text-slate-500">gg prima</span>
                <button onClick={() => salva(true)} disabled={saving}
                    className="p-1 rounded bg-emerald-600 text-white hover:bg-emerald-700"
                    title="Salva avviso" data-testid={`avviso-save-${item.id}`}>
                    <Check size={11} />
                </button>
                {attivo && (
                    <button onClick={() => salva(false)} disabled={saving}
                        className="p-1 rounded bg-rose-100 text-rose-600 hover:bg-rose-200"
                        title="Disattiva avviso" data-testid={`avviso-off-${item.id}`}>
                        <BellOff size={11} />
                    </button>
                )}
                <button onClick={() => { setEditing(false); setGiorni(item.avviso_giorni || 15); }}
                    className="p-1 rounded text-slate-400 hover:bg-slate-100" title="Annulla"
                    data-testid={`avviso-cancel-${item.id}`}>
                    <X size={11} />
                </button>
            </span>
        );
    }

    if (attivo) {
        return (
            <button onClick={() => setEditing(true)}
                className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded font-medium bg-amber-100 text-amber-700 hover:bg-amber-200"
                title="Avviso scadenza attivo — clicca per modificare"
                data-testid={`avviso-badge-${item.id}`}>
                <Bell size={11} /> Avviso {item.avviso_giorni || 15}gg
            </button>
        );
    }

    return (
        <button onClick={() => setEditing(true)}
            className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded font-medium bg-slate-100 text-slate-500 hover:bg-slate-200"
            title="Attiva avviso di scadenza (app + email)"
            data-testid={`avviso-attiva-${item.id}`}>
            <BellOff size={11} /> Attiva avviso
        </button>
    );
}
