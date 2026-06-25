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
import { Plus, Calendar, ArrowLeftRight } from "lucide-react";
import { toast } from "sonner";
import AllegatiCell from "@/components/AllegatiCell";
import BrogliaccioTab from "@/components/BrogliaccioTab";
import DatiCompagnieTab from "@/components/DatiCompagnieTab";

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
    useEffect(() => { api.get("/contabilita/conti-cassa").then((r) => setConti(r.data || [])); }, []);

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
                    <TabsTrigger value="prima-nota" data-testid="tab-prima-nota">Movimenti (elenco)</TabsTrigger>
                    <TabsTrigger value="dati-compagnie" data-testid="tab-dati-compagnie">Dati Compagnie</TabsTrigger>
                    <TabsTrigger value="estratti" data-testid="tab-estratti">Estratto conto cliente</TabsTrigger>
                </TabsList>

                <TabsContent value="brogliaccio">
                    <BrogliaccioTab />
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

                    <div className="bg-white border border-slate-200 rounded-md overflow-x-auto">
                        {primaNota === null ? <Loading /> : primaNota.movimenti.length === 0 ? <Empty message="Nessun movimento nel periodo" /> : (
                            <table className="tbl w-full min-w-[900px]">
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
                                        <th className="w-12 text-center">Allegati</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {primaNota.movimenti.map((m) => (
                                        <tr key={m.id}>
                                            <td className="num">{fmtDate(m.data_movimento)}</td>
                                            <td>
                                                <span className={`badge ${m.tipo === "entrata" ? "badge-success" : "badge-danger"}`}>
                                                    {m.tipo}
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
                                                {m.tipo === "uscita" ? fmtEur(m.importo) : ""}
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
                                    ))}
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
                                                    <td className="num">{fmtDate(m.data_movimento)}</td>
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
        numero_documento: "",
    });
    const [conti, setConti] = useState([]);
    useEffect(() => {
        api.get("/librerie/conti-cassa", { params: { attivi: true } }).then((r) => setConti(r.data));
    }, []);
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const save = async () => {
        if (!f.descrizione || !f.importo) { toast.error("Compila descrizione e importo"); return; }
        if (!f.conto_cassa_id) { toast.error("Seleziona il metodo di pagamento (Conto / Banca)"); return; }
        try {
            const conto = conti.find((c) => c.id === f.conto_cassa_id);
            const payload = {
                ...f,
                importo: parseFloat(f.importo) || 0,
                mezzo_pagamento: conto?.nome || "",  // mantiene compatibilità campo legacy
            };
            if (!payload.anagrafica_id) delete payload.anagrafica_id;
            await api.post("/contabilita/movimenti", payload);
            toast.success("Movimento registrato"); onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <DialogContent className="max-w-xl">
            <DialogHeader><DialogTitle>Nuovo movimento contabile</DialogTitle></DialogHeader>
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
                    <Label>Conto / Banca (Metodo di pagamento) *</Label>
                    <Select value={f.conto_cassa_id} onValueChange={(v) => set("conto_cassa_id", v)}>
                        <SelectTrigger data-testid="mov-conto-select"><SelectValue placeholder="Seleziona..." /></SelectTrigger>
                        <SelectContent>
                            {conti.map((c) => <SelectItem key={c.id} value={c.id}>{c.nome}</SelectItem>)}
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

