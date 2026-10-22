import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Mail, MessageCircle, PenTool, Upload, Loader2, Send, FileSignature } from "lucide-react";
import { toast } from "sonner";
import FirmaDesigner from "@/components/FirmaDesigner";

export default function AzioniCliente({ entitaTipo, entitaId, size = "sm" }) {
    const [modal, setModal] = useState(null); // "email" | "whatsapp" | "firma"
    const [contatti, setContatti] = useState(null);

    const base = { entita_tipo: entitaTipo, entita_id: entitaId };

    const openModal = async (tipo) => {
        setModal(tipo);
        if (!contatti) {
            try {
                const r = await api.post("/librerie/comunica/contesto", base);
                setContatti(r.data);
            } catch { setContatti({}); }
        }
    };

    return (
        <>
            <div className="flex items-center gap-2" data-testid="azioni-cliente-bar">
                <Button variant="outline" size={size} onClick={() => openModal("email")}
                    className="border-sky-300 text-sky-700 hover:bg-sky-50" data-testid="azione-email-btn">
                    <Mail size={14} className="mr-1" /> Email
                </Button>
                <Button variant="outline" size={size} onClick={() => openModal("whatsapp")}
                    className="border-emerald-300 text-emerald-700 hover:bg-emerald-50" data-testid="azione-whatsapp-btn">
                    <MessageCircle size={14} className="mr-1" /> WhatsApp
                </Button>
                <Button variant="outline" size={size} onClick={() => openModal("firma")}
                    className="border-violet-300 text-violet-700 hover:bg-violet-50" data-testid="azione-firma-btn">
                    <PenTool size={14} className="mr-1" /> Firma Moduli
                </Button>
            </div>

            {modal === "email" && (
                <ComunicaModal canale="email" base={base} contatti={contatti} onClose={() => setModal(null)} />
            )}
            {modal === "whatsapp" && (
                <ComunicaModal canale="whatsapp" base={base} contatti={contatti} onClose={() => setModal(null)} />
            )}
            {modal === "firma" && (
                <FirmaModal base={base} contatti={contatti} onClose={() => setModal(null)} />
            )}
        </>
    );
}

function ComunicaModal({ canale, base, contatti, onClose }) {
    const isEmail = canale === "email";
    const [modelli, setModelli] = useState([]);
    const [modelloId, setModelloId] = useState("");
    const [destinatario, setDestinatario] = useState("");
    const [oggetto, setOggetto] = useState("");
    const [corpo, setCorpo] = useState("");
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        api.get(`/librerie/modelli?tipo=${canale}`).then((r) => setModelli(r.data || [])).catch(() => {});
    }, [canale]);

    useEffect(() => {
        if (contatti) setDestinatario(isEmail ? (contatti.email || "") : (contatti.cellulare || ""));
    }, [contatti, isEmail]);

    const scegliModello = async (mid) => {
        setModelloId(mid);
        try {
            const r = await api.post("/librerie/comunica/render", { ...base, modello_id: mid });
            if (isEmail && r.data.oggetto) setOggetto(r.data.oggetto);
            setCorpo(r.data.corpo || "");
        } catch { toast.error("Errore compilazione modello"); }
    };

    const invia = async () => {
        if (!corpo.trim()) { toast.error("Il messaggio è vuoto"); return; }
        if (!destinatario.trim()) { toast.error(isEmail ? "Manca l'email" : "Manca il numero"); return; }
        setBusy(true);
        try {
            await api.post("/librerie/comunica/invia", { ...base, canale, destinatario, oggetto, corpo });
            toast.success(isEmail ? "Email inviata" : "WhatsApp inviato");
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Invio fallito");
        } finally { setBusy(false); }
    };

    return (
        <Dialog open onOpenChange={(v) => !v && onClose()}>
            <DialogContent className="max-w-2xl" data-testid={`comunica-modal-${canale}`}>
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        {isEmail ? <Mail size={18} className="text-sky-600" /> : <MessageCircle size={18} className="text-emerald-600" />}
                        {isEmail ? "Invia Email al cliente" : "Invia WhatsApp al cliente"}
                    </DialogTitle>
                </DialogHeader>
                <div className="space-y-3">
                    <div>
                        <Label className="text-xs">{isEmail ? "Destinatario (email)" : "Destinatario (cellulare)"}</Label>
                        <Input value={destinatario} onChange={(e) => setDestinatario(e.target.value)}
                            placeholder={isEmail ? "email@cliente.it" : "+39 ..."} data-testid="comunica-destinatario" />
                    </div>
                    <div>
                        <Label className="text-xs">Modello (autocompilazione dati)</Label>
                        <Select value={modelloId} onValueChange={scegliModello}>
                            <SelectTrigger data-testid="comunica-modello-select"><SelectValue placeholder="Seleziona un modello…" /></SelectTrigger>
                            <SelectContent>
                                {modelli.length === 0 && <div className="px-2 py-1.5 text-xs text-slate-400">Nessun modello {canale}. Creane in Librerie → Gestioni Modelli.</div>}
                                {modelli.map((m) => <SelectItem key={m.id} value={m.id}>{m.nome}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    {isEmail && (
                        <div>
                            <Label className="text-xs">Oggetto</Label>
                            <Input value={oggetto} onChange={(e) => setOggetto(e.target.value)} data-testid="comunica-oggetto" />
                        </div>
                    )}
                    <div>
                        <Label className="text-xs">Messaggio</Label>
                        <Textarea value={corpo} onChange={(e) => setCorpo(e.target.value)} rows={isEmail ? 9 : 6}
                            placeholder="Scrivi il messaggio o scegli un modello…" data-testid="comunica-corpo" />
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose} data-testid="comunica-chiudi">Chiudi</Button>
                    <Button onClick={invia} disabled={busy} data-testid="comunica-invia"
                        className={isEmail ? "bg-sky-600 hover:bg-sky-700" : "bg-emerald-600 hover:bg-emerald-700"}>
                        {busy ? <Loader2 size={14} className="animate-spin mr-1" /> : <Send size={14} className="mr-1" />}
                        {isEmail ? "Invia Mail" : "Invia WhatsApp"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function FirmaModal({ base, contatti, onClose }) {
    const [mode, setMode] = useState("modello"); // "modello" | "upload"
    const [modelli, setModelli] = useState([]);
    const [modelloId, setModelloId] = useState("");
    const [campiDisp, setCampiDisp] = useState([]);
    // upload
    const [doc, setDoc] = useState(null); // {storage_path, pages, immagini, nome}
    const [campi, setCampi] = useState([]);
    const [uploading, setUploading] = useState(false);
    const [canali, setCanali] = useState({ wa: true, email: true });
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        api.get("/firma/modelli").then((r) => setModelli(r.data || [])).catch(() => {});
        api.get("/firma/modelli/campi-disponibili").then((r) => setCampiDisp(r.data || [])).catch(() => {});
    }, []);

    const upload = async (file) => {
        if (!file) return;
        setUploading(true);
        const fd = new FormData();
        fd.append("file", file);
        try {
            const r = await api.post("/firma/modelli/render-pdf", fd, { headers: { "Content-Type": "multipart/form-data" } });
            setDoc(r.data); setCampi([]);
        } catch (e) { toast.error(e.response?.data?.detail || "Errore caricamento PDF"); }
        finally { setUploading(false); }
    };

    const esito = (res) => {
        const f = res.firma;
        if (f && !f.ok) { toast.error(`Firma non inviata: ${f.error}`); return; }
        const rec = res.recapito || {};
        const vie = [rec.wa?.ok && "WhatsApp", rec.email?.ok && "Email"].filter(Boolean).join(" + ");
        toast.success(`Documento inviato a firma${vie ? ` · link via ${vie}` : ""}`);
        onClose();
    };

    const inviaModello = async () => {
        if (!modelloId) { toast.error("Seleziona un modello"); return; }
        setBusy(true);
        try {
            const r = await api.post(`/firma/modelli/${modelloId}/compila`, { ...base, invia_firma: true, canali });
            esito(r.data);
        } catch (e) { toast.error(e.response?.data?.detail || "Errore invio firma"); }
        finally { setBusy(false); }
    };

    const inviaUpload = async () => {
        if (!doc) { toast.error("Carica un PDF"); return; }
        if (!campi.some((c) => c.tipo === "firma")) { toast.error("Posiziona almeno un campo firma"); return; }
        setBusy(true);
        try {
            const r = await api.post("/firma/modelli/adhoc", {
                ...base, storage_path: doc.storage_path, nome: doc.nome, campi, invia_firma: true, canali,
            });
            esito(r.data);
        } catch (e) { toast.error(e.response?.data?.detail || "Errore invio firma"); }
        finally { setBusy(false); }
    };

    return (
        <Dialog open onOpenChange={(v) => !v && onClose()}>
            <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto" data-testid="firma-modal">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2"><FileSignature size={18} className="text-violet-600" /> Firma Moduli — invio a firma digitale</DialogTitle>
                </DialogHeader>

                <div className="flex gap-2 mb-2">
                    <button onClick={() => setMode("modello")} data-testid="firma-mode-modello"
                        className={`px-3 py-1.5 rounded-md text-sm border ${mode === "modello" ? "bg-violet-600 text-white border-violet-600" : "bg-white text-slate-600 border-slate-300"}`}>
                        Usa un modello salvato
                    </button>
                    <button onClick={() => setMode("upload")} data-testid="firma-mode-upload"
                        className={`px-3 py-1.5 rounded-md text-sm border ${mode === "upload" ? "bg-violet-600 text-white border-violet-600" : "bg-white text-slate-600 border-slate-300"}`}>
                        Carica un PDF
                    </button>
                </div>

                {mode === "modello" ? (
                    <div className="space-y-3">
                        <div>
                            <Label className="text-xs">Modello di firma (con posizione firma salvata)</Label>
                            <Select value={modelloId} onValueChange={setModelloId}>
                                <SelectTrigger data-testid="firma-modello-select"><SelectValue placeholder="Seleziona un modello…" /></SelectTrigger>
                                <SelectContent>
                                    {modelli.length === 0 && <div className="px-2 py-1.5 text-xs text-slate-400">Nessun modello. Creane in Librerie → Modelli Firma.</div>}
                                    {modelli.map((m) => <SelectItem key={m.id} value={m.id}>{m.nome}</SelectItem>)}
                                </SelectContent>
                            </Select>
                            <p className="text-[11px] text-slate-500 mt-1">I dati del cliente/polizza vengono compilati automaticamente.</p>
                        </div>
                    </div>
                ) : (
                    <div className="space-y-3">
                        {!doc ? (
                            <label className="flex flex-col items-center justify-center gap-2 border-2 border-dashed border-violet-300 rounded-lg p-6 text-sm text-violet-600 cursor-pointer hover:bg-violet-50" data-testid="firma-upload-drop">
                                {uploading ? <Loader2 size={20} className="animate-spin" /> : <Upload size={20} />}
                                {uploading ? "Caricamento…" : "Carica un PDF (o Word) da firmare"}
                                <input type="file" accept=".pdf,.docx,.doc" hidden disabled={uploading}
                                    onChange={(e) => upload(e.target.files?.[0])} />
                            </label>
                        ) : (
                            <FirmaDesigner pages={doc.pages} immagini={doc.immagini} campi={campi}
                                onChange={setCampi} campiDisp={campiDisp} compact />
                        )}
                    </div>
                )}

                <div className="mt-2 border-t pt-3">
                    <Label className="text-xs">Recapita il link di firma via…</Label>
                    <div className="flex gap-4 mt-1">
                        <label className="flex items-center gap-1.5 text-sm"><input type="checkbox" checked={canali.wa} onChange={(e) => setCanali((p) => ({ ...p, wa: e.target.checked }))} data-testid="firma-canale-wa" /> WhatsApp {contatti?.cellulare ? "" : "(no numero)"}</label>
                        <label className="flex items-center gap-1.5 text-sm"><input type="checkbox" checked={canali.email} onChange={(e) => setCanali((p) => ({ ...p, email: e.target.checked }))} data-testid="firma-canale-email" /> Email {contatti?.email ? "" : "(no email)"}</label>
                    </div>
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Chiudi</Button>
                    <Button onClick={mode === "modello" ? inviaModello : inviaUpload} disabled={busy}
                        className="bg-violet-600 hover:bg-violet-700" data-testid="firma-invia">
                        {busy ? <Loader2 size={14} className="animate-spin mr-1" /> : <PenTool size={14} className="mr-1" />} Invia a firma
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
