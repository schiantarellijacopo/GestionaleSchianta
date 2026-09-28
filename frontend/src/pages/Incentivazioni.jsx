import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";
import { Award, RefreshCw, Save } from "lucide-react";

const fmtEur = (n) =>
    (Number(n) || 0).toLocaleString("it-IT", { style: "currency", currency: "EUR" });

// default: trimestre corrente
const quarter = () => {
    const d = new Date();
    const q = Math.floor(d.getMonth() / 3);
    const start = new Date(d.getFullYear(), q * 3, 1);
    const end = new Date(d.getFullYear(), q * 3 + 3, 0);
    const iso = (x) => x.toISOString().slice(0, 10);
    return [iso(start), iso(end)];
};

export default function Incentivazioni() {
    const [q0, q1] = quarter();
    const [dataInizio, setDataInizio] = useState(q0);
    const [dataFine, setDataFine] = useState(q1);
    const [config, setConfig] = useState(null);      // { campagne, realizzo_min, settings }
    const [settings, setSettings] = useState({});    // { camp: {obiettivo, colonna, bonus} }
    const [result, setResult] = useState(null);
    const [loading, setLoading] = useState(false);

    const loadConfig = useCallback(async () => {
        try {
            const { data } = await api.get("/incentivazioni/config");
            setConfig(data);
            setSettings(data.settings || {});
        } catch (e) { toast.error("Errore caricamento configurazione"); }
    }, []);

    useEffect(() => { loadConfig(); }, [loadConfig]);

    const calcola = useCallback(async () => {
        setLoading(true);
        try {
            const { data } = await api.get("/incentivazioni/calcola", {
                params: { data_inizio: dataInizio, data_fine: dataFine },
            });
            setResult(data);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore calcolo incentivi");
        } finally { setLoading(false); }
    }, [dataInizio, dataFine]);

    const setCampSetting = (camp, key, value) =>
        setSettings((p) => ({ ...p, [camp]: { ...(p[camp] || {}), [key]: value } }));

    const salvaEcalcola = async () => {
        try {
            await api.put("/incentivazioni/config", { settings });
            toast.success("Impostazioni salvate");
            await calcola();
        } catch (e) { toast.error("Errore salvataggio impostazioni"); }
    };

    const campagneMeta = config?.campagne || {};
    const resById = {};
    (result?.campagne || []).forEach((c) => { resById[c.campagna] = c; });

    return (
        <div className="space-y-6" data-testid="incentivazioni-page">
            <div className="flex items-start justify-between flex-wrap gap-3">
                <div>
                    <h1 className="text-3xl font-bold flex items-center gap-2">
                        <Award className="text-amber-600" /> Incentivazioni
                    </h1>
                    <p className="text-sm text-slate-500 mt-1">
                        Calcolo dell'incentivo di spettanza per ogni collaboratore sulla nuova produzione del periodo.
                    </p>
                </div>
                <div className="flex items-end gap-2 flex-wrap">
                    <div>
                        <Label className="text-xs">Dal</Label>
                        <Input type="date" value={dataInizio} onChange={(e) => setDataInizio(e.target.value)}
                            className="w-40" data-testid="inc-data-inizio" />
                    </div>
                    <div>
                        <Label className="text-xs">Al</Label>
                        <Input type="date" value={dataFine} onChange={(e) => setDataFine(e.target.value)}
                            className="w-40" data-testid="inc-data-fine" />
                    </div>
                    <Button onClick={salvaEcalcola} disabled={loading} data-testid="inc-calcola-btn">
                        {loading ? <RefreshCw className="animate-spin mr-1" size={16} /> : <Save className="mr-1" size={16} />}
                        Salva e calcola
                    </Button>
                </div>
            </div>

            {result && (
                <div className="text-xs text-slate-500">
                    Polizze incluse: <b>{result.polizze_incluse}</b> · Prodotti mappati a una campagna: <b>{result.prodotti_mappati}</b>
                    {result.prodotti_mappati === 0 && (
                        <span className="text-amber-600"> — nessun prodotto è flaggato. Vai in Librerie → Prodotti e assegna la campagna d'incentivazione.</span>
                    )}
                </div>
            )}

            {Object.entries(campagneMeta).map(([key, meta]) => {
                const st = settings[key] || {};
                const r = resById[key];
                return (
                    <Card key={key} className="p-5 space-y-4" data-testid={`inc-camp-${key}`}>
                        <div className="flex items-center justify-between flex-wrap gap-2">
                            <h2 className="text-lg font-semibold">{meta.nome}</h2>
                            {r && (
                                <div className="flex items-center gap-3 text-sm flex-wrap">
                                    <span>Realizzo: <b className={r.realizzo >= (config.realizzo_min) ? "text-emerald-700" : "text-rose-700"}>{r.realizzo}%</b></span>
                                    <span>Aliquota {key === "dna_danni" ? "BASE" : ""}: <b>{r.aliquota}%</b></span>
                                    {r.ha_persona && (
                                        <>
                                            <span className="text-slate-300">|</span>
                                            <span>Realizzo Persona: <b className={r.realizzo_persona >= (config.realizzo_min) ? "text-emerald-700" : "text-rose-700"}>{r.realizzo_persona}%</b></span>
                                            <span>Aliquota PERSONA: <b>{r.aliquota_persona}%</b></span>
                                        </>
                                    )}
                                    <span className={`px-2 py-0.5 rounded text-xs font-semibold ${r.accede ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800"}`}>
                                        {r.accede ? "Accede all'incentivo" : `Sotto soglia ${config.realizzo_min}%`}
                                    </span>
                                </div>
                            )}
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                            <div>
                                <Label className="text-xs">{key === "dna_danni" ? "Obiettivo DNA totale (€)" : "Obiettivo Agenzia (€)"}</Label>
                                <Input type="number" value={st.obiettivo ?? ""} placeholder="0"
                                    onChange={(e) => setCampSetting(key, "obiettivo", parseFloat(e.target.value) || 0)}
                                    data-testid={`inc-obiettivo-${key}`} />
                            </div>
                            {key === "dna_danni" ? (
                                <div>
                                    <Label className="text-xs">Obiettivo di cui Persona (€)</Label>
                                    <Input type="number" value={st.obiettivo_persona ?? ""} placeholder="0"
                                        onChange={(e) => setCampSetting(key, "obiettivo_persona", parseFloat(e.target.value) || 0)}
                                        data-testid="inc-obiettivo-persona" />
                                    <div className="text-[10px] text-slate-500 mt-1">Cura Persona + Prot. Beni Persona Fisica</div>
                                </div>
                            ) : (
                                <div>
                                    <Label className="text-xs">Colonna / Aliquota</Label>
                                    <Select value={st.colonna || meta.colonne[0].key}
                                        onValueChange={(v) => setCampSetting(key, "colonna", v)}>
                                        <SelectTrigger data-testid={`inc-colonna-${key}`}><SelectValue /></SelectTrigger>
                                        <SelectContent>
                                            {meta.colonne.map((c) => <SelectItem key={c.key} value={c.key}>{c.label}</SelectItem>)}
                                        </SelectContent>
                                    </Select>
                                </div>
                            )}
                            {meta.bonus?.length > 0 && (
                                <div>
                                    <Label className="text-xs">Bonus/Malus (%)</Label>
                                    <Select value={String(st.bonus ?? 0)}
                                        onValueChange={(v) => setCampSetting(key, "bonus", parseFloat(v))}>
                                        <SelectTrigger data-testid={`inc-bonus-${key}`}><SelectValue /></SelectTrigger>
                                        <SelectContent>
                                            {meta.bonus.map((b) => <SelectItem key={b} value={String(b)}>{b > 0 ? `+${b}%` : `${b}%`}</SelectItem>)}
                                        </SelectContent>
                                    </Select>
                                </div>
                            )}
                            <div className="flex flex-col justify-end">
                                <div className="text-xs text-slate-500">Produzione totale{key === "dna_danni" && r ? " (di cui Persona)" : ""}</div>
                                <div className="text-lg font-bold num">
                                    {fmtEur(r?.produzione_totale || 0)}
                                    {key === "dna_danni" && r ? <span className="text-sm text-slate-500 font-normal"> ({fmtEur(r.produzione_persona_totale || 0)})</span> : null}
                                </div>
                            </div>
                        </div>

                        {r && r.righe.length > 0 ? (
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="text-left text-slate-500 border-b">
                                            <th className="py-2">Collaboratore</th>
                                            <th className="py-2 text-right">Nuova produzione</th>
                                            {r.ha_persona && <th className="py-2 text-right">di cui Persona</th>}
                                            <th className="py-2 text-right">Incentivo spettante</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {r.righe.map((row, i) => (
                                            <tr key={i} className="border-b last:border-0" data-testid={`inc-row-${key}-${i}`}>
                                                <td className="py-2">{row.collaboratore}</td>
                                                <td className="py-2 text-right num">{fmtEur(row.produzione)}</td>
                                                {r.ha_persona && <td className="py-2 text-right num text-slate-500">{fmtEur(row.produzione_persona)}</td>}
                                                <td className="py-2 text-right num font-semibold text-emerald-700">{fmtEur(row.incentivo)}</td>
                                            </tr>
                                        ))}
                                        <tr className="bg-amber-50 font-bold">
                                            <td className="py-2">TOTALE</td>
                                            <td className="py-2 text-right num">{fmtEur(r.produzione_totale)}</td>
                                            {r.ha_persona && <td className="py-2 text-right num">{fmtEur(r.produzione_persona_totale)}</td>}
                                            <td className="py-2 text-right num text-emerald-800">{fmtEur(r.incentivo_totale)}</td>
                                        </tr>
                                    </tbody>
                                </table>
                            </div>
                        ) : (
                            <div className="text-sm text-slate-400 py-2">
                                {result ? "Nessuna nuova produzione per questa campagna nel periodo." : "Premi \"Salva e calcola\" per vedere i risultati."}
                            </div>
                        )}
                    </Card>
                );
            })}
        </div>
    );
}
