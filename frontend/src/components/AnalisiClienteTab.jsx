/**
 * Tab "Analisi Cliente" completa - 7 sezioni ispirate al modello SatorCRM.
 * Sostituisce l'ex tab "Pensione INPS".
 */
import { useEffect, useState, useRef } from "react";
import { api, fmtEur } from "@/lib/api";
import { openPdf } from "@/lib/pdf";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
    Wallet, Home, Target, Calculator, Briefcase, Shield, Scale,
    FileText, Save, Plus, Trash2, TrendingDown, TrendingUp, Upload,
} from "lucide-react";
import { toast } from "sonner";
import { Loading } from "@/components/Shared";

export default function AnalisiClienteTab({ anagrafica_id, ana, canEdit, onReload }) {
    const [ac, setAc] = useState(null);
    const [dirty, setDirty] = useState(false);
    const [saving, setSaving] = useState(false);

    const load = async () => {
        const r = await api.get(`/anagrafiche/${anagrafica_id}/analisi`);
        setAc(r.data);
        setDirty(false);
    };
    useEffect(() => { load();  }, [anagrafica_id]);

    const set = (k, v) => {
        setAc((p) => ({ ...p, [k]: v }));
        setDirty(true);
    };

    const save = async () => {
        setSaving(true);
        try {
            await api.put(`/anagrafiche/${anagrafica_id}/analisi`, ac);
            toast.success("Analisi salvata");
            setDirty(false);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        } finally { setSaving(false); }
    };

    const stampaDiagnosi = () => {
        const popup = window.open("", "_blank");
        openPdf(`/anagrafiche/${anagrafica_id}/analisi/pdf-diagnosi-reddito`, {}, popup);
    };
    const stampaAzzob = () => {
        const popup = window.open("", "_blank");
        openPdf(`/anagrafiche/${anagrafica_id}/analisi/pdf-progetto-azzob`, {}, popup);
    };

    if (!ac) return <Loading />;

    return (
        <div className="space-y-4 mt-4" data-testid="analisi-cliente-tab">
            {/* Toolbar */}
            <div className="bg-sky-50 border border-sky-200 rounded-md p-3 flex items-center justify-between flex-wrap gap-2">
                <div className="text-xs text-sky-900">
                    <strong>Analisi Cliente completa</strong> — situazione finanziaria, patrimonio, obiettivi,
                    pensioni e successione. Premi <em>Salva</em> per persistere le modifiche.
                </div>
                <div className="flex gap-2 flex-wrap">
                    {canEdit && (
                        <Button
                            size="sm" onClick={save} disabled={!dirty || saving}
                            className="bg-emerald-600 hover:bg-emerald-700"
                            data-testid="analisi-save-btn"
                        >
                            <Save size={13} className="mr-1" />
                            {saving ? "Salvataggio..." : (dirty ? "Salva modifiche" : "Salvato")}
                        </Button>
                    )}
                    <Button size="sm" variant="outline" onClick={stampaDiagnosi} data-testid="analisi-pdf-reddito-btn">
                        <FileText size={13} className="mr-1" /> PDF Diagnosi Reddito
                    </Button>
                    <Button size="sm" variant="outline" onClick={stampaAzzob} data-testid="analisi-pdf-azzob-btn">
                        <FileText size={13} className="mr-1" /> PDF Progetto Senza Sorprese
                    </Button>
                </div>
            </div>

            <Tabs defaultValue="finanza" className="w-full">
                <TabsList className="bg-slate-100 flex-wrap h-auto">
                    <TabsTrigger value="finanza" data-testid="sub-tab-finanza">
                        <Wallet size={13} className="mr-1" /> Finanziaria
                    </TabsTrigger>
                    <TabsTrigger value="patrimonio" data-testid="sub-tab-patrimonio">
                        <Home size={13} className="mr-1" /> Patrimonio
                    </TabsTrigger>
                    <TabsTrigger value="contesto" data-testid="sub-tab-contesto">
                        <Target size={13} className="mr-1" /> Contesto & Obiettivi
                    </TabsTrigger>
                    <TabsTrigger value="redditi" data-testid="sub-tab-redditi">
                        <Calculator size={13} className="mr-1" /> Approfondimento Redditi
                    </TabsTrigger>
                    <TabsTrigger value="pensione" data-testid="sub-tab-pensione">
                        <Briefcase size={13} className="mr-1" /> Pensione INPS
                    </TabsTrigger>
                    <TabsTrigger value="scoperture" data-testid="sub-tab-scoperture">
                        <Shield size={13} className="mr-1" /> Riepilogo Pensionistico
                    </TabsTrigger>
                    <TabsTrigger value="successione" data-testid="sub-tab-successione">
                        <Scale size={13} className="mr-1" /> Successione
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="finanza">
                    <SituazioneFinanziaria ac={ac} set={set} canEdit={canEdit} />
                </TabsContent>
                <TabsContent value="patrimonio">
                    <PatrimonioTab ac={ac} set={set} canEdit={canEdit} anagrafica_id={anagrafica_id} />
                </TabsContent>
                <TabsContent value="contesto">
                    <ContestoObiettivi ac={ac} set={set} canEdit={canEdit} />
                </TabsContent>
                <TabsContent value="redditi">
                    <ApprofondimentoRedditi anagrafica_id={anagrafica_id} dirty={dirty} />
                </TabsContent>
                <TabsContent value="pensione">
                    <PensioneInpsTab ac={ac} set={set} canEdit={canEdit} anagrafica_id={anagrafica_id} ana={ana} onReload={onReload} dirty={dirty} />
                </TabsContent>
                <TabsContent value="scoperture">
                    <ScoperturePensione anagrafica_id={anagrafica_id} dirty={dirty} />
                </TabsContent>
                <TabsContent value="successione">
                    <SuccessioneTab anagrafica_id={anagrafica_id} dirty={dirty} />
                </TabsContent>
            </Tabs>
        </div>
    );
}

// ============== SEZIONE 1: SITUAZIONE FINANZIARIA ==============
function SituazioneFinanziaria({ ac, set, canEdit }) {
    return (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
            <Card className="p-5 border-slate-200">
                <h3 className="font-semibold text-slate-900 mb-3 flex items-center gap-2">
                    <Wallet size={16} className="text-emerald-600" /> Entrate annuali
                </h3>
                <div className="space-y-3">
                    <MoneyField label="Reddito lordo annuo" value={ac.reddito_lordo_annuo} onChange={(v) => set("reddito_lordo_annuo", v)} canEdit={canEdit} testid="reddito-lordo" />
                    <MoneyField label="Dividendi da partecipazioni in società" value={ac.dividendi_partecipazioni} onChange={(v) => set("dividendi_partecipazioni", v)} canEdit={canEdit} />
                    <MoneyField label="Altri redditi annuali" value={ac.altri_redditi_annuali} onChange={(v) => set("altri_redditi_annuali", v)} canEdit={canEdit} />
                    <MoneyField label="Reddito da affitti annuali" value={ac.reddito_da_affitti} onChange={(v) => set("reddito_da_affitti", v)} canEdit={canEdit} />
                    <ToggleField label="Reddito estero" value={ac.reddito_estero} onChange={(v) => set("reddito_estero", v)} canEdit={canEdit} />
                    <ToggleField label="Regime forfettario" value={ac.regime_forfettario} onChange={(v) => set("regime_forfettario", v)} canEdit={canEdit} />
                </div>
            </Card>

            <Card className="p-5 border-slate-200">
                <h3 className="font-semibold text-slate-900 mb-3 flex items-center gap-2">
                    <TrendingUp size={16} className="text-sky-600" /> Patrimonio liquido & oneri
                </h3>
                <div className="space-y-3">
                    <MoneyField label="TFR maturato in azienda (solo se privato)" value={ac.tfr_maturato} onChange={(v) => set("tfr_maturato", v)} canEdit={canEdit} />
                    <MoneyField label="Liquidità (conto corrente / investimenti)" value={ac.liquidita} onChange={(v) => set("liquidita", v)} canEdit={canEdit} />
                    <MoneyField label="Debiti (mutui / finanziamenti / residui)" value={ac.debiti} onChange={(v) => set("debiti", v)} canEdit={canEdit} testid="debiti" />
                    <MoneyField label="Oneri deducibili" value={ac.oneri_deducibili} onChange={(v) => set("oneri_deducibili", v)} canEdit={canEdit} />
                    <MoneyField label="Oneri fondo pensione" value={ac.oneri_fondo_pensione} onChange={(v) => set("oneri_fondo_pensione", v)} canEdit={canEdit} />
                    <MoneyField label="Altre detrazioni" value={ac.altre_detrazioni} onChange={(v) => set("altre_detrazioni", v)} canEdit={canEdit} />
                </div>
            </Card>

            <Card className="p-5 border-rose-200 bg-rose-50/30 md:col-span-2">
                <h3 className="font-semibold text-slate-900 mb-3 flex items-center gap-2">
                    <TrendingDown size={16} className="text-rose-600" /> Appetito al rischio (danno devastante)
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <MoneyField
                        label="Per il cliente sarebbe DEVASTANTE se le entrate diminuissero più di € / mese"
                        value={ac.danno_devastante_entrate_mensili}
                        onChange={(v) => set("danno_devastante_entrate_mensili", v)}
                        canEdit={canEdit}
                    />
                    <MoneyField
                        label="Per il cliente sarebbe DEVASTANTE se il patrimonio diminuisse più di €"
                        value={ac.danno_devastante_patrimonio}
                        onChange={(v) => set("danno_devastante_patrimonio", v)}
                        canEdit={canEdit}
                    />
                </div>
            </Card>

            <Card className="p-5 border-emerald-200 bg-emerald-50/30 md:col-span-2">
                <h3 className="font-semibold text-slate-900 mb-3 flex items-center gap-2">
                    <TrendingUp size={16} className="text-emerald-600" /> Risparmio
                </h3>
                <MoneyField
                    label="Capacità di risparmio annuale"
                    value={ac.capacita_risparmio_annuale}
                    onChange={(v) => set("capacita_risparmio_annuale", v)}
                    canEdit={canEdit}
                />
            </Card>
        </div>
    );
}

// ============== SEZIONE 2: PATRIMONIO ==============
function PatrimonioTab({ ac, set, canEdit, anagrafica_id }) {
    const [riepilogo, setRiepilogo] = useState(null);

    useEffect(() => {
        api.get(`/anagrafiche/${anagrafica_id}/analisi/patrimonio`).then((r) => setRiepilogo(r.data));
    }, [anagrafica_id, ac]);

    const addItem = (k, def) => set(k, [...(ac[k] || []), def]);
    const removeItem = (k, idx) => set(k, (ac[k] || []).filter((_, i) => i !== idx));
    const updateItem = (k, idx, patch) => set(k, (ac[k] || []).map((it, i) => i === idx ? { ...it, ...patch } : it));

    return (
        <div className="space-y-4 mt-4">
            {/* Riepilogo */}
            {riepilogo && (
                <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2">
                    <Kpi label="Liquido" value={fmtEur(riepilogo.patrimonio_liquido)} color="emerald" />
                    <Kpi label="Immobili" value={fmtEur(riepilogo.patrimonio_immobiliare)} color="sky" />
                    <Kpi label="Veicoli" value={fmtEur(riepilogo.patrimonio_veicoli)} color="indigo" />
                    <Kpi label="Beni" value={fmtEur(riepilogo.altri_beni)} color="slate" />
                    <Kpi label="Aziende" value={fmtEur(riepilogo.patrimonio_aziendale)} color="amber" />
                    <Kpi label="Debiti" value={fmtEur(riepilogo.debiti)} color="rose" />
                    <Kpi label="Patrimonio Netto" value={fmtEur(riepilogo.patrimonio_netto)} color="emerald" big />
                </div>
            )}

            {/* Immobili */}
            <Card className="p-5 border-slate-200">
                <SectionHeader title="Immobili" icon={<Home size={16} />} count={ac.immobili?.length || 0}
                    onAdd={canEdit ? () => addItem("immobili", { tipo: "abitativo", titolo: "proprieta", percentuale_proprieta: 100, valore_commerciale: 0, rendita_catastale: 0 }) : null} />
                <div className="text-xs text-amber-900 bg-amber-50 border border-amber-200 rounded p-2 mb-3">
                    ⚠ Banca dati catastale: nessuna API pubblica gratuita; per ora inserimento manuale. Importazione XML/ZIP da Agenzia Entrate prevista in roadmap.
                </div>
                {(ac.immobili || []).map((im, i) => (
                    <ImmobileRow key={i} item={im} canEdit={canEdit}
                        onChange={(patch) => updateItem("immobili", i, patch)}
                        onRemove={() => removeItem("immobili", i)} />
                ))}
            </Card>

            {/* Veicoli */}
            <Card className="p-5 border-slate-200">
                <SectionHeader title="Veicoli" icon={<Briefcase size={16} />} count={ac.veicoli?.length || 0}
                    onAdd={canEdit ? () => addItem("veicoli", { tipo: "auto", valore_commerciale: 0 }) : null} />
                {(ac.veicoli || []).map((v, i) => (
                    <VeicoloRow key={i} item={v} canEdit={canEdit}
                        onChange={(patch) => updateItem("veicoli", i, patch)}
                        onRemove={() => removeItem("veicoli", i)} />
                ))}
            </Card>

            {/* Beni */}
            <Card className="p-5 border-slate-200">
                <SectionHeader title="Altri beni" icon={<Briefcase size={16} />} count={ac.beni?.length || 0}
                    onAdd={canEdit ? () => addItem("beni", { descrizione: "", valore: 0 }) : null} />
                {(ac.beni || []).map((b, i) => (
                    <div key={i} className="grid grid-cols-12 gap-2 items-end mb-2">
                        <div className="col-span-7">
                            <Label className="text-xs">Descrizione</Label>
                            <Input value={b.descrizione || ""} disabled={!canEdit}
                                onChange={(e) => updateItem("beni", i, { descrizione: e.target.value })} />
                        </div>
                        <div className="col-span-4">
                            <Label className="text-xs">Valore €</Label>
                            <Input type="number" value={b.valore || 0} disabled={!canEdit}
                                onChange={(e) => updateItem("beni", i, { valore: parseFloat(e.target.value) || 0 })} />
                        </div>
                        {canEdit && (
                            <Button size="sm" variant="ghost" onClick={() => removeItem("beni", i)} className="col-span-1">
                                <Trash2 size={14} className="text-rose-600" />
                            </Button>
                        )}
                    </div>
                ))}
            </Card>

            {/* Aziende */}
            <Card className="p-5 border-slate-200">
                <SectionHeader title="Aziende / Partecipazioni" icon={<Briefcase size={16} />} count={ac.aziende?.length || 0}
                    onAdd={canEdit ? () => addItem("aziende", { tipo: "srl", ragione_sociale: "", percentuale_partecipazione: 100, ebitda: 0, valore_ipotetico: 0 }) : null} />
                <div className="text-xs text-slate-600 bg-slate-50 border border-slate-200 rounded p-2 mb-3">
                    Formula valutazione SRL: <code>(EBITDA × 7 ± PFN) × % partecipazione</code>
                </div>
                {(ac.aziende || []).map((az, i) => (
                    <AziendaRow key={i} item={az} canEdit={canEdit}
                        onChange={(patch) => updateItem("aziende", i, patch)}
                        onRemove={() => removeItem("aziende", i)} />
                ))}
            </Card>
        </div>
    );
}

function ImmobileRow({ item, canEdit, onChange, onRemove }) {
    return (
        <div className="border border-slate-200 rounded-md p-3 mb-3 bg-slate-50/30">
            <div className="grid grid-cols-12 gap-2">
                <div className="col-span-3">
                    <Label className="text-xs">Tipo immobile</Label>
                    <Select value={item.tipo || "abitativo"} disabled={!canEdit} onValueChange={(v) => onChange({ tipo: v })}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="abitativo">Abitativo</SelectItem>
                            <SelectItem value="commerciale">Commerciale</SelectItem>
                            <SelectItem value="ufficio">Ufficio</SelectItem>
                            <SelectItem value="garage">Garage / Pertinenza</SelectItem>
                            <SelectItem value="terreno">Terreno</SelectItem>
                            <SelectItem value="altro">Altro</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
                <div className="col-span-3">
                    <Label className="text-xs">Titolo</Label>
                    <Select value={item.titolo || "proprieta"} disabled={!canEdit} onValueChange={(v) => onChange({ titolo: v })}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="proprieta">Proprietà</SelectItem>
                            <SelectItem value="comproprieta">Comproprietà</SelectItem>
                            <SelectItem value="usufrutto">Usufrutto</SelectItem>
                            <SelectItem value="nuda_proprieta">Nuda proprietà</SelectItem>
                            <SelectItem value="locazione">Locazione</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
                <div className="col-span-2">
                    <Label className="text-xs">% Proprietà</Label>
                    <Input type="number" value={item.percentuale_proprieta ?? 100} disabled={!canEdit}
                        onChange={(e) => onChange({ percentuale_proprieta: parseFloat(e.target.value) || 0 })} />
                </div>
                <div className="col-span-3">
                    <Label className="text-xs">Valore commerciale €</Label>
                    <Input type="number" value={item.valore_commerciale || 0} disabled={!canEdit}
                        onChange={(e) => onChange({ valore_commerciale: parseFloat(e.target.value) || 0 })} />
                </div>
                {canEdit && (
                    <Button size="sm" variant="ghost" onClick={onRemove} className="col-span-1 mt-5">
                        <Trash2 size={14} className="text-rose-600" />
                    </Button>
                )}
                <div className="col-span-5">
                    <Label className="text-xs">Indirizzo</Label>
                    <Input value={item.indirizzo || ""} disabled={!canEdit}
                        onChange={(e) => onChange({ indirizzo: e.target.value })} />
                </div>
                <div className="col-span-3">
                    <Label className="text-xs">Comune</Label>
                    <Input value={item.comune || ""} disabled={!canEdit}
                        onChange={(e) => onChange({ comune: e.target.value })} />
                </div>
                <div className="col-span-2">
                    <Label className="text-xs">Cat. Catastale</Label>
                    <Input value={item.categoria_catastale || ""} disabled={!canEdit} placeholder="A/2"
                        onChange={(e) => onChange({ categoria_catastale: e.target.value })} />
                </div>
                <div className="col-span-2">
                    <Label className="text-xs">Rendita catastale</Label>
                    <Input type="number" value={item.rendita_catastale || 0} disabled={!canEdit}
                        onChange={(e) => onChange({ rendita_catastale: parseFloat(e.target.value) || 0 })} />
                </div>
            </div>
        </div>
    );
}

function VeicoloRow({ item, canEdit, onChange, onRemove }) {
    return (
        <div className="grid grid-cols-12 gap-2 items-end mb-2">
            <div className="col-span-2">
                <Label className="text-xs">Tipo</Label>
                <Select value={item.tipo || "auto"} disabled={!canEdit} onValueChange={(v) => onChange({ tipo: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                        <SelectItem value="auto">Auto</SelectItem>
                        <SelectItem value="moto">Moto</SelectItem>
                        <SelectItem value="furgone">Furgone</SelectItem>
                        <SelectItem value="camper">Camper</SelectItem>
                        <SelectItem value="barca">Barca</SelectItem>
                        <SelectItem value="altro">Altro</SelectItem>
                    </SelectContent>
                </Select>
            </div>
            <div className="col-span-2"><Label className="text-xs">Marca</Label><Input value={item.marca || ""} disabled={!canEdit} onChange={(e) => onChange({ marca: e.target.value })} /></div>
            <div className="col-span-2"><Label className="text-xs">Modello</Label><Input value={item.modello || ""} disabled={!canEdit} onChange={(e) => onChange({ modello: e.target.value })} /></div>
            <div className="col-span-2"><Label className="text-xs">Targa</Label><Input value={item.targa || ""} disabled={!canEdit} onChange={(e) => onChange({ targa: e.target.value })} /></div>
            <div className="col-span-3"><Label className="text-xs">Valore €</Label><Input type="number" value={item.valore_commerciale || 0} disabled={!canEdit} onChange={(e) => onChange({ valore_commerciale: parseFloat(e.target.value) || 0 })} /></div>
            {canEdit && <Button size="sm" variant="ghost" onClick={onRemove} className="col-span-1"><Trash2 size={14} className="text-rose-600" /></Button>}
        </div>
    );
}

function AziendaRow({ item, canEdit, onChange, onRemove }) {
    const valoreCalcolato = ((item.ebitda || 0) * 7 + (item.posizione_finanziaria_netta || 0)) * (item.percentuale_partecipazione || 100) / 100;
    return (
        <div className="border border-slate-200 rounded-md p-3 mb-3 bg-slate-50/30">
            <div className="grid grid-cols-12 gap-2">
                <div className="col-span-2">
                    <Label className="text-xs">Tipo</Label>
                    <Select value={item.tipo || "srl"} disabled={!canEdit} onValueChange={(v) => onChange({ tipo: v })}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="srl">SRL</SelectItem>
                            <SelectItem value="spa">SPA</SelectItem>
                            <SelectItem value="snc">SNC</SelectItem>
                            <SelectItem value="sas">SAS</SelectItem>
                            <SelectItem value="ditta_individuale">Ditta individuale</SelectItem>
                            <SelectItem value="altro">Altro</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
                <div className="col-span-4"><Label className="text-xs">Ragione sociale</Label><Input value={item.ragione_sociale || ""} disabled={!canEdit} onChange={(e) => onChange({ ragione_sociale: e.target.value })} /></div>
                <div className="col-span-3"><Label className="text-xs">P.IVA</Label><Input value={item.partita_iva || ""} disabled={!canEdit} onChange={(e) => onChange({ partita_iva: e.target.value })} /></div>
                <div className="col-span-2"><Label className="text-xs">% partecipazione</Label><Input type="number" value={item.percentuale_partecipazione || 100} disabled={!canEdit} onChange={(e) => onChange({ percentuale_partecipazione: parseFloat(e.target.value) || 0 })} /></div>
                {canEdit && <Button size="sm" variant="ghost" onClick={onRemove} className="col-span-1 mt-5"><Trash2 size={14} className="text-rose-600" /></Button>}
                <div className="col-span-3"><Label className="text-xs">EBITDA €</Label><Input type="number" value={item.ebitda || 0} disabled={!canEdit} onChange={(e) => onChange({ ebitda: parseFloat(e.target.value) || 0 })} /></div>
                <div className="col-span-3"><Label className="text-xs">PFN (allargata) €</Label><Input type="number" value={item.posizione_finanziaria_netta || 0} disabled={!canEdit} onChange={(e) => onChange({ posizione_finanziaria_netta: parseFloat(e.target.value) || 0 })} /></div>
                <div className="col-span-3"><Label className="text-xs">Valore ipotetico €</Label><Input type="number" value={item.valore_ipotetico || 0} disabled={!canEdit} onChange={(e) => onChange({ valore_ipotetico: parseFloat(e.target.value) || 0 })} /></div>
                <div className="col-span-3 mt-5 text-xs text-emerald-700 bg-emerald-50 rounded px-2 py-1 font-medium">
                    Calcolato: {fmtEur(valoreCalcolato)}
                </div>
            </div>
        </div>
    );
}

// ============== SEZIONE 3: CONTESTO & OBIETTIVI ==============
function ContestoObiettivi({ ac, set, canEdit }) {
    return (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
            <TextAreaCard title="Contesto Familiare" value={ac.contesto_familiare} onChange={(v) => set("contesto_familiare", v)} canEdit={canEdit} />
            <TextAreaCard title="Contesto Lavorativo" value={ac.contesto_lavorativo} onChange={(v) => set("contesto_lavorativo", v)} canEdit={canEdit} />
            <TextAreaCard title="Contesto Patrimoniale" value={ac.contesto_patrimoniale} onChange={(v) => set("contesto_patrimoniale", v)} canEdit={canEdit} className="md:col-span-2" />

            <TextAreaCard title="Cosa ti renderebbe veramente felice e soddisfatto?" subtitle="Sogni e aspirazioni del cliente"
                value={ac.cosa_renderebbe_felice} onChange={(v) => set("cosa_renderebbe_felice", v)} canEdit={canEdit} className="md:col-span-2" highlight="emerald" />
            <TextAreaCard title="Durante la carriera lavorativa, cosa NON vuoi che accada?" value={ac.cosa_non_vuoi_carriera} onChange={(v) => set("cosa_non_vuoi_carriera", v)} canEdit={canEdit} highlight="rose" />
            <TextAreaCard title="Quando non ci sarai più, cosa NON vuoi che accada?" value={ac.cosa_non_vuoi_dopo} onChange={(v) => set("cosa_non_vuoi_dopo", v)} canEdit={canEdit} highlight="rose" />
            <TextAreaCard title="Quando smetterai di lavorare e sarai in pensione, cosa NON vuoi che accada?" value={ac.cosa_non_vuoi_pensione} onChange={(v) => set("cosa_non_vuoi_pensione", v)} canEdit={canEdit} highlight="rose" className="md:col-span-2" />
        </div>
    );
}

// ============== SEZIONE 4: APPROFONDIMENTO REDDITI ==============
function ApprofondimentoRedditi({ anagrafica_id, dirty }) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);

    const calcola = async () => {
        setLoading(true);
        try {
            const r = await api.post(`/anagrafiche/${anagrafica_id}/analisi/calcola-redditi`);
            setData(r.data);
        } catch (e) { toast.error("Errore: " + e.message); }
        finally { setLoading(false); }
    };
    useEffect(() => { calcola();  }, [anagrafica_id]);

    if (loading || !data) return <Loading />;

    return (
        <div className="space-y-4 mt-4">
            {dirty && (
                <div className="text-xs bg-amber-50 border border-amber-200 text-amber-900 rounded p-2">
                    ⚠ Modifiche non salvate. Salva per ricalcolare con i dati aggiornati.
                </div>
            )}
            <div className="text-xs bg-slate-50 border border-slate-200 text-slate-700 rounded p-2">
                Simulazione calcolata su <strong>tipo lavoratore: {data.tipo_lavoratore}</strong> {data.regime_forfettario && "(regime forfettario)"} usando valori medi di aliquote.
                Il risultato è solo un&apos;ipotesi e non ha valore certificativo.
            </div>

            {/* Flow infografico */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                <Kpi label="Reddito lordo" value={fmtEur(data.reddito_lordo)} color="emerald" big />
                <Kpi label="Contributi prev." value={`- ${fmtEur(data.contributi_lavoratore)}`} color="rose" hint={`${data.aliquota_contributiva_lavoratore_pct}%`} big />
                <Kpi label="IRPEF netta" value={`- ${fmtEur(data.irpef_netta)}`} color="rose" hint={`Marginale ${data.aliquota_irpef_marginale_pct}%`} big />
                <Kpi label="Reddito netto" value={fmtEur(data.reddito_netto)} color="sky" big highlight />
            </div>

            {/* Dettaglio IRPEF */}
            <Card className="p-5 border-slate-200">
                <h3 className="font-semibold mb-3">Calcolo IRPEF</h3>
                <table className="w-full text-sm">
                    <tbody className="divide-y divide-slate-100">
                        <tr><td className="py-2 text-slate-600">Reddito lordo</td><td className="text-right num font-medium">{fmtEur(data.reddito_lordo)}</td><td className="text-slate-400 text-xs pl-2">+</td></tr>
                        <tr><td className="py-2 text-slate-600">Altri redditi</td><td className="text-right num">{fmtEur(data.altri_redditi)}</td><td className="text-slate-400 text-xs pl-2">+</td></tr>
                        <tr><td className="py-2 text-slate-600">Contributi previdenziali</td><td className="text-right num text-rose-600">-{fmtEur(data.contributi_lavoratore)}</td><td className="text-slate-400 text-xs pl-2">-</td></tr>
                        <tr className="bg-slate-50"><td className="py-2 font-semibold">Reddito imponibile</td><td className="text-right num font-bold">{fmtEur(data.reddito_imponibile)}</td><td className="text-slate-400 text-xs pl-2">=</td></tr>
                        <tr><td className="py-2 text-slate-600">IRPEF lorda (aliq. marginale {data.aliquota_irpef_marginale_pct}%)</td><td className="text-right num font-medium">{fmtEur(data.irpef_lorda)}</td><td></td></tr>
                        <tr><td className="py-2 text-slate-600 pl-4">Detrazione lavoro dipendente</td><td className="text-right num text-emerald-600">-{fmtEur(data.detrazione_lavoro_dipendente)}</td><td></td></tr>
                        <tr><td className="py-2 text-slate-600 pl-4">Detrazione coniuge a carico</td><td className="text-right num text-emerald-600">-{fmtEur(data.detrazione_coniuge)}</td><td></td></tr>
                        <tr><td className="py-2 text-slate-600 pl-4">Detrazione figli a carico</td><td className="text-right text-xs text-slate-400 italic">Dal 2022 Assegno Unico non calcolabile</td><td></td></tr>
                        <tr><td className="py-2 text-slate-600 pl-4">Altre detrazioni</td><td className="text-right num text-emerald-600">-{fmtEur(data.altre_detrazioni)}</td><td></td></tr>
                        <tr className="bg-rose-50"><td className="py-2 font-semibold">IRPEF netta</td><td className="text-right num font-bold text-rose-700">{fmtEur(data.irpef_netta)}</td><td></td></tr>
                        <tr className="bg-emerald-50"><td className="py-2 font-bold">Reddito netto stimato</td><td className="text-right num font-bold text-emerald-700 text-lg">{fmtEur(data.reddito_netto)}</td><td className="text-slate-400 text-xs pl-2">=</td></tr>
                    </tbody>
                </table>
            </Card>
        </div>
    );
}

// ============== SEZIONE 5: PENSIONE INPS (storico + oggi + domani) ==============
function PensioneInpsTab({ ac, set, canEdit, anagrafica_id, ana, onReload, dirty }) {
    const [pens, setPens] = useState(null);
    const [loading, setLoading] = useState(false);

    const calcola = async () => {
        setLoading(true);
        try {
            const r = await api.post(`/anagrafiche/${anagrafica_id}/analisi/calcola-pensioni-future`);
            setPens(r.data);
        } catch (e) { toast.error("Errore: " + e.message); }
        finally { setLoading(false); }
    };
    useEffect(() => { calcola();  }, [anagrafica_id]);

    const addPeriodo = () => set("periodi_contributivi", [...(ac.periodi_contributivi || []), { fondo: "Commerciante", inizio_periodo: new Date().toISOString().slice(0, 10), fine_periodo: "" }]);
    const removePeriodo = (i) => set("periodi_contributivi", (ac.periodi_contributivi || []).filter((_, idx) => idx !== i));
    const updatePeriodo = (i, patch) => set("periodi_contributivi", (ac.periodi_contributivi || []).map((p, idx) => idx === i ? { ...p, ...patch } : p));

    const addReddito = () => set("storico_redditi", [...(ac.storico_redditi || []), { anno: new Date().getFullYear(), reddito: 0, contributi: 0 }]);
    const removeReddito = (i) => set("storico_redditi", (ac.storico_redditi || []).filter((_, idx) => idx !== i));
    const updateReddito = (i, patch) => set("storico_redditi", (ac.storico_redditi || []).map((r, idx) => idx === i ? { ...r, ...patch } : r));

    return (
        <div className="space-y-4 mt-4">
            <div className="text-xs bg-sky-50 border border-sky-200 text-sky-900 rounded p-2">
                <strong>Parametri di calcolo</strong>: vengono sempre calcolate tutte e tre le pensioni —
                <strong> Invalidità grave (66%-99%)</strong>, <strong>Inabilità totale al 100%</strong>, <strong>Superstiti</strong>.
            </div>

            {dirty && (
                <div className="text-xs bg-amber-50 border border-amber-200 text-amber-900 rounded p-2 flex justify-between items-center">
                    <span>⚠ Modifiche non salvate.</span>
                    <Button size="sm" variant="outline" onClick={calcola}>Ricalcola</Button>
                </div>
            )}

            {/* Archivio estratti INPS */}
            <ArchivioEstrattiInps anagrafica_id={anagrafica_id} ac={ac} canEdit={canEdit} onUpdate={() => { onReload?.(); calcola(); }} />

            {/* Carriera contributiva (periodi) */}
            <Card className="p-5 border-slate-200">
                <SectionHeader title="Carriera contributiva" icon={<Briefcase size={16} />} count={ac.periodi_contributivi?.length || 0}
                    onAdd={canEdit ? addPeriodo : null} />
                <table className="w-full text-sm">
                    <thead><tr className="text-xs text-slate-500 border-b"><th className="text-left py-1">Fondo</th><th className="text-left py-1">Inizio</th><th className="text-left py-1">Fine</th><th className="text-left py-1">Riscattato</th><th></th></tr></thead>
                    <tbody>
                        {(ac.periodi_contributivi || []).map((p, i) => (
                            <tr key={i}>
                                <td><Input value={p.fondo || ""} disabled={!canEdit} onChange={(e) => updatePeriodo(i, { fondo: e.target.value })} className="h-7" /></td>
                                <td><Input type="date" value={p.inizio_periodo || ""} disabled={!canEdit} onChange={(e) => updatePeriodo(i, { inizio_periodo: e.target.value })} className="h-7" /></td>
                                <td><Input type="date" value={p.fine_periodo || ""} disabled={!canEdit} onChange={(e) => updatePeriodo(i, { fine_periodo: e.target.value })} className="h-7" /></td>
                                <td><input type="checkbox" checked={!!p.riscattato} disabled={!canEdit} onChange={(e) => updatePeriodo(i, { riscattato: e.target.checked })} /></td>
                                <td>{canEdit && <Button size="sm" variant="ghost" onClick={() => removePeriodo(i)}><Trash2 size={12} className="text-rose-600" /></Button>}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </Card>

            {/* Storico redditi */}
            <Card className="p-5 border-slate-200">
                <SectionHeader title="Storico redditi" icon={<Wallet size={16} />} count={ac.storico_redditi?.length || 0}
                    onAdd={canEdit ? addReddito : null} />
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                    {(ac.storico_redditi || []).sort((a, b) => b.anno - a.anno).map((r, i) => {
                        const realIdx = (ac.storico_redditi || []).findIndex(x => x === r);
                        return (
                            <div key={realIdx} className="grid grid-cols-12 gap-2 items-end">
                                <div className="col-span-2"><Label className="text-xs">Anno</Label><Input type="number" value={r.anno || ""} disabled={!canEdit} onChange={(e) => updateReddito(realIdx, { anno: parseInt(e.target.value) || 0 })} className="h-8" /></div>
                                <div className="col-span-5"><Label className="text-xs">Reddito €</Label><Input type="number" value={r.reddito || 0} disabled={!canEdit} onChange={(e) => updateReddito(realIdx, { reddito: parseFloat(e.target.value) || 0 })} className="h-8" /></div>
                                <div className="col-span-4"><Label className="text-xs">Contributi €</Label><Input type="number" value={r.contributi || 0} disabled={!canEdit} onChange={(e) => updateReddito(realIdx, { contributi: parseFloat(e.target.value) || 0 })} className="h-8" /></div>
                                {canEdit && <Button size="sm" variant="ghost" onClick={() => removeReddito(realIdx)} className="col-span-1"><Trash2 size={12} className="text-rose-600" /></Button>}
                            </div>
                        );
                    })}
                </div>
            </Card>

            {loading && <Loading />}
            {pens && (
                <>
                    {/* KPI riepilogo */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <Kpi label="Anni contribuzione" value={pens.anni_contribuzione} color="sky" big />
                        <Kpi label="Settimane" value={pens.settimane_contributive} color="slate" big />
                        <Kpi label="Totale versato" value={fmtEur(pens.totale_versato)} color="emerald" big />
                        <Kpi label="Totale rivalutato" value={fmtEur(pens.totale_rivalutato)} color="sky" big highlight />
                    </div>

                    {/* Pensioni di OGGI */}
                    <Card className="p-5 border-rose-200 bg-rose-50/20">
                        <h3 className="font-semibold mb-3 flex items-center gap-2"><Shield size={16} className="text-rose-600" /> Pensioni ad oggi (Problema di OGGI)</h3>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                            {["invalidita", "inabilita", "superstite"].map((tipo) => {
                                const p = pens.pensioni_oggi[tipo];
                                if (!p) return null;
                                const labels = { invalidita: "Invalidità (66-99%)", inabilita: "Inabilità (100%)", superstite: "Superstiti" };
                                return (
                                    <div key={tipo} className="bg-white rounded-md border border-slate-200 p-4">
                                        <div className="text-xs uppercase tracking-wider text-slate-500">{labels[tipo]}</div>
                                        <div className="text-2xl font-bold text-rose-700 num mt-1">{fmtEur(p.pensione_lorda_mensile)}</div>
                                        <div className="text-xs text-slate-500">lordi / mese</div>
                                        <div className="mt-2 pt-2 border-t text-xs space-y-0.5">
                                            <div className="flex justify-between"><span className="text-slate-500">Annuo:</span><span className="num">{fmtEur(p.pensione_lorda_annua)}</span></div>
                                            <div className="flex justify-between"><span className="text-slate-500">Netto stimato:</span><span className="num">{fmtEur(p.pensione_netta_stimata)}</span></div>
                                        </div>
                                        <div className="text-[10px] text-slate-400 mt-1">{p.metodologia}</div>
                                    </div>
                                );
                            })}
                        </div>
                    </Card>

                    {/* Pensioni del DOMANI */}
                    <Card className="p-5 border-emerald-200 bg-emerald-50/20">
                        <h3 className="font-semibold mb-3 flex items-center gap-2"><TrendingUp size={16} className="text-emerald-600" /> Pensioni del domani (Vecchiaia)</h3>
                        <table className="w-full text-sm">
                            <thead><tr className="text-xs text-slate-500 border-b">
                                <th className="text-left py-2">Età</th><th className="text-left">Anno</th><th className="text-left">Modalità</th>
                                <th className="text-right">Anni contrib.</th><th className="text-right">Importo annuo</th><th className="text-right">Importo mensile</th><th className="text-right">Montante</th>
                            </tr></thead>
                            <tbody>
                                {(pens.pensioni_domani || []).map((p, i) => (
                                    <tr key={i} className="border-b border-slate-100 hover:bg-emerald-50/40">
                                        <td className="py-1.5 font-medium">{p.eta_pensionamento}</td>
                                        <td>{p.anno_pensionamento}</td>
                                        <td><span className={`px-2 py-0.5 rounded text-xs ${p.modalita === "Vecchiaia" ? "bg-emerald-100 text-emerald-800" : "bg-sky-100 text-sky-800"}`}>{p.modalita}</span></td>
                                        <td className="text-right num">{p.anni_contribuzione_totali}</td>
                                        <td className="text-right num font-medium">{fmtEur(p.importo_annuo)}</td>
                                        <td className="text-right num text-emerald-700 font-semibold">{fmtEur(p.importo_mensile)}</td>
                                        <td className="text-right num text-slate-500 text-xs">{fmtEur(p.montante_contributivo)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </Card>
                </>
            )}
        </div>
    );
}

// ============== SEZIONE 6: SCOPERTURE PENSIONISTICHE ==============
function ScoperturePensione({ anagrafica_id, dirty }) {
    const [scop, setScop] = useState(null);
    const [loading, setLoading] = useState(false);

    const calcola = async () => {
        setLoading(true);
        try {
            const r = await api.post(`/anagrafiche/${anagrafica_id}/analisi/calcola-scoperture`);
            setScop(r.data);
        } catch (e) { toast.error("Errore: " + e.message); }
        finally { setLoading(false); }
    };
    useEffect(() => { calcola();  }, [anagrafica_id]);

    if (loading || !scop) return <Loading />;

    return (
        <div className="space-y-4 mt-4">
            {dirty && (
                <div className="text-xs bg-amber-50 border border-amber-200 text-amber-900 rounded p-2 flex justify-between items-center">
                    <span>⚠ Modifiche non salvate.</span>
                    <Button size="sm" variant="outline" onClick={calcola}>Ricalcola</Button>
                </div>
            )}
            <div className="text-xs bg-slate-50 border border-slate-200 text-slate-700 rounded p-2">
                Tutte le scoperture sono calcolate partendo da un reddito di <strong>{fmtEur(scop.reddito_complessivo_annuo)}/anno</strong>.
                Anni residui fino a 70: <strong>{scop.anni_a_70}</strong>. Eventuali debiti sono inclusi nel capitale per superstiti.
            </div>

            <h3 className="text-sm font-bold text-slate-700 uppercase tracking-wider">Problema di oggi</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <ScopCard titolo="Invalidità" dati={scop.invalidita} color="rose"
                    formula="(Reddito lordo - Pens. invalidità) × anni mancanti ai 70" />
                <ScopCard titolo="Inabilità" dati={scop.inabilita} color="amber"
                    formula="(Reddito lordo - Pens. inabilità) × anni mancanti ai 70" />
                <ScopCard titolo="Superstiti (premorienza)" dati={scop.superstiti} color="rose"
                    formula={`Max{ età coniuge a 70, figlio + 25 } × scopertura + debiti (${fmtEur(scop.superstiti.debiti_inclusi)})`} />
            </div>

            <h3 className="text-sm font-bold text-slate-700 uppercase tracking-wider mt-6">Problema del futuro</h3>
            <Card className="p-5 border-sky-200 bg-sky-50/20">
                <h3 className="font-bold text-sky-800 text-sm uppercase tracking-wider mb-3">Pensione di vecchiaia · età {scop.vecchiaia.eta_pensionamento} anni</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-2 text-sm">
                        <Row label="Pensione lorda mensile (13 mens.)" value={fmtEur(scop.vecchiaia.pensione_mensile)} />
                        <Row label="Pensione lorda annua" value={fmtEur(scop.vecchiaia.pensione_annua)} />
                        <Row label="Scopertura mensile" value={fmtEur(scop.vecchiaia.scopertura_mensile)} color="rose" />
                        <Row label="Scopertura annua" value={fmtEur(scop.vecchiaia.scopertura_annua)} color="rose" />
                    </div>
                    <div className="flex flex-col items-center justify-center bg-white rounded-md p-4 border border-sky-200">
                        <div className="text-xs uppercase tracking-wider text-slate-500">Copertura pensione vecchiaia</div>
                        <div className={`text-5xl font-bold num ${scop.vecchiaia.copertura_pct >= 80 ? "text-emerald-700" : scop.vecchiaia.copertura_pct >= 50 ? "text-amber-700" : "text-rose-700"}`}>
                            {scop.vecchiaia.copertura_pct}%
                        </div>
                        <div className="text-xs text-slate-500 mt-2">del reddito attuale</div>
                    </div>
                </div>
            </Card>
        </div>
    );
}

// ============== SEZIONE 7: SUCCESSIONE ==============
function SuccessioneTab({ anagrafica_id, dirty }) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);

    const calcola = async () => {
        setLoading(true);
        try {
            const r = await api.post(`/anagrafiche/${anagrafica_id}/analisi/calcola-successione`);
            setData(r.data);
        } catch (e) { toast.error("Errore: " + e.message); }
        finally { setLoading(false); }
    };
    useEffect(() => { calcola();  }, [anagrafica_id]);

    if (loading || !data) return <Loading />;

    return (
        <div className="space-y-4 mt-4">
            {dirty && (
                <div className="text-xs bg-amber-50 border border-amber-200 text-amber-900 rounded p-2 flex justify-between items-center">
                    <span>⚠ Modifiche non salvate.</span>
                    <Button size="sm" variant="outline" onClick={calcola}>Ricalcola</Button>
                </div>
            )}
            <div className="bg-slate-50 border border-slate-200 rounded-md p-3 flex justify-between items-center">
                <div className="text-sm">
                    <strong>Patrimonio stimato:</strong> <span className="num text-lg text-sky-700 font-bold">{fmtEur(data.patrimonio)}</span>
                </div>
                <div className="text-xs text-slate-500">
                    Familiari: {data.componenti_familiari.coniuge ? "✓ Coniuge" : "✗ Coniuge"} ·
                    {data.componenti_familiari.figli} Figli ·
                    {data.componenti_familiari.genitori} Genitori ·
                    {data.componenti_familiari.fratelli} Fratelli
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Scenario scen={data.senza_testamento} titolo="Senza testamento (Successione legittima)" color="sky" />
                <Scenario scen={data.quote_legittima} titolo="Con testamento (Quote di legittima)" color="emerald" />
            </div>

            <Card className="p-4 border-amber-200 bg-amber-50/30">
                <div className="text-xs text-amber-900">
                    <strong>Nota:</strong> il calcolo si basa sull&apos;<em>albero genealogico</em> della scheda anagrafica e sul Codice Civile italiano
                    (artt. 565-586 successione legittima · artt. 536-553 quote di legittima). Non considera donazioni in vita,
                    legati testamentari o disposizioni speciali. Per scenari complessi consultare un notaio.
                </div>
            </Card>
        </div>
    );
}

// ============== COMPONENTI HELPER ==============
function MoneyField({ label, value, onChange, canEdit, testid }) {
    return (
        <div>
            <Label className="text-xs text-slate-600">{label}</Label>
            <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-sm">€</span>
                <Input
                    type="number" step="0.01" value={value ?? ""}
                    disabled={!canEdit}
                    onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
                    className="pl-7 num"
                    data-testid={testid}
                />
            </div>
        </div>
    );
}

function ToggleField({ label, value, onChange, canEdit }) {
    return (
        <div className="flex items-center justify-between py-2">
            <Label className="text-sm text-slate-700">{label}</Label>
            <Switch checked={!!value} disabled={!canEdit} onCheckedChange={onChange} />
        </div>
    );
}

function TextAreaCard({ title, subtitle, value, onChange, canEdit, className = "", highlight }) {
    const colors = {
        emerald: "border-emerald-200 bg-emerald-50/30",
        rose: "border-rose-200 bg-rose-50/30",
        sky: "border-sky-200 bg-sky-50/30",
    };
    return (
        <Card className={`p-5 ${colors[highlight] || "border-slate-200"} ${className}`}>
            <div className="font-semibold text-slate-900 mb-1">{title}</div>
            {subtitle && <div className="text-xs text-slate-500 mb-2">{subtitle}</div>}
            <Textarea
                rows={4} value={value || ""} disabled={!canEdit}
                placeholder="Compila durante l'incontro con il cliente..."
                onChange={(e) => onChange(e.target.value)}
            />
        </Card>
    );
}

function SectionHeader({ title, icon, count, onAdd }) {
    return (
        <div className="flex items-center justify-between mb-3">
            <div className="font-semibold text-slate-900 flex items-center gap-2">
                {icon} {title} {count !== undefined && <span className="text-xs text-slate-500 font-normal">({count})</span>}
            </div>
            {onAdd && (
                <Button size="sm" variant="outline" onClick={onAdd}>
                    <Plus size={13} className="mr-1" /> Aggiungi
                </Button>
            )}
        </div>
    );
}

function Kpi({ label, value, color = "slate", big = false, highlight = false, hint }) {
    const colorMap = {
        emerald: "text-emerald-700 border-emerald-200",
        sky: "text-sky-700 border-sky-200",
        rose: "text-rose-700 border-rose-200",
        amber: "text-amber-700 border-amber-200",
        slate: "text-slate-700 border-slate-200",
        indigo: "text-indigo-700 border-indigo-200",
    };
    return (
        <div className={`bg-white rounded-md border ${colorMap[color]} p-3 ${highlight ? "ring-2 ring-sky-400" : ""}`}>
            <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
            <div className={`num font-bold ${big ? "text-xl" : "text-base"} ${colorMap[color].split(" ")[0]}`}>
                {value}
            </div>
            {hint && <div className="text-[10px] text-slate-400 mt-0.5">{hint}</div>}
        </div>
    );
}

function Row({ label, value, color }) {
    const colors = {
        rose: "text-rose-700",
        emerald: "text-emerald-700",
        amber: "text-amber-700",
        sky: "text-sky-700",
    };
    return (
        <div className="flex justify-between border-b border-slate-100 pb-1">
            <span className="text-slate-600">{label}</span>
            <span className={`num font-medium ${colors[color] || "text-slate-900"}`}>{value}</span>
        </div>
    );
}


const SUCC_COLORS = ["#0EA5E9", "#10B981", "#F59E0B", "#EC4899", "#8B5CF6", "#EF4444", "#6366F1", "#14B8A6"];

function ScopCard({ titolo, dati, color, formula }) {
    return (
        <Card className={`p-5 border-${color}-200 bg-${color}-50/20`}>
            <h3 className={`font-bold text-${color}-800 text-sm uppercase tracking-wider mb-3`}>{titolo}</h3>
            <div className="space-y-2 text-sm">
                <Row label="Pensione lorda mensile (13 mens.)" value={fmtEur(dati.pensione_mensile)} />
                <Row label="Pensione lorda annua" value={fmtEur(dati.pensione_annua)} />
                <Row label="Scopertura mensile" value={fmtEur(dati.scopertura_mensile)} color="rose" />
                <Row label="Scopertura annua" value={fmtEur(dati.scopertura_annua)} color="rose" />
                <Row label="Copertura attuale" value={`${dati.copertura_pct}%`} color={dati.copertura_pct >= 80 ? "emerald" : dati.copertura_pct >= 50 ? "amber" : "rose"} />
                <div className="border-t border-slate-200 pt-3 mt-3">
                    <div className="text-xs text-slate-500 uppercase tracking-wider">Capitale da assicurare</div>
                    <div className={`text-3xl font-bold num text-${color}-700`}>{fmtEur(dati.capitale_da_assicurare)}</div>
                    {formula && <div className="text-[10px] text-slate-400 italic mt-1">{formula}</div>}
                </div>
            </div>
        </Card>
    );
}

function Scenario({ scen, titolo, color }) {
    return (
        <Card className={`p-5 border-${color}-200`}>
            <h3 className={`font-bold text-${color}-800 text-sm uppercase tracking-wider mb-3`}>{titolo}</h3>
            {scen.label.length === 0 ? (
                <div className="text-sm text-slate-500 italic">Nessuna quota da ripartire.</div>
            ) : (
                <>
                    <div className="flex h-8 rounded-md overflow-hidden border border-slate-200 mb-3">
                        {scen.label.map((l, i) => (
                            <div key={l + i} title={`${l}: ${scen.quota_pct[i]}%`}
                                style={{ width: `${scen.quota_pct[i]}%`, backgroundColor: SUCC_COLORS[i % SUCC_COLORS.length] }}
                                className="text-white text-xs flex items-center justify-center font-bold">
                                {scen.quota_pct[i] >= 8 && `${scen.quota_pct[i]}%`}
                            </div>
                        ))}
                        {scen.disponibile_pct > 0 && (
                            <div title={`Disponibile: ${scen.disponibile_pct}%`}
                                style={{ width: `${scen.disponibile_pct}%`, backgroundColor: "#94A3B8" }}
                                className="text-white text-xs flex items-center justify-center font-bold">
                                {scen.disponibile_pct >= 8 && `${scen.disponibile_pct}% DISP.`}
                            </div>
                        )}
                    </div>
                    <table className="w-full text-sm">
                        <tbody className="divide-y divide-slate-100">
                            {scen.label.map((l, i) => (
                                <tr key={l + i}>
                                    <td className="py-1.5 flex items-center gap-2">
                                        <span className="w-3 h-3 rounded" style={{ backgroundColor: SUCC_COLORS[i % SUCC_COLORS.length] }} />
                                        {l}
                                    </td>
                                    <td className="text-right num font-medium">{scen.quota_pct[i]}%</td>
                                    <td className="text-right num text-slate-600">{fmtEur(scen.quota_eur[i])}</td>
                                </tr>
                            ))}
                            {scen.disponibile_pct > 0 && (
                                <tr className="bg-slate-50">
                                    <td className="py-1.5 flex items-center gap-2"><span className="w-3 h-3 rounded bg-slate-400" /> Quota disponibile</td>
                                    <td className="text-right num font-medium">{scen.disponibile_pct}%</td>
                                    <td className="text-right num text-slate-600">{fmtEur(scen.disponibile_eur)}</td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </>
            )}
            <div className="text-[11px] text-slate-500 italic mt-3 border-t pt-2">{scen.note}</div>
        </Card>
    );
}

// ============== ARCHIVIO ESTRATTI CONTO INPS ==============
function ArchivioEstrattiInps({ anagrafica_id, ac, canEdit, onUpdate }) {
    const [uploading, setUploading] = useState(false);
    const [sostituisci, setSostituisci] = useState(false);
    const [lastResult, setLastResult] = useState(null);
    const fileRef = useRef(null);

    const estratti = (ac?.estratti_conto_inps || []).slice().sort(
        (a, b) => (b.anno_riferimento || 0) - (a.anno_riferimento || 0),
    );

    const handleFile = async (e) => {
        const f = e.target.files?.[0];
        if (!f) return;
        const fd = new FormData();
        fd.append("file", f);
        fd.append("sostituisci_storico", sostituisci ? "true" : "false");
        setUploading(true);
        try {
            const r = await api.post(
                `/anagrafiche/${anagrafica_id}/analisi/upload-estratto-inps`,
                fd,
                { headers: { "Content-Type": "multipart/form-data" } },
            );
            setLastResult(r.data);
            const sett = r.data?.parsed?.settimane_contributive || 0;
            const anni = r.data?.parsed?.storico_redditi?.length || 0;
            const peri = r.data?.parsed?.periodi_contributivi_count || 0;
            toast.success(`Estratto caricato: ${sett} sett., ${anni} anni di redditi, ${peri} periodi.`);
            onUpdate?.();
        } catch (err) {
            toast.error(err.response?.data?.detail || "Errore upload");
        } finally {
            setUploading(false);
            if (fileRef.current) fileRef.current.value = "";
        }
    };

    const elimina = async (id, nome) => {
        if (!window.confirm(`Eliminare l'estratto "${nome}"? Il file verrà rimosso (i dati nello storico restano).`)) return;
        try {
            await api.delete(`/anagrafiche/${anagrafica_id}/analisi/estratto-inps/${id}`);
            toast.success("Estratto rimosso");
            onUpdate?.();
        } catch (err) {
            toast.error(err.response?.data?.detail || "Errore");
        }
    };

    return (
        <Card className="p-5 border-sky-200 bg-sky-50/20" data-testid="archivio-inps">
            <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                <div className="font-semibold text-slate-900 flex items-center gap-2">
                    <FileText size={16} className="text-sky-600" /> Archivio Estratto Conto INPS
                    <span className="text-xs text-slate-500 font-normal">({estratti.length})</span>
                </div>
                {canEdit && (
                    <div className="flex items-center gap-2 flex-wrap">
                        <label className="flex items-center gap-1 text-xs text-slate-700 cursor-pointer">
                            <input type="checkbox" checked={sostituisci} onChange={(e) => setSostituisci(e.target.checked)} />
                            Sostituisci storico esistente
                        </label>
                        <input
                            ref={fileRef} type="file" accept=".pdf,application/pdf"
                            onChange={handleFile} className="hidden"
                            data-testid="inps-file-input"
                        />
                        <Button
                            size="sm"
                            onClick={() => fileRef.current?.click()}
                            disabled={uploading}
                            className="bg-sky-700 hover:bg-sky-800"
                            data-testid="inps-upload-btn"
                        >
                            <Upload size={13} className="mr-1" />
                            {uploading ? "Caricamento..." : "Carica estratto PDF"}
                        </Button>
                    </div>
                )}
            </div>

            <div className="text-xs text-slate-600 bg-white border border-slate-200 rounded p-2 mb-3">
                Carica il PDF dell&apos;estratto contributivo (es. &laquo;Pensione_Storico_Redditi.pdf&raquo; scaricato dal portale INPS).
                I dati verranno automaticamente estratti: <strong>periodi</strong>, <strong>storico redditi per anno</strong>,
                <strong> settimane totali</strong>, <strong>contributi versati</strong>. In genere se ne carica uno all&apos;anno
                ma puoi caricarne più di uno (storico annuale).
            </div>

            {/* Last upload feedback */}
            {lastResult && (
                <div className="bg-emerald-50 border border-emerald-200 rounded p-3 mb-3 text-xs">
                    <div className="font-semibold text-emerald-900 mb-1">✓ Ultimo caricamento:</div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                        <Kpi label="Settimane" value={lastResult.parsed?.settimane_contributive || 0} color="emerald" />
                        <Kpi label="Anni stimati" value={lastResult.parsed?.anni_stimati || 0} color="sky" />
                        <Kpi label="Totale versato" value={fmtEur(lastResult.parsed?.totale_versato || 0)} color="amber" />
                        <Kpi label="Montante stimato" value={fmtEur(lastResult.parsed?.montante_stimato || 0)} color="emerald" big />
                    </div>
                </div>
            )}

            {/* Lista estratti caricati */}
            {estratti.length === 0 ? (
                <div className="text-sm text-slate-400 italic text-center py-4">
                    Nessun estratto INPS caricato. Trascina o seleziona il PDF per popolare automaticamente lo storico redditi.
                </div>
            ) : (
                <table className="w-full text-sm">
                    <thead><tr className="text-xs text-slate-500 border-b">
                        <th className="text-left py-1">Anno rif.</th>
                        <th className="text-left">Nome file</th>
                        <th className="text-left">Caricato il</th>
                        <th className="text-right">Settimane</th>
                        <th className="text-right">Versato</th>
                        <th className="text-right">Montante</th>
                        <th></th>
                    </tr></thead>
                    <tbody className="divide-y divide-slate-100">
                        {estratti.map((e) => (
                            <tr key={e.id} className="hover:bg-white">
                                <td className="py-1.5 font-semibold">{e.anno_riferimento || "—"}</td>
                                <td>
                                    {e.url ? (
                                        <a href={e.url} target="_blank" rel="noopener noreferrer"
                                            className="text-sky-700 hover:underline flex items-center gap-1">
                                            <FileText size={11} /> {e.nome_file}
                                        </a>
                                    ) : (e.nome_file || "—")}
                                    <span className="text-[10px] text-slate-400 ml-2">{e.size_kb} KB</span>
                                </td>
                                <td className="text-xs text-slate-500">
                                    {e.data_caricamento ? new Date(e.data_caricamento).toLocaleDateString("it-IT") : "—"}
                                    {e.caricato_da_nome && <span className="text-slate-400"> · {e.caricato_da_nome}</span>}
                                </td>
                                <td className="text-right num">{e.totale_settimane || 0}</td>
                                <td className="text-right num text-amber-700">{fmtEur(e.totale_versato || 0)}</td>
                                <td className="text-right num text-emerald-700 font-semibold">{fmtEur(e.montante_stimato || 0)}</td>
                                <td className="text-right">
                                    {canEdit && (
                                        <Button size="sm" variant="ghost" onClick={() => elimina(e.id, e.nome_file)} title="Elimina">
                                            <Trash2 size={12} className="text-rose-600" />
                                        </Button>
                                    )}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </Card>
    );
}

