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
    const round2 = (x) => Math.round((parseFloat(x) || 0) * 100) / 100;
    const [f, setF] = useState(() => ({
        ...titolo,
        importo_lordo: round2(titolo.importo_lordo),
        importo_netto: round2(titolo.importo_netto),
        imposte: round2(titolo.imposte),
        provvigioni: titolo.provvigioni != null ? round2(titolo.provvigioni) : titolo.provvigioni,
    }));
    const [giornataChiusa, setGiornataChiusa] = useState(false);
    const [collaboratori, setCollaboratori] = useState([]);
    // Ripartizione provvigione multi-collaboratore
    const [operatori, setOperatori] = useState(() => {
        if (Array.isArray(titolo.provvigioni_operatori) && titolo.provvigioni_operatori.length > 0) {
            return titolo.provvigioni_operatori.map((o) => ({ operatore_id: o.operatore_id || "", provvigione: o.provvigione ?? 0 }));
        }
        if (titolo.collaboratore_id) {
            return [{ operatore_id: titolo.collaboratore_id, provvigione: titolo.provvigioni ?? 0 }];
        }
        return [];
    });
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    useEffect(() => {
        api.get("/auth/users", { params: { role: "collaboratore" } })
            .then((r) => setCollaboratori(r.data || []))
            .catch(() => setCollaboratori([]));
    }, []);

    // Eredita automaticamente i collaboratori dalla polizza se il titolo non ne ha di propri
    useEffect(() => {
        const haGiaSuoi = Array.isArray(titolo.provvigioni_operatori) && titolo.provvigioni_operatori.length > 0;
        if (!titolo.polizza_id) return;
        api.get(`/polizze/${titolo.polizza_id}`).then((r) => {
            // Tipo di pagamento: eredita dal preferito della polizza se il titolo non ne ha uno
            const preferito = r.data?.mezzo_pagamento_preferito || r.data?.ultimo_mezzo_pagamento;
            if (preferito && !titolo.mezzo_pagamento) {
                setF((p) => (p.mezzo_pagamento ? p : { ...p, mezzo_pagamento: preferito }));
            }
            if (haGiaSuoi) return;
            const po = r.data?.provvigioni_operatori || [];
            if (po.length > 0) {
                setOperatori(po.map((o) => ({ operatore_id: o.operatore_id || o.collaboratore_id || "", provvigione: o.provvigione ?? 0 })));
            } else if (r.data?.collaboratore_id && !titolo.collaboratore_id) {
                const base = titolo.provvigioni ?? r.data?.provvigioni ?? 0;
                quotaCollaboratore(r.data.collaboratore_id, base).then((q) => {
                    setOperatori([{ operatore_id: r.data.collaboratore_id, provvigione: (q ?? 0) }]);
                });
            }
        }).catch(() => {});
        // eslint-disable-next-line
    }, [titolo.id]);

    const totOperatori = operatori.reduce((s, o) => s + (parseFloat(o.provvigione) || 0), 0);
    // Quota spettante al collaboratore = totale provvigioni titolo × % collaboratore (dallo schema)
    const quotaCollaboratore = async (collabId, baseTotale) => {
        try {
            const r = await api.get("/librerie/schema-provvigionale", { params: { collaboratore_id: collabId } });
            const schemi = r.data || [];
            const schema = schemi.find((s) => s.attivo !== false) || schemi[0];
            const pct = parseFloat(schema?.percentuale_collaboratore) || 0;
            if (pct <= 0) return null;
            return Math.round((parseFloat(baseTotale) || 0) * pct / 100 * 100) / 100;
        } catch { return null; }
    };
    const addOperatore = () => setOperatori((p) => [...p, { operatore_id: "", provvigione: 0 }]);
    const removeOperatore = (i) => setOperatori((p) => p.filter((_, idx) => idx !== i));
    const setOperatore = (i, k, v) => {
        setOperatori((p) => p.map((o, idx) => idx === i ? { ...o, [k]: v } : o));
        // AUTO-CALCOLO provvigioni dallo schema del collaboratore appena selezionato
        if (k === "operatore_id" && v) {
            quotaCollaboratore(v, f.provvigioni).then((q) => {
                if (q !== null && q > 0) {
                    setOperatori((p) => p.map((o, idx) => idx === i ? { ...o, provvigione: q } : o));
                    toast.success(`Provvigione calcolata dallo schema: ${q.toFixed(2)} €`);
                }
            });
        }
    };
    const ereditaDaPolizza = async () => {
        try {
            const r = await api.get(`/polizze/${titolo.polizza_id}`);
            const po = r.data?.provvigioni_operatori || [];
            if (po.length > 0) {
                setOperatori(po.map((o) => ({ operatore_id: o.operatore_id || o.collaboratore_id || "", provvigione: o.provvigione ?? 0 })));
                toast.success("Operatori ereditati dalla polizza");
            } else if (r.data?.collaboratore_id) {
                setOperatori([{ operatore_id: r.data.collaboratore_id, provvigione: 0 }]);
                toast.info("La polizza ha un solo collaboratore");
            } else {
                toast.warning("La polizza non ha operatori configurati");
            }
        } catch { toast.error("Errore lettura polizza"); }
    };

    const recalcProvvigione = async () => {
        try {
            const r = await api.get("/provvigioni/calcola", {
                params: {
                    premio_lordo: f.importo_lordo || 0,
                    collaboratore_id: operatori[0]?.operatore_id || f.collaboratore_id || undefined,
                    ramo: titolo.ramo || undefined,
                },
            });
            if (r.data.provvigione_totale > 0) {
                set("provvigioni", r.data.provvigione_totale);
                const collabId = operatori[0]?.operatore_id || f.collaboratore_id || "";
                // Ripartizione piramidale: collaboratore diretto + upline a cascata
                const ops = [];
                if (collabId) ops.push({ operatore_id: collabId, provvigione: r.data.provvigione_collaboratore || 0 });
                (r.data.upline_breakdown || []).forEach((u) => ops.push({ operatore_id: u.operatore_id, provvigione: u.provvigione }));
                if (ops.length > 0) setOperatori(ops);
                const extra = (r.data.upline_breakdown || []).length ? ` · +${r.data.upline_breakdown.length} upline` : "";
                toast.success(`Provvigione: ${r.data.provvigione_totale}€ (${r.data.schema_nome || "schema"})${extra}`);
            } else {
                toast.warning("Nessuno schema provvigionale applicabile");
            }
        } catch { toast.error("Errore calcolo provvigione"); }
    };

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

    // Una volta incassato/coperto il titolo, provvigioni e collaboratori non sono più modificabili
    const incassato = !titolo._new && (
        ["incassato", "coperto", "liquidato", "pagato"].includes((titolo.stato || "").toLowerCase())
        || !!titolo.data_incasso
    );

    const save = async () => {
        const isNew = titolo._new || !titolo.id;
        const opsClean = operatori
            .filter((o) => o.operatore_id)
            .map((o) => {
                const c = collaboratori.find((x) => x.id === o.operatore_id);
                return { operatore_id: o.operatore_id, operatore_nome: c ? (c.name || c.email) : "", provvigione: parseFloat(o.provvigione) || 0 };
            });
        const provvTot = (f.provvigioni !== "" && f.provvigioni != null)
            ? round2(f.provvigioni)
            : (opsClean.length > 0 ? round2(opsClean.reduce((s, o) => s + o.provvigione, 0)) : 0);
        const payload = {
            tipo: f.tipo, effetto: f.effetto, scadenza: f.scadenza,
            importo_lordo: round2(f.importo_lordo),
            importo_netto: round2(f.importo_netto),
            imposte: round2(f.imposte),
            provvigioni: provvTot,
            provvigioni_operatori: opsClean,
            collaboratore_id: opsClean[0]?.operatore_id || f.collaboratore_id || null,
            mezzo_pagamento: f.mezzo_pagamento || null,
            data_incasso: f.data_incasso || null,
            coperto_fino_a: f.coperto_fino_a || null,
        };
        try {
            if (isNew) {
                payload.polizza_id = titolo.polizza_id;
                if (!payload.tipo) payload.tipo = "quietanza";
                await api.post(`/titoli`, payload);
                toast.success("Titolo creato");
            } else {
                await api.put(`/titoli/${titolo.id}`, payload);
                toast.success("Titolo aggiornato");
            }
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
                        {titolo._new ? "Nuovo titolo" : "Modifica titolo"} {titolo.numero_polizza ? `– Polizza ${titolo.numero_polizza}` : ""}
                    </DialogTitle>
                    <p className="text-[11px] text-slate-500 mt-1">
                        Lo stato del titolo si aggiorna automaticamente con incasso / copertura / storno.
                    </p>
                </DialogHeader>
                <ChiusuraGiornoBanner data={f.data_incasso} />
                <div className="grid grid-cols-2 gap-3 py-2">
                    <div>
                        <Label>Tipo (riferimento)</Label>
                        <Select value={f.tipo} onValueChange={(v) => set("tipo", v)}>
                            <SelectTrigger data-testid="titolo-tipo-select"><SelectValue placeholder="Seleziona tipo" /></SelectTrigger>
                            <SelectContent>
                                {[
                                    ["quietanza", "Quietanza di rinnovo"],
                                    ["nuova", "Polizza nuova"],
                                    ["rinnovo", "Rinnovo"],
                                    ["appendice", "Appendice"],
                                    ["annullo", "Annullo"],
                                    ["sostituzione", "Sostituzione"],
                                    ["regolazione", "Regolazione premio"],
                                    ["storno", "Storno"],
                                ].map(([v, l]) => (
                                    <SelectItem key={v} value={v}>{l}</SelectItem>
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
                    <div>
                        <Label>Provvigioni € (totale)</Label>
                        <div className="flex gap-2">
                            <Input type="number" step="0.01" value={f.provvigioni ?? 0}
                                onChange={(e) => set("provvigioni", e.target.value)} disabled={incassato}
                                data-testid="titolo-provvigioni" />
                            <Button type="button" variant="outline" size="sm" onClick={recalcProvvigione} disabled={incassato} data-testid="titolo-provv-auto">Auto</Button>
                        </div>
                        {operatori.length > 0 && <p className="text-[10px] text-slate-400 mt-0.5">Ripartito fra {operatori.length} collab. · totale {totOperatori.toFixed(2)}€ (modificabile)</p>}
                    </div>
                    <div className="col-span-2 border border-slate-200 rounded-lg p-3 bg-slate-50/60">
                        <div className="flex items-center justify-between mb-2">
                            <Label className="text-xs font-semibold text-slate-700">Ripartizione provvigione fra collaboratori</Label>
                            <div className="flex gap-2">
                                <Button type="button" variant="outline" size="sm" className="h-7 text-xs" onClick={ereditaDaPolizza} disabled={incassato} data-testid="titolo-eredita-polizza">Eredita da polizza</Button>
                                <Button type="button" size="sm" className="h-7 text-xs bg-sky-700 hover:bg-sky-800" onClick={addOperatore} disabled={incassato} data-testid="titolo-add-operatore">+ Collaboratore</Button>
                            </div>
                        </div>
                        {incassato && <div className="text-[11px] text-amber-600 mb-2">🔒 Titolo incassato: provvigioni e collaboratori non più modificabili.</div>}
                        {operatori.length === 0 ? (
                            <div className="text-[11px] text-slate-400 italic">Nessun collaboratore: usa il campo Provvigioni sopra oppure aggiungi uno o più collaboratori.</div>
                        ) : (
                            <div>
                                <table className="w-full text-xs">
                                    <thead>
                                        <tr className="bg-slate-800 text-slate-100">
                                            <th className="w-8 text-center py-1 rounded-l">#</th>
                                            <th className="text-left px-2 py-1">Operatore</th>
                                            <th className="w-32 text-right px-2 py-1">Provvigione €</th>
                                            <th className="w-14 text-center py-1 rounded-r">Azioni</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {operatori.map((o, i) => (
                                            <tr key={i} className={i % 2 ? "bg-white" : "bg-slate-50/60"} data-testid={`titolo-operatore-row-${i}`}>
                                                <td className="text-center text-slate-400">{i + 1}</td>
                                                <td className="px-1 py-1">
                                                    <Select value={o.operatore_id || "__none__"} disabled={incassato} onValueChange={(v) => setOperatore(i, "operatore_id", v === "__none__" ? "" : v)}>
                                                        <SelectTrigger className="w-full h-8" data-testid={`titolo-operatore-select-${i}`}><SelectValue placeholder="— collaboratore —" /></SelectTrigger>
                                                        <SelectContent>
                                                            <SelectItem value="__none__">— collaboratore —</SelectItem>
                                                            {collaboratori.map((c) => <SelectItem key={c.id} value={c.id}>{c.name || c.email}</SelectItem>)}
                                                        </SelectContent>
                                                    </Select>
                                                </td>
                                                <td className="px-1 py-1">
                                                    <Input type="number" step="0.01" className="w-full h-8 text-right" placeholder="€" disabled={incassato}
                                                        value={o.provvigione} onChange={(e) => setOperatore(i, "provvigione", e.target.value)}
                                                        data-testid={`titolo-operatore-provv-${i}`} />
                                                </td>
                                                <td className="text-center">
                                                    {!incassato && <button type="button" onClick={() => removeOperatore(i)} className="text-rose-500 hover:text-rose-700 text-sm" data-testid={`titolo-operatore-del-${i}`}>✕</button>}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                                <div className="text-right text-xs text-slate-600 mt-2">Totale ripartito: <b className="text-slate-900">{totOperatori.toFixed(2)} €</b></div>
                            </div>
                        )}
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
