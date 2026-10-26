import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
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
import TagsEditor from "@/components/TagsEditor";
import AzioniCliente from "@/components/AzioniCliente";

/**
 * Dialog di modifica titolo, condiviso tra pagina Titoli e PolizzaDetail.
 *
 * Props:
 *  - titolo: oggetto titolo da modificare (richiesto)
 *  - onClose: callback su chiusura/salvataggio
 *  - onDelete?: opzionale, se passato mostra pulsante elimina
 */
export default function TitoloDialog({ titolo, onClose, onDelete }) {
    const navigate = useNavigate();
    const round2 = (x) => Math.round((parseFloat(x) || 0) * 100) / 100;
    const [f, setF] = useState(() => ({
        ...titolo,
        tipo: titolo.tipo === "rinnovo" ? "quietanza" : titolo.tipo,
        importo_lordo: round2(titolo.importo_lordo),
        importo_netto: round2(titolo.importo_netto),
        imposte: round2(titolo.imposte),
        ssn: round2(titolo.ssn),
        diritti: round2(titolo.diritti),
        accessori: round2(titolo.accessori),
        provvigioni: titolo.provvigioni != null ? round2(titolo.provvigioni) : titolo.provvigioni,
    }));
    const [giornataChiusa, setGiornataChiusa] = useState(false);
    const [collaboratori, setCollaboratori] = useState([]);
    // Tipi titolo dalla libreria (Librerie → Tipi titolo), con fallback ai tipi di sistema
    const FALLBACK_TIPI = [
        ["quietanza", "Quietanza"], ["nuova", "Polizza nuova"], ["appendice", "Appendice"],
        ["inclusione", "Inclusione"], ["esclusione", "Esclusione"], ["annullo", "Annullo"],
        ["sostituzione", "Sostituzione"], ["regolazione", "Regolazione premio"], ["storno", "Storno"],
    ];
    const [tipiTitolo, setTipiTitolo] = useState(FALLBACK_TIPI);
    useEffect(() => {
        api.get("/librerie/tipi-titolo", { params: { solo_attivi: true } })
            .then((r) => { if (Array.isArray(r.data) && r.data.length) setTipiTitolo(r.data.map((t) => [t.chiave, t.nome])); })
            .catch(() => {});
    }, []);
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
    // Compagnia/ramo per risolvere lo schema provvigionale CORRETTO (la compagnia
    // sta sulla POLIZZA, non sul titolo): senza questo la ripartizione usava sempre
    // il primo schema del collaboratore ignorando la compagnia.
    const [provvCtx, setProvvCtx] = useState({ compagnia_id: titolo.compagnia_id || null, ramo: titolo.ramo || null });

    // Frazionamento polizza → calcolo automatico scadenza da effetto
    const MESI_FRAZ = { annuale: 12, semestrale: 6, quadrimestrale: 4, trimestrale: 3, bimestrale: 2, mensile: 1, unica: 12 };
    const [polFraz, setPolFraz] = useState((titolo.frazionamento || "").toLowerCase());
    const addMesiISO = (dateStr, mesi) => {
        if (!dateStr || !/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) return "";
        const [y, m, d] = dateStr.split("-").map(Number);
        const base = new Date(Date.UTC(y, m - 1, d));
        base.setUTCMonth(base.getUTCMonth() + mesi);
        if (base.getUTCDate() !== d) base.setUTCDate(0); // fine mese
        return base.toISOString().slice(0, 10);
    };
    const setEffetto = (v) => {
        const mesi = MESI_FRAZ[polFraz] || 12;
        setF((p) => ({ ...p, effetto: v, scadenza: v ? addMesiISO(v, mesi) : p.scadenza }));
    };

    // Premio LORDO = netto + imposte + SSN + diritti + accessori (auto)
    useEffect(() => {
        const lordo = round2((parseFloat(f.importo_netto) || 0) + (parseFloat(f.imposte) || 0)
            + (parseFloat(f.ssn) || 0) + (parseFloat(f.diritti) || 0) + (parseFloat(f.accessori) || 0));
        setF((p) => (round2(p.importo_lordo) === lordo ? p : { ...p, importo_lordo: lordo }));
        // eslint-disable-next-line
    }, [f.importo_netto, f.imposte, f.ssn, f.diritti, f.accessori]);

    useEffect(() => {
        api.get("/auth/users", { params: { role: "collaboratore" } })
            .then((r) => setCollaboratori((r.data || []).filter((u) => u.attivo !== false)))
            .catch(() => setCollaboratori([]));
    }, []);

    // Eredita automaticamente i collaboratori dalla polizza se il titolo non ne ha di propri
    useEffect(() => {
        const haGiaSuoi = Array.isArray(titolo.provvigioni_operatori) && titolo.provvigioni_operatori.length > 0;
        if (!titolo.polizza_id) return;
        api.get(`/polizze/${titolo.polizza_id}`).then((r) => {
            // Compagnia/ramo della polizza → schema provvigionale corretto per compagnia
            setProvvCtx({
                compagnia_id: r.data?.compagnia_id || titolo.compagnia_id || null,
                ramo: titolo.ramo || r.data?.ramo || null,
            });
            // Frazionamento: calcolo automatico scadenza da effetto
            const fraz = (r.data?.frazionamento || "annuale").toLowerCase();
            setPolFraz(fraz);
            const mesi = MESI_FRAZ[fraz] || 12;
            if (titolo._new) {
                setF((p) => {
                    const eff = p.effetto || r.data?.scadenza || r.data?.prossima_quietanza || r.data?.effetto || "";
                    return { ...p, effetto: eff, scadenza: eff ? addMesiISO(eff, mesi) : p.scadenza };
                });
            }
            // Tipo di pagamento: eredita dal preferito della polizza se il titolo non ne ha uno
            const preferito = r.data?.mezzo_pagamento_preferito || r.data?.ultimo_mezzo_pagamento;
            if (preferito && !titolo.mezzo_pagamento) {
                setF((p) => (p.mezzo_pagamento ? p : { ...p, mezzo_pagamento: preferito }));
            }
            if (haGiaSuoi) return;
            const po = r.data?.provvigioni_operatori || [];
            const ctx = { compagnia_id: r.data?.compagnia_id || titolo.compagnia_id || null, ramo: titolo.ramo || r.data?.ramo || null };
            if (po.length > 0) {
                // Ricalcola la quota di ogni operatore per il premio di QUESTO titolo:
                // la polizza memorizza gli importi dell'annuale, che NON vanno copiati
                // tali e quali su rate o storni (premi negativi → quote negative).
                const base = titolo.provvigioni ?? r.data?.provvigioni ?? 0;
                Promise.all(po.map(async (o) => {
                    const oid = o.operatore_id || o.collaboratore_id || "";
                    const q = oid ? await quotaCollaboratore(oid, base, ctx) : null;
                    return { operatore_id: oid, provvigione: q != null ? q : (o.provvigione ?? 0) };
                })).then((ops) => setOperatori(ops));
            } else if (r.data?.collaboratore_id && !titolo.collaboratore_id) {
                const base = titolo.provvigioni ?? r.data?.provvigioni ?? 0;
                quotaCollaboratore(r.data.collaboratore_id, base, ctx).then((q) => {
                    setOperatori([{ operatore_id: r.data.collaboratore_id, provvigione: (q ?? 0) }]);
                });
            }
        }).catch(() => {});
        // eslint-disable-next-line
    }, [titolo.id]);

    const totOperatori = operatori.reduce((s, o) => s + (parseFloat(o.provvigione) || 0), 0);
    // Quota spettante al collaboratore secondo lo schema PIÙ SPECIFICO per
    // (collaboratore + compagnia + ramo). Risolto lato server per coerenza con la
    // ripartizione salvata (evita di usare il primo schema ignorando la compagnia).
    const quotaCollaboratore = async (collabId, baseTotale, ctx = null) => {
        try {
            const c = ctx || provvCtx;
            const r = await api.get("/provvigioni/quota-collaboratore", {
                params: {
                    collaboratore_id: collabId,
                    provvigione_totale: parseFloat(baseTotale) || 0,
                    compagnia_id: c.compagnia_id || undefined,
                    ramo: c.ramo || undefined,
                    premio_netto: parseFloat(f.importo_netto) || 0,
                    premio_lordo: parseFloat(f.importo_lordo) || 0,
                },
            });
            const q = r.data?.provvigione_collaboratore;
            return (q != null && Math.abs(q) > 0.0001) ? q : null;
        } catch { return null; }
    };
    const addOperatore = () => setOperatori((p) => [...p, { operatore_id: "", provvigione: 0 }]);
    const removeOperatore = (i) => setOperatori((p) => p.filter((_, idx) => idx !== i));
    // Ricalcolo automatico delle quote collaboratori quando cambia il totale provvigioni
    const recalcOperatoriDaTotale = async (total) => {
        if (operatori.length === 0) return;
        const nuovi = await Promise.all(operatori.map(async (o) => {
            if (!o.operatore_id) return o;
            const q = await quotaCollaboratore(o.operatore_id, total);
            return q !== null ? { ...o, provvigione: q } : o;
        }));
        setOperatori(nuovi);
    };
    const setOperatore = (i, k, v) => {
        setOperatori((p) => p.map((o, idx) => idx === i ? { ...o, [k]: v } : o));
        // AUTO-CALCOLO provvigioni dallo schema del collaboratore appena selezionato
        if (k === "operatore_id" && v) {
            quotaCollaboratore(v, f.provvigioni).then((q) => {
                if (q !== null && Math.abs(q) > 0.0001) {
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
                    premio_netto: f.importo_netto || 0,
                    collaboratore_id: operatori[0]?.operatore_id || f.collaboratore_id || undefined,
                    compagnia_id: provvCtx.compagnia_id || undefined,
                    ramo: provvCtx.ramo || undefined,
                },
            });
            if (r.data.provvigione_totale !== 0) {
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

    // Ricalcolo automatico delle quote collaboratori dallo SCHEMA quando cambia il
    // premio NETTO/LORDO (o quando gli operatori vengono ereditati dalla polizza).
    // Evita che resti la quota ANNUALE ereditata (es. 40,96) invece del 4,5% sul
    // netto di QUESTO titolo (es. 500 → 22,50). Non tocca i titoli già incassati.
    useEffect(() => {
        if (incassato) return;
        const netto = parseFloat(f.importo_netto) || 0;
        if (!netto || operatori.length === 0) return;
        let cancel = false;
        (async () => {
            const nuovi = await Promise.all(operatori.map(async (o) => {
                if (!o.operatore_id) return o;
                const q = await quotaCollaboratore(o.operatore_id, f.provvigioni || 0);
                return (q != null && Math.abs(q) > 0.0001) ? { ...o, provvigione: q } : o;
            }));
            if (cancel) return;
            const cambiato = nuovi.some((o, i) => (o.provvigione ?? 0) !== (operatori[i].provvigione ?? 0));
            if (!cambiato) return;
            setOperatori(nuovi);
            // Allinea il totale provvigioni alla somma ripartita (coerenza titolo ↔ ripartizione)
            const somma = round2(nuovi.reduce((s, o) => s + (parseFloat(o.provvigione) || 0), 0));
            setF((p) => (round2(p.provvigioni) === somma ? p : { ...p, provvigioni: somma }));
        })();
        return () => { cancel = true; };
        // eslint-disable-next-line
    }, [f.importo_netto, f.importo_lordo, operatori.length]);

    const save = async () => {
        const isNew = titolo._new || !titolo.id;
        const opsClean = operatori
            .filter((o) => o.operatore_id)
            .map((o) => {
                const c = collaboratori.find((x) => x.id === o.operatore_id);
                return { operatore_id: o.operatore_id, operatore_nome: c ? (c.name || c.email) : (o.operatore_nome || ""), provvigione: parseFloat(o.provvigione) || 0 };
            });
        const provvTot = (f.provvigioni !== "" && f.provvigioni != null)
            ? round2(f.provvigioni)
            : (opsClean.length > 0 ? round2(opsClean.reduce((s, o) => s + o.provvigione, 0)) : 0);
        const payload = {
            tipo: f.tipo, effetto: f.effetto, scadenza: f.scadenza,
            importo_lordo: round2(f.importo_lordo),
            importo_netto: round2(f.importo_netto),
            imposte: round2(f.imposte),
            ssn: round2(f.ssn),
            diritti: round2(f.diritti),
            accessori: round2(f.accessori),
            descrizione: (f.descrizione || "").trim() || null,
            provvigioni: provvTot,
            provvigioni_operatori: opsClean,
            collaboratore_id: opsClean[0]?.operatore_id || f.collaboratore_id || null,
            mezzo_pagamento: f.mezzo_pagamento || null,
            data_incasso: f.data_incasso || null,
            coperto_fino_a: f.coperto_fino_a || null,
            tags: Array.isArray(f.tags) ? f.tags : [],
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
            const d = e.response?.data?.detail;
            const msg = Array.isArray(d) ? d.map((x) => x.msg || JSON.stringify(x)).join("; ") : (typeof d === "string" ? d : (e.message || "Errore nel salvataggio"));
            toast.error(msg);
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
            <DialogContent className="max-w-xl p-4 gap-2 max-h-[96vh] overflow-y-auto [&_input]:h-8 [&_[role=combobox]]:h-8 [&_label]:text-xs" data-testid="titolo-edit-dialog">
                <DialogHeader className="space-y-0">
                    <DialogTitle className="text-base">
                        {titolo._new ? "Nuovo titolo" : "Modifica titolo"}{" "}
                        {titolo.numero_polizza ? (
                            <>
                                – Polizza{" "}
                                {titolo.polizza_id ? (
                                    <button
                                        type="button"
                                        onClick={() => { onClose && onClose(); navigate(`/polizze/${titolo.polizza_id}`); }}
                                        className="text-sky-700 hover:text-sky-900 underline underline-offset-2 font-semibold"
                                        title="Apri la polizza"
                                        data-testid="titolo-polizza-link"
                                    >
                                        {titolo.numero_polizza}
                                    </button>
                                ) : titolo.numero_polizza}
                            </>
                        ) : ""}
                    </DialogTitle>
                    <p className="text-[11px] text-slate-500">
                        Lo stato del titolo si aggiorna automaticamente con incasso / copertura / storno.
                    </p>
                </DialogHeader>
                {!titolo._new && titolo.id && (
                    <div className="flex justify-end -mt-1 mb-1">
                        <AzioniCliente entitaTipo="titolo" entitaId={titolo.id} />
                    </div>
                )}
                <ChiusuraGiornoBanner data={f.data_incasso} />
                <div className="grid grid-cols-2 gap-x-3 gap-y-2">
                    <div>
                        <Label>Tipo (riferimento)</Label>
                        <Select value={f.tipo} onValueChange={(v) => set("tipo", v)}>
                            <SelectTrigger data-testid="titolo-tipo-select"><SelectValue placeholder="Seleziona tipo" /></SelectTrigger>
                            <SelectContent>
                                {tipiTitolo.map(([v, l]) => (
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
                    <div><Label>Effetto</Label><Input type="date" value={f.effetto || ""} onChange={(e) => setEffetto(e.target.value)} data-testid="titolo-effetto" /></div>
                    <div><Label>Scadenza</Label><Input type="date" value={f.scadenza || ""} onChange={(e) => set("scadenza", e.target.value)} data-testid="titolo-scadenza" /><div className="text-[10px] text-slate-400 mt-0.5">Da effetto + frazionamento{polFraz ? ` (${polFraz})` : ""}</div></div>
                    <div><Label>Lordo €</Label><Input type="number" step="0.01" value={f.importo_lordo || 0} readOnly disabled className="bg-slate-100" data-testid="titolo-lordo" /><div className="text-[10px] text-slate-400 mt-0.5">Calcolato: netto+imposte+SSN+diritti+accessori</div></div>
                    <div><Label>Netto €</Label><Input type="number" step="0.01" value={f.importo_netto || 0} onChange={(e) => set("importo_netto", e.target.value)} data-testid="titolo-netto" /></div>
                    <div><Label>Imposte €</Label><Input type="number" step="0.01" value={f.imposte || 0} onChange={(e) => set("imposte", e.target.value)} data-testid="titolo-imposte" /></div>
                    <div><Label>SSN €</Label><Input type="number" step="0.01" value={f.ssn || 0} onChange={(e) => set("ssn", e.target.value)} data-testid="titolo-ssn" /></div>
                    <div><Label>Diritti €</Label><Input type="number" step="0.01" value={f.diritti || 0} onChange={(e) => set("diritti", e.target.value)} data-testid="titolo-diritti" /></div>
                    <div><Label>Accessori €</Label><Input type="number" step="0.01" value={f.accessori || 0} onChange={(e) => set("accessori", e.target.value)} data-testid="titolo-accessori" /></div>
                    <div>
                        <Label>Provvigioni € (totale)</Label>
                        <div className="flex gap-2">
                            <Input type="number" step="0.01" value={f.provvigioni ?? 0}
                                onChange={(e) => set("provvigioni", e.target.value)}
                                onBlur={(e) => recalcOperatoriDaTotale(parseFloat(e.target.value) || 0)}
                                disabled={incassato}
                                data-testid="titolo-provvigioni" />
                            <Button type="button" variant="outline" size="sm" onClick={recalcProvvigione} disabled={incassato} data-testid="titolo-provv-auto">Auto</Button>
                        </div>
                        {operatori.length > 0 && <p className="text-[10px] text-slate-400 mt-0.5">Ripartito fra {operatori.length} collab. · totale {totOperatori.toFixed(2)}€ (modificabile)</p>}
                    </div>
                    <div className="col-span-2">
                        <Label>Descrizione (nota libera)</Label>
                        <textarea
                            className="w-full min-h-[64px] rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                            value={f.descrizione || ""}
                            onChange={(e) => set("descrizione", e.target.value)}
                            placeholder="Note libere sul titolo (facoltativo)"
                            data-testid="titolo-descrizione"
                        />
                    </div>
                    <div className="col-span-2">
                        <Label>Tag titolo</Label>
                        <TagsEditor
                            value={f.tags || []}
                            testid="titolo-tags"
                            placeholder="Aggiungi tag al titolo..."
                            onChange={(tags) => set("tags", tags)}
                        />
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
