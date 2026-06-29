/**
 * Scambio Dati Agenzie — super admin only. Permette di importare in massa
 * anagrafiche/polizze/titoli/sinistri/documenti di un proprio operatore
 * registrato presso un'altra agenzia.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { ArrowRightLeft, AlertCircle, Download, History, Users, FileText, AlertTriangle, Receipt, Paperclip } from "lucide-react";
import { toast } from "sonner";

export default function ScambioDati() {
    const [agenzie, setAgenzie] = useState([]);
    const [f, setF] = useState({
        agenzia_sorgente_id: "", operatore_email: "",
        importa_anagrafiche: true, importa_polizze: true,
        importa_titoli: true, importa_sinistri: true, importa_documenti: true,
    });
    const [preview, setPreview] = useState(null);
    const [busy, setBusy] = useState(false);
    const [log, setLog] = useState(null);

    const loadLog = () => api.get("/scambio-dati/log").then((r) => setLog(r.data));
    useEffect(() => {
        api.get("/agenzie").then((r) => setAgenzie((r.data || []).filter((a) => a.tipo === "partner")));
        loadLog();
    }, []);

    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const doPreview = async () => {
        if (!f.operatore_email.trim()) { toast.error("Inserisci email operatore"); return; }
        if (!f.agenzia_sorgente_id) { toast.error("Seleziona agenzia sorgente"); return; }
        try {
            const r = await api.post("/scambio-dati/preview", f);
            setPreview(r.data);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
            setPreview(null);
        }
    };

    const doImport = async () => {
        if (!preview) { toast.error("Esegui prima la preview"); return; }
        if (!window.confirm(`Importare ${preview.anagrafiche} anagrafiche, ${preview.polizze} polizze, ${preview.titoli} titoli, ${preview.sinistri} sinistri, ${preview.documenti} documenti?`)) return;
        setBusy(true);
        try {
            const r = await api.post("/scambio-dati/esegui", f);
            toast.success(`Import completato: ${r.data.anagrafiche} anagrafiche, ${r.data.polizze} polizze, ${r.data.titoli} titoli (in stato arretrato)`);
            loadLog();
            setPreview(null);
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        finally { setBusy(false); }
    };

    return (
        <div data-testid="scambio-dati-page" className="space-y-5">
            <PageHeader
                title={<span className="flex items-center gap-2"><ArrowRightLeft className="text-violet-600" /> Scambio dati tra agenzie</span>}
                subtitle="Importa dati di un tuo operatore registrato presso un'agenzia partner (super admin only)"
            />

            <Card className="p-4 border-l-4 border-amber-400 bg-amber-50/20">
                <div className="flex items-start gap-2">
                    <AlertCircle size={20} className="text-amber-600 mt-0.5" />
                    <div className="text-sm text-slate-700">
                        <strong>Solo super admin.</strong> Lo scambio dati copia anagrafiche/polizze/titoli/sinistri
                        dall'agenzia sorgente alla tua. I titoli importati restano <strong>sempre</strong> in stato
                        "da pagare arretrato" senza metodo di pagamento — dovrai gestirli manualmente.
                    </div>
                </div>
            </Card>

            <Card className="p-4">
                <h2 className="font-semibold mb-3">Configurazione import</h2>
                <div className="grid grid-cols-2 gap-3 mb-3">
                    <div><Label>Agenzia sorgente *</Label>
                        <Select value={f.agenzia_sorgente_id} onValueChange={(v) => set("agenzia_sorgente_id", v)}>
                            <SelectTrigger data-testid="sc-sorgente"><SelectValue placeholder="Seleziona" /></SelectTrigger>
                            <SelectContent>
                                {agenzie.map((a) => <SelectItem key={a.id} value={a.id}>{a.ragione_sociale}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div><Label>Email operatore *</Label>
                        <Input value={f.operatore_email} onChange={(e) => set("operatore_email", e.target.value)}
                            placeholder="info@bsbroker.it" data-testid="sc-email" /></div>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-2 my-3">
                    {[
                        ["importa_anagrafiche", "Anagrafiche"],
                        ["importa_polizze", "Polizze"],
                        ["importa_titoli", "Titoli (arretrati)"],
                        ["importa_sinistri", "Sinistri"],
                        ["importa_documenti", "Documenti"],
                    ].map(([k, l]) => (
                        <div key={k} className="flex items-center gap-2 bg-slate-50 p-2 rounded">
                            <Checkbox id={k} checked={f[k]} onCheckedChange={(v) => set(k, !!v)} />
                            <Label htmlFor={k} className="text-xs cursor-pointer">{l}</Label>
                        </div>
                    ))}
                </div>
                <div className="flex justify-end gap-2">
                    <Button variant="outline" onClick={doPreview} data-testid="sc-preview">Preview</Button>
                </div>
            </Card>

            {/* PREVIEW */}
            {preview && (
                <Card className="p-4 border-l-4 border-violet-400 bg-violet-50/30">
                    <h2 className="font-semibold text-violet-900 mb-3">Anteprima dati da importare</h2>
                    <div className="text-sm mb-3">
                        Operatore: <span className="font-bold">{preview.operatore?.name || preview.operatore?.email}</span>
                    </div>
                    <div className="grid grid-cols-5 gap-3 mb-4">
                        <PreviewStat icon={Users} v={preview.anagrafiche} l="Anagrafiche" />
                        <PreviewStat icon={FileText} v={preview.polizze} l="Polizze" />
                        <PreviewStat icon={Receipt} v={preview.titoli} l="Titoli (arretrati)" />
                        <PreviewStat icon={AlertTriangle} v={preview.sinistri} l="Sinistri" />
                        <PreviewStat icon={Paperclip} v={preview.documenti} l="Documenti" />
                    </div>
                    <Button onClick={doImport} disabled={busy} className="bg-violet-700 hover:bg-violet-800" data-testid="sc-import">
                        <Download size={14} className="mr-1" /> {busy ? "Importazione…" : "Esegui importazione"}
                    </Button>
                </Card>
            )}

            {/* LOG */}
            <Card className="p-4">
                <div className="flex items-center gap-2 mb-3">
                    <History size={16} className="text-slate-600" />
                    <h2 className="font-semibold text-slate-800">Storico scambi</h2>
                </div>
                {log === null ? <Loading /> : log.length === 0 ? <Empty message="Nessuno scambio eseguito" /> : (
                    <table className="tbl-compact w-full text-xs">
                        <thead><tr>
                            <th>Data</th><th>Operatore</th>
                            <th className="text-right">Anagr.</th><th className="text-right">Polizze</th>
                            <th className="text-right">Titoli</th><th className="text-right">Sinistri</th>
                            <th className="text-right">Doc.</th>
                        </tr></thead>
                        <tbody>
                            {log.map((l) => (
                                <tr key={l.id}>
                                    <td>{new Date(l.data).toLocaleString("it-IT")}</td>
                                    <td className="font-mono">{l.operatore_email}</td>
                                    <td className="text-right font-mono">{l.risultato?.anagrafiche}</td>
                                    <td className="text-right font-mono">{l.risultato?.polizze}</td>
                                    <td className="text-right font-mono">{l.risultato?.titoli}</td>
                                    <td className="text-right font-mono">{l.risultato?.sinistri}</td>
                                    <td className="text-right font-mono">{l.risultato?.allegati}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </Card>
        </div>
    );
}

const PreviewStat = ({ icon: Ic, v, l }) => (
    <Card className="p-3 bg-white">
        <div className="flex items-start justify-between">
            <div>
                <div className="text-[10px] uppercase text-slate-500">{l}</div>
                <div className="text-2xl font-bold text-violet-700 font-mono">{v || 0}</div>
            </div>
            <Ic size={18} className="text-violet-400 opacity-50" />
        </div>
    </Card>
);
