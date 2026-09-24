import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api, fmtDate, fmtEur } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import useMezziPagamento from "@/hooks/useMezziPagamento";
import SelectTipoPagamento from "@/components/SelectTipoPagamento";
import { Ban, PauseCircle, PlayCircle, ArrowLeftRight, Loader2, Search, RotateCcw } from "lucide-react";
import { toast } from "sonner";

/**
 * Tab "Azioni" della scheda Polizza:
 *  - Annulla contratto
 *  - Sospendi / Riattiva
 *  - Sostituisci (crea nuova polizza linkata)
 */
export default function AzioniPolizzaTab({ polizza, onChanged, canEdit = true }) {
    const navigate = useNavigate();
    const [compagnie, setCompagnie] = useState([]);
    const [rami, setRami] = useState([]);
    const [prodotti, setProdotti] = useState([]);
    useEffect(() => {
        api.get("/compagnie").then((r) => setCompagnie(r.data || []));
        api.get("/librerie/rami?dedup=1").then((r) => setRami(r.data || []));
    }, []);

    const oggi = new Date().toISOString().slice(0, 10);

    // ====== ANNULLA ======
    const [annulla, setAnnulla] = useState({
        data: polizza.data_annullamento || oggi,
        motivo: polizza.motivo_annullamento || "",
    });
    const [annLoading, setAnnLoading] = useState(false);
    // Chiede se stornare i titoli arretrati ancora aperti della polizza
    const chiediStornoArretrati = async (contesto) => {
        try {
            const r = await api.get(`/polizze/${polizza.id}/titoli-arretrati`);
            const n = r.data?.totale || 0;
            if (!n) return false;
            const imp = (r.data?.importo || 0).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
            return window.confirm(
                `Questa polizza ha ${n} titol${n === 1 ? "o" : "i"} in arretrato per ${imp}.\n\n`
                + `Vuoi stornarli (annullarli) contestualmente ${contesto}?\n\n`
                + "OK = storna i titoli · Annulla = lasciali aperti",
            );
        } catch { return false; }
    };

    const doAnnulla = async () => {
        if (!annulla.motivo.trim()) { toast.error("Motivo obbligatorio"); return; }
        if (!window.confirm("Confermi l'annullamento della polizza?")) return;
        const storna = await chiediStornoArretrati("all'annullamento");
        setAnnLoading(true);
        try {
            const r = await api.post(`/polizze/${polizza.id}/annulla`, {
                data_annullamento: annulla.data, motivo_annullamento: annulla.motivo,
                storna_titoli: storna,
            });
            const ns = r.data?.titoli_stornati || 0;
            toast.success(`Polizza annullata${ns ? ` · ${ns} titoli arretrati stornati` : ""}`);
            onChanged?.();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        finally { setAnnLoading(false); }
    };

    // ====== SOSPENDI ======
    const [sospendi, setSospendi] = useState({
        data: polizza.data_sospensione || oggi,
        riatt: polizza.riattivazione_prevista || "",
    });
    const [sospLoading, setSospLoading] = useState(false);
    const doSospendi = async () => {
        const creaTitolo = window.confirm(
            "Vuoi creare in automatico il titolo di sospensione?\n\n" +
            `Data: ${fmtDate(sospendi.data)} · Importo: 0,00 €\n\n` +
            "OK = sospendi e crea il titolo\nAnnulla = sospendi senza titolo"
        );
        setSospLoading(true);
        try {
            const r = await api.post(`/polizze/${polizza.id}/sospendi`, {
                data_sospensione: sospendi.data, riattivazione_prevista: sospendi.riatt || null,
                crea_titolo: creaTitolo,
            });
            toast.success(creaTitolo && r.data?.titolo_creato
                ? "Polizza sospesa · titolo di sospensione creato"
                : "Polizza sospesa");
            onChanged?.();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        finally { setSospLoading(false); }
    };
    const doRiattiva = async () => {
        if (!window.confirm("Riattivare la polizza?")) return;
        const creaTitolo = window.confirm(
            "Vuoi generare un titolo di ripresa collegato?\n\n" +
            `Data: ${fmtDate(oggi)} · Importo: 0,00 €\n\n` +
            "OK = riattiva e crea il titolo\nAnnulla = riattiva senza titolo"
        );
        try {
            const r = await api.post(`/polizze/${polizza.id}/riattiva`, { crea_titolo: creaTitolo });
            toast.success(creaTitolo && r.data?.titolo_creato
                ? "Polizza riattivata · titolo di ripresa creato"
                : "Polizza riattivata");
            onChanged?.();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    // ====== RIPRENDI (annulla l'annullamento) ======
    const [ripLoading, setRipLoading] = useState(false);
    const doRiprendi = async () => {
        if (!window.confirm("Riprendere il contratto? La polizza tornerà attiva.")) return;
        let ripristina_titoli = false;
        try {
            const r = await api.get(`/polizze/${polizza.id}/titoli-stornati-annullamento`);
            const n = r.data?.totale || 0;
            if (n) {
                const imp = (r.data?.importo || 0).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
                ripristina_titoli = window.confirm(
                    `All'annullamento erano stati stornati ${n} titol${n === 1 ? "o" : "i"} per ${imp}.\n\n`
                    + "Vuoi ripristinarli a 'da incassare'?\n\n"
                    + "OK = ripristina i titoli · Annulla = lasciali stornati",
                );
            }
        } catch { /* nessun titolo stornato o errore: procedi senza ripristino */ }
        setRipLoading(true);
        try {
            const r = await api.post(`/polizze/${polizza.id}/riprendi`, { ripristina_titoli });
            const nr = r.data?.titoli_ripristinati || 0;
            toast.success(`Contratto ripreso${nr ? ` · ${nr} titoli ripristinati` : ""}`);
            onChanged?.();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        finally { setRipLoading(false); }
    };

    // ====== SOSTITUISCI ======
    const [sost, setSost] = useState({
        compagnia_id: polizza.compagnia_id || "",
        ramo: polizza.ramo || "",
        prodotto: polizza.prodotto || "",
        numero_polizza: "",
        effetto: oggi,
        prossima_quietanza: "",
        scadenza: "",
        coassicurazione: false,
        premio_lordo: polizza.premio_lordo || "",
        premio_netto: polizza.premio_netto || "",
        premio_ssn: polizza.premio_ssn || "",
        premio_imposte: polizza.premio_imposte || "",
        provvigioni: polizza.provvigioni || "",
        crea_titolo: true,
        motivo: "",
        targa: polizza.targa || "",
        veicolo_marca: polizza.veicolo_marca || "",
        veicolo_modello: polizza.veicolo_modello || "",
        mezzo_pagamento_preferito: polizza.mezzo_pagamento_preferito || "",
    });
    const { mezzi } = useMezziPagamento();
    const [garanzieSost, setGaranzieSost] = useState(
        (polizza.garanzie || []).map((g) => ({
            garanzia: g.garanzia || g.garanzia_originale || "",
            massimale: g.massimale ?? g.capitale ?? "",
            netto: g.netto ?? "",
        })),
    );
    const [targaLoading, setTargaLoading] = useState(false);

    // Cambio mezzo: recupera i dati del veicolo dalla targa (cache interna → OpenAPI)
    const cercaTarga = async () => {
        const tg = (sost.targa || "").trim().toUpperCase().replace(/\s/g, "");
        if (tg.length < 5) { toast.error("Inserisci una targa valida"); return; }
        setTargaLoading(true);
        try {
            const r = await api.get(`/openapi-it/automotive-by-targa/${encodeURIComponent(tg)}`);
            const v = r.data?.veicolo || {};
            setSost((p) => ({
                ...p,
                targa: tg,
                veicolo_marca: v.marca || p.veicolo_marca,
                veicolo_modello: v.modello || p.veicolo_modello,
                veicolo_alimentazione: v.alimentazione || p.veicolo_alimentazione,
                veicolo_cilindrata: v.cilindrata || p.veicolo_cilindrata,
                veicolo_kw: v.potenza_kw || p.veicolo_kw,
                veicolo_data_immatricolazione: v.data_immatricolazione || p.veicolo_data_immatricolazione,
            }));
            toast.success(`Veicolo trovato: ${v.marca || "?"} ${v.modello || ""}`);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Veicolo non trovato per questa targa");
        } finally { setTargaLoading(false); }
    };

    // Cascata Ramo→Prodotto: ricarica prodotti quando cambia ramo o compagnia
    useEffect(() => {
        if (!sost.ramo) { setProdotti([]); return; }
        const params = { ramo: sost.ramo };
        if (sost.compagnia_id) params.compagnia_id = sost.compagnia_id;
        api.get("/librerie/prodotti", { params }).then((r) => setProdotti(r.data || []));
    }, [sost.ramo, sost.compagnia_id]);

    const [sostLoading, setSostLoading] = useState(false);

    // Premio lordo AUTO = netto + SSN + imposte
    const setPremioSost = (campo, val) => setSost((p) => {
        const next = { ...p, [campo]: val };
        const somma = (parseFloat(next.premio_netto) || 0)
            + (parseFloat(next.premio_ssn) || 0)
            + (parseFloat(next.premio_imposte) || 0);
        next.premio_lordo = somma ? somma.toFixed(2) : "";
        return next;
    });

    const doSostituisci = async () => {
        if (!sost.numero_polizza || !sost.effetto || !sost.scadenza) {
            toast.error("Numero, effetto e scadenza obbligatori"); return;
        }
        if (!window.confirm(`Sostituire polizza ${polizza.numero_polizza} con la nuova?`)) return;
        const stornaArretrati = await chiediStornoArretrati("alla sostituzione");
        setSostLoading(true);
        try {
            const numFields = ["premio_lordo", "premio_netto", "premio_ssn", "premio_imposte", "provvigioni"];
            const payload = { ...sost, storna_titoli: stornaArretrati };
            numFields.forEach((k) => {
                payload[k] = parseFloat(payload[k]) || 0;
            });
            payload.targa = (payload.targa || "").trim().toUpperCase();
            payload.garanzie = garanzieSost
                .filter((g) => (g.garanzia || "").trim())
                .map((g) => ({
                    garanzia: g.garanzia.trim().toUpperCase(),
                    massimale: parseFloat(g.massimale) || 0,
                    netto: parseFloat(g.netto) || 0,
                }));
            const r = await api.post(`/polizze/${polizza.id}/sostituisci`, payload);
            const nStorni = r.data?.titoli_stornati || 0;
            if (r.data?.titolo_id) {
                toast.success(`Polizza sostituita + titolo creato${nStorni ? ` · ${nStorni} titoli arretrati stornati` : ""}`);
            } else {
                toast.success(`Polizza sostituita${nStorni ? ` · ${nStorni} titoli arretrati stornati` : ""}`);
            }
            if (r.data?.nuova_polizza_id) {
                navigate(`/polizze/${r.data.nuova_polizza_id}`);
            } else {
                onChanged?.();
            }
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        finally { setSostLoading(false); }
    };

    // Stato corrente / disabilitazione
    const isAttiva = polizza.stato === "attiva";
    const isSospesa = polizza.stato === "sospesa";
    const isLocked = ["annullata", "sostituita"].includes(polizza.stato);

    return (
        <div className="mt-4 space-y-4" data-testid="azioni-polizza-tab">
            {/* Status banner */}
            {isLocked && (
                <Card className="border-rose-200 bg-rose-50 p-3 text-sm">
                    <div className="font-medium text-rose-800">
                        Polizza {polizza.stato} — le azioni sono disabilitate
                    </div>
                    {polizza.motivo_annullamento && <div className="text-xs text-rose-700 mt-1">Motivo: {polizza.motivo_annullamento}</div>}
                    {polizza.sostituita_da_polizza_id && (
                        <div className="text-xs mt-1">
                            <Link to={`/polizze/${polizza.sostituita_da_polizza_id}`} className="text-sky-700 hover:underline">
                                → Apri polizza sostitutiva
                            </Link>
                        </div>
                    )}
                    {polizza.stato === "annullata" && (
                        <Button
                            onClick={doRiprendi}
                            disabled={!canEdit || ripLoading}
                            className="mt-3 bg-emerald-600 hover:bg-emerald-700"
                            size="sm"
                            data-testid="riprendi-confirm"
                        >
                            {ripLoading
                                ? <Loader2 size={14} className="animate-spin mr-1" />
                                : <RotateCcw size={14} className="mr-1" />}
                            Riprendi Contratto
                        </Button>
                    )}
                </Card>
            )}
            {polizza.sostituisce_polizza && (
                <Card className="border-emerald-200 bg-emerald-50 p-3 text-sm">
                    <Link to={`/polizze/${polizza.sostituisce_polizza}`} className="text-sky-700 hover:underline">
                        ← Polizza precedente (sostituita)
                    </Link>
                </Card>
            )}

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* ANNULLA */}
                <Card className="border-rose-200 p-4" data-testid="azione-annulla">
                    <div className="text-center text-sky-700 font-semibold mb-3 uppercase tracking-wider text-sm">Annulla</div>
                    <div className="space-y-3">
                        <div>
                            <Label>Data annullamento</Label>
                            <Input type="date" value={annulla.data}
                                onChange={(e) => setAnnulla((p) => ({ ...p, data: e.target.value }))}
                                disabled={isLocked} data-testid="ann-data" />
                        </div>
                        <div>
                            <Label>Motivo annullamento</Label>
                            <Select value={annulla.motivo}
                                onValueChange={(v) => setAnnulla((p) => ({ ...p, motivo: v }))}
                                disabled={isLocked}>
                                <SelectTrigger data-testid="ann-motivo"><SelectValue placeholder="Seleziona motivo…" /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="Disdetta">Disdetta</SelectItem>
                                    <SelectItem value="Mancato pagamento">Mancato pagamento</SelectItem>
                                    <SelectItem value="Sinistro">Sinistro</SelectItem>
                                    <SelectItem value="Vendita veicolo">Vendita veicolo</SelectItem>
                                    <SelectItem value="Demolizione">Demolizione</SelectItem>
                                    <SelectItem value="Furto">Furto</SelectItem>
                                    <SelectItem value="Esportazione">Esportazione</SelectItem>
                                    <SelectItem value="Sostituzione">Sostituzione</SelectItem>
                                    <SelectItem value="Passaggio ad altra compagnia">Passaggio ad altra compagnia</SelectItem>
                                    <SelectItem value="Recesso">Recesso</SelectItem>
                                    <SelectItem value="Altro">Altro</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <Button
                            onClick={doAnnulla}
                            disabled={!canEdit || isLocked || annLoading}
                            className="w-full bg-rose-600 hover:bg-rose-700"
                            data-testid="ann-confirm"
                        >
                            {annLoading
                                ? <Loader2 size={14} className="animate-spin mr-1" />
                                : <Ban size={14} className="mr-1" />}
                            Annulla Contratto
                        </Button>
                    </div>
                </Card>

                {/* SOSPENDI / RIATTIVA */}
                <Card className="border-amber-200 p-4" data-testid="azione-sospendi">
                    <div className="text-center text-sky-700 font-semibold mb-3 uppercase tracking-wider text-sm">
                        {isSospesa ? "Riattiva" : "Sospendi"}
                    </div>
                    {isSospesa ? (
                        <div className="space-y-3">
                            <div className="text-xs text-slate-600">
                                Sospesa dal <strong>{fmtDate(polizza.data_sospensione)}</strong>
                                {polizza.riattivazione_prevista && (
                                    <> · riatt. prevista <strong>{fmtDate(polizza.riattivazione_prevista)}</strong></>
                                )}
                            </div>
                            <Button onClick={doRiattiva} disabled={!canEdit}
                                className="w-full bg-emerald-600 hover:bg-emerald-700" data-testid="riatt-confirm">
                                <PlayCircle size={14} className="mr-1" />Riattiva
                            </Button>
                        </div>
                    ) : (
                        <div className="space-y-3">
                            <div>
                                <Label>Data sospensione</Label>
                                <Input type="date" value={sospendi.data}
                                    onChange={(e) => setSospendi((p) => ({ ...p, data: e.target.value }))}
                                    disabled={isLocked} data-testid="sosp-data" />
                            </div>
                            <div>
                                <Label>Riattivazione prevista</Label>
                                <Input type="date" value={sospendi.riatt}
                                    onChange={(e) => setSospendi((p) => ({ ...p, riatt: e.target.value }))}
                                    disabled={isLocked} data-testid="sosp-riatt" />
                                {(() => {
                                    if (!sospendi.data || !sospendi.riatt) {
                                        return <div className="text-[11px] text-slate-400 mt-1">Massimo di legge: 10 mesi di sospensione per annualità.</div>;
                                    }
                                    const d1 = new Date(sospendi.data), d2 = new Date(sospendi.riatt);
                                    if (isNaN(d1) || isNaN(d2) || d2 <= d1) {
                                        return <div className="text-[11px] text-rose-600 mt-1">La riattivazione deve essere successiva alla sospensione.</div>;
                                    }
                                    const mesi = Math.round(((d2 - d1) / (1000 * 60 * 60 * 24 * 30.4375)) * 10) / 10;
                                    const residuo = Math.round((10 - mesi) * 10) / 10;
                                    const over = mesi > 10;
                                    return (
                                        <div className={`text-[11px] mt-1 ${over ? "text-rose-600 font-medium" : "text-slate-500"}`} data-testid="sosp-durata-info">
                                            Durata sospensione: <strong>{mesi.toString().replace(".", ",")} mesi</strong>
                                            {over
                                                ? <> · supera il massimo di legge (10 mesi per annualità)</>
                                                : <> · residuo su questa annualità: <strong>{residuo.toString().replace(".", ",")} mesi</strong></>}
                                        </div>
                                    );
                                })()}
                            </div>
                            <Button onClick={doSospendi}
                                disabled={!canEdit || isLocked || sospLoading}
                                className="w-full bg-amber-600 hover:bg-amber-700"
                                data-testid="sosp-confirm">
                                {sospLoading
                                    ? <Loader2 size={14} className="animate-spin mr-1" />
                                    : <PauseCircle size={14} className="mr-1" />}
                                Metti in Sospensione
                            </Button>
                        </div>
                    )}
                </Card>

                {/* SOSTITUISCI */}
                <Card className="border-violet-200 p-4" data-testid="azione-sostituisci">
                    <div className="text-center text-sky-700 font-semibold mb-3 uppercase tracking-wider text-sm">Sostituisci</div>
                    <div className="space-y-2">
                        <div>
                            <Label>Compagnia</Label>
                            <Select value={sost.compagnia_id} onValueChange={(v) => setSost((p) => ({ ...p, compagnia_id: v }))} disabled={isLocked}>
                                <SelectTrigger data-testid="sost-compagnia"><SelectValue placeholder="Seleziona…" /></SelectTrigger>
                                <SelectContent>
                                    {compagnie.map((c) => <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}</SelectItem>)}
                                </SelectContent>
                            </Select>
                        </div>
                        <div>
                            <Label>Rischio (Ramo)</Label>
                            <Select value={sost.ramo} onValueChange={(v) => { setSost((p) => ({ ...p, ramo: v, prodotto: "" })); }} disabled={isLocked}>
                                <SelectTrigger data-testid="sost-ramo"><SelectValue placeholder="Seleziona…" /></SelectTrigger>
                                <SelectContent>
                                    {rami.map((r) => <SelectItem key={r.id || r.nome} value={r.nome}>{r.nome}</SelectItem>)}
                                </SelectContent>
                            </Select>
                        </div>
                        <div>
                            <Label>Prodotto</Label>
                            <Select value={sost.prodotto || ""} onValueChange={(v) => setSost((p) => ({ ...p, prodotto: v }))} disabled={isLocked || !sost.ramo}>
                                <SelectTrigger data-testid="sost-prodotto">
                                    <SelectValue placeholder={sost.ramo ? (prodotti.length ? "Seleziona prodotto" : "Nessun prodotto") : "Scegli prima ramo"} />
                                </SelectTrigger>
                                <SelectContent>
                                    {prodotti.map((p) => <SelectItem key={p.id || p.nome} value={p.nome}>{p.nome}</SelectItem>)}
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                            <div>
                                <Label>N° Contratto</Label>
                                <Input value={sost.numero_polizza}
                                    onChange={(e) => setSost((p) => ({ ...p, numero_polizza: e.target.value }))}
                                    disabled={isLocked} data-testid="sost-numero" />
                            </div>
                            <div>
                                <Label>Data effetto</Label>
                                <Input type="date" value={sost.effetto}
                                    onChange={(e) => setSost((p) => ({ ...p, effetto: e.target.value }))}
                                    disabled={isLocked} data-testid="sost-effetto" />
                            </div>
                            <div>
                                <Label>Prossima quietanza</Label>
                                <Input type="date" value={sost.prossima_quietanza}
                                    onChange={(e) => setSost((p) => ({ ...p, prossima_quietanza: e.target.value }))}
                                    disabled={isLocked} />
                            </div>
                            <div>
                                <Label>Data scadenza</Label>
                                <Input type="date" value={sost.scadenza}
                                    onChange={(e) => setSost((p) => ({ ...p, scadenza: e.target.value }))}
                                    disabled={isLocked} data-testid="sost-scadenza" />
                            </div>
                            <div className="col-span-2">
                                <Label>Tipo pagamento</Label>
                                <SelectTipoPagamento
                                    value={sost.mezzo_pagamento_preferito || ""}
                                    onChange={(v) => setSost((p) => ({ ...p, mezzo_pagamento_preferito: v }))}
                                    placeholder={polizza.mezzo_pagamento_preferito
                                        ? `Ereditato: ${polizza.mezzo_pagamento_preferito}`
                                        : (polizza.ultimo_mezzo_pagamento
                                            ? `Auto (ultimo: ${polizza.ultimo_mezzo_pagamento})`
                                            : "Auto (segue il primo incasso)")}
                                    testid="sost-mezzo-pagamento"
                                />
                                <div className="text-[10px] text-slate-400 mt-0.5">
                                    Il metodo NON cambia con la sostituzione: viene ereditato. Modificalo qui solo se il cliente lo richiede.
                                </div>
                            </div>
                        </div>
                        {(!!polizza.targa || /auto|rca|motocicl|autocarr/i.test(`${sost.ramo || ""} ${polizza.ramo || ""}`)) && (
                            <div className="border-t border-slate-100 pt-2 mt-2">
                                <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-1.5">
                                    Veicolo nuovo contratto <span className="normal-case font-normal text-slate-400">(modificalo se hai cambiato mezzo)</span>
                                </div>
                                <div className="grid grid-cols-2 gap-2">
                                    <div>
                                        <Label>Targa</Label>
                                        <div className="flex gap-1">
                                            <Input value={sost.targa}
                                                onChange={(e) => setSost((p) => ({ ...p, targa: e.target.value.toUpperCase() }))}
                                                placeholder="es. AB123CD"
                                                disabled={isLocked} data-testid="sost-targa" />
                                            <Button type="button" size="sm" variant="outline" className="h-9 px-2 shrink-0"
                                                onClick={cercaTarga} disabled={isLocked || targaLoading}
                                                title="Recupera marca/modello dalla targa"
                                                data-testid="sost-targa-lookup">
                                                {targaLoading ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />}
                                            </Button>
                                        </div>
                                        {polizza.targa && sost.targa !== polizza.targa && (
                                            <div className="text-[10px] text-amber-700 mt-0.5">Targa precedente: {polizza.targa}</div>
                                        )}
                                    </div>
                                    <div>
                                        <Label>Marca</Label>
                                        <Input value={sost.veicolo_marca}
                                            onChange={(e) => setSost((p) => ({ ...p, veicolo_marca: e.target.value.toUpperCase() }))}
                                            placeholder="es. FIAT"
                                            disabled={isLocked} data-testid="sost-veicolo-marca" />
                                    </div>
                                    <div className="col-span-2">
                                        <Label>Modello</Label>
                                        <Input value={sost.veicolo_modello}
                                            onChange={(e) => setSost((p) => ({ ...p, veicolo_modello: e.target.value.toUpperCase() }))}
                                            placeholder="es. PANDA 1.2"
                                            disabled={isLocked} data-testid="sost-veicolo-modello" />
                                    </div>
                                </div>
                            </div>
                        )}
                        {/* GARANZIE nuova polizza */}
                        <div className="border-t border-slate-100 pt-2 mt-2">
                            <div className="flex items-center justify-between mb-1.5">
                                <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">Garanzie nuova polizza</div>
                                <button type="button"
                                    onClick={() => setGaranzieSost((g) => [...g, { garanzia: "", massimale: "", netto: "" }])}
                                    className="text-[11px] text-sky-700 hover:underline disabled:opacity-40"
                                    disabled={isLocked} data-testid="sost-add-garanzia">+ Aggiungi garanzia</button>
                            </div>
                            {garanzieSost.length === 0 ? (
                                <div className="text-[11px] text-slate-400 italic">Nessuna garanzia — usa &ldquo;+ Aggiungi garanzia&rdquo;.</div>
                            ) : garanzieSost.map((g, i) => (
                                <div key={i} className="grid grid-cols-[1fr_92px_82px_22px] gap-1.5 mb-1 items-center">
                                    <Input className="h-8 text-xs" placeholder="Garanzia (es. RCA, Furto)"
                                        value={g.garanzia}
                                        onChange={(e) => setGaranzieSost((gs) => gs.map((x, j) => (j === i ? { ...x, garanzia: e.target.value } : x)))}
                                        disabled={isLocked} data-testid={`sost-gar-nome-${i}`} />
                                    <Input className="h-8 text-xs" type="number" placeholder="Massimale"
                                        value={g.massimale}
                                        onChange={(e) => setGaranzieSost((gs) => gs.map((x, j) => (j === i ? { ...x, massimale: e.target.value } : x)))}
                                        disabled={isLocked} data-testid={`sost-gar-max-${i}`} />
                                    <Input className="h-8 text-xs" type="number" placeholder="Netto €"
                                        value={g.netto}
                                        onChange={(e) => setGaranzieSost((gs) => gs.map((x, j) => (j === i ? { ...x, netto: e.target.value } : x)))}
                                        disabled={isLocked} data-testid={`sost-gar-netto-${i}`} />
                                    <button type="button" className="text-rose-500 hover:text-rose-700 text-sm"
                                        onClick={() => setGaranzieSost((gs) => gs.filter((_, j) => j !== i))}
                                        disabled={isLocked} data-testid={`sost-gar-del-${i}`}>✕</button>
                                </div>
                            ))}
                        </div>
                        <div className="border-t border-slate-100 pt-2 mt-2">
                            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-1">Premi & Provvigioni</div>
                            <div className="grid grid-cols-2 gap-2">
                                <div>
                                    <Label>Premio netto €</Label>
                                    <Input type="number" step="0.01" value={sost.premio_netto}
                                        onChange={(e) => setPremioSost("premio_netto", e.target.value)}
                                        disabled={isLocked} data-testid="sost-pn" />
                                </div>
                                <div>
                                    <Label>Premio lordo € <span className="text-[9px] text-slate-400 normal-case">(auto: netto+SSN+imposte)</span></Label>
                                    <Input type="number" step="0.01" value={sost.premio_lordo}
                                        readOnly className="bg-slate-50 text-slate-700 cursor-default"
                                        disabled={isLocked} data-testid="sost-pl" />
                                </div>
                                <div>
                                    <Label>SSN €</Label>
                                    <Input type="number" step="0.01" value={sost.premio_ssn}
                                        onChange={(e) => setPremioSost("premio_ssn", e.target.value)}
                                        disabled={isLocked} data-testid="sost-ssn" />
                                </div>
                                <div>
                                    <Label>Imposte €</Label>
                                    <Input type="number" step="0.01" value={sost.premio_imposte}
                                        onChange={(e) => setPremioSost("premio_imposte", e.target.value)}
                                        disabled={isLocked} data-testid="sost-imposte" />
                                </div>
                                <div className="col-span-2">
                                    <Label>Provvigioni €</Label>
                                    <Input type="number" step="0.01" value={sost.provvigioni}
                                        onChange={(e) => setSost((p) => ({ ...p, provvigioni: e.target.value }))}
                                        disabled={isLocked} />
                                </div>
                            </div>
                        </div>
                        <div className="flex items-center gap-2 pt-2 border-t border-slate-100 text-xs text-slate-600">
                            <span className="inline-flex items-center gap-1 text-violet-700 font-medium">
                                <ArrowLeftRight size={12} /> Tipo titolo: sostituzione
                            </span>
                            <span className="text-slate-400">— il titolo iniziale (con n° polizza) verrà creato in automatico; gli eventuali titoli arretrati della vecchia polizza saranno stornati</span>
                        </div>
                        <div className="flex items-end gap-2 pt-1">
                            <Checkbox
                                id="coass"
                                checked={sost.coassicurazione}
                                onCheckedChange={(c) => setSost((p) => ({ ...p, coassicurazione: !!c }))}
                                disabled={isLocked}
                            />
                            <Label htmlFor="coass" className="text-sm cursor-pointer">Coassicurazione</Label>
                        </div>
                        <div>
                            <Label>Motivo sostituzione (opz.)</Label>
                            <Input value={sost.motivo}
                                onChange={(e) => setSost((p) => ({ ...p, motivo: e.target.value }))}
                                placeholder="es. Cambio compagnia, scadenza naturale"
                                disabled={isLocked} />
                        </div>
                        <Button
                            onClick={doSostituisci}
                            disabled={!canEdit || isLocked || sostLoading}
                            className="w-full bg-violet-600 hover:bg-violet-700"
                            data-testid="sost-confirm"
                        >
                            {sostLoading
                                ? <Loader2 size={14} className="animate-spin mr-1" />
                                : <ArrowLeftRight size={14} className="mr-1" />}
                            Sostituisci Contratto
                        </Button>
                    </div>
                </Card>
            </div>

            <div className="text-[10px] text-slate-400 text-center">
                Polizza n. {polizza.numero_polizza} · Premio attuale {fmtEur(polizza.premio_lordo)}
            </div>
        </div>
    );
}
