import { useEffect, useState, useRef } from "react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { FileSignature, ShieldCheck } from "lucide-react";

// Numero intero → lettere (italiano) — replica del backend per coerenza PDF/UI.
function numLettere(n) {
    n = Math.round(Number(n) || 0);
    if (n === 0) return "zero euro (a titolo gratuito)";
    const u = ["", "uno", "due", "tre", "quattro", "cinque", "sei", "sette", "otto", "nove", "dieci",
        "undici", "dodici", "tredici", "quattordici", "quindici", "sedici", "diciassette",
        "diciotto", "diciannove"];
    const d = ["", "", "venti", "trenta", "quaranta", "cinquanta", "sessanta", "settanta", "ottanta", "novanta"];
    const sotto100 = (x) => {
        if (x < 20) return u[x];
        const dec = Math.floor(x / 10), un = x % 10;
        let base = d[dec];
        if (un === 1 || un === 8) base = base.slice(0, -1);
        return base + u[un];
    };
    const sotto1000 = (x) => {
        const cent = Math.floor(x / 100), r = x % 100;
        const pre = cent === 0 ? "" : (cent === 1 ? "cento" : u[cent] + "cento");
        return pre + sotto100(r);
    };
    if (n < 1000) return sotto1000(n) + " euro";
    const migl = Math.floor(n / 1000), r = n % 1000;
    const pre = migl === 1 ? "mille" : sotto1000(migl) + "mila";
    return (pre + sotto1000(r)).trim() + " euro";
}

function formatCorr(imp) {
    const n = Math.round(Number(imp) || 0);
    if (n === 0) return "a titolo gratuito";
    return "€ " + n.toLocaleString("it-IT") + " (" + numLettere(n) + ")";
}

// Aggiorna nel testo l'Art. 4 (Corrispettivo) e la riga "Corrispettivo pattuito:".
function applicaImporto(testo, imp) {
    const corr = formatCorr(imp);
    let t = testo || "";
    t = t.replace(/(corrisponderà al Consulente )([\s\S]*?)(\.\s*Tale corrispettivo)/,
        (_m, a, _b, c) => a + corr + c);
    t = t.replace(/(Corrispettivo pattuito:\s*)(.*)/,
        (_m, a) => a + corr);
    return t;
}

// Placeholder inseribili nel testo (risolti dal backend in fase di PDF/Word/firma).
const PLACEHOLDERS = [
    { token: "{cliente}", label: "Cliente" },
    { token: "{codice_fiscale}", label: "Cod. fiscale" },
    { token: "{partita_iva}", label: "P. IVA" },
    { token: "{indirizzo}", label: "Indirizzo" },
    { token: "{email}", label: "Email" },
    { token: "{cellulare}", label: "Cellulare" },
    { token: "{consulente}", label: "Consulente" },
    { token: "{rui}", label: "RUI" },
    { token: "{importo}", label: "Importo" },
    { token: "{luogo}", label: "Luogo" },
    { token: "{data}", label: "Data" },
];

export default function ContrattoConsulenzaTab({ anagrafica_id }) {
    const [testo, setTesto] = useState("");
    const [importo, setImporto] = useState(0);
    const [stato, setStato] = useState("bozza");
    const [firmatoIl, setFirmatoIl] = useState(null);
    const [esignCanali, setEsignCanali] = useState({ wa: true, email: true });
    const [allegatoId, setAllegatoId] = useState(null);
    const [canale, setCanale] = useState("whatsapp");
    const [otp, setOtp] = useState("");
    const [otpInviato, setOtpInviato] = useState(false);
    const [otpDebug, setOtpDebug] = useState(null);
    const [busy, setBusy] = useState(false);
    const [modelli, setModelli] = useState([]);
    const [cliente, setCliente] = useState({});
    const testoRef = useRef(null);

    const insertPlaceholder = (token) => {
        const el = testoRef.current;
        if (!el) { setTesto((t) => t + token); return; }
        const start = el.selectionStart ?? testo.length;
        const end = el.selectionEnd ?? testo.length;
        const next = testo.slice(0, start) + token + testo.slice(end);
        setTesto(next);
        setTimeout(() => {
            el.focus();
            el.selectionStart = el.selectionEnd = start + token.length;
        }, 0);
    };

    const load = () => {
        api.get(`/anagrafiche/${anagrafica_id}/contratto-consulenza`).then((r) => {
            setTesto(r.data.testo || "");
            setImporto(r.data.importo || 0);
            setStato(r.data.stato || "bozza");
            setFirmatoIl(r.data.firmato_il || null);
            setAllegatoId(r.data.allegato_id || null);
            setCliente(r.data.cliente || {});
        });
    };
    useEffect(load, [anagrafica_id]);

    const loadModelli = () => { api.get(`/contratti-modelli`).then((r) => setModelli(r.data || [])).catch(() => {}); };
    useEffect(loadModelli, []);

    const salvaModello = async () => {
        const nome = window.prompt("Nome del modello (es. \"Consulenza standard aziende\"):");
        if (!nome || !nome.trim()) return;
        setBusy(true);
        try {
            await api.post(`/contratti-modelli`, { nome: nome.trim(), testo, importo: Number(importo) || 0 });
            toast.success("Modello salvato nella libreria");
            loadModelli();
        } catch { toast.error("Errore salvataggio modello"); } finally { setBusy(false); }
    };

    const applicaModello = (mid) => {
        const m = modelli.find((x) => x.id === mid);
        if (!m) return;
        setTesto(m.testo || "");
        setImporto(m.importo || 0);
        toast.success(`Modello "${m.nome}" applicato — verifica e salva`);
    };

    const eliminaModello = async (mid) => {
        if (!window.confirm("Eliminare questo modello dalla libreria?")) return;
        try { await api.delete(`/contratti-modelli/${mid}`); toast.success("Modello eliminato"); loadModelli(); }
        catch { toast.error("Errore eliminazione"); }
    };

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

    // Firma con OpenAPI eSignature: archivia il PDF come allegato e invia il link (WhatsApp/Email)
    const firmaEsignContratto = async (canali) => {
        setBusy(true);
        try {
            if (stato !== "firmato") await api.put(`/anagrafiche/${anagrafica_id}/contratto-consulenza`, { testo, importo: Number(importo) || 0 });
            const pdfRes = await api.get(`/anagrafiche/${anagrafica_id}/contratto-consulenza/pdf`, { responseType: "blob" });
            const fd = new FormData();
            fd.append("file", new Blob([pdfRes.data], { type: "application/pdf" }), "contratto_consulenza.pdf");
            const up = await api.post("/allegati", fd, {
                headers: { "Content-Type": "multipart/form-data" },
                params: { entita_tipo: "anagrafica", entita_id: anagrafica_id, categoria: "contratto_consulenza", descrizione: "Contratto di Consulenza" },
            });
            await api.post("/esignature/invia", {
                allegato_id: up.data.id,
                invia_whatsapp: !!canali.wa,
                invia_email: !!canali.email,
            });
            toast.success("Richiesta di firma inviata al cliente (OpenAPI · link via " +
                [canali.wa && "WhatsApp", canali.email && "Email"].filter(Boolean).join(" + ") + ")");
        } catch (e) {
            const detail = e.response?.data?.detail;
            const msg = (typeof detail === "string" && !detail.trim().startsWith("<")) ? detail : "Invio firma non riuscito, riprova più tardi";
            toast.error(msg);
        } finally { setBusy(false); }
    };

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
                {!firmato && (
                    <div className="flex flex-wrap items-center gap-2 mt-1 mb-1.5 p-2 bg-slate-50 border border-slate-200 rounded-md" data-testid="contratto-modelli-bar">
                        <span className="text-[11px] font-semibold text-slate-600">Libreria modelli:</span>
                        <select onChange={(e) => { if (e.target.value) { applicaModello(e.target.value); e.target.value = ""; } }}
                            defaultValue="" className="text-[12px] border border-slate-300 rounded-md h-8 px-2 bg-white max-w-[240px]"
                            data-testid="contratto-modello-select">
                            <option value="">— Applica un modello —</option>
                            {modelli.map((m) => <option key={m.id} value={m.id}>{m.nome}</option>)}
                        </select>
                        <Button onClick={salvaModello} disabled={busy} size="sm" variant="outline"
                            className="h-8 text-[12px] border-emerald-300 text-emerald-700 hover:bg-emerald-50"
                            data-testid="contratto-salva-modello">⭐ Salva come modello</Button>
                        {modelli.length > 0 && (
                            <span className="text-[10px] text-slate-400">
                                {modelli.length} modell{modelli.length === 1 ? "o" : "i"} ·
                                <span className="ml-1">gestisci:</span>
                                {modelli.map((m) => (
                                    <button key={m.id} type="button" onClick={() => eliminaModello(m.id)}
                                        title={`Elimina ${m.nome}`}
                                        className="ml-1 text-rose-400 hover:text-rose-600 underline"
                                        data-testid={`contratto-modello-del-${m.id}`}>✕{m.nome.slice(0, 12)}</button>
                                ))}
                            </span>
                        )}
                    </div>
                )}
                {!firmato && (
                    <div className="flex flex-wrap items-center gap-1.5 mt-1 mb-1.5" data-testid="contratto-placeholder-bar">
                        <span className="text-[11px] text-slate-500 mr-1">Inserisci campo:</span>
                        {PLACEHOLDERS.map((p) => (
                            <button key={p.token} type="button" onClick={() => insertPlaceholder(p.token)}
                                className="text-[11px] px-2 py-0.5 rounded-full bg-indigo-50 border border-indigo-200 text-indigo-700 hover:bg-indigo-100 transition-colors"
                                data-testid={`contratto-ph-${p.token.replace(/[{}]/g, "")}`}>
                                {p.label}
                            </button>
                        ))}
                    </div>
                )}
                <textarea
                    ref={testoRef}
                    value={testo} onChange={(e) => setTesto(e.target.value)}
                    className="w-full h-[420px] text-[12px] font-mono border border-slate-300 rounded-md p-3 mt-1 leading-relaxed"
                    data-testid="contratto-testo"
                />

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-3 items-end">
                    <div>
                        <label className="text-xs text-slate-500">Importo consulenza (€) — 0 = gratuito</label>
                        <Input type="number" min="0" value={importo}
                            onChange={(e) => {
                                const v = e.target.value;
                                setImporto(v);
                                if (stato !== "firmato") setTesto((t) => applicaImporto(t, v));
                            }}
                            data-testid="contratto-importo" />
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
                    <div className="border-t border-indigo-200 mt-3 pt-3">
                        <div className="text-xs font-semibold text-indigo-900 mb-2">Oppure firma con OpenAPI (firma elettronica avanzata · OTP SMS)</div>
                        <div className="flex flex-wrap items-center gap-3">
                            <label className="flex items-center gap-1.5 text-xs cursor-pointer">
                                <input type="checkbox" checked={esignCanali.wa} onChange={(e) => setEsignCanali((c) => ({ ...c, wa: e.target.checked }))} data-testid="contratto-esign-wa" /> WhatsApp
                            </label>
                            <label className="flex items-center gap-1.5 text-xs cursor-pointer">
                                <input type="checkbox" checked={esignCanali.email} onChange={(e) => setEsignCanali((c) => ({ ...c, email: e.target.checked }))} data-testid="contratto-esign-email" /> Email
                            </label>
                            <Button onClick={() => {
                                if (!esignCanali.wa && !esignCanali.email) { toast.error("Seleziona almeno un canale"); return; }
                                firmaEsignContratto(esignCanali);
                            }} disabled={busy} variant="outline" className="border-violet-300 text-violet-700 hover:bg-violet-50" data-testid="contratto-firma-openapi">
                                ✒️ Invia per firma (OpenAPI)
                            </Button>
                        </div>
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
