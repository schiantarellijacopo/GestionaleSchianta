/**
 * Setup Iniziale — wizard prima volta: saldi banche, saldi compagnie,
 * sospesi manuali, voci pregresse facoltative. Solo admin.
 */
import { useEffect, useState } from "react";
import { api, fmtEur } from "@/lib/api";
import { PageHeader, Loading } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Plus, Trash2, AlertCircle, CheckCircle2, RotateCcw, Building2, Coins, Banknote, FileWarning } from "lucide-react";
import { toast } from "sonner";

export default function SetupIniziale() {
    const [stato, setStato] = useState(null);
    const [banche, setBanche] = useState([]);
    const [compagnie, setCompagnie] = useState([]);
    const [conti, setConti] = useState([]);
    const [saldiBanca, setSaldiBanca] = useState([]);
    const [saldiComp, setSaldiComp] = useState([]);
    const [sospesi, setSospesi] = useState([]);
    const [vociPregresse, setVociPregresse] = useState([]);
    const [note, setNote] = useState("");

    const dataDefault = new Date().toISOString().slice(0, 10);
    const dataIniziale = new Date(Date.now() - 86400000).toISOString().slice(0, 10);

    const load = () => {
        api.get("/setup-iniziale/stato").then((r) => setStato(r.data));
        api.get("/librerie/conti-cassa?attivi=true").then((r) => setConti(r.data));
        api.get("/compagnie").then((r) => setCompagnie(r.data));
    };
    useEffect(() => { load(); }, []);

    const submit = async () => {
        if (saldiBanca.length === 0 && saldiComp.length === 0 && sospesi.length === 0 && vociPregresse.length === 0) {
            toast.error("Aggiungi almeno una voce"); return;
        }
        try {
            const r = await api.post("/setup-iniziale", {
                saldi_banche: saldiBanca, saldi_compagnie: saldiComp,
                sospesi, voci_pregresse: vociPregresse, note,
            });
            toast.success("Setup iniziale completato"); load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const reset = async () => {
        if (!window.confirm("ATTENZIONE: il reset elimina TUTTI i movimenti del setup iniziale. Continuare?")) return;
        try {
            await api.post("/setup-iniziale/reset");
            toast.success("Setup resettato"); load();
            setSaldiBanca([]); setSaldiComp([]); setSospesi([]); setVociPregresse([]); setNote("");
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    if (!stato) return <Loading />;

    if (stato.completato) {
        return (
            <div data-testid="setup-iniziale-page" className="space-y-5">
                <PageHeader title="Setup iniziale" subtitle="Configurazione contabile iniziale dell&rsquo;agenzia" />
                <Card className="p-6 border-l-4 border-emerald-500 bg-emerald-50/30">
                    <div className="flex items-center gap-3 mb-4">
                        <CheckCircle2 size={32} className="text-emerald-600" />
                        <div>
                            <h2 className="text-lg font-bold text-emerald-900">Setup iniziale completato</h2>
                            <p className="text-xs text-slate-600">
                                Eseguito il {new Date(stato.completato_at).toLocaleString("it-IT")}
                            </p>
                        </div>
                    </div>
                    <div className="grid grid-cols-4 gap-3 text-sm">
                        <KStat label="Banche" v={stato.n_banche} />
                        <KStat label="Compagnie" v={stato.n_compagnie} />
                        <KStat label="Sospesi" v={stato.n_sospesi} />
                        <KStat label="Voci pregresse" v={stato.n_voci_pregresse} />
                    </div>
                    {stato.note && <div className="mt-4 text-xs text-slate-600 italic">"{stato.note}"</div>}
                    <Button variant="outline" onClick={reset} className="mt-4 text-rose-700 border-rose-300"
                        data-testid="setup-reset">
                        <RotateCcw size={14} className="mr-1" /> Reset setup
                    </Button>
                </Card>
            </div>
        );
    }

    return (
        <div data-testid="setup-iniziale-page" className="space-y-5">
            <PageHeader title="Setup iniziale" subtitle="Configurazione contabile iniziale dell&rsquo;agenzia" />

            <Card className="p-4 border-l-4 border-amber-400 bg-amber-50/20">
                <div className="flex items-start gap-2">
                    <AlertCircle size={20} className="text-amber-600 mt-0.5" />
                    <div className="text-sm text-slate-700">
                        <strong>Setup iniziale.</strong> Inserisci i saldi di partenza al momento dell'attivazione del programma.
                        Verranno creati movimenti contabili di apertura (categoria <code className="bg-amber-100 px-1 rounded text-[10px]">setup_iniziale_*</code>),
                        che NON possono essere modificati una volta confermato il setup (solo reset).
                    </div>
                </div>
            </Card>

            {/* SALDI BANCHE */}
            <SectionEditor title="Saldi iniziali conti bancari" icon={Banknote} color="indigo"
                rows={saldiBanca}
                addRow={() => setSaldiBanca((p) => [...p, { conto_id: conti[0]?.id || "", saldo: 0, data: dataIniziale }])}
                delRow={(i) => setSaldiBanca((p) => p.filter((_, x) => x !== i))}
                renderRow={(r, i) => (
                    <>
                        <Select value={r.conto_id} onValueChange={(v) => setSaldiBanca((p) => p.map((x, j) => j === i ? { ...x, conto_id: v } : x))}>
                            <SelectTrigger className="col-span-3"><SelectValue placeholder="Conto" /></SelectTrigger>
                            <SelectContent>
                                {conti.map((c) => <SelectItem key={c.id} value={c.id}>{c.nome}</SelectItem>)}
                            </SelectContent>
                        </Select>
                        <Input type="number" step="0.01" value={r.saldo} placeholder="Saldo €" className="col-span-2"
                            onChange={(e) => setSaldiBanca((p) => p.map((x, j) => j === i ? { ...x, saldo: parseFloat(e.target.value) || 0 } : x))} />
                        <Input type="date" value={r.data}
                            onChange={(e) => setSaldiBanca((p) => p.map((x, j) => j === i ? { ...x, data: e.target.value } : x))} />
                    </>
                )}
                gridCols="col-span-7"
            />

            {/* SALDI COMPAGNIE */}
            <SectionEditor title="Saldi iniziali compagnie (DARE / AVERE)" icon={Building2} color="sky"
                rows={saldiComp}
                addRow={() => setSaldiComp((p) => [...p, { compagnia_id: compagnie[0]?.id || "", saldo_dare: 0, saldo_avere: 0, data: dataIniziale, descrizione: "" }])}
                delRow={(i) => setSaldiComp((p) => p.filter((_, x) => x !== i))}
                renderRow={(r, i) => (
                    <>
                        <Select value={r.compagnia_id} onValueChange={(v) => setSaldiComp((p) => p.map((x, j) => j === i ? { ...x, compagnia_id: v } : x))}>
                            <SelectTrigger className="col-span-3"><SelectValue placeholder="Compagnia" /></SelectTrigger>
                            <SelectContent>
                                {compagnie.map((c) => <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}</SelectItem>)}
                            </SelectContent>
                        </Select>
                        <Input type="number" step="0.01" value={r.saldo_dare} placeholder="Dare €"
                            onChange={(e) => setSaldiComp((p) => p.map((x, j) => j === i ? { ...x, saldo_dare: parseFloat(e.target.value) || 0 } : x))} />
                        <Input type="number" step="0.01" value={r.saldo_avere} placeholder="Avere €"
                            onChange={(e) => setSaldiComp((p) => p.map((x, j) => j === i ? { ...x, saldo_avere: parseFloat(e.target.value) || 0 } : x))} />
                        <Input type="date" value={r.data}
                            onChange={(e) => setSaldiComp((p) => p.map((x, j) => j === i ? { ...x, data: e.target.value } : x))} />
                    </>
                )}
                gridCols="col-span-7"
            />

            {/* SOSPESI */}
            <SectionEditor title="Sospesi manuali iniziali (facoltativo)" icon={FileWarning} color="amber"
                rows={sospesi}
                addRow={() => setSospesi((p) => [...p, { importo: 0, descrizione: "", data: dataIniziale, anagrafica_id: null }])}
                delRow={(i) => setSospesi((p) => p.filter((_, x) => x !== i))}
                renderRow={(r, i) => (
                    <>
                        <Input value={r.descrizione} placeholder="Descrizione sospeso" className="col-span-3"
                            onChange={(e) => setSospesi((p) => p.map((x, j) => j === i ? { ...x, descrizione: e.target.value } : x))} />
                        <Input type="number" step="0.01" value={r.importo} placeholder="Importo €"
                            onChange={(e) => setSospesi((p) => p.map((x, j) => j === i ? { ...x, importo: parseFloat(e.target.value) || 0 } : x))} />
                        <Input type="date" value={r.data}
                            onChange={(e) => setSospesi((p) => p.map((x, j) => j === i ? { ...x, data: e.target.value } : x))} />
                    </>
                )}
                gridCols="col-span-6"
            />

            {/* VOCI PREGRESSE */}
            <SectionEditor title="Voci pregresse facoltative" icon={Coins} color="violet"
                description="Provvigioni, spese, rimesse, entrate già esistenti prima del setup"
                rows={vociPregresse}
                addRow={() => setVociPregresse((p) => [...p, { tipo: "provvigione", importo: 0, data: dataIniziale, descrizione: "", compagnia_id: null }])}
                delRow={(i) => setVociPregresse((p) => p.filter((_, x) => x !== i))}
                renderRow={(r, i) => (
                    <>
                        <Select value={r.tipo} onValueChange={(v) => setVociPregresse((p) => p.map((x, j) => j === i ? { ...x, tipo: v } : x))}>
                            <SelectTrigger className="col-span-2"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="provvigione">Provvigione</SelectItem>
                                <SelectItem value="entrata">Entrata</SelectItem>
                                <SelectItem value="rimessa">Rimessa fatta</SelectItem>
                                <SelectItem value="spesa">Spesa</SelectItem>
                            </SelectContent>
                        </Select>
                        <Input value={r.descrizione} placeholder="Descrizione" className="col-span-2"
                            onChange={(e) => setVociPregresse((p) => p.map((x, j) => j === i ? { ...x, descrizione: e.target.value } : x))} />
                        <Input type="number" step="0.01" value={r.importo} placeholder="Importo €"
                            onChange={(e) => setVociPregresse((p) => p.map((x, j) => j === i ? { ...x, importo: parseFloat(e.target.value) || 0 } : x))} />
                        <Input type="date" value={r.data}
                            onChange={(e) => setVociPregresse((p) => p.map((x, j) => j === i ? { ...x, data: e.target.value } : x))} />
                    </>
                )}
                gridCols="col-span-7"
            />

            <Card className="p-4">
                <Label>Note di setup</Label>
                <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)}
                    placeholder="Annotazioni sul setup iniziale" />
            </Card>

            <div className="flex justify-end gap-2 sticky bottom-0 bg-white border-t border-slate-200 py-3 -mx-6 px-6">
                <Button onClick={submit} className="bg-emerald-700 hover:bg-emerald-800" data-testid="setup-submit">
                    <CheckCircle2 size={14} className="mr-1" /> Conferma setup iniziale
                </Button>
            </div>
        </div>
    );
}

const KStat = ({ label, v }) => (
    <div className="bg-white border border-emerald-200 rounded p-2 text-center">
        <div className="text-2xl font-bold text-emerald-700 font-mono">{v || 0}</div>
        <div className="text-[10px] uppercase text-slate-500">{label}</div>
    </div>
);

function SectionEditor({ title, icon: Ic, color = "sky", description, rows, addRow, delRow, renderRow, gridCols }) {
    return (
        <Card className="p-4">
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                    <Ic size={18} className={`text-${color}-600`} />
                    <div>
                        <h2 className="font-semibold text-slate-800">{title}</h2>
                        {description && <p className="text-xs text-slate-500">{description}</p>}
                    </div>
                </div>
                <Button size="sm" variant="outline" onClick={addRow}>
                    <Plus size={12} className="mr-1" /> Riga
                </Button>
            </div>
            {rows.length === 0 ? (
                <div className="text-sm text-slate-400 text-center py-3">Nessuna voce — premi &quot;Riga&quot; per aggiungere</div>
            ) : (
                <div className="space-y-2">
                    {rows.map((r, i) => (
                        <div key={i} className={`grid grid-cols-8 gap-2 items-end`}>
                            <div className={gridCols + " grid grid-cols-subgrid col-span-7 gap-2"}>
                                {renderRow(r, i)}
                            </div>
                            <button onClick={() => delRow(i)} className="text-rose-600 hover:bg-rose-50 p-1.5 rounded col-span-1 justify-self-end">
                                <Trash2 size={14} />
                            </button>
                        </div>
                    ))}
                </div>
            )}
        </Card>
    );
}
