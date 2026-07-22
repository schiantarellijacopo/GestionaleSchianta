import { useEffect, useState } from "react";
import { X, Headphones, Send, Loader2, Plus, MessageSquare } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

const CATEGORIE = [
    { v: "supporto", l: "Supporto tecnico" },
    { v: "bug", l: "Segnalazione bug" },
    { v: "feature_request", l: "Richiesta funzione" },
    { v: "billing", l: "Fatturazione / Abbonamento" },
    { v: "integrazione", l: "Integrazione esterna" },
    { v: "altro", l: "Altro" },
];

const PRIORITA = [
    { v: "bassa", l: "Bassa", cls: "text-slate-600" },
    { v: "normale", l: "Normale", cls: "text-sky-700" },
    { v: "alta", l: "Alta", cls: "text-amber-700" },
    { v: "urgente", l: "Urgente", cls: "text-rose-700" },
];

const STATO_BADGE = {
    aperto: "bg-amber-50 text-amber-700 border-amber-200",
    in_lavorazione: "bg-sky-50 text-sky-700 border-sky-200",
    risolto: "bg-emerald-50 text-emerald-700 border-emerald-200",
    chiuso: "bg-slate-50 text-slate-600 border-slate-200",
};

export default function TicketDialog({ open, onClose }) {
    const [tickets, setTickets] = useState([]);
    const [loading, setLoading] = useState(false);
    const [showForm, setShowForm] = useState(false);
    const [form, setForm] = useState({ oggetto: "", categoria: "supporto", priorita: "normale", descrizione: "" });
    const [submitting, setSubmitting] = useState(false);

    const load = () => {
        setLoading(true);
        api.get("/tickets/mie").then((r) => setTickets(r.data || []))
            .finally(() => setLoading(false));
    };
    useEffect(() => { if (open) load(); }, [open]);

    const submit = async (e) => {
        e.preventDefault();
        if (!form.oggetto.trim() || !form.descrizione.trim()) {
            toast.error("Oggetto e descrizione obbligatori");
            return;
        }
        setSubmitting(true);
        try {
            await api.post("/tickets", form);
            toast.success("Ticket inviato! Riceverai aggiornamenti via email.");
            setForm({ oggetto: "", categoria: "supporto", priorita: "normale", descrizione: "" });
            setShowForm(false);
            load();
        } catch (err) {
            toast.error(err?.response?.data?.detail || "Errore invio ticket");
        } finally {
            setSubmitting(false);
        }
    };

    if (!open) return null;
    return (
        <div className="fixed inset-0 z-[60]" data-testid="ticket-drawer">
            <div className="absolute inset-0 bg-slate-900/40" onClick={onClose} />
            <div className="absolute right-0 top-0 h-full w-full sm:w-[600px] bg-white shadow-2xl flex flex-col animate-in slide-in-from-right">
                <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200">
                    <div className="flex items-center gap-2">
                        <Headphones size={20} className="text-sky-600" />
                        <h2 className="text-lg font-semibold text-slate-800">Assistenza & Ticket</h2>
                    </div>
                    <div className="flex items-center gap-2">
                        {!showForm && (
                            <button onClick={() => setShowForm(true)}
                                className="text-xs font-semibold px-3 py-1.5 rounded-md bg-sky-600 text-white hover:bg-sky-700 flex items-center gap-1"
                                data-testid="ticket-new-btn">
                                <Plus size={14} /> Nuovo Ticket
                            </button>
                        )}
                        <button onClick={onClose} className="text-slate-400 hover:text-slate-700 p-1"
                            data-testid="ticket-close-btn">
                            <X size={20} />
                        </button>
                    </div>
                </div>

                <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
                    {showForm && (
                        <form onSubmit={submit} className="border border-sky-200 bg-sky-50/50 rounded-lg p-4 space-y-3"
                            data-testid="ticket-form">
                            <div>
                                <label className="text-xs font-semibold text-slate-600 block mb-1">Oggetto *</label>
                                <input type="text" value={form.oggetto}
                                    onChange={(e) => setForm({ ...form, oggetto: e.target.value })}
                                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-md focus:border-sky-500 outline-none"
                                    data-testid="ticket-oggetto-input" />
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className="text-xs font-semibold text-slate-600 block mb-1">Categoria</label>
                                    <select value={form.categoria}
                                        onChange={(e) => setForm({ ...form, categoria: e.target.value })}
                                        className="w-full px-3 py-2 text-sm border border-slate-300 rounded-md bg-white"
                                        data-testid="ticket-categoria-select">
                                        {CATEGORIE.map((c) => <option key={c.v} value={c.v}>{c.l}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label className="text-xs font-semibold text-slate-600 block mb-1">Priorità</label>
                                    <select value={form.priorita}
                                        onChange={(e) => setForm({ ...form, priorita: e.target.value })}
                                        className="w-full px-3 py-2 text-sm border border-slate-300 rounded-md bg-white"
                                        data-testid="ticket-priorita-select">
                                        {PRIORITA.map((p) => <option key={p.v} value={p.v}>{p.l}</option>)}
                                    </select>
                                </div>
                            </div>
                            <div>
                                <label className="text-xs font-semibold text-slate-600 block mb-1">Descrizione *</label>
                                <textarea rows={5} value={form.descrizione}
                                    onChange={(e) => setForm({ ...form, descrizione: e.target.value })}
                                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-md focus:border-sky-500 outline-none"
                                    data-testid="ticket-descrizione-input" />
                            </div>
                            <div className="flex gap-2 justify-end">
                                <button type="button" onClick={() => setShowForm(false)}
                                    className="text-xs font-semibold px-3 py-1.5 rounded-md border border-slate-300 text-slate-700 hover:bg-slate-50">
                                    Annulla
                                </button>
                                <button type="submit" disabled={submitting}
                                    className="text-xs font-semibold px-3 py-1.5 rounded-md bg-sky-600 text-white hover:bg-sky-700 flex items-center gap-1 disabled:opacity-60"
                                    data-testid="ticket-submit-btn">
                                    <Send size={12} /> {submitting ? "Invio…" : "Invia Ticket"}
                                </button>
                            </div>
                        </form>
                    )}

                    <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mt-4 mb-1">Storico Ticket</div>
                    {loading && <div className="flex justify-center py-8"><Loader2 className="animate-spin text-slate-400" /></div>}
                    {!loading && tickets.length === 0 && (
                        <div className="text-sm text-slate-500 text-center py-8 border border-dashed border-slate-200 rounded-lg">
                            Nessun ticket. Clicca <b>Nuovo Ticket</b> per aprirne uno.
                        </div>
                    )}
                    {tickets.map((t) => (
                        <div key={t.id} className="border border-slate-200 rounded-lg p-3 hover:bg-slate-50 cursor-pointer transition-colors"
                            data-testid={`ticket-item-${t.numero}`}>
                            <div className="flex items-start justify-between gap-2 mb-1">
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 mb-0.5">
                                        <span className="text-[10px] font-mono text-slate-500">{t.numero}</span>
                                        <span className={`text-[10px] uppercase tracking-wider font-semibold px-1.5 py-0.5 rounded border ${STATO_BADGE[t.stato]}`}>
                                            {t.stato}
                                        </span>
                                    </div>
                                    <div className="font-semibold text-sm text-slate-800">{t.oggetto}</div>
                                    <div className="text-xs text-slate-500 line-clamp-2 mt-0.5">{t.descrizione}</div>
                                </div>
                            </div>
                            <div className="flex items-center gap-2 mt-2 text-[10px] text-slate-500">
                                <MessageSquare size={11} />
                                <span>{new Date(t.created_at).toLocaleString("it-IT", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}</span>
                                <span className="ml-auto uppercase font-semibold">{t.categoria} · {t.priorita}</span>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}
