/**
 * RichiediDocCard — pulsante "Richiedi al cliente" per una SINGOLA card documento.
 * Genera un link pubblico sicuro legato a (entita_tipo, entita_id, categoria):
 * il cliente carica uno o più file e questi finiscono DIRETTAMENTE in questa card.
 * Riutilizzabile su qualsiasi card del programma (polizza, sinistro, titolo, anagrafica…).
 */
import { useEffect, useState } from "react";
import { api, sendWhatsApp } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Link2, Copy, Send, Trash2, Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function RichiediDocCard({
    entita_tipo,
    entita_id,
    categoria,
    label,
    anagrafica = null,       // { id, cellulare, telefono } per invio WhatsApp
    variant = "icon",         // "icon" (dentro header card) | "button"
}) {
    const [open, setOpen] = useState(false);
    const [links, setLinks] = useState([]);
    const [creating, setCreating] = useState(false);
    const [loading, setLoading] = useState(false);

    const load = () => {
        setLoading(true);
        api.get("/upload-links", { params: { entita_tipo, entita_id, categoria } })
            .then((r) => setLinks(r.data || []))
            .catch(() => setLinks([]))
            .finally(() => setLoading(false));
    };
    useEffect(() => { if (open) load(); /* eslint-disable-next-line */ }, [open]);

    const crea = async () => {
        setCreating(true);
        try {
            await api.post("/upload-links", {
                entita_tipo, entita_id, categoria,
                descrizione: label || "Documento richiesto",
                giorni_validita: 30,
            });
            toast.success("Link creato: invialo al cliente");
            load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore creazione link"); }
        finally { setCreating(false); }
    };

    const copia = (url) => { navigator.clipboard.writeText(url); toast.success("Link copiato"); };
    const elimina = async (lid) => {
        if (!window.confirm("Eliminare questa richiesta?")) return;
        try { await api.delete(`/upload-links/${lid}`); toast.success("Richiesta eliminata"); load(); }
        catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };
    const waSend = (url) => {
        const num = (anagrafica?.cellulare || anagrafica?.telefono || "").replace(/\D/g, "");
        if (!num) { toast.error("Nessun cellulare in anagrafica"); return; }
        const msg = `Salve, per completare la pratica carichi qui ${label ? `(${label})` : "il documento richiesto"}: ${url}`;
        return sendWhatsApp(num, msg, { anagrafica_id: anagrafica?.id });
    };

    const hasNum = !!(anagrafica?.cellulare || anagrafica?.telefono);

    return (
        <>
            {variant === "icon" ? (
                <button type="button" onClick={(e) => { e.stopPropagation(); setOpen(true); }}
                    title="Richiedi questo documento al cliente"
                    className="text-sky-600 hover:text-sky-800 hover:bg-sky-50 p-1 rounded shrink-0"
                    data-testid={`richiedi-card-btn-${categoria}`}>
                    <Link2 size={13} />
                </button>
            ) : (
                <Button size="sm" variant="outline" onClick={() => setOpen(true)}
                    className="text-sky-700 border-sky-200" data-testid={`richiedi-card-btn-${categoria}`}>
                    <Link2 size={13} className="mr-1" /> Richiedi al cliente
                </Button>
            )}

            <Dialog open={open} onOpenChange={setOpen}>
                <DialogContent className="max-w-md" data-testid={`richiedi-card-dialog-${categoria}`}>
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2 text-sky-800">
                            <Link2 size={16} /> Richiedi al cliente{label ? `: ${label}` : ""}
                        </DialogTitle>
                    </DialogHeader>
                    <div className="space-y-3 text-sm">
                        <div className="text-xs text-slate-500 bg-sky-50 border border-sky-200 rounded p-2">
                            Genera un link sicuro: il cliente carica il file (anche più di uno) e lo ritrovi
                            automaticamente in questa card. Spariranno dai "documenti mancanti".
                        </div>
                        <Button onClick={crea} disabled={creating} className="w-full bg-sky-700 hover:bg-sky-800"
                            data-testid={`richiedi-card-crea-${categoria}`}>
                            {creating ? "Creazione…" : "➕ Genera nuovo link"}
                        </Button>
                        {loading ? (
                            <div className="flex items-center gap-2 text-slate-400 text-xs"><Loader2 size={13} className="animate-spin" /> Caricamento…</div>
                        ) : links.length === 0 ? (
                            <div className="text-xs text-slate-400 italic text-center py-2">Nessuna richiesta attiva</div>
                        ) : (
                            <div className="space-y-1.5">
                                {links.map((l) => (
                                    <div key={l.id} className="flex items-center gap-2 text-xs bg-white border border-slate-200 rounded-lg px-2 py-1.5">
                                        <span className="flex-1 min-w-0">
                                            <span className="font-medium text-slate-700 block truncate">{l.descrizione}</span>
                                            <span className="text-slate-400">
                                                {(l.uploads || []).length} file caricati{l.used ? "" : " (in attesa)"}
                                            </span>
                                        </span>
                                        <button onClick={() => copia(l.url)} className="text-sky-600 hover:text-sky-800 p-1" title="Copia link"
                                            data-testid={`richiedi-card-copy-${l.id}`}><Copy size={13} /></button>
                                        {hasNum && (
                                            <button onClick={() => waSend(l.url)} className="text-emerald-600 hover:text-emerald-800 p-1" title="Invia su WhatsApp"
                                                data-testid={`richiedi-card-wa-${l.id}`}><Send size={13} /></button>
                                        )}
                                        <button onClick={() => elimina(l.id)} className="text-rose-500 hover:text-rose-700 p-1" title="Elimina richiesta"
                                            data-testid={`richiedi-card-del-${l.id}`}><Trash2 size={13} /></button>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </DialogContent>
            </Dialog>
        </>
    );
}
