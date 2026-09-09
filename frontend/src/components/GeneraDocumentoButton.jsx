import { useState } from "react";
import { FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
    Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
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

    const payload = (salva) => ({ entita_tipo: sezione, entita_id: entitaId, template_id: sel, titolo, corpo, salva });

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

    const firma = async () => {
        if (!sel) { toast.error("Seleziona un modello"); return; }
        setBusy(true);
        try {
            const r0 = await api.post("/documenti/genera", payload(false), { responseType: "blob" });
            const fd = new FormData();
            fd.append("file", new Blob([r0.data], { type: "application/pdf" }), `${titolo}.pdf`);
            fd.append("modalita", "biometric");
            fd.append("firmatario_id", firmatarioId || "");
            fd.append("display_name", titolo);
            const r = await api.post("/firma/richieste", fd, { headers: { "Content-Type": "multipart/form-data" } });
            const link = r.data.signing_url || r.data.viewer_link;
            if (link) window.open(link, "_blank");
            toast.success("Richiesta firma creata");
        } catch (e) {
            const msg = e.response?.data?.detail || "Errore firma";
            toast.error(String(msg).toLowerCase().includes("configur") ? "eSignAnyWhere non configurato — Librerie → Firme" : msg);
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
        </>
    );
};

export default GeneraDocumentoButton;
