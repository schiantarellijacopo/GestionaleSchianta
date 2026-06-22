import { useEffect, useState } from "react";
import { api, fmtEur, fmtDate } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Coins, FileText, Printer, ArrowLeft } from "lucide-react";

export default function EstrattoContoCompagnie() {
    const [compagnie, setCompagnie] = useState([]);
    const [saldi, setSaldi] = useState(null);
    const [selectedId, setSelectedId] = useState(null);

    useEffect(() => {
        api.get("/compagnie").then((r) => setCompagnie(r.data));
        api.get("/compagnie/saldi-cassa").then((r) => setSaldi(r.data));
    }, []);

    if (selectedId) {
        const comp = compagnie.find((c) => c.id === selectedId);
        return <DettaglioEstratto compagnia={comp} onBack={() => setSelectedId(null)} />;
    }

    return (
        <div data-testid="ec-compagnie-page">
            <PageHeader
                title="Estratto conto compagnie"
                subtitle="Saldi cassa per compagnia: dare/avere e scoperture verso le compagnie mandanti"
                actions={
                    <a href={`${import.meta.env?.VITE_BACKEND_URL || ""}/api/stampa/compagnie/saldi-cassa`}
                       target="_blank" rel="noreferrer">
                        <Button variant="outline" data-testid="ec-stampa-saldi">
                            <Printer size={14} className="mr-1" /> Stampa saldi
                        </Button>
                    </a>
                }
            />

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                <KpiCard
                    label="Compagnie attive"
                    value={saldi?.length || 0}
                    icon={<Coins size={20} />}
                />
                <KpiCard
                    label="Totale da versare"
                    value={fmtEur((saldi || []).reduce((s, r) => s + (r.saldo_da_versare > 0 ? r.saldo_da_versare : 0), 0))}
                    color="text-amber-700 bg-amber-50"
                />
                <KpiCard
                    label="Totale a credito"
                    value={fmtEur(Math.abs((saldi || []).reduce((s, r) => s + (r.saldo_da_versare < 0 ? r.saldo_da_versare : 0), 0)))}
                    color="text-emerald-700 bg-emerald-50"
                />
            </div>

            <Card className="border-slate-200 overflow-hidden">
                {saldi === null ? <Loading /> : saldi.length === 0 ? <Empty /> : (
                    <table className="tbl w-full">
                        <thead>
                            <tr>
                                <th>Codice</th>
                                <th>Compagnia</th>
                                <th>Trattiene provv.</th>
                                <th className="text-right">Incassato dai clienti €</th>
                                <th className="text-right">Versato alla compagnia €</th>
                                <th className="text-right">Saldo da versare €</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody>
                            {saldi.map((r) => (
                                <tr key={r.compagnia_id} data-testid={`ec-row-${r.compagnia_id}`}>
                                    <td className="num text-xs">{r.codice}</td>
                                    <td className="font-medium">{r.ragione_sociale}</td>
                                    <td>{r.trattiene_provvigioni ? <span className="badge badge-success">sì</span> : <span className="badge badge-neutral">no</span>}</td>
                                    <td className="num text-right">{fmtEur(r.totale_incassato)}</td>
                                    <td className="num text-right text-slate-600">{fmtEur(r.totale_versato)}</td>
                                    <td className={`num text-right font-bold ${r.saldo_da_versare > 0 ? "text-amber-700" : r.saldo_da_versare < 0 ? "text-emerald-700" : "text-slate-400"}`}>
                                        {fmtEur(r.saldo_da_versare)}
                                    </td>
                                    <td className="text-right">
                                        <button onClick={() => setSelectedId(r.compagnia_id)}
                                                className="text-xs text-sky-700 hover:underline"
                                                data-testid={`ec-detail-${r.compagnia_id}`}>
                                            <FileText size={12} className="inline mr-0.5" /> Dettaglio
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </Card>
        </div>
    );
}

function KpiCard({ label, value, icon, color }) {
    return (
        <Card className={`p-4 border-slate-200 ${color || ""}`}>
            <div className="flex items-center justify-between">
                <div>
                    <div className="text-xs uppercase tracking-widest text-slate-500">{label}</div>
                    <div className="text-2xl font-semibold num mt-1">{value}</div>
                </div>
                {icon}
            </div>
        </Card>
    );
}

function DettaglioEstratto({ compagnia, onBack }) {
    const [dal, setDal] = useState("");
    const [al, setAl] = useState("");
    const [data, setData] = useState(null);

    const load = () => {
        api.get(`/compagnie/${compagnia.id}/estratto-conto`, { params: { dal: dal || undefined, al: al || undefined } })
            .then((r) => setData(r.data));
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [compagnia.id]);

    return (
        <div data-testid="ec-dettaglio-page">
            <button onClick={onBack} className="text-sm text-slate-500 hover:text-sky-700 inline-flex items-center gap-1 mb-3">
                <ArrowLeft size={14} /> Torna ai saldi
            </button>

            <PageHeader
                title={`Estratto conto — ${compagnia?.ragione_sociale}`}
                subtitle={`Codice ${compagnia?.codice} · ${compagnia?.trattiene_provvigioni !== false ? "Trattiene provvigioni" : "Non trattiene provvigioni"}`}
                actions={
                    <a href={`${import.meta.env?.VITE_BACKEND_URL || ""}/api/stampa/compagnie/${compagnia.id}/estratto-conto${dal || al ? `?${dal ? `dal=${dal}` : ""}${dal && al ? "&" : ""}${al ? `al=${al}` : ""}` : ""}`}
                       target="_blank" rel="noreferrer">
                        <Button variant="outline" data-testid="ec-stampa-dettaglio">
                            <Printer size={14} className="mr-1" /> Stampa PDF
                        </Button>
                    </a>
                }
            />

            <Card className="p-4 border-slate-200 mb-4">
                <div className="flex items-end gap-3 flex-wrap">
                    <div>
                        <Label>Dal</Label>
                        <Input type="date" value={dal} onChange={(e) => setDal(e.target.value)} data-testid="ec-dal" />
                    </div>
                    <div>
                        <Label>Al</Label>
                        <Input type="date" value={al} onChange={(e) => setAl(e.target.value)} data-testid="ec-al" />
                    </div>
                    <Button onClick={load} data-testid="ec-applica">Applica</Button>
                    {data && (
                        <div className="ml-auto flex gap-6 text-sm">
                            <div><span className="text-slate-500">Dare:</span> <span className="font-bold num">{fmtEur(data.totale_dare)}</span></div>
                            <div><span className="text-slate-500">Avere:</span> <span className="font-bold num">{fmtEur(data.totale_avere)}</span></div>
                            <div><span className="text-slate-500">Saldo:</span> <span className={`font-bold num ${data.saldo > 0 ? "text-amber-700" : data.saldo < 0 ? "text-emerald-700" : ""}`}>{fmtEur(data.saldo)}</span></div>
                        </div>
                    )}
                </div>
            </Card>

            <Card className="border-slate-200 overflow-hidden">
                {!data ? <Loading /> : data.righe.length === 0 ? <Empty /> : (
                    <table className="tbl w-full">
                        <thead>
                            <tr>
                                <th>Data</th>
                                <th>Tipo</th>
                                <th>Polizza</th>
                                <th>Contraente</th>
                                <th>Ramo</th>
                                <th className="text-right">Lordo €</th>
                                <th className="text-right">Provv. €</th>
                                <th className="text-right">Dare €</th>
                                <th className="text-right">Avere €</th>
                            </tr>
                        </thead>
                        <tbody>
                            {data.righe.map((r, i) => (
                                <tr key={i}>
                                    <td className="num text-xs">{fmtDate(r.data)}</td>
                                    <td><span className={`badge ${r.tipo === "incasso" ? "badge-info" : "badge-success"}`}>{r.tipo}</span></td>
                                    <td className="font-mono text-xs">{r.polizza || "-"}</td>
                                    <td className="text-xs">{r.contraente || "-"}</td>
                                    <td className="text-xs">{r.ramo || "-"}</td>
                                    <td className="num text-right text-slate-600">{r.lordo ? fmtEur(r.lordo) : "-"}</td>
                                    <td className="num text-right text-slate-600">{r.provvigioni ? fmtEur(r.provvigioni) : "-"}</td>
                                    <td className="num text-right">{r.dare ? fmtEur(r.dare) : "-"}</td>
                                    <td className="num text-right">{r.avere ? fmtEur(r.avere) : "-"}</td>
                                </tr>
                            ))}
                        </tbody>
                        <tfoot>
                            <tr className="bg-slate-50 font-semibold">
                                <td colSpan="7" className="text-right">TOTALI</td>
                                <td className="num text-right">{fmtEur(data.totale_dare)}</td>
                                <td className="num text-right">{fmtEur(data.totale_avere)}</td>
                            </tr>
                        </tfoot>
                    </table>
                )}
            </Card>
        </div>
    );
}
