import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { FileSignature, ShieldCheck } from "lucide-react";

export default function ContrattoConsulenzaTab({ anagrafica_id }) {
    const [testo, setTesto] = useState("");
    const [importo, setImporto] = useState(0);
    const [stato, setStato] = useState("bozza");
    const [firmatoIl, setFirmatoIl] = useState(null);
    const [allegatoId, setAllegatoId] = useState(null);
    const [canale, setCanale] = useState("whatsapp");
    const [otp, setOtp] = useState("");
    const [otpInviato, setOtpInviato] = useState(false);
    const [otpDebug, setOtpDebug] = useState(null);
    const [busy, setBusy] = useState(false);

    const load = () => {
        api.get(`/anagrafiche/${anagrafica_id}/contratto-consulenza`).then((r) => {
            setTesto(r.data.testo || "");
            setImporto(r.data.importo || 0);
            setStato(r.data.stato || "bozza");
            setFirmatoIl(r.data.firmato_il || null);
            setAllegatoId(r.data.allegato_id || null);
        });
    };
    useEffect(load, [anagrafica_id]);

    const salva = async () => {
        setBusy(true);
        try {
            await api.put(`/anagrafiche/${anagrafica_id}/contratto-consulenza`, { testo, importo: Number(importo) || 0 });
            toast.success("Contratto salvato");
        } catch { toast.error("Errore salvataggio"); } finally { setBusy(false); }
    };

    const inviaOtp = async () => {
        setBusy(true);
        try {
            await api.put(`/anagrafiche/${anagrafica_id}/contratto-consulenza`, { testo, importo: Number(importo) || 0 });
            const r = await api.post(`/anagrafiche/${anagrafica_id}/contratto-consulenza/invia-otp`, { canale });
            setOtpInviato(true);
            setOtpDebug(r.data.otp_debug || null);
            toast.success(r.data.inviato ? `OTP inviato via ${canale} a ${r.data.destinatario || ""}` : `OTP generato (consegna ${canale} non confermata)`);
        } catch (e) { toast.error(e.response?.data?.detail || "Errore invio OTP"); } finally { setBusy(false); }
    };

    const firma = async () => {
        setBusy(true);
        try {
            const r = await api.post(`/anagrafiche/${anagrafica_id}/contratto-consulenza/firma-otp`, { otp });
            setStato("firmato"); setFirmatoIl(r.data.firmato_il); setAllegatoId(r.data.allegato_id);
            setOtp(""); setOtpInviato(false); setOtpDebug(null);
            toast.success("Contratto firmato con OTP");
        } catch (e) { toast.error(e.response?.data?.detail || "Codice non valido"); } finally { setBusy(false); }
    };

    const firmato = stato === "firmato";

    const scarica = async (fmt) => {
        setBusy(true);
        try {
            if (!firmato) {
                await api.put(`/anagrafiche/${anagrafica_id}/contratto-consulenza`, { testo, importo: Number(importo) || 0 });
            }
            const r = await api.get(`/anagrafiche/${anagrafica_id}/contratto-consulenza/${fmt}`, { responseType: "blob" });
            const blob = new Blob([r.data], { type: fmt === "pdf" ? "application/pdf" : "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
            const url = URL.createObjectURL(blob);
            if (fmt === "pdf") {
                const win = window.open(url, "_blank");
                if (!win) {
                    const a = document.createElement("a");
                    a.href = url; a.download = `Contratto_consulenza.pdf`; a.click();
                }
            } else {
                const a = document.createElement("a");
                a.href = url; a.download = `Contratto_consulenza.docx`; a.click();
            }
            setTimeout(() => URL.revokeObjectURL(url), 60000);
        } catch { toast.error("Errore generazione documento"); } finally { setBusy(false); }
    };

    return (
        <div className="space-y-4 mt-4" data-testid="contratto-consulenza-tab">
            <Card className="p-4">
                <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
                    <h3 className="font-semibold flex items-center gap-2 text-slate-800">
                        <FileSignature size={18} className="text-indigo-600" /> Contratto di Consulenza
                    </h3>
                    {firmato ? (
                        <span className="text-xs px-2 py-1 rounded-full bg-emerald-100 text-emerald-800 flex items-center gap-1" data-testid="contratto-stato">
                            <ShieldCheck size={13} /> Firmato il {firmatoIl ? new Date(firmatoIl).toLocaleString("it-IT") : ""}
                        </span>
                    ) : (
                        <span className="text-xs px-2 py-1 rounded-full bg-amber-100 text-amber-800" data-testid="contratto-stato">Bozza modificabile</span>
                    )}
                </div>

                <label className="text-xs text-slate-500">Testo del contratto (modificabile)</label>
                <textarea
                    value={testo} onChange={(e) => setTesto(e.target.value)}
                    className="w-full h-[420px] text-[12px] font-mono border border-slate-300 rounded-md p-3 mt-1 leading-relaxed"
                    data-testid="contratto-testo"
                />

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-3 items-end">
                    <div>
                        <label className="text-xs text-slate-500">Importo consulenza (€) — 0 = gratuito</label>
                        <Input type="number" min="0" value={importo} onChange={(e) => setImporto(e.target.value)} data-testid="contratto-importo" />
                    </div>
                    <Button onClick={salva} disabled={busy} variant="outline" data-testid="contratto-salva">💾 Salva bozza</Button>
                    <div className="flex gap-2">
                        <Button onClick={() => scarica("pdf")} disabled={busy} variant="outline" className="border-indigo-300 text-indigo-700 hover:bg-indigo-50 flex-1" data-testid="contratto-anteprima-pdf">📄 Anteprima PDF</Button>
                        <Button onClick={() => scarica("docx")} disabled={busy} variant="outline" className="border-sky-300 text-sky-700 hover:bg-sky-50 flex-1" data-testid="contratto-scarica-word">📝 Scarica Word</Button>
                    </div>
                </div>
            </Card>

            {!firmato && (
                <Card className="p-4 bg-indigo-50 border-indigo-200">
                    <h4 className="font-semibold text-sm text-indigo-900 mb-2">Sottoscrizione con OTP</h4>
                    <div className="flex flex-wrap items-end gap-3">
                        <div>
                            <label className="text-xs text-slate-600">Canale invio codice</label>
                            <select value={canale} onChange={(e) => setCanale(e.target.value)} className="block border border-slate-300 rounded-md h-10 px-2 text-sm" data-testid="contratto-canale">
                                <option value="whatsapp">WhatsApp</option>
                                <option value="email">Email</option>
                                <option value="sms">SMS</option>
                            </select>
                        </div>
                        <Button onClick={inviaOtp} disabled={busy} className="bg-indigo-600 hover:bg-indigo-700" data-testid="contratto-invia-otp">Invia OTP al cliente</Button>
                        {otpInviato && (
                            <>
                                <div>
                                    <label className="text-xs text-slate-600">Codice OTP</label>
                                    <Input value={otp} onChange={(e) => setOtp(e.target.value)} placeholder="6 cifre" className="w-32" data-testid="contratto-otp-input" />
                                </div>
                                <Button onClick={firma} disabled={busy || otp.length < 4} className="bg-emerald-600 hover:bg-emerald-700" data-testid="contratto-firma">✍️ Firma contratto</Button>
                            </>
                        )}
                    </div>
                    {otpDebug && (
                        <div className="text-[11px] text-slate-500 mt-2">
                            Consegna automatica non confermata: comunica al cliente il codice <b className="font-mono">{otpDebug}</b> (valido 10 min).
                        </div>
                    )}
                </Card>
            )}

            {firmato && allegatoId && (
                <a href={`${api.defaults.baseURL}/allegati/${allegatoId}/download`} target="_blank" rel="noreferrer"
                   className="inline-flex items-center gap-2 text-sm text-indigo-700 hover:underline" data-testid="contratto-pdf-link">
                    📄 Scarica il contratto firmato (PDF)
                </a>
            )}
        </div>
    );
}
