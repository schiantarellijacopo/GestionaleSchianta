import { useState, Fragment } from "react";
import { api } from "@/lib/api";
import { PageHeader, Empty } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FileText, Printer, Eye, Users, Save } from "lucide-react";
import IntestatarioAutocomplete from "@/components/IntestatarioAutocomplete";
import { toast } from "sonner";

const eur = (v) => (Number(v || 0)).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function EstrattoContoContraente() {
    const [contraenteId, setContraenteId] = useState(null);
    const [contraenteNome, setContraenteNome] = useState("");
    const [dal, setDal] = useState("");
    const [al, setAl] = useState(new Date().toISOString().slice(0, 10));
    const [filtraPer, setFiltraPer] = useState("rata");
    const [includiCollegati, setIncludiCollegati] = useState(false);
    const [includiPagamenti, setIncludiPagamenti] = useState(true);
    const [data, setData] = useState(null);
    const [busy, setBusy] = useState(false);

    const params = () => ({
        contraente_id: contraenteId, dal, al, filtra_per: filtraPer,
        includi_collegati: includiCollegati, includi_pagamenti: includiPagamenti,
    });

    const filtra = async () => {
        if (!contraenteId) { toast.error("Seleziona un contraente"); return; }
        setBusy(true);
        try {
            const r = await api.get("/estratto-conto-contraente", { params: params() });
            setData(r.data);
        } catch { toast.error("Errore nel caricamento"); } finally { setBusy(false); }
    };

    const stampaPdf = async () => {
        if (!contraenteId) { toast.error("Seleziona un contraente"); return; }
        setBusy(true);
        try {
            const r = await api.get("/estratto-conto-contraente/pdf", { params: params(), responseType: "blob" });
            const url = URL.createObjectURL(new Blob([r.data], { type: "application/pdf" }));
            const win = window.open(url, "_blank");
            if (!win) { const a = document.createElement("a"); a.href = url; a.download = "estratto_conto.pdf"; a.click(); }
            setTimeout(() => URL.revokeObjectURL(url), 60000);
        } catch { toast.error("Errore generazione PDF"); } finally { setBusy(false); }
    };

    const salvaInAnagrafica = async () => {
        if (!contraenteId) { toast.error("Seleziona un contraente"); return; }
        setBusy(true);
        try {
            const r = await api.post("/estratto-conto-contraente/salva", null, { params: params() });
            toast.success(`Estratto conto salvato in anagrafica → Documenti · "Estratti conto" (${r.data.nome_file})`);
        } catch { toast.error("Errore salvataggio estratto conto"); } finally { setBusy(false); }
    };

    return (
        <div data-testid="ec-contraente-page">
            <PageHeader title="Estratti conto contraente"
                subtitle="Elenco titoli di un contraente in un periodo, con dati di pagamento e totali" />

            <Card className="p-5 mb-5">
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <div className="space-y-3">
                        <div>
                            <Label className="text-xs text-slate-500">Contraente</Label>
                            <IntestatarioAutocomplete value={contraenteNome} anagraficaId={contraenteId}
                                onChange={(name, id) => { setContraenteNome(name); setContraenteId(id); }} />
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <Label className="text-xs text-slate-500">Data inizio</Label>
                                <Input type="date" value={dal} onChange={(e) => setDal(e.target.value)} data-testid="ecc-dal" />
                            </div>
                            <div>
                                <Label className="text-xs text-slate-500">Data fine</Label>
                                <Input type="date" value={al} onChange={(e) => setAl(e.target.value)} data-testid="ecc-al" />
                            </div>
                        </div>
                    </div>

                    <div className="space-y-3">
                        <div>
                            <Label className="text-xs text-slate-500">Filtra per data</Label>
                            <div className="flex flex-wrap gap-4 mt-1" data-testid="ecc-filtra-per">
                                {[["rata", "Rata / Scadenza titolo"], ["emissione", "Data emissione"], ["copertura", "Data copertura"]].map(([v, l]) => (
                                    <label key={v} className="flex items-center gap-1.5 text-sm cursor-pointer">
                                        <input type="radio" name="filtraPer" checked={filtraPer === v}
                                            onChange={() => setFiltraPer(v)} data-testid={`ecc-fp-${v}`} />
                                        {l}
                                    </label>
                                ))}
                            </div>
                        </div>
                        <label className="flex items-center gap-2 text-sm cursor-pointer">
                            <input type="checkbox" checked={includiPagamenti}
                                onChange={(e) => setIncludiPagamenti(e.target.checked)} data-testid="ecc-pagamenti" />
                            Includi dati pagamento
                        </label>
                        <label className="flex items-center gap-2 text-sm cursor-pointer">
                            <input type="checkbox" checked={includiCollegati}
                                onChange={(e) => setIncludiCollegati(e.target.checked)} data-testid="ecc-collegati" />
                            <Users size={14} className="text-slate-400" /> Includi contraenti collegati (gruppo/relazioni)
                        </label>
                    </div>
                </div>

                <div className="flex justify-center gap-3 mt-5">
                    <Button onClick={filtra} disabled={busy} data-testid="ecc-filtra">
                        <Eye size={14} className="mr-1" /> Anteprima
                    </Button>
                    <Button onClick={stampaPdf} disabled={busy} variant="outline"
                        className="border-indigo-300 text-indigo-700 hover:bg-indigo-50" data-testid="ecc-stampa">
                        <Printer size={14} className="mr-1" /> Apri PDF
                    </Button>
                    <Button onClick={salvaInAnagrafica} disabled={busy}
                        className="bg-emerald-600 hover:bg-emerald-700" data-testid="ecc-salva">
                        <Save size={14} className="mr-1" /> Salva estratto conto in anagrafica
                    </Button>
                </div>
            </Card>

            {data && (
                <Card className="p-5" data-testid="ecc-risultati">
                    <div className="mb-3">
                        <div className="text-lg font-semibold text-slate-800">{data.contraente.ragione_sociale}</div>
                        <div className="text-xs text-slate-500">
                            {data.contraente.indirizzo} · {data.contraente.cap} {data.contraente.comune} ({data.contraente.provincia})
                        </div>
                        <div className="text-xs text-slate-500 mt-1">
                            Estratto conto DAL {data.dal || "—"} AL {data.al || "—"}
                            {data.collegati_inclusi && data.n_contraenti > 1 && (
                                <span className="ml-2 text-indigo-600">· {data.n_contraenti} contraenti collegati inclusi</span>
                            )}
                        </div>
                    </div>

                    {data.righe.length === 0 ? (
                        <Empty title="Nessun titolo nel periodo" />
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="w-full text-xs border-collapse">
                                <thead>
                                    <tr className="bg-slate-800 text-white text-left">
                                        {["Contratto", "Rata del", "Scad. mora", "Data cop.", "Compagnia", "Rischio", "Premio", "Addiz.", "Totale", "Tipo"].map((h) => (
                                            <th key={h} className={`px-2 py-1.5 ${["Premio", "Addiz.", "Totale"].includes(h) ? "text-right" : ""}`}>{h}</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {data.righe.map((r, i) => (
                                        <Fragment key={i}>
                                            <tr className={i % 2 ? "bg-slate-50" : ""}>
                                                <td className="px-2 py-1 border-b border-slate-100">{r.contratto}</td>
                                                <td className="px-2 py-1 border-b border-slate-100">{r.rata_del}</td>
                                                <td className="px-2 py-1 border-b border-slate-100">{r.scad_mora}</td>
                                                <td className="px-2 py-1 border-b border-slate-100">{r.data_copertura}</td>
                                                <td className="px-2 py-1 border-b border-slate-100">{r.compagnia}</td>
                                                <td className="px-2 py-1 border-b border-slate-100">{r.rischio}</td>
                                                <td className="px-2 py-1 border-b border-slate-100 text-right num">{eur(r.premio)}</td>
                                                <td className="px-2 py-1 border-b border-slate-100 text-right num">{eur(r.addizionali)}</td>
                                                <td className="px-2 py-1 border-b border-slate-100 text-right num font-medium">{eur(r.totale)}</td>
                                                <td className="px-2 py-1 border-b border-slate-100">{r.tipo_cod}</td>
                                            </tr>
                                            {(r.targa_oggetto || r.pagamento) && (
                                                <tr key={`${i}-x`} className="bg-sky-50">
                                                    <td colSpan={10} className="px-2 py-1 text-[11px] text-sky-700 border-b border-slate-100">
                                                        {r.targa_oggetto && <span className="mr-3">{r.targa_oggetto}</span>}
                                                        {r.pagamento && <span>Pagamento: {r.pagamento.data} · € {eur(r.pagamento.importo)}{r.pagamento.mezzo ? ` · ${r.pagamento.mezzo}` : ""}</span>}
                                                    </td>
                                                </tr>
                                            )}
                                        </Fragment>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}

                    <div className="mt-4 flex flex-col items-end gap-1 text-sm">
                        <div className="text-slate-600">Totale premi: <span className="num font-medium">€ {eur(data.totali.premi)}</span></div>
                        <div className="text-slate-600">Totale addizionali: <span className="num font-medium">€ {eur(data.totali.addizionali)}</span></div>
                        <div className="text-slate-600">Totale già pagato: <span className="num font-medium text-emerald-600">€ {eur(data.totali.gia_pagato)}</span></div>
                        <div className="text-base font-bold text-slate-900">DA PAGARE: <span className="num">€ {eur(data.totali.da_pagare)}</span></div>
                    </div>
                </Card>
            )}
        </div>
    );
}
