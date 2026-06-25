import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api, fmtDate, fmtEur } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Ban, PauseCircle, PlayCircle, ArrowLeftRight, Loader2 } from "lucide-react";
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
        api.get("/librerie/rami").then((r) => setRami(r.data || []));
    }, []);

    const oggi = new Date().toISOString().slice(0, 10);

    // ====== ANNULLA ======
    const [annulla, setAnnulla] = useState({
        data: polizza.data_annullamento || oggi,
        motivo: polizza.motivo_annullamento || "",
    });
    const [annLoading, setAnnLoading] = useState(false);
    const doAnnulla = async () => {
        if (!annulla.motivo.trim()) { toast.error("Motivo obbligatorio"); return; }
        if (!window.confirm("Confermi l'annullamento della polizza?")) return;
        setAnnLoading(true);
        try {
            await api.post(`/polizze/${polizza.id}/annulla`, {
                data_annullamento: annulla.data, motivo_annullamento: annulla.motivo,
            });
            toast.success("Polizza annullata");
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
        setSospLoading(true);
        try {
            await api.post(`/polizze/${polizza.id}/sospendi`, {
                data_sospensione: sospendi.data, riattivazione_prevista: sospendi.riatt || null,
            });
            toast.success("Polizza sospesa");
            onChanged?.();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        finally { setSospLoading(false); }
    };
    const doRiattiva = async () => {
        if (!window.confirm("Riattivare la polizza?")) return;
        try {
            await api.post(`/polizze/${polizza.id}/riattiva`);
            toast.success("Polizza riattivata");
            onChanged?.();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
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
    });

    // Cascata Ramo→Prodotto: ricarica prodotti quando cambia ramo o compagnia
    useEffect(() => {
        if (!sost.ramo) { setProdotti([]); return; }
        const params = { ramo: sost.ramo };
        if (sost.compagnia_id) params.compagnia_id = sost.compagnia_id;
        api.get("/librerie/prodotti", { params }).then((r) => setProdotti(r.data || []));
    }, [sost.ramo, sost.compagnia_id]);

    const [sostLoading, setSostLoading] = useState(false);
    const doSostituisci = async () => {
        if (!sost.numero_polizza || !sost.effetto || !sost.scadenza) {
            toast.error("Numero, effetto e scadenza obbligatori"); return;
        }
        if (!window.confirm(`Sostituire polizza ${polizza.numero_polizza} con la nuova?`)) return;
        setSostLoading(true);
        try {
            const numFields = ["premio_lordo", "premio_netto", "premio_ssn", "premio_imposte", "provvigioni"];
            const payload = { ...sost };
            numFields.forEach((k) => {
                payload[k] = parseFloat(payload[k]) || 0;
            });
            const r = await api.post(`/polizze/${polizza.id}/sostituisci`, payload);
            if (r.data?.titolo_id) {
                toast.success("Polizza sostituita + titolo creato");
            } else {
                toast.success("Polizza sostituita");
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
                            <Input value={annulla.motivo}
                                onChange={(e) => setAnnulla((p) => ({ ...p, motivo: e.target.value }))}
                                placeholder="es. Disdetta, Sinistro, Vendita veicolo"
                                disabled={isLocked} data-testid="ann-motivo" />
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
                        </div>
                        <div className="border-t border-slate-100 pt-2 mt-2">
                            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-1">Premi & Provvigioni</div>
                            <div className="grid grid-cols-2 gap-2">
                                <div>
                                    <Label>Premio netto €</Label>
                                    <Input type="number" step="0.01" value={sost.premio_netto}
                                        onChange={(e) => setSost((p) => ({ ...p, premio_netto: e.target.value }))}
                                        disabled={isLocked} data-testid="sost-pn" />
                                </div>
                                <div>
                                    <Label>Premio lordo €</Label>
                                    <Input type="number" step="0.01" value={sost.premio_lordo}
                                        onChange={(e) => setSost((p) => ({ ...p, premio_lordo: e.target.value }))}
                                        disabled={isLocked} data-testid="sost-pl" />
                                </div>
                                <div>
                                    <Label>SSN €</Label>
                                    <Input type="number" step="0.01" value={sost.premio_ssn}
                                        onChange={(e) => setSost((p) => ({ ...p, premio_ssn: e.target.value }))}
                                        disabled={isLocked} />
                                </div>
                                <div>
                                    <Label>Imposte €</Label>
                                    <Input type="number" step="0.01" value={sost.premio_imposte}
                                        onChange={(e) => setSost((p) => ({ ...p, premio_imposte: e.target.value }))}
                                        disabled={isLocked} />
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
                            <span className="text-slate-400">— il titolo iniziale verrà creato in automatico con i dati inseriti</span>
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
