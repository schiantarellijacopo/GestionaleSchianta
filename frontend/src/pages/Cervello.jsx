/**
 * Cervello — Controllo di gestione economico-finanziario dell'agenzia.
 *
 * Tabs:
 *   - Conto Economico: P&L per comparto (Auto/Persone/Aziende/Vita)
 *   - Top Clienti: classifica Pareto 80/20
 *   - Segmentazione: clienti mono/multi-comparto + churn
 *   - Costi & Bilancio: editor costi annuali + upload bilancio
 */
import { useEffect, useState } from "react";
import { api, fmtEur } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PageHeader, Loading } from "@/components/Shared";
import { Brain, Save, Upload, TrendingUp, Trophy, PieChart, Wallet, Users, Sparkles } from "lucide-react";
import { toast } from "sonner";

const COMP_COLOR = { auto: "sky", persone: "emerald", aziende: "amber", vita: "violet" };

export default function Cervello() {
    const currentYear = new Date().getFullYear();
    const [anno, setAnno] = useState(currentYear);
    return (
        <div data-testid="cervello-page" className="space-y-3">
            <PageHeader
                title={<span className="flex items-center gap-2"><Brain className="text-violet-600" /> Il Cervello</span>}
                subtitle="Controllo di gestione · P&L per comparto · Top clienti (Pareto) · Costi e bilancio"
                actions={
                    <Select value={String(anno)} onValueChange={(v) => setAnno(parseInt(v))}>
                        <SelectTrigger className="w-32" data-testid="cerv-anno"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            {[0, -1, -2, -3, -4].map((d) => {
                                const y = currentYear + d;
                                return <SelectItem key={y} value={String(y)}>{y}</SelectItem>;
                            })}
                        </SelectContent>
                    </Select>
                }
            />
            <Tabs defaultValue="pl">
                <TabsList>
                    <TabsTrigger value="pl" data-testid="tab-pl"><TrendingUp size={14} className="mr-1" /> Conto Economico</TabsTrigger>
                    <TabsTrigger value="top" data-testid="tab-top"><Trophy size={14} className="mr-1" /> Top Clienti</TabsTrigger>
                    <TabsTrigger value="seg" data-testid="tab-seg"><PieChart size={14} className="mr-1" /> Segmentazione</TabsTrigger>
                    <TabsTrigger value="costi" data-testid="tab-costi"><Wallet size={14} className="mr-1" /> Costi & Bilancio</TabsTrigger>
                </TabsList>
                <TabsContent value="pl"><ContoEconomicoTab anno={anno} /></TabsContent>
                <TabsContent value="top"><TopClientiTab anno={anno} /></TabsContent>
                <TabsContent value="seg"><SegmentazioneTab /></TabsContent>
                <TabsContent value="costi"><CostiBilancioTab anno={anno} /></TabsContent>
            </Tabs>
        </div>
    );
}

function ContoEconomicoTab({ anno }) {
    const [data, setData] = useState(null);
    useEffect(() => {
        api.get("/cervello/analisi-pl", { params: { anno } }).then((r) => setData(r.data));
    }, [anno]);
    if (!data) return <Loading />;
    return (
        <div className="space-y-4 pt-3">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <KCard label="Polizze totali" value={data.totale_polizze} color="sky" />
                <KCard label="Provvigioni totali" value={fmtEur(data.totale_provvigioni)} color="emerald" mono />
                <KCard label="Costi totali" value={fmtEur(data.totale_costi)} color="amber" mono />
                <KCard label="Utile netto agenzia"
                    value={fmtEur(data.utile_netto_agenzia)}
                    color={data.utile_netto_agenzia >= 0 ? "emerald" : "rose"} mono />
            </div>
            <Card className="p-3">
                <h3 className="font-semibold text-slate-800 mb-3">P&L per Comparto</h3>
                <table className="w-full text-xs">
                    <thead><tr className="text-left border-b text-slate-500">
                        <th className="py-2">Comparto</th>
                        <th className="text-right">Polizze</th>
                        <th className="text-right">% pezzi</th>
                        <th className="text-right">Premi €</th>
                        <th className="text-right">Provvigioni €</th>
                        <th className="text-right">% provv.</th>
                        <th className="text-right">Resa/pezzo</th>
                        <th className="text-right">Costi rip.</th>
                        <th className="text-right">Utile netto</th>
                        <th className="text-right">Utile/pezzo</th>
                    </tr></thead>
                    <tbody>
                        {data.comparti.map((c) => (
                            <tr key={c.comparto} className="border-b border-slate-100 hover:bg-slate-50">
                                <td className="py-1.5 font-semibold">
                                    <span className={`inline-block w-2 h-2 rounded-full mr-1.5 bg-${COMP_COLOR[c.comparto]}-500`} />
                                    {c.comparto_label}
                                </td>
                                <td className="text-right">{c.n_polizze}</td>
                                <td className="text-right text-slate-500">{c.incidenza_pezzi_pct}%</td>
                                <td className="text-right font-mono">{fmtEur(c.premi_totali)}</td>
                                <td className="text-right font-mono font-semibold">{fmtEur(c.provvigioni_totali)}</td>
                                <td className="text-right text-slate-500">{c.incidenza_provv_pct}%</td>
                                <td className="text-right font-mono">{fmtEur(c.resa_media_pezzo)}</td>
                                <td className="text-right font-mono text-rose-700">{fmtEur(c.costi_ripartiti)}</td>
                                <td className={`text-right font-mono font-bold ${c.utile_netto >= 0 ? "text-emerald-700" : "text-rose-700"}`}>{fmtEur(c.utile_netto)}</td>
                                <td className={`text-right font-mono ${c.utile_pezzo >= 0 ? "text-emerald-700" : "text-rose-700"}`}>{fmtEur(c.utile_pezzo)}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </Card>
        </div>
    );
}

function TopClientiTab({ anno }) {
    const [data, setData] = useState(null);
    useEffect(() => {
        api.get("/cervello/top-clienti", { params: { anno, limit: 100 } }).then((r) => setData(r.data));
    }, [anno]);
    if (!data) return <Loading />;
    return (
        <div className="space-y-4 pt-3">
            <Card className="p-3 bg-violet-50/40 border-violet-200">
                <div className="flex items-center gap-3 text-sm">
                    <Trophy className="text-violet-600" />
                    <div>
                        <div className="font-semibold">Pareto 80/20</div>
                        <div className="text-xs text-slate-600">
                            I primi <b>{data.pareto_80_idx}</b> clienti generano l&apos;80% delle provvigioni (totale: {fmtEur(data.totale_provvigioni)} su {data.n_clienti_top} clienti)
                        </div>
                    </div>
                </div>
            </Card>
            <Card className="p-2">
                <table className="w-full text-xs">
                    <thead><tr className="text-left border-b text-slate-500">
                        <th className="py-2 w-10">#</th>
                        <th>Cliente</th><th>Tipo</th>
                        <th className="text-right">Polizze attive</th>
                        <th className="text-right">Provvigioni</th>
                        <th className="text-right">% sul totale</th>
                        <th className="text-right">% cumulata</th>
                    </tr></thead>
                    <tbody>
                        {data.items.map((r, i) => (
                            <tr key={r.anagrafica_id} className={`border-b border-slate-100 ${i < data.pareto_80_idx ? "bg-amber-50/40 font-medium" : ""}`}>
                                <td className="py-1.5 font-mono">{r.rank}</td>
                                <td>{r.nome}</td>
                                <td className="text-xs text-slate-500">{r.tipo === "persona_giuridica" ? "Azienda" : "Privato"}</td>
                                <td className="text-right">{r.n_polizze_attive}</td>
                                <td className="text-right font-mono font-semibold">{fmtEur(r.provvigioni_anno)}</td>
                                <td className="text-right text-slate-500">{r.incidenza_pct}%</td>
                                <td className="text-right text-slate-500">{r.incidenza_cumulata_pct}%</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </Card>
        </div>
    );
}

function SegmentazioneTab() {
    const [data, setData] = useState(null);
    useEffect(() => { api.get("/cervello/segmentazione").then((r) => setData(r.data)); }, []);
    if (!data) return <Loading />;
    const b = data.breakdown;
    return (
        <div className="space-y-4 pt-3">
            <Card className="p-4 bg-emerald-50/40 border-emerald-200">
                <div className="flex items-center gap-3">
                    <Users className="text-emerald-600" size={24} />
                    <div>
                        <div className="text-3xl font-bold text-slate-800">{data.tasso_multi_comparto_pct}%</div>
                        <div className="text-xs text-slate-600">
                            Tasso di multi-comparto · <b>{data.totale_clienti_con_polizze}</b> clienti con polizze attive
                        </div>
                    </div>
                </div>
                <div className="text-xs text-slate-500 mt-2">
                    Più comparti = più fidelizzazione. Target ideale: &gt;25% multi-comparto.
                </div>
            </Card>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <SegCard label="Mono Auto" value={b.mono_auto} hint="Massimo rischio churn" color="rose" />
                <SegCard label="Mono Persone" value={b.mono_persone} hint="Cross-selling target" color="amber" />
                <SegCard label="Mono Aziende" value={b.mono_aziende} hint="Up-selling target" color="indigo" />
                <SegCard label="Mono Vita" value={b.mono_vita} hint="Solo Vita: cross-sell" color="violet" />
                <SegCard label="2 Comparti" value={b.due_comparti} hint="Fidelizzati" color="sky" />
                <SegCard label="3 Comparti" value={b.tre_comparti} hint="Molto fidelizzati" color="emerald" />
                <SegCard label="4 Comparti" value={b.quattro_comparti} hint="Top fidelizzazione" color="emerald" />
            </div>
        </div>
    );
}

function CostiBilancioTab({ anno }) {
    const [costi, setCosti] = useState(null);
    const [saving, setSaving] = useState(false);
    const [uploading, setUploading] = useState(false);

    const load = () => api.get(`/cervello/costi/${anno}`).then((r) => setCosti(r.data));
    useEffect(() => { load(); }, [anno]);
    if (!costi) return <Loading />;

    const setRip = (k, v) => setCosti({ ...costi, ripartizione: { ...costi.ripartizione, [k]: parseFloat(v) || 0 } });
    const set = (k, v) => setCosti({ ...costi, [k]: parseFloat(v) || 0 });

    const save = async () => {
        const totRip = Object.values(costi.ripartizione || {}).reduce((s, v) => s + (v || 0), 0);
        if (Math.abs(totRip - 100) > 0.5) { toast.error(`Ripartizione % deve sommare a 100 (attuale: ${totRip.toFixed(1)})`); return; }
        setSaving(true);
        try {
            await api.put(`/cervello/costi/${anno}`, costi);
            toast.success(`Costi ${anno} salvati`); load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        setSaving(false);
    };

    const upload = async (e) => {
        const f = e.target.files?.[0]; if (!f) return;
        setUploading(true);
        const fd = new FormData(); fd.append("file", f);
        try {
            const r = await api.post(`/cervello/bilancio/upload?anno=${anno}`, fd,
                { headers: { "Content-Type": "multipart/form-data" } });
            toast.success(`Bilancio caricato: ${r.data.voci_lette} voci`); load();
        } catch (err) { toast.error(err.response?.data?.detail || "Errore upload"); }
        finally { setUploading(false); e.target.value = ""; }
    };

    const totale = (costi.costi_struttura || 0) + (costi.stipendi_fissi || 0)
                 + (costi.spese_marketing || 0) + (costi.spese_amministrative || 0)
                 + (costi.altri_costi || 0);

    return (
        <div className="space-y-4 pt-3">
            <Card className="p-4">
                <h3 className="font-semibold text-slate-800 mb-3">Voci di costo {anno}</h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                    <Campo label="Costi struttura (affitti/utenze)" value={costi.costi_struttura}
                        onChange={(v) => set("costi_struttura", v)} testid="costi-struttura" />
                    <Campo label="Stipendi fissi" value={costi.stipendi_fissi} onChange={(v) => set("stipendi_fissi", v)} />
                    <Campo label="Spese marketing" value={costi.spese_marketing} onChange={(v) => set("spese_marketing", v)} />
                    <Campo label="Spese amministrative" value={costi.spese_amministrative} onChange={(v) => set("spese_amministrative", v)} />
                    <Campo label="Altri costi" value={costi.altri_costi} onChange={(v) => set("altri_costi", v)} />
                    <div className="bg-slate-50 border border-slate-200 rounded p-2 flex flex-col justify-center">
                        <div className="text-[10px] uppercase tracking-wider text-slate-500">Totale costi annui</div>
                        <div className="text-2xl font-bold font-mono text-rose-700">{fmtEur(totale)}</div>
                    </div>
                </div>
            </Card>

            <Card className="p-4">
                <h3 className="font-semibold text-slate-800 mb-3">Ripartizione % costi sui comparti</h3>
                <div className="grid grid-cols-4 gap-3">
                    {["auto", "persone", "aziende", "vita"].map((c) => (
                        <div key={c}>
                            <Label className="text-xs capitalize">{c}</Label>
                            <div className="relative">
                                <Input type="number" step="0.1" value={costi.ripartizione?.[c] || 0}
                                    onChange={(e) => setRip(c, e.target.value)} data-testid={`rip-${c}`} />
                                <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-slate-400">%</span>
                            </div>
                        </div>
                    ))}
                </div>
                <div className="mt-3 text-xs text-slate-500">
                    Totale ripartizione: <b>{Object.values(costi.ripartizione || {}).reduce((s, v) => s + (v || 0), 0).toFixed(1)}%</b> (deve essere 100)
                </div>
            </Card>

            <div className="flex justify-between items-center flex-wrap gap-2">
                <div className="flex gap-2 flex-wrap">
                    <label className="inline-flex items-center gap-2 px-3 py-2 border border-sky-200 bg-sky-50 text-sky-700 rounded text-sm cursor-pointer hover:bg-sky-100" data-testid="bilancio-upload">
                        <Upload size={14} />
                        {uploading ? "Caricamento…" : "Carica bilancio (CSV/JSON)"}
                        <input type="file" hidden accept=".csv,.json,.txt" onChange={upload} />
                    </label>
                    <OcrBilancioButton anno={anno} onSaved={load} />
                </div>
                <Button onClick={save} disabled={saving} className="bg-violet-700 hover:bg-violet-800" data-testid="costi-save">
                    <Save size={14} className="mr-1" /> {saving ? "Salvataggio…" : "Salva costi"}
                </Button>
            </div>

            <div className="text-xs text-slate-500 bg-slate-50 border border-slate-200 rounded p-3">
                💡 Il file CSV può contenere voci come <code>affitto,12000</code> · <code>stipendi,80000</code>. Le voci verranno classificate automaticamente. <br />
                ✨ <b>OCR Bilancio Gemini</b>: carica un bilancio PDF/JPG → estrazione automatica costi, ricavi, utile + auto-popolamento dei costi annuali.
            </div>
        </div>
    );
}

function OcrBilancioButton({ anno, onSaved }) {
    const [busy, setBusy] = useState(false);
    const [risultato, setRisultato] = useState(null);
    const onPick = async (e) => {
        const f = e.target.files?.[0]; if (!f) return;
        setBusy(true);
        try {
            const fd = new FormData(); fd.append("file", f); fd.append("salva", "true");
            const r = await api.post("/cervello/ocr-bilancio", fd, {
                headers: { "Content-Type": "multipart/form-data" },
            });
            setRisultato(r.data);
            const anno_estratto = r.data.salvato_anno || r.data.dati_estratti?.anno;
            toast.success(`OCR completato · anno ${anno_estratto || "—"} · ${r.data.voci_create || 0} voci salvate`);
            if (onSaved) onSaved();
        } catch (err) { toast.error(err.response?.data?.detail || "Errore OCR"); }
        finally { setBusy(false); e.target.value = ""; }
    };
    return (
        <>
            <label className="inline-flex items-center gap-2 px-3 py-2 border border-violet-300 bg-violet-50 text-violet-700 rounded text-sm cursor-pointer hover:bg-violet-100"
                data-testid="cerv-ocr-bilancio">
                <Sparkles size={14} />
                {busy ? "Elaborazione AI…" : "OCR Bilancio (Gemini)"}
                <input type="file" hidden accept="application/pdf,image/*" onChange={onPick} />
            </label>
            {risultato?.dati_estratti && (
                <div className="text-[10px] text-emerald-700 mt-1">
                    ✓ Estratto: anno {risultato.dati_estratti.anno} · ricavi {risultato.dati_estratti.ricavi}€ · utile netto {risultato.dati_estratti.utile_netto}€
                </div>
            )}
        </>
    );
}

const COLOR_MAP = {
    sky: "border-sky-400 text-sky-700",
    emerald: "border-emerald-400 text-emerald-700",
    amber: "border-amber-400 text-amber-700",
    rose: "border-rose-400 text-rose-700",
    indigo: "border-indigo-400 text-indigo-700",
    violet: "border-violet-400 text-violet-700",
};
const KCard = ({ label, value, color, mono }) => (
    <Card className={`p-3 border-l-4 bg-white ${COLOR_MAP[color] || COLOR_MAP.sky}`}>
        <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
        <div className={`text-2xl font-bold mt-0.5 ${mono ? "font-mono" : ""}`}>{value ?? "—"}</div>
    </Card>
);
const SegCard = ({ label, value, hint, color }) => (
    <Card className={`p-3 border-l-4 bg-white ${COLOR_MAP[color] || COLOR_MAP.sky}`}>
        <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
        <div className="text-2xl font-bold mt-0.5">{value ?? "—"}</div>
        <div className="text-[10px] text-slate-500 italic">{hint}</div>
    </Card>
);
const Campo = ({ label, value, onChange, testid }) => (
    <div>
        <Label className="text-xs">{label}</Label>
        <Input type="number" step="0.01" value={value || 0} onChange={(e) => onChange(e.target.value)} data-testid={testid} />
    </div>
);
