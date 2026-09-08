/**
 * ImmobiliSection — sezione Immobili riutilizzabile (privati e aziende).
 * Import dati Catasto (via tab Anagrafica), geolocalizzazione su mappa e
 * inserimento manuale (comprese unità prese in affitto). Autonoma nel
 * caricamento/salvataggio dell'oggetto analisi del cliente.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Home, Plus, MapPin, Save } from "lucide-react";
import { toast } from "sonner";
import { ImmobiliMap, ImmobileRow } from "@/components/AnalisiClienteTab";

export default function ImmobiliSection({ anagrafica_id, canEdit }) {
    const [analisi, setAnalisi] = useState(null);
    const [immobili, setImmobili] = useState([]);
    const [dirty, setDirty] = useState(false);
    const [saving, setSaving] = useState(false);
    const [showMap, setShowMap] = useState(true);

    const load = async () => {
        const r = await api.get(`/anagrafiche/${anagrafica_id}/analisi`);
        setAnalisi(r.data);
        setImmobili(r.data.immobili || []);
        setDirty(false);
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [anagrafica_id]);

    const add = () => {
        setImmobili((p) => [...p, { tipo: "commerciale", titolo: "proprieta", percentuale_proprieta: 100, valore_commerciale: 0, rendita_catastale: 0 }]);
        setDirty(true);
    };
    const update = (i, patch) => { setImmobili((p) => p.map((it, idx) => idx === i ? { ...it, ...patch } : it)); setDirty(true); };
    const remove = (i) => { setImmobili((p) => p.filter((_, idx) => idx !== i)); setDirty(true); };

    const save = async () => {
        setSaving(true);
        try {
            await api.put(`/anagrafiche/${anagrafica_id}/analisi`, { ...(analisi || {}), immobili });
            toast.success("Immobili salvati");
            setDirty(false);
        } catch (e) { toast.error(e.response?.data?.detail || "Errore salvataggio"); }
        finally { setSaving(false); }
    };

    const geolocalizza = async () => {
        setSaving(true);
        try {
            if (dirty) await api.put(`/anagrafiche/${anagrafica_id}/analisi`, { ...(analisi || {}), immobili });
            const r = await api.post(`/openapi-it/analisi/${anagrafica_id}/geocode-immobili`);
            if (r.data.geocodificati > 0) {
                toast.success(`${r.data.geocodificati} immobili geolocalizzati`);
                await load();
            } else {
                toast.info("Nessun immobile da geolocalizzare (indirizzo/comune mancante).");
            }
        } catch (e) { toast.error("Errore geocoding: " + (e.response?.data?.detail || e.message)); }
        finally { setSaving(false); }
    };

    if (!analisi) return null;
    const daGeo = immobili.some((i) => !i.latitude && (i.indirizzo || i.comune));

    return (
        <Card className="p-4" data-testid="sf-immobili-card">
            <div className="flex items-center justify-between mb-3">
                <h4 className="font-semibold text-slate-800 text-sm flex items-center gap-2">
                    <Home size={16} /> Immobili aziendali <span className="text-slate-400">({immobili.length})</span>
                </h4>
                <div className="flex gap-2">
                    <Button size="sm" variant={showMap ? "default" : "outline"} className="text-xs h-8"
                        onClick={() => setShowMap((v) => !v)} data-testid="sf-immobili-map-btn">
                        <MapPin size={12} className="mr-1" /> Mappa
                    </Button>
                    {canEdit && daGeo && (
                        <Button size="sm" variant="outline" className="text-xs h-8" onClick={geolocalizza} disabled={saving} data-testid="sf-immobili-geocode-btn">
                            <MapPin size={12} className="mr-1" /> Geolocalizza immobili
                        </Button>
                    )}
                    {canEdit && (
                        <Button size="sm" variant="outline" className="text-xs h-8" onClick={add} data-testid="sf-immobili-add-btn">
                            <Plus size={12} className="mr-1" /> Aggiungi
                        </Button>
                    )}
                    {canEdit && (
                        <Button size="sm" className="text-xs h-8 bg-emerald-600 hover:bg-emerald-700" onClick={save} disabled={!dirty || saving} data-testid="sf-immobili-save-btn">
                            <Save size={12} className="mr-1" /> {saving ? "Salvo…" : (dirty ? "Salva" : "Salvato")}
                        </Button>
                    )}
                </div>
            </div>

            <div className="text-xs text-sky-900 bg-sky-50 border border-sky-200 rounded p-2 mb-3">
                💡 Usa il pulsante <b>Catasto</b> (nel tab Anagrafica) per importare automaticamente gli immobili reali dell'azienda. Gli immobili con indirizzo/comune vengono mostrati sulla mappa. Puoi anche inserire manualmente unità <b>prese in affitto</b> (Titolo → "In affitto").
            </div>

            <ImmobiliMap immobili={showMap ? immobili : []} />

            {immobili.length === 0 ? (
                <div className="text-center text-slate-400 text-sm py-4">Nessun immobile. Importa dal Catasto o aggiungi manualmente.</div>
            ) : (
                immobili.map((im, i) => (
                    <ImmobileRow key={i} item={im} canEdit={canEdit}
                        onChange={(patch) => update(i, patch)} onRemove={() => remove(i)} />
                ))
            )}
        </Card>
    );
}
