/**
 * LibreriaTarghe — registro veicoli del tenant interrogabile per targa.
 * Per ogni targa: proprietario/intestatario, libretto allegato, dati veicolo
 * e storico delle polizze collegate. Evita di ricaricare il libretto ad ogni
 * nuova polizza in sostituzione.
 */
import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { api, API_BASE, imgUrl } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Car, Search, FileText, User, BookOpen, Download, ChevronRight } from "lucide-react";

const STATO_COLOR = {
    attiva: "bg-emerald-100 text-emerald-700",
    sospesa: "bg-amber-100 text-amber-700",
    annullata: "bg-slate-200 text-slate-600",
    scaduta: "bg-rose-100 text-rose-700",
    disdetta: "bg-rose-100 text-rose-700",
};

function fmtData(d) {
    if (!d) return "—";
    try {
        const s = String(d).slice(0, 10);
        return `${s.slice(8, 10)}/${s.slice(5, 7)}/${s.slice(0, 4)}`;
    } catch { return d; }
}

function Veicolo({ v }) {
    if (!v) return null;
    const parts = [v.marca, v.modello].filter(Boolean).join(" ");
    return (
        <div className="text-sm text-slate-600">
            {parts && <span className="font-medium text-slate-800">{parts}</span>}
            {v.immatricolazione && <span> · imm. {fmtData(v.immatricolazione)}</span>}
            {v.telaio && <span className="block text-xs text-slate-400">Telaio {v.telaio}</span>}
        </div>
    );
}

export default function LibreriaTarghe() {
    const navigate = useNavigate();
    const [q, setQ] = useState("");
    const [items, setItems] = useState([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(true);
    const [sel, setSel] = useState(null);      // targa selezionata (detail)
    const [detail, setDetail] = useState(null);
    const [detailLoading, setDetailLoading] = useState(false);

    const load = useCallback(() => {
        setLoading(true);
        api.get("/librerie/targhe", { params: { q, limit: 60 } })
            .then((r) => { setItems(r.data.items || []); setTotal(r.data.total || 0); })
            .catch(() => { setItems([]); setTotal(0); })
            .finally(() => setLoading(false));
    }, [q]);

    useEffect(() => {
        const t = setTimeout(load, 300);
        return () => clearTimeout(t);
    }, [load]);

    const openDetail = (targa) => {
        setSel(targa);
        setDetail(null);
        setDetailLoading(true);
        api.get(`/librerie/targhe/${encodeURIComponent(targa)}`)
            .then((r) => setDetail(r.data))
            .catch(() => setDetail({ trovata: false }))
            .finally(() => setDetailLoading(false));
    };

    return (
        <div className="p-6 max-w-6xl mx-auto" data-testid="libreria-targhe-page">
            <PageHeader
                title="Libreria Targhe"
                subtitle="Registro veicoli: interroga una targa per trovare libretto, proprietario e storico polizze."
            />

            <div className="relative max-w-md mb-6">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                <Input
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                    placeholder="Cerca targa… (es. GY308AK)"
                    className="pl-9 uppercase"
                    data-testid="search-targa"
                />
            </div>

            {loading ? <Loading /> : items.length === 0 ? (
                <Empty message={q ? "Nessuna targa trovata" : "Nessuna targa in archivio"} />
            ) : (
                <>
                    <div className="text-xs text-slate-500 mb-3" data-testid="targhe-count">
                        {total} targhe{q ? " trovate" : " in archivio"}
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                        {items.map((t) => (
                            <Card
                                key={t.targa}
                                onClick={() => openDetail(t.targa)}
                                className="p-4 cursor-pointer hover:shadow-md hover:border-sky-300 transition-shadow"
                                data-testid={`targa-card-${t.targa}`}
                            >
                                <div className="flex items-center justify-between mb-2">
                                    <div className="flex items-center gap-2">
                                        <Car className="h-4 w-4 text-sky-600" />
                                        <span className="font-mono font-bold tracking-wider text-slate-900">{t.targa}</span>
                                    </div>
                                    <ChevronRight className="h-4 w-4 text-slate-300" />
                                </div>
                                <div className="text-sm text-slate-700 truncate flex items-center gap-1" title={t.proprietario || ""}>
                                    <User className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                                    {t.proprietario || <span className="text-slate-400">Proprietario n/d</span>}
                                </div>
                                <Veicolo v={t.veicolo} />
                                <div className="flex flex-wrap gap-1.5 mt-3">
                                    <Badge variant="outline" className="text-[11px]">
                                        {t.n_polizze} polizz{t.n_polizze === 1 ? "a" : "e"}
                                    </Badge>
                                    {t.is_libro_matricola && (
                                        <Badge variant="outline" className="text-[11px] border-indigo-300 text-indigo-700">Libro Matricola</Badge>
                                    )}
                                    {t.has_libretto ? (
                                        <Badge className="text-[11px] bg-emerald-100 text-emerald-700 hover:bg-emerald-100">
                                            <BookOpen className="h-3 w-3 mr-1" /> Libretto
                                        </Badge>
                                    ) : (
                                        <Badge variant="outline" className="text-[11px] text-slate-400">No libretto</Badge>
                                    )}
                                </div>
                            </Card>
                        ))}
                    </div>
                </>
            )}

            <Dialog open={!!sel} onOpenChange={(o) => { if (!o) { setSel(null); setDetail(null); } }}>
                <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="targa-detail-dialog">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">
                            <Car className="h-5 w-5 text-sky-600" />
                            <span className="font-mono tracking-wider">{sel}</span>
                        </DialogTitle>
                    </DialogHeader>

                    {detailLoading ? <Loading /> : !detail || !detail.trovata ? (
                        <Empty message="Dettaglio non disponibile" />
                    ) : (
                        <div className="space-y-5">
                            {/* Proprietari */}
                            <section>
                                <h3 className="text-xs font-semibold uppercase text-slate-400 mb-1">Proprietario / Intestatario</h3>
                                {detail.proprietari?.length ? (
                                    <div className="flex flex-wrap gap-1.5">
                                        {detail.proprietari.map((p) => (
                                            <Badge key={p} variant="outline" className="text-xs">{p}</Badge>
                                        ))}
                                    </div>
                                ) : <span className="text-sm text-slate-400">n/d</span>}
                            </section>

                            {/* Veicolo */}
                            <section>
                                <h3 className="text-xs font-semibold uppercase text-slate-400 mb-1">Dati veicolo</h3>
                                <Veicolo v={detail.veicolo} />
                            </section>

                            {/* Libretto */}
                            <section>
                                <h3 className="text-xs font-semibold uppercase text-slate-400 mb-1">Libretto di circolazione</h3>
                                {detail.libretti?.length ? (
                                    <div className="space-y-1.5">
                                        {detail.libretti.map((l) => (
                                            <a
                                                key={l.id}
                                                href={imgUrl(`${API_BASE}${l.download_url}`)}
                                                target="_blank" rel="noreferrer"
                                                className="flex items-center gap-2 text-sm text-sky-700 hover:underline"
                                                data-testid={`libretto-download-${l.id}`}
                                            >
                                                <FileText className="h-4 w-4" />
                                                {l.nome_file || "libretto.pdf"}
                                                <Download className="h-3.5 w-3.5 text-slate-400" />
                                            </a>
                                        ))}
                                    </div>
                                ) : <span className="text-sm text-slate-400">Nessun libretto allegato</span>}
                            </section>

                            {/* Polizze storico */}
                            <section>
                                <h3 className="text-xs font-semibold uppercase text-slate-400 mb-2">Polizze collegate ({detail.polizze?.length || 0})</h3>
                                <div className="space-y-2">
                                    {(detail.polizze || []).map((p) => (
                                        <button
                                            key={p.id}
                                            type="button"
                                            onClick={() => { setSel(null); setDetail(null); navigate(`/polizze/${p.id}`); }}
                                            className="block w-full text-left border border-slate-200 rounded-lg p-3 hover:border-sky-300 hover:bg-sky-50/40 transition-colors"
                                            data-testid={`polizza-link-${p.id}`}
                                        >
                                            <div className="flex items-center justify-between">
                                                <span className="font-medium text-slate-800 text-sm">{p.numero_polizza || "—"}</span>
                                                <Badge className={`text-[11px] ${STATO_COLOR[p.stato] || "bg-slate-100 text-slate-600"}`}>{p.stato || "—"}</Badge>
                                            </div>
                                            <div className="text-xs text-slate-500 mt-1">
                                                {[p.compagnia, p.ramo, p.prodotto].filter(Boolean).join(" · ")}
                                            </div>
                                            <div className="text-xs text-slate-500">
                                                {p.contraente && <span>{p.contraente} · </span>}
                                                {fmtData(p.data_effetto)} → {fmtData(p.data_scadenza)}
                                            </div>
                                        </button>
                                    ))}
                                </div>
                            </section>

                            {/* Applicazioni libro matricola */}
                            {detail.applicazioni?.length > 0 && (
                                <section>
                                    <h3 className="text-xs font-semibold uppercase text-slate-400 mb-2">Applicazioni Libro Matricola ({detail.applicazioni.length})</h3>
                                    <div className="space-y-1.5">
                                        {detail.applicazioni.map((a) => (
                                            <div key={a.id} className="text-sm text-slate-600 border border-slate-200 rounded-lg p-2">
                                                <span className="font-medium">#{a.numero}</span> · {a.intestatario || "—"}
                                                <Badge className={`ml-2 text-[11px] ${STATO_COLOR[a.stato] || "bg-slate-100 text-slate-600"}`}>{a.stato || "—"}</Badge>
                                            </div>
                                        ))}
                                    </div>
                                </section>
                            )}
                        </div>
                    )}
                </DialogContent>
            </Dialog>
        </div>
    );
}
