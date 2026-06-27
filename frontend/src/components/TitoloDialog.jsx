import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import ChiusuraGiornoBanner from "@/components/ChiusuraGiornoBanner";
import SelectTipoPagamento from "@/components/SelectTipoPagamento";

/**
 * Dialog di modifica titolo, condiviso tra pagina Titoli e PolizzaDetail.
 *
 * Props:
 *  - titolo: oggetto titolo da modificare (richiesto)
 *  - onClose: callback su chiusura/salvataggio
 *  - onDelete?: opzionale, se passato mostra pulsante elimina
 */
export default function TitoloDialog({ titolo, onClose, onDelete }) {
    const [f, setF] = useState({ ...titolo });
    const [giornataChiusa, setGiornataChiusa] = useState(false);
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    // Controlla se la giornata della data_incasso è chiusa → disabilita Salva/Elimina
    useEffect(() => {
        const d = f.data_incasso;
        if (!d || !/^\d{4}-\d{2}-\d{2}$/.test(d)) { setGiornataChiusa(false); return; }
        let cancel = false;
        api.get(`/contabilita/giornata-stato/${d}`)
            .then((r) => { if (!cancel) setGiornataChiusa(!!r.data?.chiusa); })
            .catch(() => { if (!cancel) setGiornataChiusa(false); });
        return () => { cancel = true; };
    }, [f.data_incasso]);

    // Opzioni metodo di pagamento (statiche, riallinaeabili con libreria)
    const MEZZI = [
        "bonifico", "RID/SDD", "contanti", "assegno",
        "POS", "bollettino", "carta_credito", "compagnia", "altro",
    ];

    const save = async () => {
        try {
            await api.put(`/titoli/${titolo.id}`, {
                tipo: f.tipo, effetto: f.effetto, scadenza: f.scadenza,
                importo_lordo: parseFloat(f.importo_lordo) || 0,
                importo_netto: parseFloat(f.importo_netto) || 0,
                imposte: parseFloat(f.imposte) || 0,
                provvigioni: parseFloat(f.provvigioni) || 0,
                mezzo_pagamento: f.mezzo_pagamento || null,
                data_incasso: f.data_incasso || null,
                coperto_fino_a: f.coperto_fino_a || null,
            });
            toast.success("Titolo aggiornato");
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        }
    };

    const elimina = async () => {
        if (!window.confirm("Eliminare definitivamente questo titolo?")) return;
        try {
            await api.delete(`/titoli/${titolo.id}`);
            toast.success("Titolo eliminato");
            if (onDelete) onDelete();
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-xl" data-testid="titolo-edit-dialog">
                <DialogHeader>
                    <DialogTitle>
                        Modifica titolo {titolo.numero_polizza ? `– Polizza ${titolo.numero_polizza}` : ""}
                    </DialogTitle>
                    <p className="text-[11px] text-slate-500 mt-1">
                        Lo stato del titolo si aggiorna automaticamente con incasso / copertura / storno.
                    </p>
                </DialogHeader>
                <ChiusuraGiornoBanner data={f.data_incasso} />
                <div className="grid grid-cols-2 gap-3 py-2">
                    <div>
                        <Label>Tipo</Label>
                        <Select value={f.tipo} onValueChange={(v) => set("tipo", v)}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                                {["nuova", "rinnovo", "appendice", "regolazione", "storno", "sostituzione"].map((t) => (
                                    <SelectItem key={t} value={t}>{t}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <Label>Tipo pagamento</Label>
                        <SelectTipoPagamento
                            value={f.mezzo_pagamento || ""}
                            onChange={(v) => set("mezzo_pagamento", v)}
                            testid="mezzo-pagamento-select"
                        />
                    </div>
                    <div><Label>Effetto</Label><Input type="date" value={f.effetto || ""} onChange={(e) => set("effetto", e.target.value)} /></div>
                    <div><Label>Scadenza</Label><Input type="date" value={f.scadenza || ""} onChange={(e) => set("scadenza", e.target.value)} /></div>
                    <div><Label>Lordo €</Label><Input type="number" step="0.01" value={f.importo_lordo || 0} onChange={(e) => set("importo_lordo", e.target.value)} /></div>
                    <div><Label>Netto €</Label><Input type="number" step="0.01" value={f.importo_netto || 0} onChange={(e) => set("importo_netto", e.target.value)} /></div>
                    <div><Label>Imposte €</Label><Input type="number" step="0.01" value={f.imposte || 0} onChange={(e) => set("imposte", e.target.value)} /></div>
                    <div><Label>Provvigioni €</Label><Input type="number" step="0.01" value={f.provvigioni || 0} onChange={(e) => set("provvigioni", e.target.value)} /></div>
                    <div>
                        <Label>Data incasso</Label>
                        <Input
                            type="date"
                            value={f.data_incasso || ""}
                            onChange={(e) => set("data_incasso", e.target.value)}
                            placeholder="Si compila ad incasso"
                            data-testid="titolo-data-incasso"
                        />
                        <p className="text-[10px] text-slate-400 mt-0.5">Si compila automaticamente all&apos;incasso.</p>
                    </div>
                    <div>
                        <Label>Copertura fino al</Label>
                        <Input
                            type="date"
                            value={f.coperto_fino_a || ""}
                            onChange={(e) => set("coperto_fino_a", e.target.value)}
                            data-testid="titolo-copertura"
                        />
                        <p className="text-[10px] text-slate-400 mt-0.5">Si compila quando il titolo entra in copertura.</p>
                    </div>
                </div>
                <DialogFooter className="flex justify-between sm:justify-between">
                    {onDelete ? (
                        <Button
                            variant="outline"
                            onClick={elimina}
                            disabled={giornataChiusa}
                            data-testid="titolo-delete-btn"
                            className="text-rose-600 border-rose-200 hover:bg-rose-50 disabled:opacity-50 disabled:cursor-not-allowed"
                            title={giornataChiusa ? "Prima Nota chiusa — riaprire per eliminare" : ""}
                        >
                            Elimina
                        </Button>
                    ) : <div />}
                    <div className="flex gap-2">
                        <Button variant="outline" onClick={onClose}>Annulla</Button>
                        <Button
                            onClick={save}
                            disabled={giornataChiusa}
                            data-testid="titolo-save-edit"
                            className="bg-sky-700 hover:bg-sky-800 disabled:opacity-50 disabled:cursor-not-allowed"
                            title={giornataChiusa ? "Prima Nota chiusa — riaprire per modificare" : ""}
                        >
                            Salva
                        </Button>
                    </div>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
