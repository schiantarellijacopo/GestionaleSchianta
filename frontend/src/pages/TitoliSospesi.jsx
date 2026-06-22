import { useEffect, useState, useMemo, useCallback } from "react";
import { Link } from "react-router-dom";
import { api, fmtEur, fmtDate } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Coins, Clock, AlertTriangle, CheckCircle } from "lucide-react";
import { toast } from "sonner";

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

function DialogIncasso({ titolo, conti, onClose }) {
    const oggi = new Date().toISOString().slice(0, 10);
    const [pref, setPref] = useState(null);
    useEffect(() => {
        if (titolo.contraente_id) {
            api.get(`/anagrafiche/${titolo.contraente_id}`).then((r) => setPref(r.data));
        }
    }, [titolo.contraente_id]);
    const defaultMezzo = pref?.preferenza_pagamento || pref?.ultimo_mezzo_pagamento || "contanti";
    const [f, setF] = useState({
        data_incasso: oggi,
        mezzo_pagamento: defaultMezzo,
        conto_cassa_id: conti[0]?.id || "",
        importo_pagato: titolo.importo_lordo,
        motivo_sconto: "",
    });
    useEffect(() => {
        if (pref) setF((p) => ({ ...p, mezzo_pagamento: defaultMezzo }));
    // eslint-disable-next-line
    }, [pref]);
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
    const sconto = Math.max(0, (titolo.importo_lordo || 0) - (parseFloat(f.importo_pagato) || 0));

    const conferma = async () => {
        try {
            await api.post(`/titoli/${titolo.id}/incassa`, {
                data_incasso: f.data_incasso,
                mezzo_pagamento: f.mezzo_pagamento,
                conto_cassa_id: f.conto_cassa_id || null,
                importo_pagato: parseFloat(f.importo_pagato) || 0,
                motivo_sconto: sconto > 0 ? (f.motivo_sconto || "Sconto applicato") : null,
            });
            toast.success(sconto > 0
                ? `Incassato €${f.importo_pagato} (sconto €${sconto.toFixed(2)} in prima nota)`
                : `Incassato €${f.importo_pagato}`);
            onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <Dialog open onOpenChange={onClose}>
            <DialogContent className="max-w-lg">
                <DialogHeader>
                    <DialogTitle>Incasso titolo — {titolo.contraente_nome}</DialogTitle>
                </DialogHeader>

                <div className="bg-amber-50 border border-amber-200 rounded-md p-3 text-xs text-amber-900 space-y-0.5">
                    <div><strong>Polizza:</strong> {titolo.numero_polizza} ({titolo.ramo})</div>
                    <div><strong>Importo da incassare:</strong> <span className="num font-bold">{fmtEur(titolo.importo_lordo)}</span></div>
                    <div><strong>Anticipato dall&apos;agenzia il:</strong> {fmtDate(titolo.data_copertura)} ({titolo.giorni_anticipo} gg fa)</div>
                    {pref?.preferenza_pagamento && (
                        <div className="mt-1 text-emerald-700">
                            ★ <strong>Preferenza cliente:</strong> {pref.preferenza_pagamento}
                            {pref.ultimo_mezzo_pagamento && pref.ultimo_mezzo_pagamento !== pref.preferenza_pagamento &&
                                ` (ultimo usato: ${pref.ultimo_mezzo_pagamento})`}
                        </div>
                    )}
                </div>

                <div className="space-y-3 py-2">
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <Label>Data incasso</Label>
                            <Input type="date" value={f.data_incasso} onChange={(e) => set("data_incasso", e.target.value)} data-testid="inc-data" />
                        </div>
                        <div>
                            <Label>Mezzo pagamento</Label>
                            <Select value={f.mezzo_pagamento} onValueChange={(v) => set("mezzo_pagamento", v)}>
                                <SelectTrigger data-testid="inc-mezzo"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="contanti">Contanti</SelectItem>
                                    <SelectItem value="bonifico">Bonifico</SelectItem>
                                    <SelectItem value="assegno">Assegno</SelectItem>
                                    <SelectItem value="pos">POS / Carta</SelectItem>
                                    <SelectItem value="rid">RID</SelectItem>
                                    <SelectItem value="altro">Altro</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    </div>
                    <div>
                        <Label>Conto cassa di destinazione</Label>
                        <Select value={f.conto_cassa_id || "__none__"} onValueChange={(v) => set("conto_cassa_id", v === "__none__" ? "" : v)}>
                            <SelectTrigger data-testid="inc-conto"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="__none__">— nessuno —</SelectItem>
                                {conti.map((c) => <SelectItem key={c.id} value={c.id}>{c.nome} ({c.tipo})</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="bg-emerald-50 border border-emerald-200 rounded-md p-3 space-y-2">
                        <Label className="text-emerald-900 font-semibold">Importo effettivamente pagato dal cliente</Label>
                        <Input
                            type="number"
                            step="0.01"
                            value={f.importo_pagato}
                            onChange={(e) => set("importo_pagato", e.target.value)}
                            className="text-lg font-semibold"
                            data-testid="inc-importo-pagato"
                        />
                        {sconto > 0 && (
                            <div className="bg-white border border-amber-300 rounded p-2 mt-2 text-xs">
                                <div className="flex justify-between items-center font-semibold text-amber-700">
                                    <span>Sconto applicato:</span>
                                    <span className="num">{fmtEur(sconto)}</span>
                                </div>
                                <div className="text-[10px] text-amber-600 mt-1">
                                    Verrà registrato come <strong>uscita</strong> in prima nota (categoria &quot;sconto_cliente&quot;)
                                </div>
                                <Input
                                    placeholder="Motivo dello sconto (opzionale)"
                                    value={f.motivo_sconto}
                                    onChange={(e) => set("motivo_sconto", e.target.value)}
                                    className="mt-2 text-xs"
                                    data-testid="inc-motivo-sconto"
                                />
                            </div>
                        )}
                    </div>
                </div>

                <DialogFooter>
                    <Button onClick={conferma} className="bg-emerald-600 hover:bg-emerald-700" data-testid="inc-conferma">
                        Conferma incasso
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
