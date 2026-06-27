import { useEffect, useState } from "react";
import { api, fmtDate, fmtEur } from "@/lib/api";
import { PageHeader, Empty, Loading } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, Calendar, ArrowLeftRight, Printer, Trash2, Search } from "lucide-react";
import { toast } from "sonner";
import AllegatiCell from "@/components/AllegatiCell";
import BrogliaccioTab from "@/components/BrogliaccioTab";
import DatiCompagnieTab from "@/components/DatiCompagnieTab";
import ChiusuraGiornoBanner from "@/components/ChiusuraGiornoBanner";
import ChiusuraPill from "@/components/ChiusuraPill";
import { API_BASE } from "@/lib/api";

export default function Contabilita() {
    const [dal, setDal] = useState("");
    const [al, setAl] = useState("");
    const [primaNota, setPrimaNota] = useState(null);
    const [estrattoAna, setEstrattoAna] = useState("");
    const [estratto, setEstratto] = useState(null);
    const [anagrafiche, setAnagrafiche] = useState([]);
    const [open, setOpen] = useState(false);
    const [giroOpen, setGiroOpen] = useState(false);
    const [conti, setConti] = useState([]);

    const load = () => {
        const params = {};
        if (dal) params.dal = dal;
        if (al) params.al = al;
        api.get("/contabilita/prima-nota", { params }).then((r) => setPrimaNota(r.data));
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [dal, al]);
    useEffect(() => { api.get("/anagrafiche").then((r) => setAnagrafiche(r.data)); }, []);
    useEffect(() => { api.get("/librerie/conti-cassa").then((r) => setConti(r.data || [])); }, []);

    const caricaEstratto = (id) => {
        setEstrattoAna(id);
        if (id) api.get(`/contabilita/estratto-conto/${id}`).then((r) => setEstratto(r.data));
        else setEstratto(null);
    };

    return (
        <div data-testid="contabilita-page">
            <PageHeader
                title="Contabilità"
                subtitle="Prima nota, estratti conto, movimenti contabili"
                actions={
                    <div className="flex gap-2">
                        <Dialog open={giroOpen} onOpenChange={setGiroOpen}>
                            <DialogTrigger asChild>
                                <Button variant="outline" data-testid="giroconto-button" className="border-violet-300 text-violet-700 hover:bg-violet-50">
                                    <ArrowLeftRight size={16} className="mr-1" /> Giroconto
                                </Button>
                            </DialogTrigger>
                            <GirocontoDialog conti={conti} onClose={() => { setGiroOpen(false); load(); }} />
                        </Dialog>
                        <Dialog open={open} onOpenChange={setOpen}>
                            <DialogTrigger asChild>
                                <Button data-testid="mov-new-button" className="bg-sky-700 hover:bg-sky-800">
                                    <Plus size={16} className="mr-1" /> Nuovo movimento
                                </Button>
                            </DialogTrigger>
                            <NuovoMovimentoDialog anagrafiche={anagrafiche} onClose={() => { setOpen(false); load(); }} />
                        </Dialog>
                    </div>
                }
            />

            <Tabs defaultValue="brogliaccio">
                <TabsList className="bg-slate-100">
                    <TabsTrigger value="brogliaccio" data-testid="tab-brogliaccio">Brogliaccio (Prima nota)</TabsTrigger>
                    <TabsTrigger value="storico" data-testid="tab-storico-pn">Storico Prima Nota</TabsTrigger>
                    <TabsTrigger value="prima-nota" data-testid="tab-prima-nota">Movimenti (elenco)</TabsTrigger>
                    <TabsTrigger value="dati-compagnie" data-testid="tab-dati-compagnie">Dati Compagnie</TabsTrigger>
                    <TabsTrigger value="estratti" data-testid="tab-estratti">Estratto conto cliente</TabsTrigger>
                </TabsList>

                <TabsContent value="brogliaccio">
                    <BrogliaccioTab />
                </TabsContent>

                <TabsContent value="storico">
                    <StoricoPrimaNotaTab />
                </TabsContent>

                <TabsContent value="dati-compagnie">
                    <DatiCompagnieTab />
                </TabsContent>

                <TabsContent value="prima-nota">
                    <div className="flex items-center gap-3 mt-4 mb-4">
                        <Calendar size={16} className="text-slate-400" />
                        <Label className="text-xs">Dal</Label>
                        <Input type="date" value={dal} onChange={(e) => setDal(e.target.value)} className="w-44" />
                        <Label className="text-xs">Al</Label>
                        <Input type="date" value={al} onChange={(e) => setAl(e.target.value)} className="w-44" />
                    </div>

                    {primaNota && (
                        <div className="grid grid-cols-3 gap-4 mb-5">
                            <Card className="p-5 border-slate-200 border-l-4 border-l-emerald-500">
                                <div className="stat-label">Totale entrate</div>
                                <div className="stat-value text-emerald-700">{fmtEur(primaNota.totale_entrate)}</div>
                            </Card>
                            <Card className="p-5 border-slate-200 border-l-4 border-l-rose-500">
                                <div className="stat-label">Totale uscite</div>
                                <div className="stat-value text-rose-700">{fmtEur(primaNota.totale_uscite)}</div>
                            </Card>
                            <Card className="p-5 border-slate-200 border-l-4 border-l-sky-600">
                                <div className="stat-label">Saldo</div>
                                <div className="stat-value">{fmtEur(primaNota.saldo)}</div>
                            </Card>
                        </div>
                    )}

                    <div className="tbl-scroll" style={{ "--c1-w": "100px", "--c2-w": "100px" }}>
                        {primaNota === null ? <Loading /> : primaNota.movimenti.length === 0 ? <Empty message="Nessun movimento nel periodo" /> : (
                            <table className="tbl freeze-3 w-full min-w-[900px]">
                                <thead>
                                    <tr>
                                        <th>Data</th>
                                        <th>Tipo</th>
                                        <th>Categoria</th>
                                        <th>Descrizione</th>
                                        <th>Mezzo</th>
                                        <th>Documento</th>
                                        <th className="text-right">Entrata</th>
                                        <th className="text-right">Uscita</th>
                                        <th className="text-right">Rimessa</th>
                                        <th className="w-12 text-center">Allegati</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {primaNota.movimenti.map((m) => {
                                        const isRimessa = m.categoria === "pagamento_compagnia";
                                        return (
                                            <tr key={m.id}>
                                                <td className="num">
                                                    <div className="flex items-center gap-1.5">
                                                        {fmtDate(m.data_movimento)}
                                                        <ChiusuraPill data={m.data_movimento} />
                                                    </div>
                                                </td>
                                                <td>
                                                    <span className={`badge ${m.tipo === "entrata" ? "badge-success" : isRimessa ? "badge-info" : "badge-danger"}`}>
                                                        {isRimessa ? "rimessa" : m.tipo}
                                                    </span>
                                                </td>
                                                <td className="text-xs text-slate-600">{m.categoria}</td>
                                                <td>{m.descrizione}</td>
                                                <td className="text-xs text-slate-500">{m.mezzo_pagamento}</td>
                                                <td className="text-xs text-slate-500 num">{m.numero_documento}</td>
                                                <td className="num text-right text-emerald-700 font-medium">
                                                    {m.tipo === "entrata" ? fmtEur(m.importo) : ""}
                                                </td>
                                                <td className="num text-right text-rose-700 font-medium">
                                                    {m.tipo === "uscita" && !isRimessa ? fmtEur(m.importo) : ""}
                                                </td>
                                                <td className="num text-right text-violet-700 font-medium">
                                                    {isRimessa ? fmtEur(m.importo) : ""}
                                                </td>
                                                <td className="text-center">
                                                    <AllegatiCell
                                                        entita_tipo="movimento"
                                                        entita_id={m.id}
                                                        count={m.allegati_count}
                                                        hint={m.tipo === "entrata" ? "Allega ricevuta / assegno" : "Allega fattura / busta paga"}
                                                        onChange={load}
                                                    />
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        )}
                    </div>
                </TabsContent>

                <TabsContent value="estratti">
                    <div className="mt-4 mb-4 max-w-md">
                        <Label>Seleziona cliente</Label>
                        <Select value={estrattoAna} onValueChange={caricaEstratto}>
                            <SelectTrigger data-testid="estratto-cliente-select"><SelectValue placeholder="Seleziona cliente" /></SelectTrigger>
                            <SelectContent>
                                {anagrafiche.map((a) => <SelectItem key={a.id} value={a.id}>{a.ragione_sociale}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>

                    {estratto && (
                        <>
                            <Card className="p-5 border-slate-200 mb-4">
                                <div className="flex items-center justify-between">
                                    <div>
                                        <div className="stat-label">Cliente</div>
                                        <div className="text-lg font-medium">{estratto.anagrafica?.ragione_sociale}</div>
                                    </div>
                                    <div className="text-right">
                                        <div className="stat-label">Saldo</div>
                                        <div className="text-2xl font-semibold num text-sky-700">{fmtEur(estratto.saldo_finale)}</div>
                                    </div>
                                </div>
                            </Card>
                            <Card className="border-slate-200 overflow-hidden">
                                {estratto.movimenti.length === 0 ? (
                                    <Empty message="Nessun movimento per questo cliente" />
                                ) : (
                                    <table className="tbl w-full">
                                        <thead>
                                            <tr>
                                                <th>Data</th>
                                                <th>Descrizione</th>
                                                <th className="text-right">Dare</th>
                                                <th className="text-right">Avere</th>
                                                <th className="text-right">Saldo progressivo</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {estratto.movimenti.map((m) => (
                                                <tr key={m.id}>
                                                    <td className="num">
                                                        <div className="flex items-center gap-1.5">
                                                            {fmtDate(m.data_movimento)}
                                                            <ChiusuraPill data={m.data_movimento} />
                                                        </div>
                                                    </td>
                                                    <td>{m.descrizione}</td>
                                                    <td className="num text-right text-emerald-700">{m.tipo === "entrata" ? fmtEur(m.importo) : ""}</td>
                                                    <td className="num text-right text-rose-700">{m.tipo === "uscita" ? fmtEur(m.importo) : ""}</td>
                                                    <td className="num text-right font-medium">{fmtEur(m.saldo_progressivo)}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                )}
                            </Card>
                        </>
                    )}
                </TabsContent>
            </Tabs>
        </div>
    );
}

function NuovoMovimentoDialog({ anagrafiche, onClose }) {
    const [f, setF] = useState({
        data_movimento: new Date().toISOString().slice(0, 10),
        tipo: "entrata",
        categoria: "incasso_premio",
        importo: 0,
        descrizione: "",
        anagrafica_id: "",
        conto_cassa_id: "",
        mezzo_pagamento: "",
        numero_documento: "",
    });
    const [conti, setConti] = useState([]);
    const [tipiPag, setTipiPag] = useState([]);
    useEffect(() => {
        api.get("/librerie/conti-cassa", { params: { attivi: true } }).then((r) => setConti(r.data));
        api.get("/librerie/tipi-pagamento", { params: { attivi: true } }).then((r) => setTipiPag(r.data));
    }, []);
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const save = async () => {
        if (!f.descrizione || !f.importo) { toast.error("Compila descrizione e importo"); return; }
        if (!f.mezzo_pagamento) { toast.error("Seleziona il tipo di pagamento"); return; }
        try {
            // Deriva conto_cassa_id dal tipo pagamento selezionato
            const tp = tipiPag.find((t) => t.label === f.mezzo_pagamento);
            const payload = {
                ...f,
                importo: parseFloat(f.importo) || 0,
                conto_cassa_id: tp?.conto_id || f.conto_cassa_id || null,
            };
            if (!payload.anagrafica_id) delete payload.anagrafica_id;
            await api.post("/contabilita/movimenti", payload);
            toast.success("Movimento registrato"); onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <DialogContent className="max-w-xl">
            <DialogHeader><DialogTitle>Nuovo movimento contabile</DialogTitle></DialogHeader>
            <ChiusuraGiornoBanner data={f.data_movimento} className="mb-2" />
            <div className="grid grid-cols-2 gap-3 py-2">
                <div><Label>Data *</Label><Input type="date" value={f.data_movimento} onChange={(e) => set("data_movimento", e.target.value)} /></div>
                <div>
                    <Label>Tipo *</Label>
                    <Select value={f.tipo} onValueChange={(v) => set("tipo", v)}>
                        <SelectTrigger data-testid="mov-tipo-select"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="entrata">Entrata</SelectItem>
                            <SelectItem value="uscita">Uscita</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
                <div>
                    <Label>Categoria</Label>
                    <Select value={f.categoria} onValueChange={(v) => set("categoria", v)}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="incasso_premio">Incasso premio</SelectItem>
                            <SelectItem value="pagamento_compagnia">Pagamento compagnia (rimessa E/C)</SelectItem>
                            <SelectItem value="provvigioni">Provvigioni</SelectItem>
                            <SelectItem value="rimborso_cliente">Rimborso cliente</SelectItem>
                            <SelectItem value="sconto_cliente">Sconto cliente</SelectItem>
                            <SelectItem value="spese_amministrative">Spese amministrative</SelectItem>
                            <SelectItem value="anticipo">Anticipo / Sospeso</SelectItem>
                            <SelectItem value="altro">Altro</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
                <div><Label>Importo € *</Label><Input data-testid="mov-importo-input" type="number" step="0.01" value={f.importo} onChange={(e) => set("importo", e.target.value)} /></div>
                <div className="col-span-2"><Label>Descrizione *</Label><Input data-testid="mov-desc-input" value={f.descrizione} onChange={(e) => set("descrizione", e.target.value)} /></div>
                <div>
                    <Label>Cliente (opzionale)</Label>
                    <Select value={f.anagrafica_id} onValueChange={(v) => set("anagrafica_id", v)}>
                        <SelectTrigger><SelectValue placeholder="-" /></SelectTrigger>
                        <SelectContent>
                            {anagrafiche.map((a) => <SelectItem key={a.id} value={a.id}>{a.ragione_sociale}</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
                <div>
                    <Label>Tipo pagamento *</Label>
                    <Select value={f.mezzo_pagamento || ""} onValueChange={(v) => set("mezzo_pagamento", v)}>
                        <SelectTrigger data-testid="mov-tipo-pagamento-select"><SelectValue placeholder="Seleziona..." /></SelectTrigger>
                        <SelectContent>
                            {tipiPag.map((t) => <SelectItem key={t.id} value={t.label}>{t.label}</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
                <div className="col-span-2"><Label>N. documento</Label><Input value={f.numero_documento} onChange={(e) => set("numero_documento", e.target.value)} /></div>
            </div>
            <DialogFooter>
                <Button data-testid="mov-save-button" onClick={save} className="bg-sky-700 hover:bg-sky-800">Registra</Button>
            </DialogFooter>
        </DialogContent>
    );
}

function GirocontoDialog({ conti, onClose }) {
    const today = new Date().toISOString().slice(0, 10);
    const [f, setF] = useState({
        data: today,
        conto_da: "",
        conto_a: "",
        importo: "",
        descrizione: "",
    });
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
    const save = async () => {
        if (!f.conto_da || !f.conto_a) { toast.error("Seleziona entrambi i conti"); return; }
        if (f.conto_da === f.conto_a) { toast.error("I conti devono essere diversi"); return; }
        const imp = parseFloat(f.importo);
        if (!imp || imp <= 0) { toast.error("Importo non valido"); return; }
        try {
            const r = await api.post("/contabilita/giroconto", {
                data_movimento: f.data,
                conto_da_id: f.conto_da,
                conto_a_id: f.conto_a,
                importo: imp,
                descrizione: f.descrizione || null,
            });
            toast.success(`Giroconto registrato: ${r.data.descrizione_breve || ""}`);
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore giroconto");
        }
    };
    const nomeDa = conti.find((c) => c.id === f.conto_da)?.nome;
    const nomeA = conti.find((c) => c.id === f.conto_a)?.nome;
    const imp = parseFloat(f.importo) || 0;
    return (
        <DialogContent className="max-w-lg" data-testid="dialog-giroconto">
            <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                    <ArrowLeftRight size={18} className="text-violet-700" />
                    Giroconto tra conti
                </DialogTitle>
            </DialogHeader>
            <div className="bg-violet-50 border border-violet-200 rounded-md p-3 text-xs text-violet-900">
                <strong>Cosa fa:</strong> sposta un importo da un conto cassa a un altro (esempio: prelievo da banca → contanti, o trasferimento tra banche).
                Genera due movimenti contabili gemelli: uscita dal conto di partenza, entrata sul conto di destinazione (giornata in pareggio).
            </div>
            <div className="space-y-3 py-2">
                <ChiusuraGiornoBanner data={f.data} />
                <div>
                    <Label>Data</Label>
                    <Input type="date" value={f.data} onChange={(e) => set("data", e.target.value)} data-testid="giro-data" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <Label className="text-rose-700 font-semibold">DA (uscita)</Label>
                        <Select value={f.conto_da} onValueChange={(v) => set("conto_da", v)}>
                            <SelectTrigger data-testid="giro-conto-da"><SelectValue placeholder="seleziona…" /></SelectTrigger>
                            <SelectContent>
                                {conti.map((c) => <SelectItem key={c.id} value={c.id}>{c.nome}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <Label className="text-emerald-700 font-semibold">A (entrata)</Label>
                        <Select value={f.conto_a} onValueChange={(v) => set("conto_a", v)}>
                            <SelectTrigger data-testid="giro-conto-a"><SelectValue placeholder="seleziona…" /></SelectTrigger>
                            <SelectContent>
                                {conti.filter((c) => c.id !== f.conto_da).map((c) => <SelectItem key={c.id} value={c.id}>{c.nome}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                </div>
                <div>
                    <Label>Importo (€)</Label>
                    <Input
                        type="number" step="0.01" min="0.01"
                        value={f.importo} onChange={(e) => set("importo", e.target.value)}
                        className="text-lg font-semibold"
                        data-testid="giro-importo"
                    />
                </div>
                <div>
                    <Label>Descrizione (opzionale)</Label>
                    <Input value={f.descrizione} onChange={(e) => set("descrizione", e.target.value)} placeholder="es. Prelievo bancomat" />
                </div>
                {imp > 0 && nomeDa && nomeA && (
                    <div className="bg-slate-50 border border-slate-200 rounded p-3 text-xs space-y-1" data-testid="giro-preview">
                        <div className="font-semibold text-slate-700">Anteprima movimenti:</div>
                        <div className="flex justify-between">
                            <span>📤 <span className="font-medium">{nomeDa}</span></span>
                            <span className="num font-semibold text-rose-700">- {fmtEur(imp)}</span>
                        </div>
                        <div className="flex justify-between">
                            <span>📥 <span className="font-medium">{nomeA}</span></span>
                            <span className="num font-semibold text-emerald-700">+ {fmtEur(imp)}</span>
                        </div>
                    </div>
                )}
            </div>
            <DialogFooter>
                <Button variant="outline" onClick={onClose}>Annulla</Button>
                <Button onClick={save} className="bg-violet-700 hover:bg-violet-800" data-testid="giro-save">Registra giroconto</Button>
            </DialogFooter>
        </DialogContent>
    );
}


function StoricoPrimaNotaTab() {
    const oggi = new Date();
    const [anno, setAnno] = useState(String(oggi.getFullYear()));
    const [q, setQ] = useState("");
    const [items, setItems] = useState(null);
    const [pageSize, setPageSize] = useState(50);

    const load = () => {
        setItems(null);
        const params = { limit: 1000 };
        if (anno && anno !== "__all__") params.anno = parseInt(anno, 10);
        if (q) params.q = q;
        api.get("/contabilita/chiusure-giorno", { params }).then((r) => setItems(r.data || []));
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

    const elimina = async (it) => {
        if (!window.confirm(
            `Eliminare la chiusura del ${it.data}?\nI movimenti del giorno verranno riaperti (sarai in grado di modificarli nel Brogliaccio).`,
        )) return;
        try {
            await api.delete(`/contabilita/chiusura-giorno/${it.id}`);
            toast.success("Chiusura eliminata · giornata riaperta");
            load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const visibili = items ? items.slice(0, pageSize) : null;
    const annoOptions = [];
    for (let y = oggi.getFullYear() + 1; y >= 2018; y--) annoOptions.push(y);

    return (
        <div className="mt-4" data-testid="storico-prima-nota">
            {/* Header filtri */}
            <Card className="p-4 border-slate-200 mb-3">
                <div className="flex items-end gap-3 flex-wrap">
                    <div>
                        <Label className="text-xs">Anno</Label>
                        <Select value={anno} onValueChange={setAnno}>
                            <SelectTrigger className="w-32" data-testid="storico-anno">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="__all__">Tutti</SelectItem>
                                {annoOptions.map((y) => (
                                    <SelectItem key={y} value={String(y)}>{y}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    <Button onClick={load} className="bg-sky-700 hover:bg-sky-800" data-testid="storico-carica">
                        Carica
                    </Button>
                    <div className="ml-auto flex items-end gap-3">
                        <div>
                            <Label className="text-xs">Visualizza</Label>
                            <Select value={String(pageSize)} onValueChange={(v) => setPageSize(parseInt(v, 10))}>
                                <SelectTrigger className="w-24"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="25">25</SelectItem>
                                    <SelectItem value="50">50</SelectItem>
                                    <SelectItem value="100">100</SelectItem>
                                    <SelectItem value="1000">Tutti</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <div>
                            <Label className="text-xs">Cerca</Label>
                            <div className="relative">
                                <Search size={12} className="absolute left-2 top-2.5 text-slate-400" />
                                <Input
                                    value={q}
                                    onChange={(e) => setQ(e.target.value)}
                                    onKeyDown={(e) => e.key === "Enter" && load()}
                                    className="pl-7 w-56"
                                    placeholder="data, ID..."
                                    data-testid="storico-cerca"
                                />
                            </div>
                        </div>
                    </div>
                </div>
            </Card>

            {/* Tabella storico */}
            <Card className="border-slate-200 overflow-hidden">
                {items === null ? <Loading /> : items.length === 0 ? (
                    <Empty message="Nessuna chiusura presente per l'anno selezionato" />
                ) : (
                    <table className="tbl w-full">
                        <thead className="bg-slate-900 text-white">
                            <tr>
                                <th className="text-left px-3 py-2 w-24">ID</th>
                                <th className="text-left px-3 py-2">Data</th>
                                <th className="text-left px-3 py-2">N. movimenti</th>
                                <th className="text-left px-3 py-2">Chiusa da</th>
                                <th className="text-right px-3 py-2">Entrate €</th>
                                <th className="text-right px-3 py-2">Provv €</th>
                                <th className="text-right px-3 py-2">Spese €</th>
                                <th className="text-center px-3 py-2 w-40">Azioni</th>
                            </tr>
                        </thead>
                        <tbody>
                            {visibili.map((it) => {
                                const k = it.riepilogo?.riepilogo_kpi || {};
                                return (
                                    <StoricoRow
                                        key={it.id}
                                        it={it}
                                        k={k}
                                        onDelete={() => elimina(it)}
                                    />
                                );
                            })}
                        </tbody>
                    </table>
                )}
                {items && items.length > pageSize && (
                    <div className="p-3 text-center text-xs text-slate-500 border-t border-slate-200">
                        Visualizzati {visibili.length} di {items.length} · Aumenta "Visualizza" per vederne di più
                    </div>
                )}
            </Card>
        </div>
    );
}

function StoricoRow({ it, k, onDelete }) {
    const [vista, setVista] = useState("prima_nota"); // o "brogliaccio"
    return (
        <tr className="hover:bg-slate-50" data-testid={`storico-row-${it.id}`}>
            <td className="px-3 py-2 font-mono text-xs text-slate-600">{it.id.slice(0, 8)}</td>
            <td className="px-3 py-2 font-medium">{fmtDate(it.data)}</td>
            <td className="px-3 py-2 num text-sm">{it.riepilogo?.n_movimenti || 0}</td>
            <td className="px-3 py-2 text-xs text-slate-500">{it.closed_by_name || "—"}</td>
            <td className="px-3 py-2 num text-right text-emerald-700">{fmtEur(k.entrate || 0)}</td>
            <td className="px-3 py-2 num text-right text-sky-700">{fmtEur(k.provvigioni || 0)}</td>
            <td className="px-3 py-2 num text-right text-rose-600">{fmtEur(k.spese || 0)}</td>
            <td className="px-3 py-2">
                <div className="flex items-center justify-center gap-1">
                    <Select value={vista} onValueChange={setVista}>
                        <SelectTrigger className="h-7 w-32 text-xs"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="prima_nota">Prima Nota</SelectItem>
                            <SelectItem value="brogliaccio">Brogliaccio</SelectItem>
                        </SelectContent>
                    </Select>
                    <a
                        href={`${API_BASE}/contabilita/chiusura-giorno/${it.id}/pdf`}
                        target="_blank" rel="noreferrer"
                        title={vista === "prima_nota" ? "Stampa Prima Nota" : "Stampa Brogliaccio"}
                        data-testid={`storico-stampa-${it.id}`}
                    >
                        <button className="inline-flex items-center justify-center h-7 w-7 rounded border border-slate-200 hover:bg-slate-100">
                            <Printer size={12} />
                        </button>
                    </a>
                    <button
                        onClick={onDelete}
                        className="inline-flex items-center justify-center h-7 w-7 rounded border border-rose-200 hover:bg-rose-50 text-rose-600"
                        title="Elimina chiusura (riapre la giornata)"
                        data-testid={`storico-del-${it.id}`}
                    >
                        <Trash2 size={12} />
                    </button>
                </div>
            </td>
        </tr>
    );
}

