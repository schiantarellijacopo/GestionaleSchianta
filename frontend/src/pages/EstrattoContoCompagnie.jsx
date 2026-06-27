import { useEffect, useState, useCallback } from "react";
import { api, fmtEur, fmtDate, API_BASE } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Coins, FileText, Printer, ArrowLeft, History, ChevronRight, ChevronDown, Paperclip, Eye } from "lucide-react";
import AllegatiCell from "@/components/AllegatiCell";
import useMezziPagamento from "@/hooks/useMezziPagamento";
import SelectTipoPagamento from "@/components/SelectTipoPagamento";

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
    const [tab, setTab] = useState("movimenti");
    const [dal, setDal] = useState("");
    const [al, setAl] = useState("");
    const [collaboratoreId, setCollaboratoreId] = useState("all");
    const [collaboratori, setCollaboratori] = useState([]);
    const [conti, setConti] = useState([]);
    const [data, setData] = useState(null);
    const [selected, setSelected] = useState(new Set());
    const [payOpen, setPayOpen] = useState(false);

    useEffect(() => {
        api.get("/utenti").then((r) => setCollaboratori(
            (r.data || []).filter((u) => ["collaboratore", "dipendente"].includes(u.role))
        )).catch(() => {});
        api.get("/librerie/conti-cassa").then((r) => setConti(r.data || []));
    }, []);

    const load = useCallback(() => {
        const params = { dal: dal || undefined, al: al || undefined };
        if (collaboratoreId !== "all") params.collaboratore_id = collaboratoreId;
        api.get(`/compagnie/${compagnia.id}/estratto-conto`, { params })
            .then((r) => { setData(r.data); setSelected(new Set()); });
    }, [compagnia.id, dal, al, collaboratoreId]);
    useEffect(() => { load(); }, [load]);

    const incassi = (data?.righe || []).filter((r) => r.tipo === "incasso");
    const daVersare = incassi.filter((r) => r.stato_pagamento !== "pagato");
    const pagamenti = (data?.righe || []).filter((r) => r.tipo === "pagamento");
    // Solo non-pagati + pagamenti vengono mostrati nella tab "Movimenti & versamenti".
    // I titoli già pagati sono visibili solo nello "Storico rimesse".
    const righeAttive = [...daVersare, ...pagamenti].sort(
        (a, b) => (a.data || "").localeCompare(b.data || ""),
    );
    const importoSel = incassi
        .filter((r) => selected.has(r.titolo_id))
        .reduce((s, r) => s + (r.dare || 0), 0);

    const stampaSelezionati = async () => {
        try {
            const r = await api.post(
                `/stampa/compagnie/${compagnia.id}/titoli-selezionati`,
                { titoli_ids: Array.from(selected) },
                { responseType: "blob" },
            );
            const url = URL.createObjectURL(r.data);
            window.open(url, "_blank");
        } catch (e) {
            alert(e.response?.data?.detail || "Errore stampa");
        }
    };

    const toggle = (id) => setSelected((p) => {
        const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n;
    });
    const toggleAll = () => {
        if (selected.size > 0) setSelected(new Set());
        else setSelected(new Set(daVersare.map((r) => r.titolo_id)));
    };

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

            <Tabs value={tab} onValueChange={setTab}>
                <TabsList className="mb-3">
                    <TabsTrigger value="movimenti" data-testid="ec-tab-movimenti">
                        <FileText size={13} className="mr-1" />Movimenti & versamenti
                    </TabsTrigger>
                    <TabsTrigger value="storico" data-testid="ec-tab-storico">
                        <History size={13} className="mr-1" />Storico rimesse
                    </TabsTrigger>
                </TabsList>
                <TabsContent value="movimenti">

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
                    <div>
                        <Label>Collaboratore</Label>
                        <Select value={collaboratoreId} onValueChange={setCollaboratoreId}>
                            <SelectTrigger className="w-56" data-testid="ec-collab"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Tutti</SelectItem>
                                {collaboratori.map((c) => (
                                    <SelectItem key={c.id} value={c.id}>{c.name || c.email}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
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
                {selected.size > 0 && (
                    <div className="mt-3 flex items-center gap-3 p-2 bg-amber-50 border border-amber-200 rounded">
                        <span className="text-sm font-medium text-amber-900">
                            {selected.size} titoli selezionati · Totale: <span className="num">{fmtEur(importoSel)}</span>
                        </span>
                        <div className="ml-auto flex gap-2">
                            <Button size="sm" variant="outline"
                                onClick={stampaSelezionati} data-testid="ec-stampa-selezionati">
                                <Printer size={13} className="mr-1" />Stampa selezionati
                            </Button>
                            <Button size="sm" className="bg-emerald-700 hover:bg-emerald-800"
                                onClick={() => setPayOpen(true)} data-testid="ec-paga-btn">
                                <Coins size={13} className="mr-1" />Paga compagnia
                            </Button>
                        </div>
                    </div>
                )}
            </Card>

            <div className="tbl-scroll bg-white" style={{ "--c1-w": "40px", "--c2-w": "140px" }}>
                {!data ? <Loading /> : righeAttive.length === 0 ? <Empty message="Nessun titolo da versare nel periodo (i titoli pagati sono nello Storico rimesse)" /> : (
                    <table className="tbl freeze-3 w-full min-w-[1100px]">
                        <thead>
                            <tr>
                                <th className="w-10 text-center">
                                    <input type="checkbox" onChange={toggleAll}
                                        checked={selected.size > 0 && selected.size === daVersare.length}
                                        ref={(el) => { if (el) el.indeterminate = selected.size > 0 && selected.size < daVersare.length; }}
                                        data-testid="ec-check-all" />
                                </th>
                                <th>Data</th>
                                <th>Tipo</th>
                                <th>Polizza</th>
                                <th>Contraente</th>
                                <th>Collaboratore</th>
                                <th>Ramo</th>
                                <th className="text-right">Lordo €</th>
                                <th className="text-right">Provv. €</th>
                                <th className="text-right">Dare €</th>
                                <th className="text-right">Avere €</th>
                            </tr>
                        </thead>
                        <tbody>
                            {righeAttive.map((r, i) => (
                                <tr key={r._movimento_id || `${r.data}-${r.tipo}-${i}`}>
                                    <td className="text-center">
                                        {r.tipo === "incasso" && (
                                            <input type="checkbox" checked={selected.has(r.titolo_id)}
                                                onChange={() => toggle(r.titolo_id)}
                                                data-testid={`ec-check-${r.titolo_id}`} />
                                        )}
                                    </td>
                                    <td className="num text-xs">{fmtDate(r.data)}</td>
                                    <td><span className={`badge ${r.tipo === "incasso" ? "badge-info" : "badge-success"}`}>{r.tipo}</span></td>
                                    <td className="font-mono text-xs">{r.polizza || "-"}</td>
                                    <td className="text-xs">{r.contraente || "-"}</td>
                                    <td className="text-xs text-sky-700">{r.collaboratore || "-"}</td>
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
                                <td colSpan="9" className="text-right">TOTALI ATTIVI</td>
                                <td className="num text-right">{fmtEur(daVersare.reduce((s, r) => s + (r.dare || 0), 0))}</td>
                                <td className="num text-right">{fmtEur(pagamenti.reduce((s, r) => s + (r.avere || 0), 0))}</td>
                            </tr>
                        </tfoot>
                    </table>
                )}
            </div>

            {payOpen && (
                <PagamentoDialog
                    compagnia={compagnia}
                    titoliIds={Array.from(selected)}
                    totale={importoSel}
                    conti={conti}
                    onClose={(refresh) => {
                        setPayOpen(false);
                        if (refresh) load();
                    }}
                />
            )}
                </TabsContent>
                <TabsContent value="storico">
                    <StoricoRimesseCompagnia compagniaId={compagnia.id} />
                </TabsContent>
            </Tabs>
        </div>
    );
}

function StoricoRimesseCompagnia({ compagniaId }) {
    const [data, setData] = useState(null);
    const [dal, setDal] = useState("");
    const [al, setAl] = useState("");
    const [expanded, setExpanded] = useState(new Set());

    const load = useCallback(() => {
        const params = { dal: dal || undefined, al: al || undefined };
        api.get(`/compagnie/${compagniaId}/rimesse-storico`, { params })
            .then((r) => setData(r.data));
    }, [compagniaId, dal, al]);
    useEffect(() => { load(); }, [load]);

    const toggle = (id) => setExpanded((p) => {
        const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n;
    });

    return (
        <div data-testid="ec-storico-tab">
            <Card className="p-4 border-slate-200 mb-3">
                <div className="flex items-end gap-3 flex-wrap">
                    <div>
                        <Label>Dal</Label>
                        <Input type="date" value={dal} onChange={(e) => setDal(e.target.value)} data-testid="ec-stor-dal" />
                    </div>
                    <div>
                        <Label>Al</Label>
                        <Input type="date" value={al} onChange={(e) => setAl(e.target.value)} data-testid="ec-stor-al" />
                    </div>
                    <Button onClick={load} data-testid="ec-stor-applica">Applica</Button>
                    {data && (
                        <div className="ml-auto text-sm">
                            <span className="text-slate-500">Rimesse:</span>{" "}
                            <span className="font-bold">{data.n_rimesse}</span>
                            <span className="mx-3 text-slate-300">·</span>
                            <span className="text-slate-500">Totale pagato:</span>{" "}
                            <span className="font-bold num text-emerald-700">{fmtEur(data.totale_pagato)}</span>
                        </div>
                    )}
                </div>
            </Card>
            <Card className="border-slate-200 overflow-hidden">
                {!data ? <Loading /> : data.rimesse.length === 0 ? <Empty message="Nessuna rimessa registrata" /> : (
                    <table className="tbl w-full">
                        <thead>
                            <tr>
                                <th className="w-8"></th>
                                <th>Data</th>
                                <th>Descrizione</th>
                                <th className="text-right">N. titoli</th>
                                <th className="text-right">Importo</th>
                                <th className="text-center">Allegati</th>
                                <th className="text-center">Stampa</th>
                            </tr>
                        </thead>
                        <tbody>
                            {data.rimesse.map((r) => (
                                <RowRimessa key={r.id} r={r} expanded={expanded.has(r.id)} onToggle={() => toggle(r.id)} onChange={load} />
                            ))}
                        </tbody>
                    </table>
                )}
            </Card>
        </div>
    );
}

function RowRimessa({ r, expanded, onToggle, onChange }) {
    return (
        <>
            <tr className="cursor-pointer hover:bg-slate-50" onClick={onToggle} data-testid={`ec-stor-row-${r.id}`}>
                <td className="text-center">
                    {expanded ? <ChevronDown size={14} className="inline" /> : <ChevronRight size={14} className="inline" />}
                </td>
                <td className="num text-xs">{fmtDate(r.data_movimento)}</td>
                <td className="text-sm">{r.descrizione || "—"}</td>
                <td className="num text-right">{r.n_titoli}</td>
                <td className="num text-right font-semibold text-emerald-700">{fmtEur(r.importo)}</td>
                <td className="text-center" onClick={(e) => e.stopPropagation()}>
                    <AllegatiCell
                        entita_tipo="movimento"
                        entita_id={r.id}
                        count={r.n_allegati}
                        hint="Allega fattura/distinta"
                        onChange={onChange}
                    />
                </td>
                <td className="text-center" onClick={(e) => e.stopPropagation()}>
                    <a
                        href={`${API_BASE}/stampa/rimessa/${r.id}`}
                        target="_blank" rel="noreferrer"
                        title="Stampa estratto conto compagnia"
                        data-testid={`ec-stor-stampa-${r.id}`}
                    >
                        <Button size="sm" variant="outline" className="h-7 px-2">
                            <Printer size={12} />
                        </Button>
                    </a>
                </td>
            </tr>
            {expanded && (
                <tr className="bg-slate-50">
                    <td colSpan={7} className="p-3">
                        <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
                            Titoli versati ({r.titoli?.length || 0})
                        </div>
                        {(!r.titoli || r.titoli.length === 0) ? (
                            <div className="text-xs text-slate-400">Nessun titolo collegato.</div>
                        ) : (
                            <table className="tbl w-full text-xs">
                                <thead>
                                    <tr>
                                        <th>Polizza</th>
                                        <th>Ramo</th>
                                        <th>Contraente</th>
                                        <th>Data incasso</th>
                                        <th className="text-right">Lordo €</th>
                                        <th className="text-right">Provv. €</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {r.titoli.map((t) => (
                                        <tr key={t.id}>
                                            <td className="font-mono">{t.numero_polizza || "—"}</td>
                                            <td>{t.ramo || "—"}</td>
                                            <td>{t.contraente_nome || "—"}</td>
                                            <td className="num">{fmtDate(t.data_incasso)}</td>
                                            <td className="num text-right">{fmtEur(t.importo_lordo)}</td>
                                            <td className="num text-right text-slate-500">{fmtEur(t.provvigioni)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </td>
                </tr>
            )}
        </>
    );
}

function PagamentoDialog({ compagnia, titoliIds, totale, conti, onClose }) {
    const [data, setData] = useState(new Date().toISOString().slice(0, 10));
    const [descr, setDescr] = useState(`Versamento ${compagnia.ragione_sociale} — ${titoliIds.length} titoli`);
    const [mezzo, setMezzo] = useState("");
    const [saving, setSaving] = useState(false);

    const conferma = async () => {
        setSaving(true);
        try {
            await api.post(`/compagnie/${compagnia.id}/paga-titoli`, {
                titoli_ids: titoliIds,
                mezzo_pagamento: mezzo,
                data_movimento: data,
                descrizione: descr,
            });
            onClose(true);
        } catch (e) {
            alert(e.response?.data?.detail || "Errore");
        } finally { setSaving(false); }
    };

    return (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center" data-testid="ec-pay-dialog">
            <Card className="bg-white p-6 max-w-md w-full">
                <h3 className="font-semibold text-lg mb-3">Pagamento compagnia</h3>
                <p className="text-sm text-slate-600 mb-4">
                    Versare a <strong>{compagnia.ragione_sociale}</strong>{" "}
                    <span className="num font-semibold text-emerald-700">{fmtEur(totale)}</span>{" "}
                    per {titoliIds.length} titoli.
                </p>
                <div className="space-y-3">
                    <div>
                        <Label>Data movimento</Label>
                        <Input type="date" value={data} onChange={(e) => setData(e.target.value)} />
                    </div>
                    <div>
                        <Label>Tipo pagamento</Label>
                        <SelectTipoPagamento
                            value={mezzo}
                            onChange={setMezzo}
                            testid="ec-pay-mezzo"
                        />
                        <div className="text-[10px] text-slate-500 mt-1">
                            Il conto/banca da cui esce il pagamento è derivato dal tipo selezionato.
                        </div>
                    </div>
                    <div>
                        <Label>Descrizione</Label>
                        <Input value={descr} onChange={(e) => setDescr(e.target.value)} />
                    </div>
                </div>
                <div className="flex gap-2 justify-end mt-5">
                    <Button variant="outline" onClick={() => onClose(false)}>Annulla</Button>
                    <Button onClick={conferma} disabled={saving} className="bg-emerald-700 hover:bg-emerald-800" data-testid="ec-pay-confirm">
                        {saving ? "Salvataggio…" : "Conferma versamento"}
                    </Button>
                </div>
            </Card>
        </div>
    );
}
