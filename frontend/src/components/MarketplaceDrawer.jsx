import { useEffect, useState } from "react";
import { X, ShoppingCart, Check, Loader2, Zap, Shield, MessageCircle, Cloud, Database, PenTool } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

const ICONS = {
    shield: Shield, signature: PenTool, message: MessageCircle,
    whatsapp: MessageCircle, cloud: Cloud, database: Database,
};

const STATO_LABEL = {
    attivo: { txt: "Attivo", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
    richiesto: { txt: "Richiesto", cls: "bg-amber-50 text-amber-700 border-amber-200" },
    in_lavorazione: { txt: "In Attesa", cls: "bg-sky-50 text-sky-700 border-sky-200" },
    non_attivo: { txt: "Non Attivo", cls: "bg-slate-50 text-slate-600 border-slate-200" },
    rifiutato: { txt: "Rifiutato", cls: "bg-rose-50 text-rose-700 border-rose-200" },
};

export default function MarketplaceDrawer({ open, onClose }) {
    const [moduli, setModuli] = useState([]);
    const [loading, setLoading] = useState(false);
    const [requesting, setRequesting] = useState(null);

    const load = () => {
        setLoading(true);
        api.get("/marketplace/moduli").then((r) => setModuli(r.data || []))
            .finally(() => setLoading(false));
    };
    useEffect(() => { if (open) load(); }, [open]);

    const richiedi = async (codice) => {
        setRequesting(codice);
        try {
            await api.post("/marketplace/richieste", { module_codice: codice });
            toast.success("Richiesta inviata! Ti risponderemo a breve.");
            load();
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Errore invio richiesta");
        } finally {
            setRequesting(null);
        }
    };

    if (!open) return null;
    return (
        <div className="fixed inset-0 z-[60]" data-testid="marketplace-drawer">
            <div className="absolute inset-0 bg-slate-900/40" onClick={onClose} />
            <div className="absolute right-0 top-0 h-full w-full sm:w-[560px] bg-white shadow-2xl flex flex-col animate-in slide-in-from-right">
                <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200">
                    <div className="flex items-center gap-2">
                        <ShoppingCart size={20} className="text-violet-600" />
                        <h2 className="text-lg font-semibold text-slate-800">Marketplace Moduli</h2>
                    </div>
                    <button onClick={onClose} className="text-slate-400 hover:text-slate-700 p-1"
                        data-testid="marketplace-close-btn">
                        <X size={20} />
                    </button>
                </div>
                <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
                    {loading && <div className="flex justify-center py-10"><Loader2 className="animate-spin text-slate-400" /></div>}
                    {!loading && moduli.length === 0 && (
                        <div className="text-sm text-slate-500 text-center py-10">Nessun modulo disponibile.</div>
                    )}
                    {moduli.map((m) => {
                        const Icon = ICONS[m.icona] || Zap;
                        const stato = STATO_LABEL[m.stato_agenzia] || STATO_LABEL.non_attivo;
                        const disabled = ["attivo", "richiesto", "in_lavorazione"].includes(m.stato_agenzia);
                        return (
                            <div key={m.codice} className="border border-slate-200 rounded-lg p-4 hover:shadow-md transition-shadow"
                                data-testid={`marketplace-module-${m.codice}`}>
                                <div className="flex items-start gap-3">
                                    <div className="w-10 h-10 rounded-md bg-violet-50 flex items-center justify-center text-violet-600 flex-shrink-0">
                                        <Icon size={20} />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-start justify-between gap-2 mb-1">
                                            <h3 className="font-semibold text-sm text-slate-800">{m.nome}</h3>
                                            <span className={`text-[10px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded border ${stato.cls}`}>{stato.txt}</span>
                                        </div>
                                        <p className="text-xs text-slate-600 mb-2 leading-relaxed">{m.descrizione}</p>
                                        <div className="flex items-center justify-between">
                                            <div className="text-sm">
                                                <span className="font-semibold text-slate-800">€ {m.prezzo_eur?.toFixed(2)}</span>
                                                <span className="text-xs text-slate-500 ml-1">
                                                    {m.tipo === "ricorrente" ? "/mese" : m.tipo === "consumo" ? "/pacchetto" : "una tantum"}
                                                </span>
                                            </div>
                                            <button
                                                type="button"
                                                onClick={() => richiedi(m.codice)}
                                                disabled={disabled || requesting === m.codice}
                                                data-testid={`marketplace-request-${m.codice}`}
                                                className="text-xs font-semibold px-3 py-1.5 rounded-md bg-violet-600 text-white hover:bg-violet-700 disabled:bg-slate-200 disabled:text-slate-500 disabled:cursor-not-allowed transition-colors"
                                            >
                                                {m.stato_agenzia === "attivo" ? (<><Check size={12} className="inline mr-1" />Attivo</>)
                                                    : requesting === m.codice ? "…"
                                                    : disabled ? "In attesa" : "Richiedi attivazione"}
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
                <div className="px-5 py-3 border-t border-slate-100 text-[11px] text-slate-500 bg-slate-50">
                    Le richieste vengono elaborate dal team entro 24h lavorative.
                </div>
            </div>
        </div>
    );
}
