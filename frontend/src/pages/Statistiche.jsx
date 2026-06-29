/**
 * Statistiche — hub con tabs per più moduli (Overview, ISA, ...).
 */
import { useEffect, useState } from "react";
import { api, fmtEur } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { PageHeader, Loading } from "@/components/Shared";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import {
    TrendingUp, Users, Building, FileText, AlertTriangle, Wallet,
    Calendar, Trophy, PieChart, Gauge, BarChart3,
} from "lucide-react";

const COLOR = {
    sky: "border-sky-400 text-sky-700",
    indigo: "border-indigo-400 text-indigo-700",
    emerald: "border-emerald-400 text-emerald-700",
    violet: "border-violet-400 text-violet-700",
    amber: "border-amber-400 text-amber-700",
    rose: "border-rose-400 text-rose-700",
    slate: "border-slate-400 text-slate-700",
};

export default function Statistiche() {
    const [tab, setTab] = useState("overview");
    return (
        <div className="space-y-3">
            <PageHeader title="Statistiche" subtitle="Hub di analisi · scegli il modulo dai tab" />
            <Tabs value={tab} onValueChange={setTab}>
                <TabsList>
                    <TabsTrigger value="overview" data-testid="stat-tab-overview">
                        <BarChart3 size={14} className="mr-1" /> Overview
                    </TabsTrigger>
                    <TabsTrigger value="isa" data-testid="stat-tab-isa">
                        <Gauge size={14} className="mr-1" /> Indice ISA
                    </TabsTrigger>
                </TabsList>
                <TabsContent value="overview" className="space-y-4 mt-4"><OverviewModulo /></TabsContent>
                <TabsContent value="isa" className="space-y-4 mt-4"><IsaModulo /></TabsContent>
            </Tabs>
        </div>
    );
}

function OverviewModulo() {
    const [s, setS] = useState(null);
    useEffect(() => { api.get("/statistiche/overview").then((r) => setS(r.data)).catch(() => setS({})); }, []);
    if (!s) return <Loading />;
    return (
        <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <KCard color="sky" icon={Users} label="Clienti privati" value={s.clienti_privati} />
                <KCard color="indigo" icon={Building} label="Clienti aziende" value={s.clienti_aziende} />
                <KCard color="emerald" icon={TrendingUp} label="Nuovi clienti (30g)" value={s.nuovi_clienti_30g} />
                <KCard color="violet" icon={FileText} label="Polizze attive" value={s.polizze_attive} />
                <KCard color="amber" icon={Calendar} label="In scadenza (30g)" value={s.polizze_in_scadenza_30g} />
                <KCard color="rose" icon={AlertTriangle} label="Sinistri aperti" value={s.sinistri_aperti} />
                <KCard color="slate" icon={AlertTriangle} label="Sinistri ultimo anno" value={s.sinistri_ultimo_anno} />
                <KCard color="emerald" icon={Wallet} label="Premio attivo totale" value={fmtEur(s.premio_attivo_totale)} mono />
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4">
                {s.top_compagnie?.length > 0 && (
                    <Card className="p-4">
                        <h2 className="text-sm font-semibold mb-3 flex items-center gap-2"><Trophy size={16} className="text-amber-600" /> Top 5 Compagnie</h2>
                        <table className="tbl-compact w-full text-xs"><tbody>
                            {s.top_compagnie.map((c, i) => (
                                <tr key={c.nome}>
                                    <td className="w-8 text-slate-400 font-bold">#{i + 1}</td>
                                    <td className="font-medium">{c.nome}</td>
                                    <td className="text-right text-slate-500">{c.polizze} pol.</td>
                                    <td className="text-right font-mono font-semibold text-emerald-700">{fmtEur(c.premio_totale)}</td>
                                </tr>
                            ))}
                        </tbody></table>
                    </Card>
                )}
                {s.top_rami?.length > 0 && (
                    <Card className="p-4">
                        <h2 className="text-sm font-semibold mb-3 flex items-center gap-2"><PieChart size={16} className="text-violet-600" /> Top 5 Rami</h2>
                        <table className="tbl-compact w-full text-xs"><tbody>
                            {s.top_rami.map((r, i) => (
                                <tr key={r.ramo}>
                                    <td className="w-8 text-slate-400 font-bold">#{i + 1}</td>
                                    <td className="font-medium">{r.ramo}</td>
                                    <td className="text-right text-slate-500">{r.polizze} pol.</td>
                                    <td className="text-right font-mono font-semibold text-emerald-700">{fmtEur(r.premio_totale)}</td>
                                </tr>
                            ))}
                        </tbody></table>
                    </Card>
                )}
            </div>
        </>
    );
}

function IsaModulo() {
    const [isa, setIsa] = useState(null);
    const [filtri, setFiltri] = useState({ anno: new Date().getFullYear(), base_data: "incasso" });
    const setF = (k, v) => setFiltri((p) => ({ ...p, [k]: v }));
    useEffect(() => {
        api.get("/statistiche/isa", { params: filtri }).then((r) => setIsa(r.data)).catch(() => setIsa(null));
    }, [filtri]);
    const anniOpzioni = []; const annoCorr = new Date().getFullYear();
    for (let a = annoCorr; a >= annoCorr - 4; a--) anniOpzioni.push(a);
    return (
        <div className="space-y-3">
            <Card className="p-3 flex flex-wrap gap-3 items-end">
                <div>
                    <Label className="text-xs">Anno</Label>
                    <Select value={String(filtri.anno)} onValueChange={(v) => setF("anno", parseInt(v))}>
                        <SelectTrigger className="w-32" data-testid="isa-anno"><SelectValue /></SelectTrigger>
                        <SelectContent>{anniOpzioni.map((a) => <SelectItem key={a} value={String(a)}>{a}</SelectItem>)}</SelectContent>
                    </Select>
                </div>
                <div>
                    <Label className="text-xs">Base ricavi</Label>
                    <Select value={filtri.base_data} onValueChange={(v) => setF("base_data", v)}>
                        <SelectTrigger className="w-56" data-testid="isa-base"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="incasso">Data incasso titolo</SelectItem>
                            <SelectItem value="copertura">Data copertura titolo</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
            </Card>
            {isa ? <IsaPanel isa={isa} /> : <Loading />}
        </div>
    );
}

const KCard = ({ icon: Ic, label, value, color, mono }) => (
    <Card className={`p-3 border-l-4 bg-white ${COLOR[color] || COLOR.sky}`} data-testid={`stat-${label}`}>
        <div className="flex items-start justify-between">
            <div>
                <div className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">{label}</div>
                <div className={`text-2xl font-bold mt-0.5 ${mono ? "font-mono" : ""}`}>{value ?? "—"}</div>
            </div>
            <Ic size={20} className={`opacity-40 ${(COLOR[color] || "").split(" ")[1]}`} />
        </div>
    </Card>
);

function IsaPanel({ isa }) {
    const cmap = {
        emerald: { bg: "from-emerald-50 to-emerald-100/40", text: "text-emerald-700", border: "border-emerald-400", fill: "bg-emerald-500" },
        sky: { bg: "from-sky-50 to-sky-100/40", text: "text-sky-700", border: "border-sky-400", fill: "bg-sky-500" },
        amber: { bg: "from-amber-50 to-amber-100/40", text: "text-amber-700", border: "border-amber-400", fill: "bg-amber-500" },
        orange: { bg: "from-orange-50 to-orange-100/40", text: "text-orange-700", border: "border-orange-400", fill: "bg-orange-500" },
        rose: { bg: "from-rose-50 to-rose-100/40", text: "text-rose-700", border: "border-rose-400", fill: "bg-rose-500" },
    };
    const c = cmap[isa.colore] || cmap.sky;
    return (
        <Card className={`p-5 bg-gradient-to-br ${c.bg} border-l-4 ${c.border}`} data-testid="isa-panel">
            <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                    <Gauge size={32} className={c.text} />
                    <div>
                        <div className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">
                            Indice ISA · {isa.anno} · base: {isa.base_data === "copertura" ? "data copertura" : "data incasso"}
                        </div>
                        <div className="flex items-baseline gap-2">
                            <span className={`text-4xl font-bold ${c.text} font-mono`}>{isa.punteggio}</span>
                            <span className="text-slate-500">/ 10</span>
                        </div>
                        <div className={`text-sm font-semibold ${c.text}`}>{isa.livello}</div>
                    </div>
                </div>
                <div className="text-right text-xs">
                    <div className="text-slate-500">Ricavi {isa.anno}</div>
                    <div className="font-mono font-bold">{fmtEur(isa.dati_calcolo?.ricavi)}</div>
                    <div className="text-slate-500 mt-1">Utile lordo</div>
                    <div className={`font-mono font-bold ${(isa.dati_calcolo?.utile || 0) >= 0 ? "text-emerald-700" : "text-rose-700"}`}>
                        {fmtEur(isa.dati_calcolo?.utile)}
                    </div>
                </div>
            </div>
            <div className="space-y-3">
                {(isa.indicatori || []).map((i) => (
                    <div key={i.nome}>
                        <div className="flex items-baseline justify-between text-xs mb-1">
                            <div>
                                <span className="font-semibold text-slate-800">{i.nome}</span>
                                <span className="text-slate-500 ml-2">{i.descrizione}</span>
                                <span className="text-[10px] text-slate-400 ml-2">(peso {i.peso}%)</span>
                            </div>
                            <div>
                                <span className="font-mono text-slate-700">{i.valore} {i.unita}</span>
                                <span className="text-slate-400 ml-2">→ <span className={`font-bold ${c.text}`}>{i.punteggio}</span>/10</span>
                            </div>
                        </div>
                        <div className="h-1.5 bg-slate-200/60 rounded overflow-hidden">
                            <div className={`h-full ${c.fill}`} style={{ width: `${Math.min(100, (i.punteggio / 10) * 100)}%` }} />
                        </div>
                    </div>
                ))}
            </div>
            <div className="mt-4 text-[11px] text-slate-500 italic">{isa.note}</div>
        </Card>
    );
}
