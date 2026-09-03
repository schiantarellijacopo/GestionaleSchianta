/**
 * CatastoImportDialog — mostra gli immobili trovati al Catasto e permette di
 * scegliere "tutti o solo alcuni" prima di importarli nell'Analisi Cliente.
 */
import { useState } from "react";
import { api, fmtEur } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { Home, Loader2, MapPin } from "lucide-react";
import { toast } from "sonner";

export default function CatastoImportDialog({ aid, immobili, soggetto, onClose, onImported }) {
    const [selected, setSelected] = useState(() => immobili.map((_, i) => i));
    const [busy, setBusy] = useState(false);
    const allChecked = selected.length === immobili.length && immobili.length > 0;

    const toggle = (i) =>
        setSelected((p) => (p.includes(i) ? p.filter((x) => x !== i) : [...p, i]));
    const toggleAll = () =>
        setSelected(allChecked ? [] : immobili.map((_, i) => i));

    const importa = async () => {
        if (selected.length === 0) { toast.error("Seleziona almeno un immobile"); return; }
        setBusy(true);
        try {
            const payload = { immobili: selected.map((i) => immobili[i]) };
            const r = await api.post(`/openapi-it/cadastre/${aid}/importa-immobili`, payload);
            toast.success(`${r.data.aggiunti} immobili importati nell'Analisi Cliente`);
            onImported?.();
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore importazione");
        } finally { setBusy(false); }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto" data-testid="catasto-import-dialog">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Home size={18} className="text-sky-700" />
                        Immobili trovati al Catasto
                    </DialogTitle>
                    <DialogDescription>
                        Seleziona gli immobili da importare nella sezione Immobili dell'Analisi Cliente.
                    </DialogDescription>
                </DialogHeader>

                {soggetto && (
                    <div className="text-xs text-slate-600 -mt-2">
                        Soggetto: <b>{soggetto.denominazione}</b> · CF/P.IVA {soggetto.cf}
                        {soggetto.sede ? ` · ${soggetto.sede}` : ""}
                    </div>
                )}

                {immobili.length === 0 ? (
                    <div className="text-sm text-slate-500 bg-slate-50 border border-dashed rounded p-6 text-center">
                        Nessun immobile strutturato disponibile. La visura PDF è stata comunque salvata negli Allegati.
                    </div>
                ) : (
                    <>
                        <div className="flex items-center justify-between border-b pb-2">
                            <label className="flex items-center gap-2 text-sm font-medium cursor-pointer">
                                <Checkbox checked={allChecked} onCheckedChange={toggleAll} data-testid="catasto-select-all" />
                                Seleziona tutti ({immobili.length})
                            </label>
                            <span className="text-xs text-slate-500">{selected.length} selezionati</span>
                        </div>
                        <div className="space-y-2 max-h-[45vh] overflow-y-auto">
                            {immobili.map((im, i) => (
                                <label key={i}
                                    className={`flex items-start gap-3 border rounded p-2.5 cursor-pointer transition-colors ${selected.includes(i) ? "border-sky-400 bg-sky-50/50" : "border-slate-200 hover:bg-slate-50"}`}
                                    data-testid={`catasto-item-${i}`}>
                                    <Checkbox checked={selected.includes(i)} onCheckedChange={() => toggle(i)} className="mt-0.5" />
                                    <div className="flex-1 min-w-0 text-xs">
                                        <div className="font-medium text-sm capitalize flex items-center gap-2">
                                            {im.tipo}
                                            {im.categoria_catastale && <span className="text-slate-500 font-mono text-[11px]">({im.categoria_catastale})</span>}
                                        </div>
                                        {im.indirizzo && <div className="text-slate-600 flex items-center gap-1"><MapPin size={10} /> {im.indirizzo}</div>}
                                        <div className="text-slate-500">
                                            {im.comune} {im.provincia ? `(${im.provincia})` : ""}
                                            {im.foglio ? ` · Fg ${im.foglio}` : ""}{im.particella ? ` Part ${im.particella}` : ""}{im.sub ? ` Sub ${im.sub}` : ""}
                                        </div>
                                        <div className="flex gap-4 mt-0.5 text-[11px]">
                                            {im.rendita_catastale > 0 && <span className="text-amber-700">Rendita {fmtEur(im.rendita_catastale)}</span>}
                                            {im.superficie_mq > 0 && <span className="text-slate-600">{im.superficie_mq} m²</span>}
                                            <span className="text-slate-500">Quota {im.percentuale_proprieta}% · {im.titolo}</span>
                                        </div>
                                    </div>
                                </label>
                            ))}
                        </div>
                    </>
                )}

                <DialogFooter>
                    <Button variant="outline" onClick={onClose} disabled={busy}>Chiudi</Button>
                    {immobili.length > 0 && (
                        <Button onClick={importa} disabled={busy || selected.length === 0}
                            className="bg-sky-700 hover:bg-sky-800" data-testid="catasto-import-btn">
                            {busy ? <Loader2 size={14} className="animate-spin mr-1" /> : null}
                            Importa {selected.length} immobili
                        </Button>
                    )}
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
