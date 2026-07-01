import { useEffect, useState, useMemo, useCallback } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, fmtEur, fmtDate } from "@/lib/api";
import { formatPhone, telHref } from "@/lib/phone";
import { openPdf } from "@/lib/pdf";
import { PageHeader, Loading } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";
import DialogIncasso from "@/components/DialogIncasso";
import SelectTipoPagamento from "@/components/SelectTipoPagamento";
import { Coins, Clock, AlertTriangle, CheckCircle, Printer, Layers } from "lucide-react";

export default function TitoliSospesi() {
    const [searchParams, setSearchParams] = useSearchParams();
    const ggMin = parseInt(searchParams.get("gg_min") || "0", 10);
    const [items, setItems] = useState(null);
    const [collab, setCollab] = useState([]);
    const [filtroCollab, setFiltroCollab] = useState("all");
    const [conti, setConti] = useState([]);
    const [paying, setPaying] = useState(null);  // titolo in pagamento singolo
    const [selectedIds, setSelectedIds] = useState(new Set());
    const [bulkOpen, setBulkOpen] = useState(false);

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

    // Filtro derivato da URL ?gg_min=N
    const visibleItems = useMemo(() => {
        if (!items) return null;
        if (!ggMin) return items;
        return items.filter((t) => (t.giorni_anticipo || 0) >= ggMin);
    }, [items, ggMin]);

    const clearGgMin = () => {
        const p = new URLSearchParams(searchParams);
        p.delete("gg_min");
        setSearchParams(p);
    };

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

    // Multi-select logic
    const toggleOne = (id) => {
        setSelectedIds((prev) => {
            const n = new Set(prev);
            if (n.has(id)) n.delete(id); else n.add(id);
            return n;
        });
    };
    const toggleAll = () => {
        const visible = visibleItems || [];
        if (visible.length && visible.every((t) => selectedIds.has(t.id))) {
            setSelectedIds(new Set());
        } else {
            setSelectedIds(new Set(visible.map((t) => t.id)));
        }
    };
    const selectedItems = useMemo(
        () => (visibleItems || []).filter((t) => selectedIds.has(t.id)),
        [visibleItems, selectedIds],
    );
    const selectedTotal = useMemo(
        () => selectedItems.reduce((s, t) => s + (t.importo_lordo || 0), 0),
        [selectedItems],
    );
    // Reset selection when filtroCollab or items change materially
    useEffect(() => { setSelectedIds(new Set()); }, [filtroCollab, ggMin]);

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
                <Button
                    variant="outline"
                    onClick={() => openPdf("/stampa/titoli/sospesi", filtroCollab !== "all" ? { collaboratore_id: filtroCollab } : {})}
                    data-testid="sospesi-print-pdf"
                    disabled={!items || items.length === 0}
                >
                    <Printer size={14} className="mr-1" /> Stampa PDF
                </Button>
                <Button
                    className="bg-emerald-600 hover:bg-emerald-700"
                    onClick={() => setBulkOpen(true)}
                    disabled={selectedIds.size === 0}
                    data-testid="sospesi-bulk-incassa"
                >
                    <Layers size={14} className="mr-1" />
                    Incassa selezionati ({selectedIds.size}){selectedIds.size > 0 ? ` · ${fmtEur(selectedTotal)}` : ""}
                </Button>
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
                {ggMin > 0 && (
                    <div
                        className="flex items-center justify-between gap-3 px-4 py-2 border-b border-amber-300 bg-amber-50"
                        data-testid="sospesi-active-filter"
                    >
                        <div className="text-sm text-amber-900">
                            <span className="font-semibold">Filtro attivo:</span> Sospesi da oltre {ggMin} giorni
                            <span className="text-amber-700 num ml-2">— {(visibleItems || []).length} risultati</span>
                        </div>
                        <Button size="sm" variant="ghost" onClick={clearGgMin} data-testid="sospesi-clear-filter">
                            Rimuovi filtro
                        </Button>
                    </div>
                )}
                {visibleItems === null ? <Loading /> : visibleItems.length === 0 ? (
                    <div className="text-center py-16 text-slate-500">
                        <CheckCircle size={32} className="mx-auto mb-2 text-emerald-500" />
                        {ggMin > 0 ? `Nessun titolo sospeso da oltre ${ggMin} giorni.` : "Nessun titolo sospeso — tutti i clienti hanno pagato."}
                    </div>
                ) : (
                    <table className="tbl w-full">
                        <thead>
                            <tr>
                                <th className="w-8">
                                    <Checkbox
                                        checked={visibleItems.length > 0 && visibleItems.every((t) => selectedIds.has(t.id))}
                                        onCheckedChange={toggleAll}
                                        data-testid="sospesi-toggle-all"
                                    />
                                </th>
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
                            {visibleItems.map((t) => {
                                const old = (t.giorni_anticipo || 0) > 30;
                                const isChecked = selectedIds.has(t.id);
                                return (
                                    <tr key={t.id} data-testid={`sospeso-${t.id}`} className={isChecked ? "bg-emerald-50/60" : ""}>
                                        <td>
                                            <Checkbox
                                                checked={isChecked}
                                                onCheckedChange={() => toggleOne(t.id)}
                                                data-testid={`sospeso-check-${t.id}`}
                                            />
                                        </td>
                                        <td className="font-medium">
                                            <Link to={`/anagrafiche/${t.contraente_id}`} className="text-sky-700 hover:underline">
                                                {t.contraente_nome}
                                            </Link>
                                        </td>
                                        <td className="text-xs">{t.cellulare
                                            ? <a href={`tel:${telHref(t.cellulare)}`} className="text-sky-700 hover:underline">{formatPhone(t.cellulare)}</a>
                                            : "—"}</td>
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
                                <td colSpan="9" className="text-right">TOTALE ANTICIPI</td>
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
            {bulkOpen && (
                <BulkIncassaDialog
                    titoli={selectedItems}
                    onClose={(reload) => {
                        setBulkOpen(false);
                        if (reload) { setSelectedIds(new Set()); load(); }
                    }}
                />
            )}
        </div>
    );
}


// =====================================================================
// BulkIncassaDialog — incassa più titoli sospesi in un colpo solo
// Ogni riga ha un importo editabile (default = premio); un unico
// Tipo di pagamento + data incasso vengono applicati a tutti i titoli.
// =====================================================================
function BulkIncassaDialog({ titoli, onClose }) {
    const oggi = new Date().toISOString().slice(0, 10);
    const [dataIncasso, setDataIncasso] = useState(oggi);
    const [tipoPag, setTipoPag] = useState("");
    const [perTit, setPerTit] = useState(() => {
        const o = {};
        for (const t of titoli) {
            o[t.id] = {
                importo_pagato: (parseFloat(t.importo_lordo) || 0).toFixed(2),
                tipo_chiusura: "sconto",
            };
        }
        return o;
    });
    const [saving, setSaving] = useState(false);
    const setPT = (id, k, v) => setPerTit((p) => ({ ...p, [id]: { ...p[id], [k]: v } }));

    const totalePremio = useMemo(
        () => titoli.reduce((s, t) => s + (parseFloat(t.importo_lordo) || 0), 0),
        [titoli],
    );
    const totalePagato = useMemo(
        () => Object.values(perTit).reduce((s, r) => s + (parseFloat(r.importo_pagato) || 0), 0),
        [perTit],
    );

    const conferma = async () => {
        if (!tipoPag) { toast.error("Seleziona il tipo di pagamento"); return; }
        setSaving(true);
        let ok = 0, ko = 0, totale = 0;
        for (const t of titoli) {
            const pt = perTit[t.id] || {};
            const importo = parseFloat(pt.importo_pagato);
            if (isNaN(importo) || importo < 0) { ko += 1; continue; }
            const lordo = parseFloat(t.importo_lordo) || 0;
            const residuo = Math.max(0, lordo - importo);
            const tipo_ch = residuo > 0 ? (pt.tipo_chiusura || "sconto") : "sconto";
            try {
                await api.post(`/titoli/${t.id}/incassa`, {
                    data_incasso: dataIncasso,
                    mezzo_pagamento: tipoPag,
                    conto_cassa_id: null,
                    importo_pagato: importo,
                    tipo_chiusura: tipo_ch,
                    motivo_sconto: tipo_ch === "sconto" && residuo > 0 ? "Sconto applicato" : null,
                });
                ok += 1;
                totale += importo;
            } catch { ko += 1; }
        }
        setSaving(false);
        if (ok > 0) toast.success(`${ok} titoli incassati per ${fmtEur(totale)}${ko > 0 ? ` · ${ko} errori` : ""}`);
        else toast.error("Nessun titolo incassato");
        onClose(ok > 0);
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose(false)}>
            <DialogContent className="max-w-3xl max-h-[92vh] overflow-hidden flex flex-col" data-testid="bulk-sospesi-dialog">
                <DialogHeader>
                    <DialogTitle>
                        <Layers className="inline mr-2 -mt-1 text-emerald-600" size={18} />
                        Incassa {titoli.length} titoli sospesi — {fmtEur(totalePremio)} totali
                    </DialogTitle>
                </DialogHeader>
                <div className="grid grid-cols-2 gap-3 py-2">
                    <div>
                        <Label>Data incasso</Label>
                        <Input type="date" value={dataIncasso} onChange={(e) => setDataIncasso(e.target.value)} data-testid="bulk-sosp-data" />
                    </div>
                    <div>
                        <Label>Tipo pagamento *</Label>
                        <SelectTipoPagamento value={tipoPag} onChange={setTipoPag} testid="bulk-sosp-tipo" />
                    </div>
                </div>
                <div className="text-xs bg-amber-50 border border-amber-200 rounded p-2 text-amber-900">
                    Modifica l&apos;importo pagato per ciascun titolo. Se importo &lt; premio → residuo trattato come <strong>sconto</strong> (o sospeso).
                    Il conto/cassa viene determinato automaticamente dal tipo pagamento.
                </div>
                <div className="border border-slate-200 rounded overflow-auto flex-1 mt-2">
                    <table className="w-full text-xs">
                        <thead className="bg-slate-50 sticky top-0">
                            <tr>
                                <th className="text-left px-2 py-1.5">Cliente</th>
                                <th className="text-left px-2 py-1.5">Polizza</th>
                                <th className="text-right px-2 py-1.5">Premio</th>
                                <th className="text-right px-2 py-1.5 w-[110px]">Pagato</th>
                                <th className="text-right px-2 py-1.5 w-[80px]">Residuo</th>
                                <th className="text-left px-2 py-1.5 w-[130px]">Se residuo</th>
                            </tr>
                        </thead>
                        <tbody>
                            {titoli.map((t) => {
                                const lordo = parseFloat(t.importo_lordo) || 0;
                                const pt = perTit[t.id] || {};
                                const pagato = parseFloat(pt.importo_pagato);
                                const residuo = Math.max(0, lordo - (isNaN(pagato) ? 0 : pagato));
                                const hasResiduo = residuo > 0.005;
                                return (
                                    <tr key={t.id} className="border-t border-slate-100">
                                        <td className="px-2 py-1 truncate max-w-[180px]" title={t.contraente_nome}>{t.contraente_nome || "—"}</td>
                                        <td className="px-2 py-1 font-mono text-slate-600">{t.numero_polizza}</td>
                                        <td className="px-2 py-1 text-right num">{fmtEur(lordo)}</td>
                                        <td className="px-2 py-1">
                                            <Input type="number" step="0.01" min="0"
                                                value={pt.importo_pagato}
                                                onChange={(e) => setPT(t.id, "importo_pagato", e.target.value)}
                                                className="h-7 text-right num text-xs px-1"
                                                data-testid={`bulk-sosp-imp-${t.id}`}
                                            />
                                        </td>
                                        <td className="px-2 py-1 text-right num text-slate-600">{hasResiduo ? fmtEur(residuo) : "—"}</td>
                                        <td className="px-2 py-1">
                                            {hasResiduo ? (
                                                <Select
                                                    value={pt.tipo_chiusura || "sconto"}
                                                    onValueChange={(v) => setPT(t.id, "tipo_chiusura", v)}
                                                >
                                                    <SelectTrigger className="h-7 text-xs"><SelectValue /></SelectTrigger>
                                                    <SelectContent>
                                                        <SelectItem value="sconto">Sconto</SelectItem>
                                                        <SelectItem value="sospeso">Sospeso (residuo)</SelectItem>
                                                    </SelectContent>
                                                </Select>
                                            ) : <span className="text-slate-300">—</span>}
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                        <tfoot>
                            <tr className="bg-slate-50 font-semibold">
                                <td colSpan="2" className="px-2 py-1.5 text-right">TOTALI</td>
                                <td className="px-2 py-1.5 text-right num">{fmtEur(totalePremio)}</td>
                                <td className="px-2 py-1.5 text-right num text-emerald-700">{fmtEur(totalePagato)}</td>
                                <td colSpan="2"></td>
                            </tr>
                        </tfoot>
                    </table>
                </div>
                <DialogFooter className="mt-3">
                    <Button variant="outline" onClick={() => onClose(false)} disabled={saving}>Annulla</Button>
                    <Button onClick={conferma} disabled={saving || !tipoPag} className="bg-emerald-600 hover:bg-emerald-700" data-testid="bulk-sosp-conferma">
                        {saving ? "Incasso in corso…" : `Conferma incasso ${titoli.length} titoli`}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
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
