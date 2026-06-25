/**
 * DialogIncassoCopertura — Replica del facsimile "Incasso / Copertura".
 *
 * Flusso unificato sui titoli:
 *  1) Si controllano e si modificano i dati del titolo (Tipo, date)
 *  2) Si può attivare la "Copertura" (l'agenzia anticipa per il cliente)
 *      con sub-opzioni: invio email a operatori/contraenti, pagamento in direzione
 *  3) Si può attivare l'"Incasso" che apre i campi importo pagato + radio
 *      sconto/sospeso (residuo)
 */
import { useEffect, useMemo, useState } from "react";
import { api, fmtEur } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import {
    RadioGroup, RadioGroupItem,
} from "@/components/ui/radio-group";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { X } from "lucide-react";
import { toast } from "sonner";

const TIPO_TITOLO_OPTS = [
    { v: "quietanza", l: "Quietanza" },
    { v: "rinnovo", l: "Rinnovo" },
    { v: "nuova", l: "Nuova" },
    { v: "appendice", l: "Appendice" },
    { v: "regolazione", l: "Regolazione" },
    { v: "storno", l: "Storno" },
];

function addDays(iso, days) {
    if (!iso) return "";
    const d = new Date(`${iso}T00:00:00`);
    d.setDate(d.getDate() + days);
    return d.toISOString().slice(0, 10);
}

export default function DialogIncassoCopertura({ titolo, conti, onClose, onDone }) {
    const today = new Date().toISOString().slice(0, 10);
    const lordo = parseFloat(titolo.importo_lordo) || 0;
    const [pref, setPref] = useState(null);

    useEffect(() => {
        if (titolo.contraente_id) {
            api.get(`/anagrafiche/${titolo.contraente_id}`).then((r) => setPref(r.data)).catch(() => {});
        }
    }, [titolo.contraente_id]);

    const giaCoperto = !!titolo.titolo_coperto;
    const giaIncassato = titolo.stato === "incassato";

    // --- DATI BASE titolo
    const [f, setF] = useState({
        tipo: titolo.tipo || "quietanza",
        data_emissione: titolo.data_emissione || titolo.effetto || today,
        effetto: titolo.effetto || today,
        ora_effetto: titolo.ora_effetto || "24:00",
        data_competenza: titolo.data_competenza || titolo.effetto || today,
        scadenza_mora: titolo.scadenza_mora || addDays(titolo.effetto || today, 15),
    });
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    // --- COPERTURA
    const [copertura, setCopertura] = useState(!giaCoperto); // default check se non ancora coperto
    const [emailOperatori, setEmailOperatori] = useState(false);
    const [emailContraenti, setEmailContraenti] = useState(false);
    const [inDirezione, setInDirezione] = useState(false);

    // --- INCASSO
    const [incasso, setIncasso] = useState(false);
    // Default mezzo pagamento (priorità):
    //  1. polizza.mezzo_pagamento_preferito (specifico di questa polizza)
    //  2. polizza.ultimo_mezzo_pagamento
    //  3. anagrafica preferenza_pagamento
    //  4. anagrafica ultimo_mezzo_pagamento
    //  5. "contanti"
    const polizzaPreferito = titolo.mezzo_pagamento_preferito || titolo.ultimo_mezzo_pagamento;
    const defaultMezzoPol = polizzaPreferito
        || pref?.preferenza_pagamento
        || pref?.ultimo_mezzo_pagamento
        || "contanti";

    const [inc, setInc] = useState({
        data_incasso: today,
        mezzo_pagamento: defaultMezzoPol,
        conto_cassa_id: conti?.[0]?.id || "",
        importo_pagato: lordo,
        tipo_chiusura: "sconto",
        motivo_sconto: "",
    });
    useEffect(() => {
        if (polizzaPreferito) {
            setInc((p) => ({ ...p, mezzo_pagamento: polizzaPreferito }));
        } else if (pref?.preferenza_pagamento) {
            setInc((p) => ({ ...p, mezzo_pagamento: pref.preferenza_pagamento }));
        }
    }, [pref, polizzaPreferito]);
    const setI = (k, v) => setInc((p) => ({ ...p, [k]: v }));

    const residuo = useMemo(
        () => Math.max(0, lordo - (parseFloat(inc.importo_pagato) || 0)),
        [lordo, inc.importo_pagato],
    );
    const hasResiduo = residuo > 0.005;

    const conferma = async () => {
        try {
            // 1) AGGIORNA DATI BASE (tipo + date) sempre
            await api.put(`/titoli/${titolo.id}`, {
                tipo: f.tipo,
                data_emissione: f.data_emissione,
                effetto: f.effetto,
                ora_effetto: f.ora_effetto,
                data_competenza: f.data_competenza,
                scadenza_mora: f.scadenza_mora,
            });

            // 2) COPERTURA (se richiesta e non già coperto)
            if (copertura && !giaCoperto) {
                await api.post(`/titoli/bulk-copertura`, {
                    ids: [titolo.id],
                    data_copertura: f.effetto || today,
                    note: inDirezione ? "Pagamento effettuato dal cliente direttamente in direzione" : null,
                });
                if (inDirezione) {
                    await api.put(`/titoli/${titolo.id}`, { pagamento_in_direzione: true });
                }
                if (emailOperatori || emailContraenti) {
                    try {
                        await api.post(`/titoli/notifica-copertura`, {
                            id: titolo.id,
                            a_operatori: emailOperatori,
                            a_contraenti: emailContraenti,
                        });
                    } catch { /* non bloccante */ }
                }
            }

            // 3) INCASSO (se richiesto)
            if (incasso && !giaIncassato) {
                await api.post(`/titoli/${titolo.id}/incassa`, {
                    data_incasso: inc.data_incasso,
                    mezzo_pagamento: inc.mezzo_pagamento,
                    conto_cassa_id: null,
                    importo_pagato: parseFloat(inc.importo_pagato) || 0,
                    tipo_chiusura: hasResiduo ? inc.tipo_chiusura : "sconto",
                    motivo_sconto:
                        hasResiduo && inc.tipo_chiusura === "sconto"
                            ? (inc.motivo_sconto || "Sconto applicato")
                            : null,
                });
            }

            const msg = [
                copertura && !giaCoperto ? "copertura registrata" : null,
                incasso && !giaIncassato
                    ? (hasResiduo
                        ? (inc.tipo_chiusura === "sospeso"
                            ? `incassato ${fmtEur(inc.importo_pagato)} (residuo ${fmtEur(residuo)} a sospeso)`
                            : `incassato ${fmtEur(inc.importo_pagato)} (sconto ${fmtEur(residuo)})`)
                        : `incassato ${fmtEur(inc.importo_pagato)}`)
                    : null,
            ].filter(Boolean).join(" — ");
            toast.success(msg || "Salvato");
            if (onDone) onDone();
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore salvataggio");
        }
    };

    // Stile celle "tabella" del facsimile
    const cellLabel = "bg-slate-100 text-slate-700 font-medium text-right px-3 py-2 align-middle border border-slate-200 w-[180px]";
    const cellValueRO = "bg-cyan-50 text-cyan-900 px-3 py-2 align-middle border border-slate-200";
    const cellValueEdit = "bg-cyan-50 px-2 py-1 align-middle border border-slate-200";

    return (
        <Dialog open onOpenChange={onClose}>
            <DialogContent
                className="max-w-2xl p-0 overflow-hidden bg-white"
                data-testid="dialog-incasso-copertura"
            >
                {/* Header stile facsimile */}
                <DialogHeader className="px-6 py-3 border-b border-slate-200 bg-white flex flex-row items-center justify-between">
                    <DialogTitle className="text-slate-800 font-semibold">
                        Incasso / Copertura
                    </DialogTitle>
                    <button
                        onClick={onClose}
                        className="text-slate-400 hover:text-slate-600"
                        data-testid="dialog-close"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </DialogHeader>

                <div className="px-6 py-4 max-h-[78vh] overflow-y-auto">
                    {/* ---- Tabella anagrafica ---- */}
                    <table className="w-full border-collapse text-sm">
                        <tbody>
                            <tr>
                                <td className={cellLabel}>Contraente</td>
                                <td className={cellValueRO} data-testid="ico-contraente">
                                    {titolo.contraente_nome || "—"}
                                </td>
                            </tr>
                            <tr>
                                <td className={cellLabel}>Compagnia</td>
                                <td className={cellValueRO} data-testid="ico-compagnia">
                                    {titolo.compagnia_nome || "—"}
                                </td>
                            </tr>
                            <tr>
                                <td className={cellLabel}>Tipo</td>
                                <td className={cellValueRO}>{titolo.ramo || "—"}</td>
                            </tr>

                            <tr>
                                <td className={cellLabel}>Tipo titolo</td>
                                <td className={cellValueEdit}>
                                    <Select value={f.tipo} onValueChange={(v) => set("tipo", v)}>
                                        <SelectTrigger className="bg-white" data-testid="ico-tipo-titolo">
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {TIPO_TITOLO_OPTS.map((o) => (
                                                <SelectItem key={o.v} value={o.v}>{o.l}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </td>
                            </tr>

                            <tr>
                                <td className={cellLabel}>Data emissione</td>
                                <td className={cellValueEdit}>
                                    <Input
                                        type="date" value={f.data_emissione}
                                        onChange={(e) => set("data_emissione", e.target.value)}
                                        className="bg-white" data-testid="ico-data-emissione"
                                    />
                                </td>
                            </tr>
                        </tbody>
                    </table>

                    {/* ---- Rata del / Dalle ore / Data competenza / Scadenza mora ---- */}
                    <table className="w-full border-collapse text-sm mt-4">
                        <tbody>
                            <tr>
                                <td className={cellLabel}>Rata del</td>
                                <td className={cellValueEdit}>
                                    <Input
                                        type="date" value={f.effetto}
                                        onChange={(e) => set("effetto", e.target.value)}
                                        className="bg-white" data-testid="ico-rata-del"
                                    />
                                </td>
                                <td className={cellLabel + " w-[120px]"}>Dalle ore</td>
                                <td className={cellValueEdit + " w-[120px]"}>
                                    <Input
                                        type="time" value={f.ora_effetto}
                                        onChange={(e) => set("ora_effetto", e.target.value)}
                                        className="bg-white" data-testid="ico-ora"
                                    />
                                </td>
                            </tr>
                            <tr>
                                <td className={cellLabel}>Data competenza</td>
                                <td className={cellValueEdit}>
                                    <Input
                                        type="date" value={f.data_competenza}
                                        onChange={(e) => set("data_competenza", e.target.value)}
                                        className="bg-white" data-testid="ico-data-competenza"
                                    />
                                </td>
                                <td className={cellLabel}>Scadenza mora</td>
                                <td className={cellValueEdit}>
                                    <Input
                                        type="date" value={f.scadenza_mora}
                                        onChange={(e) => set("scadenza_mora", e.target.value)}
                                        className="bg-white" data-testid="ico-scadenza-mora"
                                    />
                                </td>
                            </tr>
                        </tbody>
                    </table>

                    {/* ---- COPERTURA ---- */}
                    <div className="mt-6">
                        <label
                            htmlFor="cb-copertura"
                            className="flex items-center gap-3 cursor-pointer"
                        >
                            <Checkbox
                                id="cb-copertura"
                                checked={copertura}
                                onCheckedChange={(v) => setCopertura(v === true)}
                                disabled={giaCoperto}
                                data-testid="cb-copertura"
                            />
                            <span className="text-cyan-700 font-semibold text-lg">
                                Copertura {giaCoperto && <span className="text-emerald-700 text-xs ml-2">(già coperto)</span>}
                            </span>
                        </label>
                        {copertura && (
                            <div className="pl-8 mt-2 space-y-2" data-testid="copertura-options">
                                <label className="flex items-center gap-2 text-cyan-700 text-sm cursor-pointer">
                                    <Checkbox
                                        checked={emailOperatori}
                                        onCheckedChange={(v) => setEmailOperatori(v === true)}
                                        data-testid="cb-email-op"
                                    />
                                    Invia email di notifica a operatori
                                </label>
                                <label className="flex items-center gap-2 text-cyan-700 text-sm cursor-pointer">
                                    <Checkbox
                                        checked={emailContraenti}
                                        onCheckedChange={(v) => setEmailContraenti(v === true)}
                                        data-testid="cb-email-cnt"
                                    />
                                    Invia email di notifica a contraenti
                                </label>
                                <label className="flex items-center gap-2 text-cyan-700 text-sm cursor-pointer">
                                    <Checkbox
                                        checked={inDirezione}
                                        onCheckedChange={(v) => setInDirezione(v === true)}
                                        data-testid="cb-direzione"
                                    />
                                    Pagamento (premio) effettuato dal cliente direttamente in direzione
                                </label>
                            </div>
                        )}
                    </div>

                    {/* ---- INCASSO ---- */}
                    <div className="mt-4">
                        <label
                            htmlFor="cb-incasso"
                            className="flex items-center gap-3 cursor-pointer"
                        >
                            <Checkbox
                                id="cb-incasso"
                                checked={incasso}
                                onCheckedChange={(v) => setIncasso(v === true)}
                                disabled={giaIncassato}
                                data-testid="cb-incasso"
                            />
                            <span className="text-cyan-700 font-semibold text-lg">
                                Incasso {giaIncassato && <span className="text-emerald-700 text-xs ml-2">(già incassato)</span>}
                            </span>
                        </label>

                        {incasso && (
                            <div className="pl-8 mt-3 space-y-3" data-testid="incasso-options">
                                <div className="grid grid-cols-2 gap-3">
                                    <div>
                                        <div className="text-xs text-slate-600 mb-1">Data incasso</div>
                                        <Input
                                            type="date" value={inc.data_incasso}
                                            onChange={(e) => setI("data_incasso", e.target.value)}
                                            data-testid="ico-data-incasso"
                                        />
                                    </div>
                                    <div>
                                        <div className="text-xs text-slate-600 mb-1">Mezzo pagamento</div>
                                        <Select
                                            value={inc.mezzo_pagamento}
                                            onValueChange={(v) => setI("mezzo_pagamento", v)}
                                        >
                                            <SelectTrigger data-testid="ico-mezzo"><SelectValue /></SelectTrigger>
                                            <SelectContent>
                                                <SelectItem value="contanti">Contanti</SelectItem>
                                                <SelectItem value="bonifico">Bonifico</SelectItem>
                                                <SelectItem value="assegno">Assegno</SelectItem>
                                                <SelectItem value="pos">POS / Carta</SelectItem>
                                                <SelectItem value="rid">RID</SelectItem>
                                                <SelectItem value="altro">Altro</SelectItem>
                                            </SelectContent>
                                        </Select>
                                        {polizzaPreferito && (
                                            <div className="text-[10px] text-emerald-700 mt-1" data-testid="hint-mezzo-polizza">
                                                ★ Preferito su questa polizza: <strong>{polizzaPreferito}</strong>
                                            </div>
                                        )}
                                    </div>
                                </div>
                                <div className="text-[10px] text-slate-500">
                                    Il conto/banca viene determinato automaticamente dal mezzo di pagamento (vedi Librerie → Conti cassa).
                                </div>

                                <div className="bg-emerald-50 border border-emerald-200 rounded p-3">
                                    <div className="text-xs text-emerald-900 font-semibold mb-1">
                                        Importo pagato dal cliente (premio: {fmtEur(lordo)})
                                    </div>
                                    <Input
                                        type="number" step="0.01"
                                        value={inc.importo_pagato}
                                        onChange={(e) => setI("importo_pagato", e.target.value)}
                                        className="text-lg font-semibold bg-white"
                                        data-testid="ico-importo-pagato"
                                    />

                                    {hasResiduo && (
                                        <div
                                            className="bg-white border border-amber-300 rounded p-2 mt-2 space-y-2"
                                            data-testid="residuo-section"
                                        >
                                            <div className="flex justify-between items-center font-semibold text-amber-800 text-sm">
                                                <span>Residuo:</span>
                                                <span className="num">{fmtEur(residuo)}</span>
                                            </div>
                                            <RadioGroup
                                                value={inc.tipo_chiusura}
                                                onValueChange={(v) => setI("tipo_chiusura", v)}
                                                className="space-y-1"
                                            >
                                                <label
                                                    htmlFor="opt-sc"
                                                    className={`flex items-start gap-2 p-2 rounded border cursor-pointer ${
                                                        inc.tipo_chiusura === "sconto"
                                                            ? "border-amber-400 bg-amber-50"
                                                            : "border-slate-200 hover:bg-slate-50"
                                                    }`}
                                                >
                                                    <RadioGroupItem id="opt-sc" value="sconto" data-testid="opt-sconto" />
                                                    <span className="text-xs">
                                                        <strong>Applica sconto</strong> — {fmtEur(residuo)} in Prima Nota uscita
                                                    </span>
                                                </label>
                                                <label
                                                    htmlFor="opt-sp"
                                                    className={`flex items-start gap-2 p-2 rounded border cursor-pointer ${
                                                        inc.tipo_chiusura === "sospeso"
                                                            ? "border-amber-400 bg-amber-50"
                                                            : "border-slate-200 hover:bg-slate-50"
                                                    }`}
                                                >
                                                    <RadioGroupItem id="opt-sp" value="sospeso" data-testid="opt-sospeso" />
                                                    <span className="text-xs">
                                                        <strong>Lascia a sospeso</strong> — nuovo titolo residuo da {fmtEur(residuo)}
                                                    </span>
                                                </label>
                                            </RadioGroup>
                                            {inc.tipo_chiusura === "sconto" && (
                                                <Input
                                                    placeholder="Motivo sconto (opzionale)"
                                                    value={inc.motivo_sconto}
                                                    onChange={(e) => setI("motivo_sconto", e.target.value)}
                                                    className="text-xs bg-white"
                                                    data-testid="ico-motivo-sconto"
                                                />
                                            )}
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>

                    {/* ---- Totale ---- */}
                    <div className="mt-6 border-t border-slate-200 pt-3 flex justify-end items-center gap-3">
                        <span className="text-slate-700 font-medium">Totale:</span>
                        <span
                            className="bg-cyan-50 border border-slate-200 px-3 py-1.5 text-base num font-semibold text-cyan-900"
                            data-testid="ico-totale"
                        >
                            {fmtEur(lordo)}
                        </span>
                    </div>
                </div>

                {/* ---- Footer ---- */}
                <div className="px-6 py-3 border-t border-slate-200 bg-slate-50 flex justify-end gap-2">
                    <Button
                        variant="outline" onClick={onClose}
                        data-testid="ico-chiudi"
                    >Chiudi</Button>
                    <Button
                        onClick={conferma}
                        className="bg-slate-800 hover:bg-slate-900"
                        data-testid="ico-conferma"
                    >Conferma</Button>
                </div>
            </DialogContent>
        </Dialog>
    );
}
