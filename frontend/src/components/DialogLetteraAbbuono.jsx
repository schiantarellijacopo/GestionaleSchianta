/**
 * DialogLetteraAbbuono — visualizza il PDF della lettera di abbuono associata
 * a un titolo (con sconto > 0) e raccoglie la doppia firma digitale
 * (operatore + cliente).
 *
 * Apertura:
 *   - dopo conferma incasso con sconto applicato (auto-trigger)
 *   - manualmente dal dettaglio titolo / polizza
 */
import { useEffect, useState } from "react";
import { api, API_BASE, fmtEur } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FileText, X, CheckCircle2, PenTool, Upload } from "lucide-react";
import { toast } from "sonner";
import SignaturePad from "@/components/SignaturePad";

export default function DialogLetteraAbbuono({ titoloId, lettera: initialLettera = null, onClose, onSigned }) {
    const { user: authUser } = useAuth();
    const [lettera, setLettera] = useState(initialLettera);
    const [loading, setLoading] = useState(!initialLettera);
    const [firmaOp, setFirmaOp] = useState(null);
    const [firmaCli, setFirmaCli] = useState(null);
    const [nomeCli, setNomeCli] = useState("");
    const [saving, setSaving] = useState(false);
    const [pdfTimestamp, setPdfTimestamp] = useState(Date.now());
    const [opMode, setOpMode] = useState("profilo"); // "profilo" | "manuale"

    // Profilo operatore corrente: pesca firma_digitale_url
    const [myProfile, setMyProfile] = useState(null);
    useEffect(() => {
        if (!authUser?.id) return;
        api.get(`/auth/users/${authUser.id}`)
            .then((r) => setMyProfile(r.data))
            .catch(() => setMyProfile(null));
    }, [authUser?.id]);
    const haFirmaProfilo = !!myProfile?.firma_digitale_url;

    const reload = async () => {
        if (!titoloId) return;
        setLoading(true);
        try {
            const r = await api.get("/lettere-abbuono", { params: { titolo_id: titoloId } });
            const ex = (r.data || [])[0];
            if (ex) {
                setLettera(ex);
            } else {
                // crea (idempotente)
                const c = await api.post(`/titoli/${titoloId}/lettera-abbuono`);
                setLettera(c.data);
            }
        } catch (e) {
            toast.error(e.response?.data?.detail || "Impossibile caricare la lettera");
        }
        setLoading(false);
    };

    useEffect(() => {
        if (!initialLettera && titoloId) reload();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [titoloId]);

    const pdfUrl = lettera
        ? `${API_BASE}/lettere-abbuono/${lettera.id}/pdf?t=${pdfTimestamp}`
        : null;

    const inviaFirma = async (tipo, b64, nome, opts = {}) => {
        if (!lettera) return;
        setSaving(true);
        try {
            const payload = { tipo, nome };
            if (opts.from_user_profile) {
                payload.from_user_profile = true;
            } else {
                payload.b64 = b64;
            }
            const r = await api.post(`/lettere-abbuono/${lettera.id}/firma`, payload);
            setLettera(r.data);
            setPdfTimestamp(Date.now());
            toast.success(`Firma ${tipo} salvata`);
            if (tipo === "operatore") setFirmaOp(null);
            if (tipo === "cliente") setFirmaCli(null);
            if (onSigned) onSigned(r.data);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore salvataggio firma");
        }
        setSaving(false);
    };

    const opFirmato = !!lettera?.firma_operatore_b64;
    const cliFirmato = !!lettera?.firma_cliente_b64;

    return (
        <Dialog open onOpenChange={onClose}>
            <DialogContent
                className="max-w-5xl p-0 overflow-hidden bg-white"
                data-testid="dialog-lettera-abbuono"
            >
                <DialogHeader className="px-6 py-3 border-b border-slate-200 bg-sky-50 flex flex-row items-center justify-between">
                    <DialogTitle className="text-sky-900 font-semibold flex items-center gap-2">
                        <FileText size={18} /> Lettera di abbuono — firma digitale
                    </DialogTitle>
                    <button
                        onClick={onClose}
                        className="text-slate-400 hover:text-slate-600"
                        data-testid="lab-close"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </DialogHeader>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-0 max-h-[80vh]">
                    {/* Anteprima PDF */}
                    <div className="border-r border-slate-200 bg-slate-50 overflow-hidden flex flex-col">
                        {loading && (
                            <div className="p-6 text-sm text-slate-500">Caricamento lettera…</div>
                        )}
                        {!loading && pdfUrl && (
                            <iframe
                                title="lettera-abbuono-pdf"
                                src={pdfUrl}
                                className="w-full h-[60vh] lg:h-[80vh]"
                                data-testid="lab-pdf-iframe"
                            />
                        )}
                        {!loading && lettera && (
                            <div className="px-4 py-2 text-[11px] text-slate-500 bg-white border-t border-slate-200 flex items-center justify-between">
                                <span>Sconto: <strong>{fmtEur(lettera.importo_sconto)}</strong></span>
                                <a
                                    href={pdfUrl}
                                    target="_blank" rel="noreferrer"
                                    className="text-sky-700 hover:text-sky-900 underline"
                                    data-testid="lab-download"
                                >Scarica PDF</a>
                            </div>
                        )}
                    </div>

                    {/* Firme */}
                    <div className="p-5 overflow-y-auto space-y-5">
                        {/* Firma Operatore */}
                        <div data-testid="lab-firma-op-section">
                            <div className="flex items-center justify-between mb-2">
                                <span className="font-semibold text-slate-700">Firma Operatore</span>
                                {opFirmato && (
                                    <span className="text-emerald-700 text-xs flex items-center gap-1">
                                        <CheckCircle2 size={14} /> Firmato il {(lettera.firma_operatore_at || "").slice(0, 10)}
                                    </span>
                                )}
                            </div>
                            {!opFirmato ? (
                                <>
                                    {haFirmaProfilo && opMode === "profilo" ? (
                                        <div className="border border-sky-200 bg-sky-50 rounded p-3 space-y-2">
                                            <div className="flex items-center gap-3">
                                                <img
                                                    src={`${API_BASE.replace(/\/api$/, '')}${myProfile.firma_digitale_url}`}
                                                    alt="firma"
                                                    className="bg-white border rounded p-1 max-h-16"
                                                    data-testid="lab-firma-profilo-preview"
                                                />
                                                <div className="text-xs text-slate-700">
                                                    <strong>{myProfile.name || authUser?.name}</strong>
                                                    <div className="text-slate-500">Firma archiviata sul profilo collaboratore</div>
                                                </div>
                                            </div>
                                            <div className="flex gap-2 flex-wrap">
                                                <Button
                                                    size="sm"
                                                    disabled={saving}
                                                    onClick={() => inviaFirma("operatore", null, null, { from_user_profile: true })}
                                                    className="bg-sky-700 hover:bg-sky-800"
                                                    data-testid="lab-firma-da-profilo"
                                                >
                                                    <PenTool size={14} className="mr-1" />
                                                    Conferma con la mia firma
                                                </Button>
                                                <Button
                                                    size="sm"
                                                    variant="outline"
                                                    onClick={() => setOpMode("manuale")}
                                                    data-testid="lab-firma-manuale-mode"
                                                >Firma manualmente</Button>
                                            </div>
                                        </div>
                                    ) : (
                                        <>
                                            {!haFirmaProfilo && (
                                                <div className="border border-amber-200 bg-amber-50 rounded p-2 mb-2 text-xs text-amber-900 flex items-start gap-2">
                                                    <Upload size={14} className="flex-shrink-0 mt-0.5" />
                                                    <div>
                                                        Nessuna firma archiviata sul profilo. Vai in <strong>Librerie → Utenti / Collaboratori → Documenti → Firma digitale</strong> per caricarla e firmare con un click in futuro.
                                                    </div>
                                                </div>
                                            )}
                                            <SignaturePad
                                                testid="sig-operatore"
                                                label="Firma del responsabile dell'agenzia"
                                                onChange={setFirmaOp}
                                            />
                                            <div className="flex gap-2 mt-2">
                                                <Button
                                                    size="sm"
                                                    disabled={!firmaOp || saving}
                                                    onClick={() => inviaFirma("operatore", firmaOp, null)}
                                                    className="bg-slate-800 hover:bg-slate-900"
                                                    data-testid="lab-salva-firma-op"
                                                >Salva firma operatore</Button>
                                                {haFirmaProfilo && (
                                                    <Button
                                                        size="sm" variant="ghost"
                                                        onClick={() => setOpMode("profilo")}
                                                    >← Usa firma dal profilo</Button>
                                                )}
                                            </div>
                                        </>
                                    )}
                                </>
                            ) : (
                                <div className="border border-emerald-200 bg-emerald-50 rounded p-3 flex items-center justify-between">
                                    <span className="text-xs text-emerald-900">
                                        Firmato da: <strong>{lettera.firma_operatore_nome || "—"}</strong>
                                    </span>
                                </div>
                            )}
                        </div>

                        {/* Firma Cliente */}
                        <div data-testid="lab-firma-cli-section">
                            <div className="flex items-center justify-between mb-2">
                                <span className="font-semibold text-slate-700">Firma Cliente</span>
                                {cliFirmato && (
                                    <span className="text-emerald-700 text-xs flex items-center gap-1">
                                        <CheckCircle2 size={14} /> Firmato il {(lettera.firma_cliente_at || "").slice(0, 10)}
                                    </span>
                                )}
                            </div>
                            {!cliFirmato ? (
                                <>
                                    <Input
                                        placeholder="Nome cliente (opzionale)"
                                        value={nomeCli}
                                        onChange={(e) => setNomeCli(e.target.value)}
                                        className="mb-2 text-sm"
                                        data-testid="lab-nome-cli"
                                    />
                                    <SignaturePad
                                        testid="sig-cliente"
                                        label="Firma del cliente che accetta l'abbuono"
                                        onChange={setFirmaCli}
                                    />
                                    <Button
                                        size="sm"
                                        disabled={!firmaCli || saving}
                                        onClick={() => inviaFirma("cliente", firmaCli, nomeCli || null)}
                                        className="mt-2 bg-slate-800 hover:bg-slate-900"
                                        data-testid="lab-salva-firma-cli"
                                    >Salva firma cliente</Button>
                                </>
                            ) : (
                                <div className="border border-emerald-200 bg-emerald-50 rounded p-3 flex items-center justify-between">
                                    <span className="text-xs text-emerald-900">
                                        Firmato da: <strong>{lettera.firma_cliente_nome || "Cliente"}</strong>
                                    </span>
                                </div>
                            )}
                        </div>

                        {opFirmato && cliFirmato && (
                            <div className="border border-emerald-300 bg-emerald-50 rounded p-3 text-sm text-emerald-900 flex items-start gap-2"
                                 data-testid="lab-completed-msg">
                                <CheckCircle2 size={18} className="text-emerald-700 mt-0.5 flex-shrink-0" />
                                <div>
                                    <strong>Lettera completamente firmata.</strong>
                                    Il PDF firmato è stato archiviato negli allegati del titolo.
                                </div>
                            </div>
                        )}
                    </div>
                </div>

                <div className="px-6 py-3 border-t border-slate-200 bg-slate-50 flex justify-end gap-2">
                    <Button
                        variant="outline" onClick={onClose}
                        data-testid="lab-chiudi"
                    >Chiudi</Button>
                </div>
            </DialogContent>
        </Dialog>
    );
}
