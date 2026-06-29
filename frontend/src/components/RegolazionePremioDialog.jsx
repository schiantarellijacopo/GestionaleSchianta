/**
 * RegolazionePremioDialog — calcolo regolazione premio per polizze con flag
 * regolazione_premio=true (es. RC fatturato, monte mercedi, addetti).
 * Mostra anche lo storico calcoli.
 */
import { useEffect, useState } from "react";
import { api, fmtEur } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Calculator, History } from "lucide-react";
import { toast } from "sonner";

export default function RegolazionePremioDialog({ polizza, onClose, onSaved }) {
    const [base, setBase] = useState(0);
    const [tasso, setTasso] = useState(polizza.regolazione_tasso || 0);
    const [periodo, setPeriodo] = useState(String(new Date().getFullYear() - 1));
    const [note, setNote] = useState("");
    const [storico, setStorico] = useState([]);
    const [risultato, setRisultato] = useState(null);
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        api.get(`/polizze/${polizza.id}/regolazione-premio/storico`).then((r) => setStorico(r.data || []));
    }, [polizza.id]);

    const calcola = async (salva = false) => {
        if (!base || base <= 0) { toast.error("Inserisci la base imponibile (es. fatturato)"); return; }
        setBusy(true);
        try {
            const r = await api.post(`/polizze/${polizza.id}/regolazione-premio/calcola`, {
                base_imponibile: parseFloat(base),
                tasso_override: tasso ? parseFloat(tasso) : null,
                periodo, note, salva,
            });
            setRisultato(r.data);
            if (salva) {
                toast.success(`Calcolo salvato · Dovuto ${fmtEur(r.data.dovuto)}`);
                const upd = await api.get(`/polizze/${polizza.id}/regolazione-premio/storico`);
                setStorico(upd.data || []);
                if (onSaved) onSaved();
            }
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        finally { setBusy(false); }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-3xl" data-testid="regolazione-dialog">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Calculator className="text-violet-600" /> Regolazione Premio · Polizza {polizza.numero_polizza}
                    </DialogTitle>
                </DialogHeader>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 py-2">
                    {/* Calcolo */}
                    <div className="space-y-3">
                        <h4 className="font-semibold text-sm text-slate-800">Nuovo calcolo</h4>
                        <div>
                            <Label className="text-xs">Periodo (es. anno)</Label>
                            <Input value={periodo} onChange={(e) => setPeriodo(e.target.value)}
                                placeholder="2025" data-testid="reg-periodo" />
                        </div>
                        <div>
                            <Label className="text-xs">
                                Base imponibile ({polizza.regolazione_base || "fatturato"}) *
                            </Label>
                            <Input type="number" step="0.01" value={base}
                                onChange={(e) => setBase(parseFloat(e.target.value) || 0)}
                                placeholder="Es. 500000.00" data-testid="reg-base" />
                        </div>
                        <div>
                            <Label className="text-xs">Tasso applicato (%) — opzionale, default polizza</Label>
                            <Input type="number" step="0.001" value={tasso}
                                onChange={(e) => setTasso(parseFloat(e.target.value) || 0)}
                                placeholder={`Default ${polizza.regolazione_tasso || 0}%`} data-testid="reg-tasso" />
                        </div>
                        <div className="text-[11px] text-slate-500 bg-slate-50 border border-slate-200 rounded p-2">
                            Premio minimo non rimborsabile: <b className="num">{fmtEur(polizza.regolazione_minima || 0)}</b>
                        </div>
                        <div>
                            <Label className="text-xs">Note</Label>
                            <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
                        </div>
                        <div className="flex gap-2">
                            <Button variant="outline" onClick={() => calcola(false)} disabled={busy}
                                data-testid="reg-calcola-prova">
                                Calcola (prova)
                            </Button>
                            <Button onClick={() => calcola(true)} disabled={busy}
                                className="bg-violet-700 hover:bg-violet-800" data-testid="reg-calcola-salva">
                                Calcola e salva
                            </Button>
                        </div>
                    </div>

                    {/* Risultato + Storico */}
                    <div className="space-y-3">
                        {risultato && (
                            <div className="border-2 border-violet-200 bg-violet-50 rounded-lg p-3" data-testid="reg-risultato">
                                <h4 className="font-semibold text-sm text-violet-800 mb-2">Risultato calcolo</h4>
                                <div className="grid grid-cols-2 gap-2 text-xs">
                                    <div><span className="text-slate-500">Tasso applicato:</span> <b className="font-mono">{risultato.tasso_applicato_pct}%</b></div>
                                    <div><span className="text-slate-500">Base:</span> <b className="font-mono">{fmtEur(risultato.base_imponibile)}</b></div>
                                    <div><span className="text-slate-500">Premio calcolato:</span> <b className="font-mono">{fmtEur(risultato.premio_calcolato)}</b></div>
                                    <div><span className="text-slate-500">Minimo non rimb.:</span> <b className="font-mono">{fmtEur(risultato.minimo_non_rimborsabile)}</b></div>
                                </div>
                                <div className="mt-3 pt-3 border-t border-violet-200 flex justify-between items-end">
                                    <span className="text-sm font-medium text-slate-700">Dovuto cliente:</span>
                                    <span className="text-2xl font-bold font-mono text-violet-700" data-testid="reg-dovuto">{fmtEur(risultato.dovuto)}</span>
                                </div>
                            </div>
                        )}
                        <div>
                            <h4 className="font-semibold text-sm text-slate-800 flex items-center gap-1 mb-2">
                                <History size={13} /> Storico ({storico.length})
                            </h4>
                            <div className="space-y-1 max-h-72 overflow-y-auto">
                                {storico.length === 0 ? (
                                    <div className="text-xs text-slate-500 italic">Nessun calcolo precedente</div>
                                ) : storico.map((s) => (
                                    <div key={s.id || s.data_calcolo} className="text-xs border border-slate-200 rounded p-2 bg-white">
                                        <div className="flex justify-between">
                                            <b>{s.periodo || "—"}</b>
                                            <span className="text-slate-500">{s.data_calcolo}</span>
                                        </div>
                                        <div className="text-slate-600">
                                            base {fmtEur(s.base_imponibile)} × {s.tasso_applicato_pct}% =
                                            <b className="text-violet-700 ml-1">{fmtEur(s.dovuto)}</b>
                                        </div>
                                        {s.note && <div className="text-slate-500 italic mt-0.5">{s.note}</div>}
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Chiudi</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
