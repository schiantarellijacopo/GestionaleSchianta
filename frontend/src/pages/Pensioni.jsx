import { useState, useRef } from "react";
import { api, fmtEur } from "@/lib/api";
import { PageHeader } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Calculator, FileUp, Info } from "lucide-react";
import { toast } from "sonner";

export default function Pensioni() {
    const [tipo, setTipo] = useState("invalidita");
    const [form, setForm] = useState({
        settimane: 1500,
        retribuzione: 25000,
        eta: 45,
        invalidita: 75,
        familiari: 1,
    });
    const [risultato, setRisultato] = useState(null);
    const fileRef = useRef(null);
    const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

    const calcola = async () => {
        try {
            const res = await api.post("/pensioni/calcola", {
                tipo_pensione: tipo,
                settimane_contributive: parseInt(form.settimane) || 0,
                retribuzione_media_annua: parseFloat(form.retribuzione) || 0,
                eta: parseInt(form.eta) || 0,
                percentuale_invalidita: parseFloat(form.invalidita) || 0,
                numero_familiari: parseInt(form.familiari) || 0,
            });
            setRisultato(res.data);
            toast.success("Calcolo completato");
        } catch (e) { toast.error("Errore: " + e.message); }
    };

    const parseFile = async (file) => {
        if (!file) return;
        const fd = new FormData();
        fd.append("file", file);
        try {
            const res = await api.post("/pensioni/parse-estratto", fd, {
                headers: { "Content-Type": "multipart/form-data" },
            });
            if (res.data.settimane_contributive) {
                set("settimane", res.data.settimane_contributive);
                toast.success(`Letti: ${res.data.settimane_contributive} settimane, retribuzione €${res.data.retribuzione_media_annua}`);
            }
            if (res.data.retribuzione_media_annua) {
                set("retribuzione", res.data.retribuzione_media_annua);
            }
            if (res.data.warning) toast.message(res.data.warning);
        } catch (e) { toast.error("Errore parsing: " + e.message); }
    };

    return (
        <div data-testid="pensioni-page">
            <PageHeader
                title="Calcolo pensioni INPS"
                subtitle="Stima pensione di invalidità, inabilità e ai superstiti"
            />

            <Card className="p-4 border-amber-200 bg-amber-50 mb-6 flex gap-3 items-start" data-testid="pensioni-info">
                <Info size={16} className="text-amber-600 mt-0.5 shrink-0" />
                <div className="text-xs text-amber-800">
                    {"Le stime sono indicative basate sui parametri INPS 2025/2026 (calcolo contributivo + coefficienti di trasformazione). Non sostituiscono il calcolo ufficiale INPS. Carica l'estratto conto contributivo INPS in formato PDF, TXT o CSV per pre-compilare automaticamente settimane e retribuzione."}
                </div>
            </Card>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <Card className="p-6 border-slate-200">
                    <div className="flex items-center gap-2 mb-4">
                        <Calculator size={18} className="text-sky-700" />
                        <h3 className="font-medium text-slate-900">Parametri di calcolo</h3>
                    </div>

                    <div className="space-y-4">
                        <div>
                            <Label>Tipo pensione</Label>
                            <Select value={tipo} onValueChange={setTipo}>
                                <SelectTrigger data-testid="pens-tipo-select"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="invalidita">Invalidità (assegno ordinario)</SelectItem>
                                    <SelectItem value="inabilita">Inabilità</SelectItem>
                                    <SelectItem value="superstite">Superstiti (reversibilità)</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>

                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <Label>Settimane contributive</Label>
                                <Input data-testid="pens-settimane-input" type="number" value={form.settimane} onChange={(e) => set("settimane", e.target.value)} />
                            </div>
                            <div>
                                <Label>Retribuzione media annua €</Label>
                                <Input data-testid="pens-retrib-input" type="number" step="100" value={form.retribuzione} onChange={(e) => set("retribuzione", e.target.value)} />
                            </div>
                            <div>
                                <Label>Età (anni)</Label>
                                <Input data-testid="pens-eta-input" type="number" value={form.eta} onChange={(e) => set("eta", e.target.value)} />
                            </div>
                            {tipo === "invalidita" && (
                                <div>
                                    <Label>% Invalidità riconosciuta</Label>
                                    <Input type="number" value={form.invalidita} onChange={(e) => set("invalidita", e.target.value)} />
                                </div>
                            )}
                            {tipo === "superstite" && (
                                <div>
                                    <Label>Familiari aventi diritto</Label>
                                    <Input type="number" value={form.familiari} onChange={(e) => set("familiari", e.target.value)} />
                                </div>
                            )}
                        </div>

                        <div className="pt-2 border-t border-slate-100 flex items-center gap-3">
                            <input ref={fileRef} type="file" accept=".pdf,.txt,.csv" className="hidden" onChange={(e) => parseFile(e.target.files?.[0])} />
                            <Button variant="outline" onClick={() => fileRef.current?.click()} data-testid="pens-import-button">
                                <FileUp size={14} className="mr-1" /> Carica estratto INPS
                            </Button>
                            <Button onClick={calcola} data-testid="pens-calcola-button" className="bg-sky-700 hover:bg-sky-800 ml-auto">
                                <Calculator size={14} className="mr-1" /> Calcola pensione
                            </Button>
                        </div>
                    </div>
                </Card>

                <Card className="p-6 border-slate-200 bg-slate-900 text-slate-100" data-testid="pens-risultato">
                    <h3 className="font-medium mb-1 text-sky-300">Risultato stima</h3>
                    {!risultato ? (
                        <div className="text-slate-400 text-sm py-12 text-center">
                            {`Compila i parametri e clicca "Calcola pensione"`}
                        </div>
                    ) : (
                        <div>
                            <div className="text-xs uppercase tracking-widest text-slate-400 mt-4">Pensione mensile lorda</div>
                            <div className="text-5xl font-semibold tracking-tight num mt-1">{fmtEur(risultato.pensione_lorda_mensile)}</div>

                            <div className="grid grid-cols-2 gap-4 mt-6 pt-6 border-t border-slate-700">
                                <div>
                                    <div className="text-xs uppercase tracking-widest text-slate-400">Annua lorda</div>
                                    <div className="text-xl num">{fmtEur(risultato.pensione_lorda_annua)}</div>
                                </div>
                                <div>
                                    <div className="text-xs uppercase tracking-widest text-slate-400">Netta stimata</div>
                                    <div className="text-xl num">{fmtEur(risultato.pensione_netta_stimata)}</div>
                                </div>
                                <div className="col-span-2">
                                    <div className="text-xs uppercase tracking-widest text-slate-400">Metodologia</div>
                                    <div className="text-sm">{risultato.metodologia}</div>
                                </div>
                            </div>

                            <div className="mt-6 pt-6 border-t border-slate-700 text-xs space-y-1">
                                <div><span className="text-slate-400">Anni contributivi:</span> <span className="num">{risultato.dettaglio?.anni_contributivi}</span></div>
                                <div><span className="text-slate-400">Montante:</span> <span className="num">{fmtEur(risultato.dettaglio?.montante_contributivo)}</span></div>
                                <div><span className="text-slate-400">Coefficiente trasformazione:</span> <span className="num">{(risultato.coefficiente_applicato * 100).toFixed(3)}%</span></div>
                                {risultato.dettaglio?.note?.map((n, i) => (
                                    <div key={i} className="text-amber-300 text-xs">⚠ {n}</div>
                                ))}
                            </div>
                        </div>
                    )}
                </Card>
            </div>
        </div>
    );
}
