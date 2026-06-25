import { useEffect, useState } from "react";
import { api, fmtEur, API_BASE } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Loading } from "@/components/Shared";
import { Printer, Lock, Mail, Calendar as CalIcon, History, Unlock, AlertCircle } from "lucide-react";
import { toast } from "sonner";
import AllegatiCell from "@/components/AllegatiCell";

const today = () => new Date().toISOString().slice(0, 10);

const fmt = (n, withZero = false) => {
    if (n === null || n === undefined) return "";
    if (!withZero && n === 0) return "";
    return fmtEur(n);
};

export default function BrogliaccioTab() {
    const [data, setData] = useState(today());
    const [b, setB] = useState(null);
    const [busy, setBusy] = useState(false);
    const [chiudiOpen, setChiudiOpen] = useState(false);
    const [riapriOpen, setRiapriOpen] = useState(false);
    const [riapriMotivo, setRiapriMotivo] = useState("");
    const [storicoOpen, setStoricoOpen] = useState(false);
    const [storico, setStorico] = useState([]);

    const load = () => {
        api.get("/contabilita/brogliaccio", { params: { data } }).then((r) => setB(r.data));
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [data]);

    const stampa = () => {
        const link = document.createElement("a");
        link.href = `${API_BASE}/contabilita/brogliaccio/stampa?data=${data}`;
        link.target = "_blank";
        document.body.appendChild(link); link.click(); link.remove();
    };

    const chiudiGiornata = async (inviaCommercialista) => {
        setBusy(true);
        try {
            const r = await api.post("/contabilita/chiusura-giorno", {
                data, invia_commercialista: inviaCommercialista,
            });
            if (inviaCommercialista) {
                const inv = r.data.invio_commercialista;
                if (inv?.ok) toast.success(`Chiusura completata e inviata a ${inv.inviata_a}`);
                else toast.warning(`Chiusura ok ma invio fallito: ${inv?.errore || ""}`);
            } else {
                toast.success(`Giornata ${data} chiusa correttamente`);
            }
            setChiudiOpen(false);
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        } finally { setBusy(false); }
    };

    const inviaCommercialista = async () => {
        if (!b?.chiusura?.id) return;
        setBusy(true);
        try {
            const r = await api.post(`/contabilita/chiusura-giorno/${b.chiusura.id}/invia`);
            if (r.data.ok) toast.success(`Inviato a ${r.data.inviata_a}`);
            else toast.error(`Invio fallito: ${r.data.errore}`);
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        } finally { setBusy(false); }
    };

    const riapriGiornata = async () => {
        if (!b?.chiusura?.id) return;
        if (!riapriMotivo.trim()) { toast.error("Inserisci il motivo della riapertura"); return; }
        setBusy(true);
        try {
            await api.post(`/contabilita/chiusura-giorno/${b.chiusura.id}/riapri`, { motivo: riapriMotivo });
            toast.success("Giornata riaperta - puoi nuovamente modificare i movimenti");
            setRiapriOpen(false); setRiapriMotivo("");
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        } finally { setBusy(false); }
    };

    const showStorico = async () => {
        const r = await api.get("/contabilita/chiusure-giorno");
        setStorico(r.data);
        setStoricoOpen(true);
    };

    if (!b) return <div className="mt-4"><Loading /></div>;

    const conti = b.conti_cassa || [];

    return (
        <div className="mt-4 space-y-4" data-testid="brogliaccio-tab">
            {/* Toolbar */}
            <Card className="p-4 border-slate-200">
                <div className="flex flex-wrap items-center gap-3">
                    <CalIcon size={18} className="text-slate-400" />
                    <div>
                        <Label className="text-[10px] text-slate-500">Data brogliaccio</Label>
                        <Input
                            type="date" value={data} onChange={(e) => setData(e.target.value)}
                            className="w-44" data-testid="brogliaccio-data"
                        />
                    </div>
                    <Button variant="outline" size="sm" onClick={() => setData(today())} data-testid="brogliaccio-oggi">Oggi</Button>

                    {b.chiusa && (
                        <div className="bg-emerald-50 border border-emerald-300 px-3 py-1.5 rounded-md text-xs text-emerald-800 inline-flex items-center gap-1.5" data-testid="brogliaccio-chiusa">
                            <Lock size={13} />
                            <b>Giornata chiusa</b> il {(b.chiusura?.created_at || "").slice(0, 19).replace("T", " ")} da {b.chiusura?.closed_by_name}
                            {b.chiusura?.email_inviata_at && (
                                <span className="ml-2">· Inviata a <b>{b.chiusura.email_inviata_a}</b></span>
                            )}
                            {b.chiusura?.email_errore && (
                                <span className="ml-2 text-rose-700">· Errore invio: {b.chiusura.email_errore}</span>
                            )}
                        </div>
                    )}

                    <div className="ml-auto flex gap-2">
                        <Button variant="outline" onClick={stampa} data-testid="brogliaccio-stampa">
                            <Printer size={14} className="mr-1" /> Stampa PDF
                        </Button>
                        {b.chiusa ? (
                            <>
                                <Button
                                    variant="outline" onClick={inviaCommercialista} disabled={busy}
                                    data-testid="brogliaccio-invia"
                                >
                                    <Mail size={14} className="mr-1" /> Invia commercialista
                                </Button>
                                <Button
                                    variant="outline" onClick={() => setRiapriOpen(true)} disabled={busy}
                                    data-testid="brogliaccio-riapri"
                                >
                                    <Unlock size={14} className="mr-1" /> Riapri
                                </Button>
                            </>
                        ) : (
                            <Button
                                onClick={() => setChiudiOpen(true)}
                                disabled={busy || (b.righe?.length || 0) === 0}
                                className="bg-emerald-600 hover:bg-emerald-700"
                                data-testid="brogliaccio-chiudi"
                            >
                                <Lock size={14} className="mr-1" /> Chiudi giornata
                            </Button>
                        )}
                        <Button variant="outline" onClick={showStorico} data-testid="brogliaccio-storico">
                            <History size={14} className="mr-1" /> Storico
                        </Button>
                    </div>
                </div>
            </Card>

            {/* Tabella brogliaccio */}
            <Card className="border-slate-200 overflow-x-auto">
                {(b.righe?.length || 0) === 0 ? (
                    <div className="p-10 text-center text-sm text-slate-500">
                        <AlertCircle size={32} className="mx-auto text-slate-300 mb-2" />
                        Nessun movimento registrato per il {data}
                    </div>
                ) : (
                    <table className="tbl w-full text-xs min-w-[1200px]" data-testid="brogliaccio-tbl">
                        <thead>
                            <tr className="bg-slate-900 text-white">
                                <th className="text-left px-2 py-2">Descrizione</th>
                                <th className="text-right px-2 py-2">Totale</th>
                                <th className="text-right px-2 py-2">Provv</th>
                                <th className="text-right px-2 py-2">Saldo</th>
                                <th className="text-right px-2 py-2">Sospesi</th>
                                <th className="text-right px-2 py-2">Spese</th>
                                {conti.map((c) => (
                                    <th key={c.id} className="text-right px-2 py-2 whitespace-nowrap" title={c.nome}>
                                        {c.nome}
                                    </th>
                                ))}
                                <th className="w-10 text-center px-2 py-2"></th>
                            </tr>
                        </thead>
                        <tbody>
                            {b.righe.map((r) => (
                                <tr key={r.id} className="hover:bg-slate-50" data-testid={`brog-row-${r.id}`}>
                                    <td className="px-2 py-1.5">
                                        <div className="font-medium text-slate-800">
                                            {r.contraente || r.descrizione || "—"}
                                        </div>
                                        <div className="text-[10px] text-slate-500 flex flex-wrap gap-x-2">
                                            {r.numero_polizza && <span className="num">N. {r.numero_polizza}</span>}
                                            {r.compagnia && <span>· {r.compagnia}</span>}
                                            {!r.numero_polizza && !r.compagnia && r.contraente && r.descrizione && <span>{r.descrizione}</span>}
                                        </div>
                                    </td>
                                    <td className={`num text-right px-2 ${r.totale >= 0 ? "text-emerald-700" : "text-rose-700"} font-medium`}>{fmt(r.totale)}</td>
                                    <td className="num text-right px-2 text-sky-700">{fmt(r.provv)}</td>
                                    <td className={`num text-right px-2 font-medium ${r.saldo < 0 ? "text-rose-700" : ""}`}>{fmt(r.saldo)}</td>
                                    <td className={`num text-right px-2 ${r.crediti > 0 ? "text-amber-700" : r.crediti < 0 ? "text-emerald-700" : ""}`}>{fmt(r.crediti)}</td>
                                    <td className="num text-right px-2 text-rose-600">{fmt(r.spese)}</td>
                                    {conti.map((c) => {
                                        const v = r.per_conto?.[c.id];
                                        return (
                                            <td key={c.id} className={`num text-right px-2 ${v > 0 ? "text-emerald-600" : v < 0 ? "text-rose-600" : "text-slate-300"}`}>
                                                {fmt(v)}
                                            </td>
                                        );
                                    })}
                                    <td className="text-center px-2">
                                        <AllegatiCell
                                            entita_tipo="movimento"
                                            entita_id={r.id}
                                            count={r.allegati_count}
                                            canEdit={!b.chiusa}
                                            hint="Allega ricevuta / fattura"
                                            onChange={load}
                                        />
                                    </td>
                                </tr>
                            ))}
                            {/* TOTALE GIORNATA */}
                            {b.totali_giornata && (
                                <tr className="bg-amber-100 font-bold border-t-2 border-slate-900">
                                    <td className="px-2 py-2">TOTALE GIORNATA</td>
                                    <td className="num text-right px-2">{fmt(b.totali_giornata.totale, true)}</td>
                                    <td className="num text-right px-2">{fmt(b.totali_giornata.provv, true)}</td>
                                    <td className="num text-right px-2">{fmt(b.totali_giornata.saldo, true)}</td>
                                    <td className="num text-right px-2">{fmt(b.totali_giornata.crediti, true)}</td>
                                    <td className="num text-right px-2">{fmt(b.totali_giornata.spese, true)}</td>
                                    {conti.map((c) => (
                                        <td key={c.id} className="num text-right px-2">
                                            {fmt(b.totali_giornata.per_conto?.[c.id], true)}
                                        </td>
                                    ))}
                                    <td></td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                )}
            </Card>

            {/* Riepilogo conti */}
            <Card className="border-slate-200">
                <div className="px-4 py-2 bg-slate-50 border-b border-slate-200">
                    <div className="text-sm font-semibold uppercase tracking-wider text-slate-700">Riepilogo conti</div>
                </div>
                <table className="tbl w-full text-xs">
                    <thead>
                        <tr className="bg-slate-900 text-white">
                            <th className="text-left px-3 py-2">Descrizione</th>
                            <th className="text-right px-3 py-2">Imp. Precedente</th>
                            <th className="text-right px-3 py-2">Imp. Giornata</th>
                            <th className="text-right px-3 py-2">Totale Periodo</th>
                        </tr>
                    </thead>
                    <tbody>
                        {(b.conti_riepilogo || []).map((c) => (
                            <tr key={c.id} data-testid={`riep-${c.id}`}>
                                <td className="px-3 py-1.5 font-medium">{c.nome}</td>
                                <td className="num text-right px-3">{fmt(c.imp_precedente, true)}</td>
                                <td className={`num text-right px-3 ${c.imp_giornata > 0 ? "text-emerald-700" : c.imp_giornata < 0 ? "text-rose-700" : ""}`}>{fmt(c.imp_giornata, true)}</td>
                                <td className="num text-right px-3 font-semibold">{fmt(c.totale_periodo, true)}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </Card>

            {/* KPI cards */}
            {b.riepilogo_kpi && (
                <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2" data-testid="brog-kpi">
                    <KPI label="Entrate" v={b.riepilogo_kpi.entrate} accent="emerald" />
                    <KPI label="Provvigioni" v={b.riepilogo_kpi.provvigioni} accent="sky" />
                    <KPI label="Sospesi" v={b.riepilogo_kpi.crediti} accent="amber" />
                    <KPI label="Rimesse" v={b.riepilogo_kpi.rimesse} accent="violet" />
                    <KPI label="Sconti" v={b.riepilogo_kpi.sconti} accent="orange" />
                    <KPI label="Spese" v={b.riepilogo_kpi.spese} accent="rose" />
                    <KPI label="Saldo Cassa Cmp." v={b.liquidita?.saldo_cassa_compagnie ?? 0} accent="slate" bold />
                </div>
            )}

            {/* Liquidità */}
            {b.liquidita && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3" data-testid="brog-liquidita">
                    <Card className="p-5 border-emerald-200 border-l-4 border-l-emerald-500 bg-emerald-50/30">
                        <div className="text-xs uppercase tracking-wider text-emerald-800 mb-1">Liquidità Disponibile</div>
                        <div className="text-3xl font-bold text-emerald-700 num">{fmt(b.liquidita.liquidita_disponibile, true)}</div>
                        <div className="text-[11px] text-slate-500 mt-2">
                            {fmt(b.liquidita.sum_conti, true)} (conti) − {fmt(b.liquidita.sospesi_attivi, true)} (sospesi/anticipi) − {fmt(b.liquidita.saldo_cassa_compagnie, true)} (debito vs. compagnie)
                        </div>
                    </Card>
                    <Card className="p-5 border-sky-200 border-l-4 border-l-sky-500 bg-sky-50/30">
                        <div className="text-xs uppercase tracking-wider text-sky-800 mb-1">Liquidità Postera</div>
                        <div className="text-3xl font-bold text-sky-700 num">{fmt(b.liquidita.liquidita_postera, true)}</div>
                        <div className="text-[11px] text-slate-500 mt-2">
                            {fmt(b.liquidita.sum_conti, true)} (conti) − {fmt(b.liquidita.saldo_cassa_compagnie, true)} (debito vs. compagnie)
                        </div>
                    </Card>
                </div>
            )}

            {/* Saldi per compagnia (cumulativo periodo) */}
            {(b.saldi_compagnie || []).length > 0 && (
                <Card className="border-slate-200">
                    <div className="px-4 py-2 bg-slate-50 border-b border-slate-200">
                        <div className="text-sm font-semibold uppercase tracking-wider text-slate-700">
                            Saldo Cassa per Compagnia
                            <span className="ml-2 text-[11px] font-normal text-slate-500 normal-case">
                                (cumulativo fino al {data} - cresce con gli incassi, si azzera con i pagamenti E/C)
                            </span>
                        </div>
                    </div>
                    <table className="tbl w-full text-xs">
                        <thead>
                            <tr className="bg-slate-900 text-white">
                                <th className="text-left px-3 py-2">Compagnia</th>
                                <th className="text-center px-3 py-2">Regime</th>
                                <th className="text-right px-3 py-2">Saldo cassa attuale</th>
                            </tr>
                        </thead>
                        <tbody>
                            {b.saldi_compagnie.map((s) => (
                                <tr key={s.compagnia_id} data-testid={`saldo-comp-${s.compagnia_id}`}>
                                    <td className="px-3 py-1.5 font-medium">{s.compagnia}</td>
                                    <td className="text-center text-[10px]">
                                        {s.trattiene_provvigioni
                                            ? <span className="badge badge-success">Tratteniamo provv.</span>
                                            : <span className="badge badge-warning">No trattenute</span>}
                                    </td>
                                    <td className={`num text-right px-3 font-bold ${s.saldo_cassa > 0 ? "text-rose-700" : s.saldo_cassa < 0 ? "text-emerald-700" : "text-slate-500"}`}>
                                        {fmt(s.saldo_cassa, true)}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </Card>
            )}

            {/* Dialog chiudi giornata */}
            <Dialog open={chiudiOpen} onOpenChange={setChiudiOpen}>
                <DialogContent>
                    <DialogHeader><DialogTitle>Chiudi giornata {data}</DialogTitle></DialogHeader>
                    <div className="py-2 space-y-3 text-sm">
                        <div className="bg-amber-50 border border-amber-200 rounded p-3 text-amber-900 text-xs">
                            <b>Attenzione:</b> dopo la chiusura, i movimenti del giorno saranno congelati. Per modificarli serve <b>riaprire</b> la giornata (solo admin).
                        </div>
                        <div>{b.righe?.length || 0} movimenti verranno chiusi.</div>
                        <div>Totale giornata: <b className="num">{fmtEur(b.totali_giornata?.totale || 0)}</b></div>
                    </div>
                    <DialogFooter className="gap-2 flex-wrap">
                        <Button variant="outline" onClick={() => setChiudiOpen(false)}>Annulla</Button>
                        <Button onClick={() => chiudiGiornata(false)} disabled={busy} className="bg-emerald-600 hover:bg-emerald-700" data-testid="chiudi-only">
                            <Lock size={14} className="mr-1" /> Solo chiudi
                        </Button>
                        <Button onClick={() => chiudiGiornata(true)} disabled={busy} className="bg-sky-700 hover:bg-sky-800" data-testid="chiudi-invia">
                            <Mail size={14} className="mr-1" /> Chiudi e invia commercialista
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Dialog riapri */}
            <Dialog open={riapriOpen} onOpenChange={setRiapriOpen}>
                <DialogContent>
                    <DialogHeader><DialogTitle>Riapri giornata {data}</DialogTitle></DialogHeader>
                    <div className="py-2 space-y-3">
                        <div className="bg-rose-50 border border-rose-200 rounded p-3 text-rose-900 text-xs">
                            La riapertura sblocca i movimenti del giorno per la modifica. Operazione tracciata nel log attività.
                        </div>
                        <div>
                            <Label>Motivo riapertura *</Label>
                            <Input
                                value={riapriMotivo} onChange={(e) => setRiapriMotivo(e.target.value)}
                                placeholder="Es. correzione importo movimento X"
                                data-testid="riapri-motivo"
                            />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setRiapriOpen(false)}>Annulla</Button>
                        <Button onClick={riapriGiornata} disabled={busy} className="bg-rose-600 hover:bg-rose-700" data-testid="riapri-conferma">
                            Riapri giornata
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Dialog storico chiusure */}
            <Dialog open={storicoOpen} onOpenChange={setStoricoOpen}>
                <DialogContent className="max-w-3xl">
                    <DialogHeader><DialogTitle>Storico chiusure giornaliere</DialogTitle></DialogHeader>
                    <div className="max-h-[70vh] overflow-y-auto">
                        <table className="tbl w-full text-xs">
                            <thead>
                                <tr>
                                    <th>Data</th>
                                    <th>Chiusa da</th>
                                    <th>Chiusa il</th>
                                    <th>Email</th>
                                    <th>Stato</th>
                                    <th></th>
                                </tr>
                            </thead>
                            <tbody>
                                {storico.length === 0 && <tr><td colSpan="6" className="text-center text-slate-400 py-6">Nessuna chiusura</td></tr>}
                                {storico.map((c) => (
                                    <tr key={c.id}>
                                        <td className="num font-semibold">{c.data}</td>
                                        <td>{c.closed_by_name}</td>
                                        <td className="num text-xs">{(c.created_at || "").slice(0, 19).replace("T", " ")}</td>
                                        <td className="text-xs">{c.email_inviata_a || (c.email_errore ? <span className="text-rose-600">Errore</span> : "—")}</td>
                                        <td>
                                            {c.riaperta_at
                                                ? <span className="badge badge-warning">riaperta</span>
                                                : <span className="badge badge-success">chiusa</span>}
                                        </td>
                                        <td>
                                            <a
                                                href={`${API_BASE}/contabilita/chiusura-giorno/${c.id}/pdf`}
                                                target="_blank" rel="noreferrer"
                                                className="text-sky-700 hover:underline text-xs"
                                            >Scarica PDF</a>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </DialogContent>
            </Dialog>
        </div>
    );
}

function KPI({ label, v, accent = "slate", bold }) {
    const colors = {
        emerald: "border-l-emerald-500",
        sky: "border-l-sky-500",
        amber: "border-l-amber-500",
        violet: "border-l-violet-500",
        orange: "border-l-orange-500",
        rose: "border-l-rose-500",
        slate: "border-l-slate-700",
    };
    return (
        <Card className={`p-3 border-slate-200 border-l-4 ${colors[accent]}`}>
            <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
            <div className={`num ${bold ? "text-xl font-bold text-slate-900" : "text-base font-semibold text-slate-800"}`}>
                {fmtEur(v || 0)}
            </div>
        </Card>
    );
}
