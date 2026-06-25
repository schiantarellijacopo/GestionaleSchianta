import { useEffect, useState, useMemo, useCallback } from "react";
import { Link } from "react-router-dom";
import { api, fmtEur, fmtDate } from "@/lib/api";
import { PageHeader, Loading } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import DialogIncasso from "@/components/DialogIncasso";
import { Coins, Clock, AlertTriangle, CheckCircle } from "lucide-react";

export default function TitoliSospesi() {
    const [items, setItems] = useState(null);
    const [collab, setCollab] = useState([]);
    const [filtroCollab, setFiltroCollab] = useState("all");
    const [conti, setConti] = useState([]);
    const [paying, setPaying] = useState(null);  // titolo in pagamento

    const load = useCallback(() => {
        const params = {};
        if (filtroCollab !== "all") params.collaboratore_id = filtroCollab;
        api.get("/titoli/sospesi", { params }).then((r) => setItems(r.data));
    }, [filtroCollab]);

    useEffect(() => {
        api.get("/collaboratori").then((r) => setCollab(r.data));
        api.get("/librerie/conti-cassa").then((r) => setConti(r.data));
    }, []);
    useEffect(() => { load(); }, [load]);

    const totali = useMemo(() => {
        const arr = items || [];
        return {
            count: arr.length,
            importo: arr.reduce((s, t) => s + (t.importo_lordo || 0), 0),
            piuVecchio: arr.reduce((m, t) => Math.max(m, t.giorni_anticipo || 0), 0),
        };
    }, [items]);

    const riepilogoCollab = useMemo(() => {
        const arr = items || [];
        const map = new Map();
        for (const t of arr) {
            const id = t.collaboratore_id || "__none__";
            const nome = t.collaboratore_nome || "— senza collaboratore —";
            const cur = map.get(id) || { id, nome, count: 0, importo: 0 };
            cur.count += 1;
            cur.importo += (t.importo_lordo || 0);
            map.set(id, cur);
        }
        return Array.from(map.values()).sort((a, b) => b.importo - a.importo);
    }, [items]);

    return (
        <div data-testid="sospesi-page">
            <PageHeader
                title="Sospesi — titoli anticipati dall'agenzia"
                subtitle="Clienti coperti dall'agenzia ma che non hanno ancora pagato. Clicca per incassare."
            />

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-5">
                <KpiCard
                    icon={<Coins className="text-amber-600" size={20} />}
                    label="Titoli sospesi"
                    value={totali.count}
                    bg="bg-amber-50 border-amber-200"
                />
                <KpiCard
                    icon={<AlertTriangle className="text-red-600" size={20} />}
                    label="Anticipo dell'agenzia"
                    value={fmtEur(totali.importo)}
                    bg="bg-red-50 border-red-200"
                />
                <KpiCard
                    icon={<Clock className="text-slate-600" size={20} />}
                    label="Anticipo più vecchio"
                    value={totali.piuVecchio ? `${totali.piuVecchio} gg` : "—"}
                />
            </div>

            <Card className="border-slate-200 p-3 mb-4 flex items-end gap-3 flex-wrap">
                <div className="flex-1 max-w-xs">
                    <Label className="text-xs">Filtra per collaboratore</Label>
                    <Select value={filtroCollab} onValueChange={setFiltroCollab}>
                        <SelectTrigger data-testid="sospesi-filter-collab"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">Tutti</SelectItem>
                            {collab.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
            </Card>

            {riepilogoCollab.length > 0 && (
                <Card className="border-slate-200 mb-4 overflow-hidden" data-testid="sospesi-riepilogo-collab">
                    <div className="px-4 py-2 bg-slate-50 border-b border-slate-200 text-xs uppercase tracking-wider text-slate-600 font-semibold">
                        Riepilogo per collaboratore
                    </div>
                    <table className="tbl w-full">
                        <thead>
                            <tr>
                                <th>Collaboratore</th>
                                <th className="text-right">N° titoli</th>
                                <th className="text-right">Totale anticipato</th>
                            </tr>
                        </thead>
                        <tbody>
                            {riepilogoCollab.map((r) => (
                                <tr key={r.id} data-testid={`riep-collab-${r.id}`}>
                                    <td className="font-medium">{r.nome}</td>
                                    <td className="num text-right">{r.count}</td>
                                    <td className="num text-right font-semibold">{fmtEur(r.importo)}</td>
                                </tr>
                            ))}
                        </tbody>
                        <tfoot>
                            <tr className="bg-slate-50 font-semibold">
                                <td className="text-right">TOTALE</td>
                                <td className="num text-right">{totali.count}</td>
                                <td className="num text-right">{fmtEur(totali.importo)}</td>
                            </tr>
                        </tfoot>
                    </table>
                </Card>
            )}

            <Card className="border-slate-200 overflow-hidden">
                {items === null ? <Loading /> : items.length === 0 ? (
                    <div className="text-center py-16 text-slate-500">
                        <CheckCircle size={32} className="mx-auto mb-2 text-emerald-500" />
                        Nessun titolo sospeso — tutti i clienti hanno pagato.
                    </div>
                ) : (
                    <table className="tbl w-full">
                        <thead>
                            <tr>
                                <th>Cliente</th>
                                <th>Cellulare</th>
                                <th>Collaboratore</th>
                                <th>Polizza</th>
                                <th>Ramo / Targa</th>
                                <th>Coperto il</th>
                                <th>Anticipo</th>
                                <th>Scad. polizza</th>
                                <th className="text-right">Importo €</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody>
                            {items.map((t) => {
                                const old = (t.giorni_anticipo || 0) > 30;
                                return (
                                    <tr key={t.id} data-testid={`sospeso-${t.id}`}>
                                        <td className="font-medium">
                                            <Link to={`/anagrafiche/${t.contraente_id}`} className="text-sky-700 hover:underline">
                                                {t.contraente_nome}
                                            </Link>
                                        </td>
                                        <td className="text-xs">{t.cellulare || "—"}</td>
                                        <td className="text-xs">{t.collaboratore_nome || <span className="text-slate-300">—</span>}</td>
                                        <td>
                                            <Link to={`/polizze/${t.polizza_id}`} className="font-mono text-xs text-sky-700 hover:underline">
                                                {t.numero_polizza}
                                            </Link>
                                        </td>
                                        <td className="text-xs">
                                            <span className="badge badge-neutral">{t.ramo}</span>
                                            {t.targa && <span className="ml-1 font-mono text-xs text-slate-500">{t.targa}</span>}
                                        </td>
                                        <td className="num text-xs">{fmtDate(t.data_copertura)}</td>
                                        <td className="num text-xs">
                                            <span className={old ? "text-red-600 font-semibold" : "text-slate-500"}>
                                                {t.giorni_anticipo} gg
                                            </span>
                                        </td>
                                        <td className="num text-xs">{fmtDate(t.scadenza_polizza)}</td>
                                        <td className="num text-right font-bold">{fmtEur(t.importo_lordo)}</td>
                                        <td className="text-right">
                                            <Button size="sm" className="bg-emerald-600 hover:bg-emerald-700"
                                                    onClick={() => setPaying(t)}
                                                    data-testid={`sospeso-paga-${t.id}`}>
                                                Incassa
                                            </Button>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                        <tfoot>
                            <tr className="bg-slate-50 font-semibold">
                                <td colSpan="8" className="text-right">TOTALE ANTICIPI</td>
                                <td className="num text-right">{fmtEur(totali.importo)}</td>
                                <td></td>
                            </tr>
                        </tfoot>
                    </table>
                )}
            </Card>

            {paying && (
                <DialogIncasso titolo={paying} conti={conti}
                              onClose={() => { setPaying(null); load(); }} />
            )}
        </div>
    );
}

function KpiCard({ icon, label, value, bg }) {
    return (
        <Card className={`p-4 border-slate-200 ${bg || ""}`}>
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
