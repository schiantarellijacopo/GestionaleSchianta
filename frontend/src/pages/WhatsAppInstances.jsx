import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { PageHeader, Loading } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import {
    MessageCircle, Plus, RefreshCcw, Trash2, LogOut,
    QrCode, Send, ShieldAlert, CheckCircle2, Loader2,
} from "lucide-react";

// ─── Utility: colore + label per lo stato Evolution API ──────────────
const STATE_META = {
    open: { label: "Connessa", color: "bg-emerald-100 text-emerald-800 border-emerald-300" },
    connecting: { label: "In connessione", color: "bg-amber-100 text-amber-800 border-amber-300" },
    close: { label: "Disconnessa", color: "bg-slate-100 text-slate-700 border-slate-300" },
    disconnected: { label: "Disconnessa", color: "bg-slate-100 text-slate-700 border-slate-300" },
    created: { label: "Creata (attende QR)", color: "bg-sky-100 text-sky-800 border-sky-300" },
    unknown: { label: "Sconosciuto", color: "bg-slate-100 text-slate-500 border-slate-200" },
};

const stateBadge = (st) => {
    const meta = STATE_META[st] || STATE_META.unknown;
    return (
        <Badge className={`${meta.color} border font-medium`}>
            {st === "open" && <CheckCircle2 size={12} className="mr-1" />}
            {st === "connecting" && <Loader2 size={12} className="mr-1 animate-spin" />}
            {meta.label}
        </Badge>
    );
};

export default function WhatsAppInstances() {
    const [cfg, setCfg] = useState(null);
    const [list, setList] = useState(null);
    const [creating, setCreating] = useState(false);
    const [qrDialog, setQrDialog] = useState(null); // { name, base64, code }

    const load = useCallback(async () => {
        try {
            const c = await api.get("/whatsapp-evo/config");
            setCfg(c.data);
            const r = await api.get("/whatsapp-evo/instances");
            setList(r.data);
        } catch (e) {
            toast.error("Errore caricamento: " + (e.response?.data?.detail || e.message));
            setList([]);
        }
    }, []);

    useEffect(() => { load(); }, [load]);

    if (list == null) return <Loading />;

    return (
        <div className="space-y-4">
            <PageHeader
                title="WhatsApp — Istanze Agenzie"
                subtitle="Gestione multi-tenant di sessioni WhatsApp via Evolution API"
                icon={MessageCircle}
                testid="whatsapp-instances-page"
            />

            {/* Stato configurazione */}
            <Card className="p-4">
                <div className="flex items-center justify-between gap-4 flex-wrap">
                    <div className="flex items-center gap-3">
                        {cfg?.configured ? (
                            <Badge className="bg-emerald-100 text-emerald-800 border-emerald-300 border">
                                <CheckCircle2 size={12} className="mr-1" /> Evolution API configurata
                            </Badge>
                        ) : (
                            <Badge className="bg-red-100 text-red-800 border-red-300 border">
                                <ShieldAlert size={12} className="mr-1" /> Non configurata
                            </Badge>
                        )}
                        {cfg?.url && (
                            <div className="text-xs text-slate-600 font-mono truncate max-w-[500px]">
                                {cfg.url}
                            </div>
                        )}
                    </div>
                    <div className="flex gap-2">
                        <Button variant="outline" onClick={load} data-testid="wa-refresh-btn">
                            <RefreshCcw size={14} className="mr-1" /> Aggiorna
                        </Button>
                        <Button
                            className="bg-emerald-600 hover:bg-emerald-700"
                            onClick={() => setCreating(true)}
                            disabled={!cfg?.configured}
                            data-testid="wa-create-btn"
                        >
                            <Plus size={14} className="mr-1" /> Nuova istanza
                        </Button>
                    </div>
                </div>
                {!cfg?.configured && (
                    <div className="mt-3 text-xs bg-amber-50 border border-amber-200 rounded p-3 text-amber-900">
                        <strong>Configurazione richiesta.</strong> Aggiungi le seguenti variabili
                        d&apos;ambiente nel backend:
                        <ul className="list-disc list-inside mt-1 space-y-0.5 font-mono">
                            <li><code>WHATSAPP_API_URL</code> = URL base Evolution (es. https://evolution-api-production-xxx.up.railway.app)</li>
                            <li><code>WHATSAPP_API_KEY</code> = valore di <code>AUTHENTICATION_API_KEY</code> di Railway</li>
                        </ul>
                        Poi riavvia il backend.
                    </div>
                )}
            </Card>

            {/* Lista istanze */}
            <Card className="p-0 overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="tbl w-full">
                        <thead>
                            <tr>
                                <th>Agenzia</th>
                                <th>Instance name</th>
                                <th>Stato</th>
                                <th>Creata il</th>
                                <th className="text-right">Azioni</th>
                            </tr>
                        </thead>
                        <tbody>
                            {list.length === 0 && (
                                <tr><td colSpan="5" className="text-center text-slate-500 py-8">
                                    Nessuna istanza creata. Clicca <strong>Nuova istanza</strong> per iniziare.
                                </td></tr>
                            )}
                            {list.map((inst) => (
                                <tr key={inst.instance_name} data-testid={`wa-row-${inst.instance_name}`}>
                                    <td className="font-medium">{inst.agenzia_nome}</td>
                                    <td className="font-mono text-xs text-slate-600">{inst.instance_name}</td>
                                    <td>{stateBadge(inst.state_live || inst.state)}</td>
                                    <td className="text-xs text-slate-500">{inst.created_at?.slice(0, 10)}</td>
                                    <td className="text-right">
                                        <div className="flex gap-1 justify-end">
                                            <Button size="sm" variant="outline" title="QR / Connetti"
                                                    onClick={() => openQr(inst.instance_name, setQrDialog)}
                                                    data-testid={`wa-qr-${inst.instance_name}`}>
                                                <QrCode size={13} />
                                            </Button>
                                            <Button size="sm" variant="outline" title="Test invio"
                                                    onClick={() => testSend(inst.instance_name)}
                                                    data-testid={`wa-send-${inst.instance_name}`}>
                                                <Send size={13} />
                                            </Button>
                                            <Button size="sm" variant="outline" title="Disconnetti"
                                                    onClick={() => onLogout(inst.instance_name, load)}
                                                    data-testid={`wa-logout-${inst.instance_name}`}>
                                                <LogOut size={13} />
                                            </Button>
                                            <Button size="sm" variant="outline" title="Elimina istanza"
                                                    className="text-red-600 hover:bg-red-50"
                                                    onClick={() => onDelete(inst.instance_name, load)}
                                                    data-testid={`wa-del-${inst.instance_name}`}>
                                                <Trash2 size={13} />
                                            </Button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </Card>

            {creating && (
                <CreateInstanceDialog
                    onClose={(refresh) => { setCreating(false); if (refresh) load(); }}
                    onQr={(payload) => { setQrDialog(payload); }}
                />
            )}

            {qrDialog && (
                <QrDialog data={qrDialog} onClose={() => setQrDialog(null)} onDone={load} />
            )}
        </div>
    );
}

// ─── Helpers per azioni riga ─────────────────────────────────────────
async function openQr(name, setQrDialog) {
    try {
        const r = await api.get(`/whatsapp-evo/instances/${name}/qr`);
        if (!r.data.base64 && !r.data.code) {
            toast.info("QR non disponibile — l'istanza è già connessa o in errore.");
            return;
        }
        setQrDialog({ instance_name: name, ...r.data });
    } catch (e) {
        toast.error(e.response?.data?.detail || "Errore recupero QR");
    }
}

async function onLogout(name, reload) {
    if (!window.confirm(`Disconnettere il numero da '${name}'?`)) return;
    try {
        await api.post(`/whatsapp-evo/instances/${name}/logout`);
        toast.success("Disconnessa");
        reload();
    } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
}

async function onDelete(name, reload) {
    if (!window.confirm(`ELIMINARE definitivamente l'istanza '${name}'? Questa azione è irreversibile.`)) return;
    try {
        await api.delete(`/whatsapp-evo/instances/${name}`);
        toast.success("Istanza eliminata");
        reload();
    } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
}

async function testSend(name) {
    const number = window.prompt("Numero destinatario (es. 393401234567):");
    if (!number) return;
    const text = window.prompt("Messaggio di test:", "Test da assicura CRM ✅");
    if (!text) return;
    try {
        await api.post(`/whatsapp-evo/instances/${name}/send-text`, { number, text });
        toast.success("Messaggio inviato");
    } catch (e) { toast.error(e.response?.data?.detail || "Errore invio"); }
}

// ─── Dialog: Nuova istanza ───────────────────────────────────────────
function CreateInstanceDialog({ onClose, onQr }) {
    const [nome, setNome] = useState("");
    const [saving, setSaving] = useState(false);
    const submit = async () => {
        if (!nome.trim()) { toast.error("Nome agenzia obbligatorio"); return; }
        setSaving(true);
        try {
            const r = await api.post("/whatsapp-evo/instances", { agenzia_nome: nome.trim() });
            toast.success(`Istanza creata: ${r.data.instance_name}`);
            if (r.data.qr && (r.data.qr.base64 || r.data.qr.code)) {
                onQr({ instance_name: r.data.instance_name, ...r.data.qr });
            }
            onClose(true);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore creazione");
        } finally { setSaving(false); }
    };
    return (
        <Dialog open onOpenChange={() => onClose(false)}>
            <DialogContent className="max-w-md" data-testid="wa-create-dialog">
                <DialogHeader><DialogTitle>Nuova istanza WhatsApp</DialogTitle></DialogHeader>
                <div className="space-y-3 py-2">
                    <div>
                        <Label>Nome agenzia *</Label>
                        <Input value={nome} onChange={(e) => setNome(e.target.value)}
                               placeholder="Es. Agenzia Roma Prati"
                               data-testid="wa-create-nome" autoFocus />
                        <div className="text-xs text-slate-500 mt-1">
                            L&apos;instance name su Evolution API sarà generato in slug automaticamente.
                        </div>
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={() => onClose(false)}>Annulla</Button>
                    <Button onClick={submit} disabled={saving} className="bg-emerald-600 hover:bg-emerald-700"
                            data-testid="wa-create-submit">
                        {saving ? "Creazione…" : "Crea + Genera QR"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

// ─── Dialog: QR + polling stato ──────────────────────────────────────
function QrDialog({ data, onClose, onDone }) {
    const [state, setState] = useState(null);
    const [qr, setQr] = useState(data);

    // Auto-refresh QR ogni 20s + polling stato ogni 3s
    useEffect(() => {
        let stopped = false;
        const pollState = async () => {
            try {
                const r = await api.get(`/whatsapp-evo/instances/${data.instance_name}/status`);
                if (!stopped) setState(r.data.state);
                if (r.data.state === "open") {
                    toast.success("WhatsApp collegato con successo!");
                    onDone();
                    setTimeout(() => onClose(), 1200);
                }
            } catch (e) { /* ignore */ }
        };
        const refreshQr = async () => {
            try {
                const r = await api.get(`/whatsapp-evo/instances/${data.instance_name}/qr`);
                if (!stopped && (r.data.base64 || r.data.code)) {
                    setQr({ instance_name: data.instance_name, ...r.data });
                }
            } catch (e) { /* ignore */ }
        };
        pollState();
        const stateInt = setInterval(pollState, 3000);
        const qrInt = setInterval(refreshQr, 25000);
        return () => { stopped = true; clearInterval(stateInt); clearInterval(qrInt); };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [data.instance_name]);

    const imgSrc = qr.base64
        ? (qr.base64.startsWith("data:") ? qr.base64 : `data:image/png;base64,${qr.base64}`)
        : null;

    return (
        <Dialog open onOpenChange={onClose}>
            <DialogContent className="max-w-md" data-testid="wa-qr-dialog">
                <DialogHeader>
                    <DialogTitle>
                        <QrCode className="inline mr-2 -mt-1" size={18} />
                        Collega WhatsApp — {qr.instance_name}
                    </DialogTitle>
                </DialogHeader>
                <div className="text-xs bg-sky-50 border border-sky-200 rounded p-2 text-sky-900 mb-3">
                    Sul telefono apri <strong>WhatsApp → Impostazioni → Dispositivi collegati → Collega un dispositivo</strong>
                    e inquadra il QR qui sotto. Il QR si rigenera automaticamente ogni ~25 secondi.
                </div>
                <div className="flex flex-col items-center gap-3 py-2">
                    {imgSrc ? (
                        <img src={imgSrc} alt="QR WhatsApp" className="w-64 h-64 border border-slate-200 rounded"
                             data-testid="wa-qr-image" />
                    ) : (
                        <div className="w-64 h-64 flex items-center justify-center bg-slate-100 rounded text-slate-500 text-sm">
                            <Loader2 className="animate-spin mr-2" size={18} /> Generazione QR…
                        </div>
                    )}
                    {qr.pairingCode && (
                        <div className="text-center">
                            <div className="text-xs text-slate-500">Oppure inserisci questo codice:</div>
                            <div className="font-mono text-lg font-bold tracking-widest">{qr.pairingCode}</div>
                        </div>
                    )}
                    <div className="text-xs text-slate-600 mt-1">
                        Stato attuale: {state ? stateBadge(state) : "…"}
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Chiudi</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
