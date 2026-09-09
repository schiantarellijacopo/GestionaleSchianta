/**
 * Dialog "Privacy & Consensi" - gestisce flag dei 4 consensi GDPR
 * (dati particolari, marketing, comunicazione terzi, profilazione),
 * canvas firma digitale e download PDF firmato.
 */
import { useState, useRef, useEffect } from "react";
import { api } from "@/lib/api";
import { openPdf } from "@/lib/pdf";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";
import { FileText, PenLine, Eraser, Save, Download, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

const VOCI = [
    {
        key: "consenso_dati_particolari",
        titolo: "1. Trattamento dati particolari",
        descr: "Per le finalità indicate al punto 1 dell'informativa (gestione attività di intermediazione, adempimenti obbligatori, consulenza, sinistri, reclami).",
    },
    {
        key: "consenso_commerciale",
        titolo: "2. Marketing diretto (punti 2a, 2b, 2c)",
        descr: "Informazione e promozione commerciale a mezzo posta, telefono, e-mail, SMS, MMS e sistemi automatizzati.",
    },
    {
        key: "consenso_comunicazione_terzi",
        titolo: "3. Comunicazione dati a terzi (punto 2d)",
        descr: "Comunicazione dei dati personali a soggetti terzi nel settore assicurativo e complementare per finalità promozionali.",
    },
    {
        key: "consenso_profilazione",
        titolo: "4. Profilazione (punto 2e)",
        descr: "Analisi dei bisogni e delle esigenze assicurative del cliente tramite elaborazioni elettroniche per individuare prodotti/servizi mirati.",
    },
];

export default function PrivacyConsensiDialog({ open, onOpenChange, anagrafica_id, ana, canEdit, onReload }) {
    const [consensi, setConsensi] = useState({
        consenso_dati_particolari: false,
        consenso_commerciale: false,
        consenso_comunicazione_terzi: false,
        consenso_profilazione: false,
    });
    const [saving, setSaving] = useState(false);
    const [firmando, setFirmando] = useState(false);
    const [firmaMenu, setFirmaMenu] = useState(false);
    const [uploadModello, setUploadModello] = useState(false);

    const caricaModello = async (f) => {
        if (!f) return;
        setUploadModello(true);
        try {
            const fd = new FormData();
            fd.append("file", f);
            await api.post("/librerie/azienda/privacy-modello", fd, { headers: { "Content-Type": "multipart/form-data" } });
            toast.success(`Modello privacy caricato: ${f.name}`);
        } catch (e) { toast.error(e.response?.data?.detail || "Errore caricamento modello"); }
        finally { setUploadModello(false); }
    };

    const scaricaModello = async () => {
        try {
            const r = await api.get("/librerie/azienda/privacy-modello", { responseType: "blob" });
            const url = URL.createObjectURL(new Blob([r.data]));
            window.open(url, "_blank");
            setTimeout(() => URL.revokeObjectURL(url), 60000);
        } catch (e) {
            toast.error(e.response?.status === 404 ? "Nessun modello caricato" : "Errore download");
        }
    };
    const canvasRef = useRef(null);
    const [drawing, setDrawing] = useState(false);
    const [hasSign, setHasSign] = useState(false);

    const firmaEsign = async (modalita) => {
        setFirmando(true);
        try {
            const pdfRes = await api.get(`/anagrafiche/${anagrafica_id}/privacy/genera-pdf`, { responseType: "blob" });
            const fd = new FormData();
            fd.append("file", new Blob([pdfRes.data], { type: "application/pdf" }), "privacy.pdf");
            fd.append("modalita", modalita);
            fd.append("firmatario_id", anagrafica_id);
            fd.append("display_name", "Informativa Privacy & Consensi");
            const r = await api.post("/firma/richieste", fd, { headers: { "Content-Type": "multipart/form-data" } });
            const link = r.data.signing_url || r.data.viewer_link;
            if (link) {
                if (modalita === "link_whatsapp") {
                    const tel = (ana?.cellulare || "").replace(/[^0-9]/g, "");
                    const txt = encodeURIComponent(`Gentile cliente, firmi qui l'informativa privacy: ${link}`);
                    window.open(`https://wa.me/${tel}?text=${txt}`, "_blank");
                    toast.success("Apro WhatsApp con il link di firma");
                } else {
                    window.open(link, "_blank");
                    toast.success("Richiesta firma creata");
                }
            } else {
                toast.success("Richiesta firma inviata al cliente");
            }
        } catch (e) {
            const msg = e.response?.data?.detail || "Errore invio firma";
            if (String(msg).toLowerCase().includes("configur")) toast.error("eSignAnyWhere non configurato — vai in Librerie → Firme");
            else toast.error(msg);
        } finally { setFirmando(false); setFirmaMenu(false); }
    };

    useEffect(() => {
        if (!ana || !open) return;
        setConsensi({
            consenso_dati_particolari: !!ana.consenso_dati_particolari,
            consenso_commerciale: !!ana.consenso_commerciale,
            consenso_comunicazione_terzi: !!ana.consenso_comunicazione_terzi,
            consenso_profilazione: !!ana.consenso_profilazione,
        });
        setHasSign(!!ana.firma_cliente_url);
        // pulisci canvas all'apertura
        const t = setTimeout(() => {
            const c = canvasRef.current;
            if (c) {
                const ctx = c.getContext("2d");
                ctx.fillStyle = "#ffffff";
                ctx.fillRect(0, 0, c.width, c.height);
                ctx.strokeStyle = "#1e293b";
                ctx.lineWidth = 2;
                ctx.lineCap = "round";
            }
        }, 100);
        return () => clearTimeout(t);
    }, [ana, open]);

    const toggle = (k) => setConsensi((p) => ({ ...p, [k]: !p[k] }));

    const salvaConsensi = async () => {
        setSaving(true);
        try {
            await api.put(`/anagrafiche/${anagrafica_id}/consensi-privacy`, consensi);
            toast.success("Consensi salvati");
            onReload?.();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        finally { setSaving(false); }
    };

    // === Canvas firma ===
    const getPos = (e) => {
        const c = canvasRef.current;
        const r = c.getBoundingClientRect();
        const sx = c.width / r.width;
        const sy = c.height / r.height;
        const x = (e.touches ? e.touches[0].clientX : e.clientX) - r.left;
        const y = (e.touches ? e.touches[0].clientY : e.clientY) - r.top;
        return { x: x * sx, y: y * sy };
    };
    const startDraw = (e) => {
        if (!canEdit) return;
        e.preventDefault();
        setDrawing(true);
        const { x, y } = getPos(e);
        const ctx = canvasRef.current.getContext("2d");
        ctx.beginPath();
        ctx.moveTo(x, y);
    };
    const draw = (e) => {
        if (!drawing) return;
        e.preventDefault();
        const { x, y } = getPos(e);
        const ctx = canvasRef.current.getContext("2d");
        ctx.lineTo(x, y);
        ctx.stroke();
    };
    const endDraw = () => setDrawing(false);
    const clearCanvas = () => {
        const c = canvasRef.current;
        const ctx = c.getContext("2d");
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, c.width, c.height);
    };
    const salvaFirma = async () => {
        try {
            const dataUrl = canvasRef.current.toDataURL("image/png");
            await api.post(`/anagrafiche/${anagrafica_id}/firma-digitale`, {
                immagine_base64: dataUrl,
            });
            toast.success("Firma salvata");
            setHasSign(true);
            onReload?.();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore firma"); }
    };

    const stampaPdf = async () => {
        if (canEdit) {
            try {
                await api.put(`/anagrafiche/${anagrafica_id}/consensi-privacy`, consensi);
            } catch (_e) { /* non bloccare la stampa */ }
        }
        // salva_archivio=true → il PDF viene salvato anche nel modulo documenti
        await openPdf(`/anagrafiche/${anagrafica_id}/privacy/genera-pdf`, { salva_archivio: "true" });
        onReload?.();
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto" data-testid="privacy-dialog">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2 text-lg">
                        <ShieldCheck className="text-sky-600" size={20} />
                        Informativa Privacy & Consensi GDPR
                    </DialogTitle>
                </DialogHeader>

                <div className="space-y-4">
                    {/* Modello privacy agenzia */}
                    <div className="flex items-center justify-between gap-2 bg-violet-50 border border-violet-200 rounded-md p-2.5" data-testid="privacy-modello-box">
                        <span className="text-xs text-violet-900">📎 Modello Privacy agenzia (PDF/Word) — usato come base per tutti i clienti</span>
                        <div className="flex items-center gap-2">
                            <button onClick={scaricaModello} className="text-xs text-violet-700 underline" data-testid="privacy-modello-download">Scarica modello</button>
                            <label className="text-xs px-2 py-1 rounded bg-violet-700 text-white cursor-pointer hover:bg-violet-800" data-testid="privacy-modello-upload">
                                {uploadModello ? "Carico…" : "Importa modello"}
                                <input type="file" accept=".pdf,.doc,.docx" className="hidden"
                                    onChange={(e) => caricaModello(e.target.files?.[0])} />
                            </label>
                        </div>
                    </div>
                    {/* Info */}
                    <div className="bg-sky-50 border border-sky-200 text-sky-900 text-xs rounded-md p-3">
                        Spunta i consensi prestati dal cliente, raccogli la firma digitale, poi
                        scarica il PDF dell'informativa GDPR (artt. 13-14 Reg. UE 2016/679) già
                        compilato con i dati del cliente.
                    </div>

                    {/* Consensi */}
                    <div className="space-y-2">
                        <Label className="text-sm font-semibold text-slate-800">Consensi (acconsento / non acconsento)</Label>
                        {VOCI.map((v) => (
                            <Card key={v.key} className={`p-3 border ${consensi[v.key] ? "border-emerald-300 bg-emerald-50/40" : "border-slate-200"}`}>
                                <div className="flex items-start gap-3">
                                    <Checkbox
                                        checked={consensi[v.key]}
                                        disabled={!canEdit}
                                        onCheckedChange={() => toggle(v.key)}
                                        data-testid={`cons-${v.key}`}
                                        className="mt-1"
                                    />
                                    <div className="flex-1">
                                        <div className="font-semibold text-sm text-slate-900">{v.titolo}</div>
                                        <div className="text-xs text-slate-600 mt-0.5">{v.descr}</div>
                                        <div className={`text-xs mt-1 font-medium ${consensi[v.key] ? "text-emerald-700" : "text-slate-500"}`}>
                                            {consensi[v.key] ? "☒ acconsento" : "☐ non acconsento"}
                                        </div>
                                    </div>
                                </div>
                            </Card>
                        ))}
                    </div>

                    {/* Firma digitale */}
                    <Card className="p-3 border-slate-200">
                        <div className="flex items-center justify-between mb-2">
                            <Label className="text-sm font-semibold flex items-center gap-2">
                                <PenLine size={14} /> Firma digitale del cliente
                            </Label>
                            <div className="flex gap-1">
                                <Button size="sm" variant="ghost" onClick={clearCanvas} disabled={!canEdit} data-testid="firma-clear">
                                    <Eraser size={13} className="mr-1" /> Pulisci
                                </Button>
                                <Button size="sm" variant="outline" onClick={salvaFirma} disabled={!canEdit} data-testid="firma-salva">
                                    <Save size={13} className="mr-1" /> Salva firma
                                </Button>
                            </div>
                        </div>

                        {hasSign && ana?.firma_cliente_url && (
                            <div className="text-xs text-emerald-700 mb-2 flex items-center gap-2">
                                ✓ Firma esistente in archivio:
                                <img src={ana.firma_cliente_url} alt="firma" className="h-8 bg-white rounded border" />
                            </div>
                        )}

                        <canvas
                            ref={canvasRef}
                            width={600} height={150}
                            className="w-full h-32 border border-dashed border-slate-300 rounded bg-white cursor-crosshair touch-none"
                            onMouseDown={startDraw}
                            onMouseMove={draw}
                            onMouseUp={endDraw}
                            onMouseLeave={endDraw}
                            onTouchStart={startDraw}
                            onTouchMove={draw}
                            onTouchEnd={endDraw}
                            data-testid="firma-canvas"
                        />
                        <div className="text-[10px] text-slate-500 italic mt-1">
                            Disegna la firma con mouse o touch. Clicca <em>Salva firma</em> per archiviarla, poi <em>Scarica PDF</em>.
                        </div>
                    </Card>
                </div>

                <DialogFooter className="gap-2 mt-2">
                    <Button variant="ghost" onClick={() => onOpenChange(false)}>Chiudi</Button>
                    {canEdit && (
                        <Button onClick={salvaConsensi} disabled={saving} className="bg-sky-700 hover:bg-sky-800" data-testid="cons-salva">
                            <Save size={13} className="mr-1" /> {saving ? "Salvataggio..." : "Salva consensi"}
                        </Button>
                    )}
                    <Button onClick={stampaPdf} className="bg-emerald-600 hover:bg-emerald-700" data-testid="cons-pdf">
                        <Download size={13} className="mr-1" /> Scarica PDF firmato
                    </Button>
                    <div className="relative">
                        <Button onClick={() => setFirmaMenu((v) => !v)} disabled={firmando} className="bg-violet-700 hover:bg-violet-800" data-testid="cons-firma-esign">
                            ✍️ {firmando ? "Invio…" : "Firma con eSignAnyWhere"} ▾
                        </Button>
                        {firmaMenu && (
                            <div className="absolute bottom-full right-0 mb-1 w-64 bg-white border border-slate-200 rounded-md shadow-lg z-50 overflow-hidden" data-testid="cons-firma-menu">
                                <button onClick={() => firmaEsign("biometric")} className="w-full text-left px-3 py-2 text-sm hover:bg-slate-50" data-testid="firma-mode-biometric">✒️ Grafometrica (su tablet)</button>
                                <button onClick={() => firmaEsign("otp_sms")} className="w-full text-left px-3 py-2 text-sm hover:bg-slate-50" data-testid="firma-mode-otp-sms">📱 OTP via SMS</button>
                                <button onClick={() => firmaEsign("link_whatsapp")} className="w-full text-left px-3 py-2 text-sm hover:bg-slate-50" data-testid="firma-mode-whatsapp">🟢 Link via WhatsApp</button>
                                <button onClick={() => firmaEsign("link")} className="w-full text-left px-3 py-2 text-sm hover:bg-slate-50" data-testid="firma-mode-email">✉️ Link via Email</button>
                            </div>
                        )}
                    </div>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
