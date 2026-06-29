/**
 * RaccoltaDatiTab — modulo strutturato di onboarding del cliente
 * basato sui PDF "RACCOLTA DATI" (motivazioni, appetito rischio, famiglia,
 * lavoro, aziende, risparmi, immobili, bilancio familiare, obiettivi, rischi).
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Save, Calculator, AlertTriangle, Heart, Home, Briefcase, Building, Wallet, Target } from "lucide-react";
import { toast } from "sonner";

const SEZIONI = [
    {
        key: "motivazioni",
        label: "Motivazioni & Aspettative",
        icon: Heart,
        color: "rose",
        campi: [{ key: "testo", label: "Quali sono le tue motivazioni e aspettative?", type: "textarea", rows: 3 }],
    },
    {
        key: "appetito_rischio",
        label: "Appetito al Rischio",
        icon: AlertTriangle,
        color: "amber",
        campi: [
            { key: "devastante_importo", label: "Danno devastante (€) — priorità assoluta", type: "number" },
            { key: "sostenibile_importo", label: "Danno sostenibile (€) — priorità secondaria", type: "number" },
            { key: "irrisorio_importo", label: "Danno irrisorio (€) — non prioritario", type: "number" },
            { key: "soglia_reddito_mensile", label: "Reddito: se le entrate diminuissero più di € … al mese", type: "number" },
            { key: "soglia_patrimonio", label: "Patrimonio: se il patrimonio diminuisse più di €", type: "number" },
            { key: "valutazione_reddito", label: "Valutazione rischio reddito", type: "select",
              options: ["Trascurabile", "Basso", "Medio", "Alto", "Molto Alto"] },
            { key: "valutazione_patrimonio", label: "Valutazione rischio patrimonio", type: "select",
              options: ["Trascurabile", "Basso", "Medio", "Alto", "Molto Alto"] },
        ],
    },
    {
        key: "famiglia",
        label: "Famiglia",
        icon: Heart,
        color: "pink",
        campi: [
            { key: "albero_genealogico", label: "Albero genealogico (genitori, fratelli, coniuge, figli)", type: "textarea", rows: 3 },
            { key: "convivente_nascita", label: "Coniuge/Convivente: data e luogo di nascita", type: "text" },
            { key: "figli_dati", label: "Figli: nomi, date e luoghi di nascita", type: "textarea", rows: 2 },
            { key: "chi_dipende_da_chi", label: "Riepilogo: chi dipende da chi", type: "textarea", rows: 2 },
        ],
    },
    {
        key: "lavoro",
        label: "Lavoro",
        icon: Briefcase,
        color: "sky",
        campi: [
            { key: "occupazione_specifica", label: "Di cosa ti occupi nello specifico?", type: "textarea", rows: 2 },
            { key: "carriera", label: "Descrivi la tua carriera lavorativa", type: "textarea", rows: 3 },
            { key: "rifarei_percorso", label: "Se tornassi indietro, rifaresti lo stesso percorso?", type: "textarea", rows: 2 },
        ],
    },
    {
        key: "aziende",
        label: "Aziende",
        icon: Building,
        color: "indigo",
        campi: [
            { key: "possiede_azienda", label: "Possiedi un'azienda o quote di aziende? (sì/no/quali)", type: "text" },
            { key: "storia_fondazione", label: "Come è nata l'azienda (storia di fondazione)", type: "textarea", rows: 3 },
            { key: "ciclo_produttivo", label: "Descrivi il ciclo produttivo della tua azienda", type: "textarea", rows: 3 },
        ],
    },
    {
        key: "risparmi",
        label: "Risparmi",
        icon: Wallet,
        color: "emerald",
        campi: [
            { key: "liquidita_conto", label: "Liquidità in conto corrente (€)", type: "number" },
            { key: "liquidita_investimenti", label: "Liquidità in investimenti (€)", type: "number" },
            { key: "altro_risparmi", label: "Altro (descrizione + importo)", type: "textarea", rows: 2 },
        ],
    },
    {
        key: "immobili",
        label: "Immobili",
        icon: Home,
        color: "amber",
        campi: [
            { key: "elenco", label: "Elenco/descrizione immobili posseduti", type: "textarea", rows: 4 },
        ],
    },
    {
        key: "altri_beni",
        label: "Altri Beni",
        icon: Wallet,
        color: "violet",
        campi: [
            { key: "elenco", label: "Opere d'arte, collezioni, auto d'epoca, oggetti preziosi…", type: "textarea", rows: 3 },
        ],
    },
    {
        key: "hobby",
        label: "Hobby & Passioni",
        icon: Heart,
        color: "rose",
        campi: [
            { key: "elenco", label: "Hobby, passioni, viaggi, sport, volontariato", type: "textarea", rows: 3 },
        ],
    },
    {
        key: "bilancio_familiare",
        label: "Bilancio Famigliare",
        icon: Calculator,
        color: "slate",
        campi: [
            { key: "entrate_ral", label: "Entrate · RAL (€)", type: "number" },
            { key: "entrate_affitti", label: "Entrate · Affitti (€)", type: "number" },
            { key: "entrate_pensione", label: "Entrate · Pensione (€)", type: "number" },
            { key: "entrate_altro", label: "Entrate · Altro (€)", type: "number" },
            { key: "uscite_minimo_vitale", label: "Uscite · Minimo vitale (€)", type: "number" },
            { key: "uscite_esigenze_vizi", label: "Uscite · Esigenze/Vizi (€)", type: "number" },
            { key: "uscite_risparmio", label: "Uscite · Risparmio (€)", type: "number" },
            { key: "attivi_cassa_prev", label: "Attivi · Cassa di previdenza obbligatoria (€)", type: "number" },
            { key: "attivi_pip", label: "Attivi · PIP (€)", type: "number" },
            { key: "attivi_tfr", label: "Attivi · TFR (€)", type: "number" },
            { key: "passivi_mutuo", label: "Passivi · Mutuo (€)", type: "number" },
            { key: "passivi_finanziamenti", label: "Passivi · Finanziamenti (€)", type: "number" },
            { key: "passivi_debiti", label: "Passivi · Altri debiti (€)", type: "number" },
            { key: "passivi_figli_anni", label: "Passivi · N. figli da mantenere (10k€/anno fino a 25 anni)", type: "number" },
            { key: "passivi_genitori_nonautosuff", label: "Passivi · Genitori non autosufficienti (€ 100k-500k)", type: "number" },
        ],
    },
    {
        key: "obiettivi_impegni",
        label: "Obiettivi & Impegni",
        icon: Target,
        color: "sky",
        campi: [
            { key: "obiettivi", label: "Quali sono i tuoi obiettivi?", type: "textarea", rows: 2 },
            { key: "tra_n_anni", label: "Come ti vedi tra X anni?", type: "textarea", rows: 2 },
            { key: "preoccupazioni", label: "Quali sono le tue maggiori preoccupazioni?", type: "textarea", rows: 2 },
            { key: "cosa_non_accada_pensione", label: "Cosa NON vuoi che accada da qui alla pensione?", type: "textarea", rows: 2 },
            { key: "cosa_non_accada_in_pensione", label: "Cosa NON vuoi che accada IN pensione?", type: "textarea", rows: 2 },
            { key: "cosa_non_accada_dopo", label: "Cosa NON vuoi che accada quando non ci sarai più?", type: "textarea", rows: 2 },
            { key: "testamento", label: "Hai scritto il testamento? (Sì/No + dettagli)", type: "text" },
        ],
    },
    {
        key: "gestione_rischi_attuale",
        label: "Gestione Rischi Attuale",
        icon: AlertTriangle,
        color: "rose",
        campi: [
            { key: "come_gestisci", label: "Attualmente come gestisci i tuoi rischi?", type: "textarea", rows: 3 },
            { key: "assicurazioni_vigenti", label: "Che tipo di assicurazioni hai in vigore?", type: "textarea", rows: 3 },
            { key: "criteri_scelte", label: "Quali sono i criteri con i quali hai fatto queste scelte?", type: "textarea", rows: 2 },
        ],
    },
];

export default function RaccoltaDatiTab({ anagrafica_id, canEdit }) {
    const [dati, setDati] = useState({});
    const [aggiornatoIl, setAggiornatoIl] = useState(null);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        api.get(`/anagrafiche/${anagrafica_id}`).then((r) => {
            setDati(r.data.raccolta_dati || {});
            setAggiornatoIl(r.data.raccolta_dati_aggiornata_il);
        });
    }, [anagrafica_id]);

    const setCampo = (sez, k, v) => setDati((p) => ({ ...p, [sez]: { ...(p[sez] || {}), [k]: v } }));

    const save = async () => {
        setSaving(true);
        try {
            await api.put(`/anagrafiche/${anagrafica_id}/raccolta-dati`, { raccolta_dati: dati });
            toast.success("Raccolta dati salvata");
            const r = await api.get(`/anagrafiche/${anagrafica_id}`);
            setAggiornatoIl(r.data.raccolta_dati_aggiornata_il);
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        finally { setSaving(false); }
    };

    return (
        <div className="space-y-4 mt-4" data-testid="raccolta-dati-tab">
            <Card className="p-3 bg-sky-50 border-sky-200 flex items-center justify-between">
                <div className="text-xs">
                    <strong className="text-sky-800">Raccolta Dati onboarding</strong> · Form strutturato basato sul PDF &quot;RACCOLTA DATI&quot;.
                    {aggiornatoIl && <span className="text-slate-600 ml-2">· Aggiornato il {new Date(aggiornatoIl).toLocaleDateString("it-IT")}</span>}
                </div>
                {canEdit && (
                    <Button size="sm" onClick={save} disabled={saving} className="bg-sky-700 hover:bg-sky-800" data-testid="rd-save-top">
                        <Save size={13} className="mr-1" /> {saving ? "Salvataggio…" : "Salva"}
                    </Button>
                )}
            </Card>

            {SEZIONI.map((sez) => {
                const Icon = sez.icon;
                const vals = dati[sez.key] || {};
                return (
                    <Card key={sez.key} className={`p-4 border-l-4 border-${sez.color}-400`} data-testid={`rd-sez-${sez.key}`}>
                        <h3 className={`font-semibold text-${sez.color}-700 flex items-center gap-2 mb-3`}>
                            <Icon size={16} /> {sez.label}
                        </h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            {sez.campi.map((c) => (
                                <div key={c.key} className={c.type === "textarea" ? "md:col-span-2" : ""}>
                                    <Label className="text-xs text-slate-600">{c.label}</Label>
                                    {c.type === "textarea" ? (
                                        <Textarea rows={c.rows || 3} value={vals[c.key] || ""}
                                            onChange={(e) => setCampo(sez.key, c.key, e.target.value)}
                                            disabled={!canEdit} data-testid={`rd-${sez.key}-${c.key}`} />
                                    ) : c.type === "number" ? (
                                        <Input type="number" step="0.01" value={vals[c.key] ?? ""}
                                            onChange={(e) => setCampo(sez.key, c.key, parseFloat(e.target.value) || 0)}
                                            disabled={!canEdit} data-testid={`rd-${sez.key}-${c.key}`} />
                                    ) : c.type === "select" ? (
                                        <Select value={vals[c.key] || ""} onValueChange={(v) => setCampo(sez.key, c.key, v)} disabled={!canEdit}>
                                            <SelectTrigger data-testid={`rd-${sez.key}-${c.key}`}><SelectValue placeholder="—" /></SelectTrigger>
                                            <SelectContent>
                                                {c.options.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}
                                            </SelectContent>
                                        </Select>
                                    ) : (
                                        <Input value={vals[c.key] || ""}
                                            onChange={(e) => setCampo(sez.key, c.key, e.target.value)}
                                            disabled={!canEdit} data-testid={`rd-${sez.key}-${c.key}`} />
                                    )}
                                </div>
                            ))}
                        </div>
                    </Card>
                );
            })}

            {canEdit && (
                <div className="flex justify-end sticky bottom-2">
                    <Button onClick={save} disabled={saving} className="bg-sky-700 hover:bg-sky-800 shadow-lg" data-testid="rd-save-bottom">
                        <Save size={14} className="mr-1" /> {saving ? "Salvataggio…" : "Salva raccolta dati"}
                    </Button>
                </div>
            )}
        </div>
    );
}
