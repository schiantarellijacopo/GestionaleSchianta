import { useEffect, useState, useCallback } from "react";
import { api, fmtEur, fmtDate } from "@/lib/api";
import { PageHeader, Empty, Loading } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { Landmark, Search, RotateCcw, Printer, FileSpreadsheet } from "lucide-react";
import { API_BASE } from "@/lib/api";
import DateInputIt from "@/components/DateInputIt";

export default function Banche() {
    const [saldi, setSaldi] = useState(null);
    const [conto, setConto] = useState("all");
    const [dal, setDal] = useState("");
    const [al, setAl] = useState("");
    const [cliente, setCliente] = useState("");
    const [numeroPolizza, setNumeroPolizza] = useState("");
    const [descrizione, setDescrizione] = useState("");
    const [collab, setCollab] = useState("all");
    const [collaboratori, setCollaboratori] = useState([]);
    const [mov, setMov] = useState(null);

    useEffect(() => {
        api.get("/contabilita/banche/saldi").then((r) => setSaldi(r.data)).catch(() => {});
        api.get("/collaboratori").then((r) => setCollaboratori(
            (r.data || []).filter((u) => ["collaboratore", "dipendente"].includes(u.role))
        )).catch(() => {});
    }, []);

    const loadMov = useCallback(() => {
        setMov(null);
        const params = {};
        if (conto !== "all") params.conto_cassa_id = conto;
        if (dal) params.dal = dal;
        if (al) params.al = al;
        if (cliente.trim()) params.cliente = cliente.trim();
        if (numeroPolizza.trim()) params.numero_polizza = numeroPolizza.trim();
        if (descrizione.trim()) params.descrizione = descrizione.trim();
        if (collab !== "all") params.collaboratore_id = collab;
        api.get("/contabilita/banche/movimenti", { params }).then((r) => setMov(r.data)).catch(() => setMov({ movimenti: [] }));
    }, [conto, dal, al, cliente, numeroPolizza, descrizione, collab]);

    useEffect(() => { loadMov(); /* eslint-disable-next-line */ }, [conto]);

    const reset = () => {
        setConto("all"); setDal(""); setAl(""); setCliente(""); setNumeroPolizza(""); setDescrizione(""); setCollab("all");
        setTimeout(loadMov, 0);
    };

    const contiAttivi = (saldi?.conti || []).filter((c) => c.attivo);
    const contiTutti = saldi?.conti || [];

    const buildQuery = () => {
        const p = new URLSearchParams();
        if (conto !== "all") p.set("conto_cassa_id", conto);
        if (dal) p.set("dal", dal);
        if (al) p.set("al", al);
        if (cliente.trim()) p.set("cliente", cliente.trim());
        if (numeroPolizza.trim()) p.set("numero_polizza", numeroPolizza.trim());
        if (descrizione.trim()) p.set("descrizione", descrizione.trim());
        if (collab !== "all") p.set("collaboratore_id", collab);
        return p.toString();
    };
    const exportPdf = () => window.open(`${API_BASE}/contabilita/banche/movimenti/stampa?${buildQuery()}`, "_blank");
    const exportXlsx = () => window.open(`${API_BASE}/contabilita/banche/movimenti/export.xlsx?${buildQuery()}`, "_blank");

    return (
        <div data-testid="banche-page">
            <PageHeader
                title="Banche"
                subtitle="Saldo e movimentazione di ogni conto/banca"
                actions={
                    <div className="flex gap-2">
                        <Button variant="outline" onClick={exportPdf} data-testid="banche-pdf">
                            <Printer size={14} className="mr-1" /> PDF
                        </Button>
                        <Button variant="outline" onClick={exportXlsx} data-testid="banche-xlsx">
                            <FileSpreadsheet size={14} className="mr-1" /> Excel
                        </Button>
                    </div>
                }
            />

            {/* Card saldi per banca */}
            {!saldi ? <Loading /> : (
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 mb-5" data-testid="banche-saldi">
                    {contiAttivi.map((c) => (
                        <button
                            key={c.id}
                            onClick={() => setConto(c.id)}
                            className={`text-left transition-all ${conto === c.id ? "ring-2 ring-sky-500" : ""}`}
                            data-testid={`banca-card-${c.id}`}
                        >
                            <Card className={`p-4 border-slate-200 border-l-4 ${c.saldo_attuale >= 0 ? "border-l-emerald-500" : "border-l-rose-500"} hover:shadow-md`}>
                                <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-slate-500 mb-1">
                                    <Landmark size={13} /> {c.nome}
                                </div>
                                <div className={`num text-2xl font-bold ${c.saldo_attuale >= 0 ? "text-emerald-700" : "text-rose-700"}`}>
                                    {fmtEur(c.saldo_attuale)}
                                </div>
                                <div className="text-[10px] text-slate-400 mt-1">
                                    Iniz. {fmtEur(c.saldo_iniziale)} · +{fmtEur(c.entrate)} · −{fmtEur(c.uscite)}
                                </div>
                            </Card>
                        </button>
                    ))}
                    <Card className="p-4 border-slate-200 border-l-4 border-l-slate-700 bg-slate-50">
                        <div className="text-xs uppercase tracking-wider text-slate-500 mb-1">Totale liquidità</div>
                        <div className="num text-2xl font-bold text-slate-900">{fmtEur(saldi.saldo_totale)}</div>
                    </Card>
                </div>
            )}

            {/* Filtri */}
            <Card className="p-4 border-slate-200 mb-4">
                <div className="flex items-end gap-3 flex-wrap">
                    <div>
                        <Label className="text-xs">Banca</Label>
                        <Select value={conto} onValueChange={setConto}>
                            <SelectTrigger className="w-52 h-9" data-testid="banche-f-conto"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Tutte le banche</SelectItem>
                                {contiTutti.map((c) => (
                                    <SelectItem key={c.id} value={c.id}>{c.nome}{c.attivo ? "" : " (non attivo)"}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <Label className="text-xs">Dal</Label>
                        <DateInputIt value={dal} onChange={setDal} className="w-32 h-9" data-testid="banche-f-dal" />
                    </div>
                    <div>
                        <Label className="text-xs">Al</Label>
                        <DateInputIt value={al} onChange={setAl} className="w-32 h-9" data-testid="banche-f-al" />
                    </div>
                    <div>
                        <Label className="text-xs">Cliente</Label>
                        <Input value={cliente} onChange={(e) => setCliente(e.target.value)} placeholder="Nome / cognome…" className="w-48 h-9" data-testid="banche-f-cliente" />
                    </div>
                    <div>
                        <Label className="text-xs">N. polizza</Label>
                        <Input value={numeroPolizza} onChange={(e) => setNumeroPolizza(e.target.value)} placeholder="Numero…" className="w-40 h-9" data-testid="banche-f-polizza" />
                    </div>
                    <div>
                        <Label className="text-xs">Descrizione</Label>
                        <Input value={descrizione} onChange={(e) => setDescrizione(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") loadMov(); }} placeholder="Es. Hera, bonifico…" className="w-48 h-9" data-testid="banche-f-descrizione" />
                    </div>
                    <div>
                        <Label className="text-xs">Collaboratore</Label>
                        <Select value={collab} onValueChange={setCollab}>
                            <SelectTrigger className="w-48 h-9" data-testid="banche-f-collab"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Tutti</SelectItem>
                                {collaboratori.map((c) => (
                                    <SelectItem key={c.id} value={c.id}>{c.name || c.email}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    <Button onClick={loadMov} className="bg-sky-700 hover:bg-sky-800 h-9" data-testid="banche-applica">
                        <Search size={14} className="mr-1" /> Applica
                    </Button>
                    <Button variant="outline" onClick={reset} className="h-9" data-testid="banche-reset">
                        <RotateCcw size={14} className="mr-1" /> Azzera
                    </Button>
                    {mov && (
                        <div className="ml-auto flex gap-5 text-sm">
                            <div><span className="text-slate-500">Entrate:</span> <span className="num font-bold text-emerald-700">{fmtEur(mov.totale_entrate)}</span></div>
                            <div><span className="text-slate-500">Uscite:</span> <span className="num font-bold text-rose-700">{fmtEur(mov.totale_uscite)}</span></div>
                            {mov.progressivo && (
                                <div><span className="text-slate-500">Saldo finale:</span> <span className="num font-bold">{fmtEur(mov.saldo_finale)}</span></div>
                            )}
                        </div>
                    )}
                </div>
            </Card>

            {/* Tabella movimenti */}
            <div className="tbl-scroll bg-white">
                {mov === null ? <Loading /> : (mov.movimenti || []).length === 0 ? (
                    <Empty message="Nessun movimento per i filtri selezionati" />
                ) : (
                    <table className="tbl w-full min-w-[1000px]" data-testid="banche-tbl">
                        <thead>
                            <tr>
                                <th>Data</th>
                                <th>Banca</th>
                                <th>Descrizione</th>
                                <th>Contraente</th>
                                <th>Polizza</th>
                                <th>Collaboratore</th>
                                <th className="text-right">Entrata €</th>
                                <th className="text-right">Uscita €</th>
                                {mov.progressivo && <th className="text-right">Saldo €</th>}
                            </tr>
                        </thead>
                        <tbody>
                            {mov.progressivo && mov.saldo_apertura !== null && (
                                <tr className="bg-slate-50 text-xs">
                                    <td colSpan={mov.progressivo ? 8 : 8} className="text-right font-medium text-slate-500">Saldo di apertura periodo</td>
                                    <td className="num text-right font-semibold">{fmtEur(mov.saldo_apertura)}</td>
                                </tr>
                            )}
                            {mov.movimenti.map((m) => (
                                <tr key={m.id} data-testid={`banche-row-${m.id}`}>
                                    <td className="num text-xs">{fmtDate(m.data_movimento)}</td>
                                    <td className="text-xs">{m.conto_nome || "—"}</td>
                                    <td className="text-xs">
                                        {m.descrizione || "—"}
                                        {m.categoria && <span className="ml-1 text-[10px] text-slate-400">· {m.categoria}</span>}
                                    </td>
                                    <td className="text-xs">{m.contraente || "—"}</td>
                                    <td className="font-mono text-xs">{m.numero_polizza || "—"}</td>
                                    <td className="text-xs text-sky-700">{m.collaboratore || "—"}</td>
                                    <td className="num text-right text-emerald-700 font-medium">{m.tipo === "entrata" ? fmtEur(m.importo) : ""}</td>
                                    <td className="num text-right text-rose-700 font-medium">{m.tipo === "uscita" ? fmtEur(m.importo) : ""}</td>
                                    {mov.progressivo && <td className="num text-right font-semibold">{fmtEur(m.saldo_progressivo)}</td>}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
}
