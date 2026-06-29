/**
 * PotentiDomandeTab — 30 "potenti domande" dal PDF "Le potenti domande
 * del primo appuntamento" per profilare il cliente.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Save, MessageCircleQuestion } from "lucide-react";
import { toast } from "sonner";

const DOMANDE = [
    "Com'è composta la tua famiglia?",
    "Ah, quanto tempo fa ti sei sposato?",
    "Cosa fa tua moglie, il tuo compagno, tuo marito?",
    "I tuoi figli quanti anni hanno?",
    "Quali sono le attività che fanno i figli?",
    "Quanto è difficile allevare oggi i figli?",
    "Con il Coronavirus come avete gestito la situazione?",
    "Quanto difficile è allevare oggi una famiglia rispetto a un tempo?",
    "Quante complicanze ci sono?",
    "Quanto grandi gli impegni lavorativi?",
    "Di cosa ti occupi di preciso?",
    "Da quanto tempo è che fai questo tipo di attività?",
    "Cosa diresti sia cambiato rispetto a quando hai iniziato?",
    "Hai sempre fatto questo lavoro?",
    "Lavorativamente parlando, come vedi il futuro?",
    "Possiede degli immobili e/o dei terreni?",
    "Hai veicoli a motore?",
    "Quanti veicoli a motore avete in famiglia?",
    "A chi sono intestati?",
    "Hai delle quote di aziende?",
    "La liquidità rispetto ai debiti, come siamo?",
    "Com'è nata la tua azienda?",
    "Cosa ti ha spinto a fondarla o cosa ha spinto il babbo a fondarla quando lo ha fatto?",
    "Cosa è cambiato rispetto ad allora?",
    "Se potessi ripartire da capo, cosa cambieresti?",
    "Perché i clienti acquistano da te?",
    "Come vedi il futuro?",
    "Fai qualche attività nel tempo libero?",
    "Che può essere viaggi, animali, sport, volontariato, collezionismo?",
    "Quali sono le tue priorità?",
];

export default function PotentiDomandeTab({ anagrafica_id, canEdit }) {
    const [risposte, setRisposte] = useState({});
    const [aggiornatoIl, setAggiornatoIl] = useState(null);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        api.get(`/anagrafiche/${anagrafica_id}`).then((r) => {
            const map = {};
            for (const x of (r.data.potenti_domande_risposte || [])) {
                map[x.domanda_id] = x.risposta;
            }
            setRisposte(map);
            setAggiornatoIl(r.data.potenti_domande_aggiornate_il);
        });
    }, [anagrafica_id]);

    const save = async () => {
        setSaving(true);
        try {
            const arr = DOMANDE.map((d, i) => ({
                domanda_id: i + 1, domanda: d, risposta: risposte[i + 1] || "",
            })).filter((x) => x.risposta.trim());
            const r = await api.put(`/anagrafiche/${anagrafica_id}/potenti-domande`, { risposte: arr });
            toast.success(`Salvate ${r.data.n_risposte} risposte`);
            setAggiornatoIl(r.data.aggiornato_il);
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        finally { setSaving(false); }
    };

    const compilate = Object.values(risposte).filter((r) => r?.trim()).length;

    return (
        <div className="space-y-3 mt-4" data-testid="potenti-domande-tab">
            <Card className="p-3 bg-violet-50 border-violet-200 flex items-center justify-between">
                <div className="text-xs">
                    <strong className="text-violet-800">Le 30 Potenti Domande</strong> · primo appuntamento ·
                    <span className="ml-2 font-mono text-violet-700">{compilate}/30 compilate</span>
                    {aggiornatoIl && <span className="text-slate-600 ml-2">· Aggiornato il {new Date(aggiornatoIl).toLocaleDateString("it-IT")}</span>}
                </div>
                {canEdit && (
                    <Button size="sm" onClick={save} disabled={saving} className="bg-violet-700 hover:bg-violet-800" data-testid="pd-save-top">
                        <Save size={13} className="mr-1" /> {saving ? "Salvataggio…" : "Salva"}
                    </Button>
                )}
            </Card>

            <div className="space-y-2">
                {DOMANDE.map((d, idx) => {
                    const id = idx + 1;
                    const val = risposte[id] || "";
                    return (
                        <Card key={id} className={`p-3 border-l-4 ${val.trim() ? "border-emerald-400 bg-emerald-50/30" : "border-slate-200"}`}
                            data-testid={`pd-domanda-${id}`}>
                            <div className="flex items-start gap-2">
                                <span className="text-violet-600 font-mono text-xs font-bold mt-1.5">#{id}</span>
                                <div className="flex-1">
                                    <div className="text-sm font-medium text-slate-800 flex items-center gap-2">
                                        <MessageCircleQuestion size={13} className="text-violet-500 shrink-0" />
                                        {d}
                                    </div>
                                    <Textarea rows={2} className="mt-1.5 text-sm" placeholder="Risposta del cliente…"
                                        value={val} onChange={(e) => setRisposte((p) => ({ ...p, [id]: e.target.value }))}
                                        disabled={!canEdit} data-testid={`pd-r-${id}`} />
                                </div>
                            </div>
                        </Card>
                    );
                })}
            </div>

            {canEdit && (
                <div className="flex justify-end sticky bottom-2">
                    <Button onClick={save} disabled={saving} className="bg-violet-700 hover:bg-violet-800 shadow-lg" data-testid="pd-save-bottom">
                        <Save size={14} className="mr-1" /> {saving ? "Salvataggio…" : "Salva risposte"}
                    </Button>
                </div>
            )}
        </div>
    );
}
