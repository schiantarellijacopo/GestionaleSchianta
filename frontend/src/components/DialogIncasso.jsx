/**
 * DialogIncasso — riutilizzabile per incassare un Titolo.
 *
 * Mostra:
 *  - Premio originale (importo_lordo)
 *  - Importo effettivo pagato (modificabile)
 *  - Se importo_pagato < lordo → due opzioni di chiusura:
 *      • sconto: il residuo va in Prima Nota come uscita "sconto_cliente"
 *      • sospeso: viene generato un nuovo titolo residuo a sospeso
 */
import { useEffect, useState } from "react";
import { api, fmtEur, fmtDate } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
    RadioGroup, RadioGroupItem,
} from "@/components/ui/radio-group";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { toast } from "sonner";

export default function DialogIncasso({ titolo, conti, onClose, onDone }) {
    const oggi = new Date().toISOString().slice(0, 10);
    const lordo = parseFloat(titolo.importo_lordo) || 0;
    const [pref, setPref] = useState(null);

    useEffect(() => {
        if (titolo.contraente_id) {
            api.get(`/anagrafiche/${titolo.contraente_id}`).then((r) => setPref(r.data)).catch(() => {});
        }
    }, [titolo.contraente_id]);

    const defaultMezzo = pref?.preferenza_pagamento || pref?.ultimo_mezzo_pagamento || "contanti";
    const [f, setF] = useState({
        data_incasso: oggi,
        mezzo_pagamento: defaultMezzo,
        conto_cassa_id: conti?.[0]?.id || "",
        importo_pagato: lordo,
        tipo_chiusura: "sconto",
        motivo_sconto: "",
    });

    useEffect(() => {
        if (pref) setF((p) => ({ ...p, mezzo_pagamento: defaultMezzo }));
        // eslint-disable-next-line
    }, [pref]);

    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
    const residuo = Math.max(0, lordo - (parseFloat(f.importo_pagato) || 0));
    const hasResiduo = residuo > 0.005;

    const conferma = async () => {
        try {
            const res = await api.post(`/titoli/${titolo.id}/incassa`, {
                data_incasso: f.data_incasso,
                mezzo_pagamento: f.mezzo_pagamento,
                conto_cassa_id: f.conto_cassa_id || null,
                importo_pagato: parseFloat(f.importo_pagato) || 0,
                tipo_chiusura: hasResiduo ? f.tipo_chiusura : "sconto",
                motivo_sconto:
                    hasResiduo && f.tipo_chiusura === "sconto"
                        ? (f.motivo_sconto || "Sconto applicato")
                        : null,
            });
            const r = res.data || {};
            if (!hasResiduo) {
                toast.success(`Incassato ${fmtEur(f.importo_pagato)}`);
            } else if (f.tipo_chiusura === "sconto") {
                toast.success(
                    `Incassato ${fmtEur(f.importo_pagato)} — sconto ${fmtEur(residuo)} in prima nota`,
                );
            } else {
                toast.success(
                    `Incassato ${fmtEur(f.importo_pagato)} — residuo ${fmtEur(residuo)} lasciato a sospeso`,
                );
            }
            if (onDone) onDone(r);
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore incasso");
        }
    };

    return (
        <Dialog open onOpenChange={onClose}>
            <DialogContent className="max-w-lg" data-testid="dialog-incasso">
                <DialogHeader>
                    <DialogTitle>Incasso titolo — {titolo.contraente_nome || "—"}</DialogTitle>
                </DialogHeader>

                <div className="bg-amber-50 border border-amber-200 rounded-md p-3 text-xs text-amber-900 space-y-0.5">
                    <div><strong>Polizza:</strong> {titolo.numero_polizza} ({titolo.ramo})</div>
                    <div>
                        <strong>Premio (importo lordo):</strong>{" "}
                        <span className="num font-bold text-base text-amber-900" data-testid="dlg-premio">
                            {fmtEur(lordo)}
                        </span>
                    </div>
                    {titolo.data_copertura && (
                        <div>
                            <strong>Anticipato dall&apos;agenzia il:</strong> {fmtDate(titolo.data_copertura)}
                            {titolo.giorni_anticipo != null && ` (${titolo.giorni_anticipo} gg fa)`}
                        </div>
                    )}
                    {pref?.preferenza_pagamento && (
                        <div className="mt-1 text-emerald-700">
                            ★ <strong>Preferenza cliente:</strong> {pref.preferenza_pagamento}
                            {pref.ultimo_mezzo_pagamento &&
                                pref.ultimo_mezzo_pagamento !== pref.preferenza_pagamento &&
                                ` (ultimo usato: ${pref.ultimo_mezzo_pagamento})`}
                        </div>
                    )}
                </div>

                <div className="space-y-3 py-2">
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <Label>Data incasso</Label>
                            <Input
                                type="date" value={f.data_incasso}
                                onChange={(e) => set("data_incasso", e.target.value)}
                                data-testid="inc-data"
                            />
                        </div>
                        <div>
                            <Label>Mezzo pagamento</Label>
                            <Select value={f.mezzo_pagamento} onValueChange={(v) => set("mezzo_pagamento", v)}>
                                <SelectTrigger data-testid="inc-mezzo"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="contanti">Contanti</SelectItem>
                                    <SelectItem value="bonifico">Bonifico</SelectItem>
                                    <SelectItem value="assegno">Assegno</SelectItem>
                                    <SelectItem value="pos">POS / Carta</SelectItem>
                                    <SelectItem value="rid">RID</SelectItem>
                                    <SelectItem value="altro">Altro</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    </div>

                    <div>
                        <Label>Conto cassa di destinazione</Label>
                        <Select
                            value={f.conto_cassa_id || "__none__"}
                            onValueChange={(v) => set("conto_cassa_id", v === "__none__" ? "" : v)}
                        >
                            <SelectTrigger data-testid="inc-conto"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="__none__">— nessuno —</SelectItem>
                                {(conti || []).map((c) => (
                                    <SelectItem key={c.id} value={c.id}>
                                        {c.nome} ({c.tipo})
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>

                    <div className="bg-emerald-50 border border-emerald-200 rounded-md p-3 space-y-2">
                        <Label className="text-emerald-900 font-semibold">
                            Importo effettivamente pagato dal cliente
                        </Label>
                        <Input
                            type="number" step="0.01"
                            value={f.importo_pagato}
                            onChange={(e) => set("importo_pagato", e.target.value)}
                            className="text-lg font-semibold"
                            data-testid="inc-importo-pagato"
                        />
                        <div className="text-[11px] text-emerald-800/80">
                            Premio originale: <strong>{fmtEur(lordo)}</strong>
                        </div>

                        {hasResiduo && (
                            <div className="bg-white border border-amber-300 rounded p-3 mt-2 space-y-2" data-testid="residuo-section">
                                <div className="flex justify-between items-center font-semibold text-amber-800">
                                    <span>Residuo da gestire:</span>
                                    <span className="num text-base">{fmtEur(residuo)}</span>
                                </div>

                                <RadioGroup
                                    value={f.tipo_chiusura}
                                    onValueChange={(v) => set("tipo_chiusura", v)}
                                    className="space-y-1"
                                >
                                    <label
                                        htmlFor="opt-sconto"
                                        className={`flex items-start gap-2 p-2 rounded border cursor-pointer ${
                                            f.tipo_chiusura === "sconto"
                                                ? "border-amber-400 bg-amber-50"
                                                : "border-slate-200 hover:bg-slate-50"
                                        }`}
                                        data-testid="opt-sconto-label"
                                    >
                                        <RadioGroupItem id="opt-sconto" value="sconto" data-testid="opt-sconto" />
                                        <div className="flex-1 text-xs">
                                            <div className="font-semibold text-slate-900">Applica sconto cliente</div>
                                            <div className="text-slate-600">
                                                Lo sconto di <strong className="num">{fmtEur(residuo)}</strong> entra in
                                                Prima Nota come <em>uscita</em> (categoria “sconto_cliente”).
                                            </div>
                                        </div>
                                    </label>

                                    <label
                                        htmlFor="opt-sospeso"
                                        className={`flex items-start gap-2 p-2 rounded border cursor-pointer ${
                                            f.tipo_chiusura === "sospeso"
                                                ? "border-amber-400 bg-amber-50"
                                                : "border-slate-200 hover:bg-slate-50"
                                        }`}
                                        data-testid="opt-sospeso-label"
                                    >
                                        <RadioGroupItem id="opt-sospeso" value="sospeso" data-testid="opt-sospeso" />
                                        <div className="flex-1 text-xs">
                                            <div className="font-semibold text-slate-900">Lascia il residuo a sospeso</div>
                                            <div className="text-slate-600">
                                                Viene creato un <strong>nuovo titolo</strong> di{" "}
                                                <strong className="num">{fmtEur(residuo)}</strong> in stato{" "}
                                                <em>“da incassare”</em>, visibile nei Sospesi.
                                            </div>
                                        </div>
                                    </label>
                                </RadioGroup>

                                {f.tipo_chiusura === "sconto" && (
                                    <Input
                                        placeholder="Motivo dello sconto (opzionale)"
                                        value={f.motivo_sconto}
                                        onChange={(e) => set("motivo_sconto", e.target.value)}
                                        className="text-xs"
                                        data-testid="inc-motivo-sconto"
                                    />
                                )}
                            </div>
                        )}
                    </div>
                </div>

                <DialogFooter>
                    <Button
                        onClick={conferma}
                        className="bg-emerald-600 hover:bg-emerald-700"
                        data-testid="inc-conferma"
                    >
                        Conferma incasso
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
