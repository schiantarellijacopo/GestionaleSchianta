/**
 * Modelli Piramide — editor dei template globali (Privati / Aziende).
 * Le modifiche alle righe si propagano a TUTTI i clienti del tipo corrispondente.
 */
import { useEffect, useState } from "react";
import { api, formatError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Loading, PageHeader } from "@/components/Shared";
import PiramidePrivati from "@/components/PiramidePrivati";
import { Triangle, Plus, Trash2, RotateCcw, Save, Building2, User } from "lucide-react";
import { toast } from "sonner";

const LEVEL_COLORS = {
    crescita: "#1a5f6b", cassa_grandi: "#217887", cassa_lievi: "#217887",
    liquidita: "#217887", perdita: "#388a44", danni: "#388a44",
    premorienza: "#b93e3e", invalidita: "#b93e3e",
};

export default function ModelliPiramide() {
    const [templates, setTemplates] = useState(null);
    const [tab, setTab] = useState("privati");

    const load = () => api.get("/piramide-templates").then((r) => setTemplates(r.data));
    useEffect(() => { load(); }, []);

    if (!templates) return <Loading />;

    return (
        <div data-testid="modelli-piramide-page" className="space-y-4">
            <PageHeader
                title={<span className="flex items-center gap-2"><Triangle className="text-sky-700" /> Modelli Piramide</span>}
                subtitle="Personalizza le righe dei modelli: le modifiche si propagano a tutti i clienti"
            />
            <div className="bg-amber-50 border border-amber-200 rounded p-3 text-xs text-amber-900">
                <strong>Regola di visibilità:</strong> il modello <strong>Privati</strong> si applica alle persone fisiche;
                il modello <strong>Aziende</strong> si applica automaticamente alle anagrafiche con
                <strong> partita IVA</strong> o di tipo persona giuridica.
            </div>
            <Tabs value={tab} onValueChange={setTab}>
                <TabsList>
                    <TabsTrigger value="privati" data-testid="tab-modello-privati">
                        <User size={13} className="mr-1" /> Piramide Privati
                    </TabsTrigger>
                    <TabsTrigger value="aziende" data-testid="tab-modello-aziende">
                        <Building2 size={13} className="mr-1" /> Piramide Aziende
                    </TabsTrigger>
                </TabsList>
                <TabsContent value="privati">
                    <TemplateEditor key="privati" tipo="privati" initial={templates.privati} onSaved={load} />
                </TabsContent>
                <TabsContent value="aziende">
                    <TemplateEditor key="aziende" tipo="aziende" initial={templates.aziende} onSaved={load} />
                </TabsContent>
            </Tabs>
        </div>
    );
}

function TemplateEditor({ tipo, initial, onSaved }) {
    const [draft, setDraft] = useState(initial);
    const [saving, setSaving] = useState(false);

    const setLevel = (lid, patch) => setDraft((d) => ({
        ...d,
        levels: d.levels.map((l) => (l.id === lid ? { ...l, ...patch } : l)),
    }));
    const setVoce = (lid, idx, label) => setDraft((d) => ({
        ...d,
        levels: d.levels.map((l) => l.id === lid
            ? { ...l, voci: l.voci.map((v, i) => (i === idx ? { ...v, label } : v)) }
            : l),
    }));
    const addVoce = (lid) => setDraft((d) => ({
        ...d,
        levels: d.levels.map((l) => l.id === lid
            ? { ...l, voci: [...l.voci, { id: `voce_${Date.now().toString(36)}`, label: "" }] }
            : l),
    }));
    const removeVoce = (lid, idx) => setDraft((d) => ({
        ...d,
        levels: d.levels.map((l) => l.id === lid
            ? { ...l, voci: l.voci.filter((_, i) => i !== idx) }
            : l),
    }));
    const setWedge = (idx, label) => setDraft((d) => ({
        ...d,
        wedges: d.wedges.map((w, i) => (i === idx ? { ...w, label } : w)),
    }));

    const salva = async () => {
        for (const l of draft.levels) {
            if (l.modo === "voci" && l.voci.some((v) => !v.label.trim())) {
                toast.error(`Compila (o elimina) le righe vuote nella sezione "${l.titolo}"`);
                return;
            }
        }
        setSaving(true);
        try {
            const r = await api.put(`/piramide-templates/${tipo}`, draft);
            setDraft(r.data);
            toast.success("Modello salvato — propagato a tutti i clienti");
            onSaved();
        } catch (e) { toast.error(formatError(e)); }
        finally { setSaving(false); }
    };

    const reset = async () => {
        if (!window.confirm("Ripristinare il modello predefinito? Le personalizzazioni andranno perse.")) return;
        try {
            const r = await api.post(`/piramide-templates/${tipo}/reset`);
            setDraft(r.data);
            toast.success("Modello ripristinato");
            onSaved();
        } catch (e) { toast.error(formatError(e)); }
    };

    return (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mt-3 items-start">
            {/* EDITOR */}
            <Card className="p-4 space-y-3" data-testid={`editor-modello-${tipo}`}>
                <div className="flex items-center justify-between">
                    <div className="text-sm font-semibold text-slate-700">Sezioni e righe del modello</div>
                    <div className="flex gap-2">
                        <Button size="sm" variant="outline" onClick={reset} data-testid={`btn-reset-${tipo}`}>
                            <RotateCcw size={12} className="mr-1" /> Predefinito
                        </Button>
                        <Button size="sm" onClick={salva} disabled={saving}
                                className="bg-sky-700 hover:bg-sky-800" data-testid={`btn-salva-modello-${tipo}`}>
                            <Save size={12} className="mr-1" /> {saving ? "Salvataggio…" : "Salva modello"}
                        </Button>
                    </div>
                </div>

                {draft.levels.map((l) => (
                    <div key={l.id} className="border border-slate-200 rounded p-2.5 space-y-1.5"
                         data-testid={`editor-livello-${l.id}`}>
                        <div className="flex items-center gap-2">
                            <span className="w-3.5 h-3.5 rounded-sm shrink-0" style={{ background: LEVEL_COLORS[l.id] }} />
                            <Input value={l.titolo}
                                   onChange={(e) => setLevel(l.id, { titolo: e.target.value })}
                                   className="text-xs font-semibold h-8 uppercase"
                                   data-testid={`input-titolo-${l.id}`} />
                        </div>
                        {l.modo === "voci" && (
                            <div className="pl-5 space-y-1">
                                {l.voci.map((v, i) => (
                                    <div key={v.id} className="flex items-center gap-1.5">
                                        <Input value={v.label}
                                               onChange={(e) => setVoce(l.id, i, e.target.value)}
                                               placeholder="Etichetta riga — es. VEICOLI, sei protetto fino a"
                                               className="text-xs h-7"
                                               data-testid={`input-voce-${l.id}-${i}`} />
                                        <button onClick={() => removeVoce(l.id, i)}
                                                className="text-slate-400 hover:text-rose-600 shrink-0"
                                                title="Elimina riga"
                                                data-testid={`btn-del-voce-${l.id}-${i}`}>
                                            <Trash2 size={13} />
                                        </button>
                                    </div>
                                ))}
                                <button onClick={() => addVoce(l.id)}
                                        className="text-[11px] text-sky-700 hover:text-sky-900 font-medium flex items-center gap-1"
                                        data-testid={`btn-add-voce-${l.id}`}>
                                    <Plus size={11} /> Aggiungi riga
                                </button>
                            </div>
                        )}
                        {l.modo === "input" && (
                            <div className="pl-5 text-[10px] text-slate-400 italic">
                                Sezione a campo unico (importo inserito sulla piramide).
                            </div>
                        )}
                    </div>
                ))}

                <div className="border border-slate-200 rounded p-2.5 space-y-1.5">
                    <div className="text-xs font-semibold text-slate-600">Etichette zone laterali</div>
                    {draft.wedges.map((w, i) => (
                        <Input key={i} value={w.label}
                               onChange={(e) => setWedge(i, e.target.value)}
                               className="text-xs h-7 uppercase"
                               data-testid={`input-wedge-${i}`} />
                    ))}
                </div>

                <label className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer select-none">
                    <input type="checkbox"
                           checked={draft.mostra_testamento !== false}
                           onChange={(e) => setDraft((d) => ({ ...d, mostra_testamento: e.target.checked }))}
                           data-testid={`check-testamento-${tipo}`} />
                    Mostra sezione Testamento / Eredi legittimi
                </label>
            </Card>

            {/* ANTEPRIMA LIVE */}
            <div className="space-y-2" data-testid={`preview-modello-${tipo}`}>
                <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Anteprima live</div>
                <div className="overflow-x-auto">
                    <PiramidePrivati
                        template={draft}
                        voci_calcolate={{}}
                        clienteNome={tipo === "aziende" ? "ESEMPIO S.R.L." : "MARIO ROSSI"}
                        agenziaName="Anteprima modello"
                        onSave={null}
                    />
                </div>
            </div>
        </div>
    );
}
