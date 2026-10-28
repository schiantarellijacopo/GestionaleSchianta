import { useState } from "react";
import { FileText, PenTool } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
    Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { api } from "@/lib/api";

const SEZIONE_LABEL = { contraente: "Contraente", polizza: "Polizza", sinistro: "Sinistro" };

export const GeneraDocumentoButton = ({ sezione, entitaId, firmatarioId, onSaved, size = "sm", variant = "outline", className = "" }) => {
    const [open, setOpen] = useState(false);
    const [modelli, setModelli] = useState(null);
    const [sel, setSel] = useState("");
    const [titolo, setTitolo] = useState("");
    const [corpo, setCorpo] = useState("");
    const [busy, setBusy] = useState(false);
    const [firmaAlleg, setFirmaAlleg] = useState(null); // {allegato_id, nome_file}
    const [canali, setCanali] = useState({ wa: true, email: true });

    const apri = async () => {
        setOpen(true);
        setModelli(null); setSel(""); setCorpo(""); setTitolo("");
        try {
            const r = await api.get("/documenti/modelli-sezione", { params: { sezione } });
            setModelli(r.data || []);
        } catch { setModelli([]); toast.error("Errore caricamento modelli"); }
    };

    const scegli = (id) => {
        setSel(id);
        const m = (modelli || []).find((x) => x.id === id);
        setCorpo(m?.corpo || ""); setTitolo(m?.nome || "Documento");
    };

    // Mappa il documento generato alla card dedicata dell'anagrafica (se pertinente)
    const cardCategoria = () => {
        const t = `${titolo || ""}`.toLowerCase();
        if (sezione === "contraente" && /autocertific/.test(t) && /famig/.test(t)) return "autocertificazione_stato_famiglia";
        return undefined;
    };
    const payload = (salva) => {
        const p = { entita_tipo: sezione, entita_id: entitaId, template_id: sel, titolo, corpo, salva };
        const cat = cardCategoria();
        if (cat) p.categoria = cat;
        return p;
    };

    const anteprima = async () => {
        if (!sel) { toast.error("Seleziona un modello"); return; }
        setBusy(true);
        try {
            const r = await api.post("/documenti/genera", payload(false), { responseType: "blob" });
            const url = URL.createObjectURL(new Blob([r.data], { type: "application/pdf" }));
            const w = window.open(url, "_blank");
            if (!w) { const a = document.createElement("a"); a.href = url; a.download = `${titolo}.pdf`; a.click(); }
            setTimeout(() => URL.revokeObjectURL(url), 60000);
        } catch { toast.error("Errore anteprima"); } finally { setBusy(false); }
    };

    const salva = async () => {
        if (!sel) { toast.error("Seleziona un modello"); return; }
        setBusy(true);
        try {
            const r = await api.post("/documenti/genera", payload(true));
            toast.success(`Documento archiviato tra gli allegati (${r.data.nome_file})`);
            setOpen(false); onSaved?.();
        } catch { toast.error("Errore generazione"); } finally { setBusy(false); }
    };

    // Firma con OpenAPI eSignature: genera+archivia il PDF, poi apre il popup di scelta canale
    const firma = async () => {
        if (!sel) { toast.error("Seleziona un modello"); return; }
        setBusy(true);
        try {
            const r = await api.post("/documenti/genera", payload(true));
            setFirmaAlleg({ allegato_id: r.data.allegato_id, nome_file: r.data.nome_file });
            setCanali({ wa: true, email: true });
            toast.success("Documento generato — scegli come inviarlo per la firma");
            onSaved?.();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore generazione documento");
        } finally { setBusy(false); }
    };

    const inviaFirma = async () => {
        if (!firmaAlleg?.allegato_id) return;
        if (!canali.wa && !canali.email) { toast.error("Seleziona almeno un canale di invio"); return; }
        setBusy(true);
        try {
            await api.post("/esignature/invia", {
                allegato_id: firmaAlleg.allegato_id,
                invia_whatsapp: canali.wa,
                invia_email: canali.email,
            });
            toast.success("Richiesta di firma inviata al cliente (link via " +
                [canali.wa && "WhatsApp", canali.email && "Email"].filter(Boolean).join(" + ") + ")");
            setFirmaAlleg(null);
            setOpen(false);
        } catch (e) {
            const detail = e.response?.data?.detail;
            const msg = (typeof detail === "string" && !detail.trim().startsWith("<")) ? detail : "Invio firma non riuscito, riprova più tardi";
            toast.error(msg);
        } finally { setBusy(false); }
    };

    return (
        <>
            <Button size={size} variant={variant} className={className} onClick={apri} data-testid={`genera-doc-btn-${sezione}`}>
                <FileText size={14} className="mr-1" /> Genera documento
            </Button>
            <Dialog open={open} onOpenChange={(o) => !o && setOpen(false)}>
                <DialogContent className="max-w-2xl max-h-[88vh] overflow-y-auto" data-testid="genera-doc-dialog">
                    <DialogHeader>
                        <DialogTitle>Genera documento — {SEZIONE_LABEL[sezione]}</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-3 py-1">
                        <div>
                            <Label>Modello</Label>
                            <Select value={sel} onValueChange={scegli}>
                                <SelectTrigger data-testid="genera-doc-modello"><SelectValue placeholder={modelli === null ? "Caricamento..." : "Seleziona un modello"} /></SelectTrigger>
                                <SelectContent>
                                    {(modelli || []).map((m) => <SelectItem key={m.id} value={m.id}>{m.nome}</SelectItem>)}
                                </SelectContent>
                            </Select>
                            {modelli !== null && modelli.length === 0 && (
                                <div className="text-[11px] text-amber-600 mt-1">Nessun modello per questa sezione. Aggiungine in Librerie → Gestioni Modelli con il flag &quot;{SEZIONE_LABEL[sezione]}&quot;.</div>
                            )}
                        </div>
                        {sel && (
                            <>
                                <div>
                                    <Label>Titolo documento</Label>
                                    <input value={titolo} onChange={(e) => setTitolo(e.target.value)}
                                        className="w-full h-9 px-3 rounded-md border border-slate-200 text-sm" data-testid="genera-doc-titolo" />
                                </div>
                                <div>
                                    <Label>Testo (modificabile — i segnaposto verranno compilati)</Label>
                                    <Textarea rows={12} value={corpo} onChange={(e) => setCorpo(e.target.value)}
                                        className="text-xs font-mono" data-testid="genera-doc-corpo" />
                                </div>
                            </>
                        )}
                    </div>
                    <DialogFooter className="gap-2 flex-wrap">
                        <Button variant="outline" onClick={() => setOpen(false)}>Chiudi</Button>
                        <Button variant="outline" onClick={anteprima} disabled={busy || !sel} data-testid="genera-doc-anteprima">Anteprima PDF</Button>
                        <Button variant="outline" onClick={firma} disabled={busy || !sel}
                            className="border-emerald-300 text-emerald-700 hover:bg-emerald-50" data-testid="genera-doc-firma">Firma</Button>
                        <Button onClick={salva} disabled={busy || !sel} className="bg-indigo-700 hover:bg-indigo-800" data-testid="genera-doc-salva">
                            {busy ? "…" : "Genera e archivia"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Popup scelta canale invio firma (OpenAPI eSignature) */}
            <Dialog open={!!firmaAlleg} onOpenChange={(o) => !o && setFirmaAlleg(null)}>
                <DialogContent className="max-w-md" data-testid="genera-doc-firma-invio-dialog">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2"><PenTool size={16} className="text-violet-600" /> Invia per firma</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-3 text-sm">
                        <div className="text-xs text-slate-500 bg-slate-50 rounded p-2">
                            Documento: <b>{firmaAlleg?.nome_file}</b><br />
                            Firma elettronica avanzata YouSign · il cliente riceverà un codice OTP via email per completare la firma.
                        </div>
                        <div>
                            <Label className="text-xs uppercase tracking-wide text-slate-600 mb-1.5 block">Invia il link di firma via</Label>
                            <div className="flex flex-col gap-2">
                                <label className="flex items-center gap-2 cursor-pointer p-2 border rounded">
                                    <Checkbox checked={canali.wa} onCheckedChange={(v) => setCanali((c) => ({ ...c, wa: !!v }))} data-testid="firma-canale-wa" />
                                    <span>WhatsApp</span>
                                </label>
                                <label className="flex items-center gap-2 cursor-pointer p-2 border rounded">
                                    <Checkbox checked={canali.email} onCheckedChange={(v) => setCanali((c) => ({ ...c, email: !!v }))} data-testid="firma-canale-email" />
                                    <span>Email</span>
                                </label>
                            </div>
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setFirmaAlleg(null)}>Annulla</Button>
                        <Button onClick={inviaFirma} disabled={busy} className="bg-violet-700 hover:bg-violet-800" data-testid="genera-doc-firma-invia">
                            {busy ? "Invio…" : "Invia richiesta firma"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    );
};

export default GeneraDocumentoButton;
