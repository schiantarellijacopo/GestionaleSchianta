/**
 * DocCardsScadenza — sezione documenti a CARD per tipologia, stile "card Polizza".
 * Una card per ogni tipologia configurata (sempre visibile anche se vuota),
 * con upload interno alla card e gestione scadenze (rilascio/scadenza + avviso).
 *
 * props:
 *  - cardKey: chiave config /config/card-visibilita (compagnia | agenzia_partner | azienda | collaboratore)
 *  - fallbackTipi: string[] tipologie di default se la config è vuota
 *  - files: array documenti [{id, nome_file, url, tipologia, descrizione, data_rilascio, data_scadenza, avviso_attivo, avviso_giorni}]
 *  - onUpload: async (tipologia, {file, descrizione, data_rilascio, data_scadenza}) => item (deve lanciare in caso di errore)
 *  - onDelete: async (id) => void
 *  - avvisoEntita / avvisoEntitaId: per AvvisoScadenzaControl (null = avviso non disponibile)
 *  - onAvviso: (itemId, patch) => void
 *  - testidPrefix: prefisso per i data-testid
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Upload, FileText, Trash2, Paperclip, X } from "lucide-react";
import DateInputIt from "@/components/DateInputIt";
import AvvisoScadenzaControl from "@/components/AvvisoScadenzaControl";

function scadenzaBadge(dataScadenza) {
    if (!dataScadenza) return null;
    const d = new Date(dataScadenza + "T00:00:00");
    if (isNaN(d)) return null;
    const oggi = new Date(); oggi.setHours(0, 0, 0, 0);
    const giorni = Math.round((d - oggi) / 86400000);
    const dmt = d.toLocaleDateString("it-IT");
    if (giorni < 0) return { label: `Scaduto il ${dmt}`, cls: "bg-red-100 text-red-700" };
    if (giorni <= 30) return { label: `In scadenza (${dmt})`, cls: "bg-amber-100 text-amber-700" };
    return { label: `Scade il ${dmt}`, cls: "bg-slate-100 text-slate-600" };
}

const slugify = (t) => (t || "altro").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "") || "altro";

export default function DocCardsScadenza({
    cardKey,
    fallbackTipi = [],
    files = [],
    onUpload,
    onDelete,
    avvisoEntita = null,
    avvisoEntitaId = null,
    onAvviso,
    testidPrefix = "doc",
}) {
    const [tipi, setTipi] = useState(fallbackTipi);

    useEffect(() => {
        api.get("/config/card-visibilita")
            .then((r) => {
                const lst = (r.data?.[cardKey] || []).map((c) => c.label).filter(Boolean);
                if (lst.length) setTipi(lst);
            }).catch(() => {});
    }, [cardKey]);

    const gruppi = {};
    (files || []).forEach((it) => { const k = it.tipologia || "Altro"; (gruppi[k] = gruppi[k] || []).push(it); });
    const ordine = [...tipi, ...Object.keys(gruppi).filter((k) => !tipi.includes(k))];
    if (!ordine.includes("Altro")) ordine.push("Altro");

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3" data-testid={`${testidPrefix}-cards`}>
            {ordine.map((t) => (
                <DocCard key={t} tipologia={t} files={gruppi[t] || []}
                    onUpload={onUpload} onDelete={onDelete}
                    avvisoEntita={avvisoEntita} avvisoEntitaId={avvisoEntitaId} onAvviso={onAvviso}
                    testidPrefix={testidPrefix} />
            ))}
        </div>
    );
}

function DocCard({ tipologia, files, onUpload, onDelete, avvisoEntita, avvisoEntitaId, onAvviso, testidPrefix }) {
    const [open, setOpen] = useState(true);
    const [adding, setAdding] = useState(false);
    const [file, setFile] = useState(null);
    const [descrizione, setDescrizione] = useState("");
    const [dataRilascio, setDataRilascio] = useState("");
    const [dataScadenza, setDataScadenza] = useState("");
    const [busy, setBusy] = useState(false);
    const slug = slugify(tipologia);

    const reset = () => { setFile(null); setDescrizione(""); setDataRilascio(""); setDataScadenza(""); setAdding(false); };

    const carica = async () => {
        if (!file) { toast.error("Seleziona un file"); return; }
        setBusy(true);
        try {
            await onUpload(tipologia, { file, descrizione, data_rilascio: dataRilascio, data_scadenza: dataScadenza });
            reset();
        } catch { /* toast gestito a monte */ }
        finally { setBusy(false); }
    };

    return (
        <Card className="p-0 overflow-hidden border-slate-200" data-testid={`${testidPrefix}-card-${slug}`}>
            <div className="w-full flex items-center gap-2 px-3 py-2.5 bg-slate-50">
                <button type="button" onClick={() => setOpen((o) => !o)}
                    className="flex items-center gap-2 flex-1 min-w-0 text-left hover:text-slate-900"
                    data-testid={`${testidPrefix}-toggle-${slug}`}>
                    <FileText size={16} className="text-slate-500 shrink-0" />
                    <span className="font-medium text-sm text-slate-800 flex-1 truncate">{tipologia}</span>
                </button>
                <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-200 text-slate-600">{files.length}</span>
                <button type="button" onClick={() => setOpen((o) => !o)}
                    className={`text-slate-400 transition-transform ${open ? "rotate-180" : ""}`}>▾</button>
            </div>
            {open && (
                <div className="p-2.5 space-y-2">
                    {files.length === 0 ? (
                        <div className="text-center text-xs text-slate-400 italic py-3">Nessun documento</div>
                    ) : files.map((a) => {
                        const sc = scadenzaBadge(a.data_scadenza);
                        return (
                            <div key={a.id} className="flex items-center gap-2 p-2 bg-white rounded border border-slate-200 hover:border-sky-300 group"
                                data-testid={`${testidPrefix}-item-${a.id}`}>
                                <Paperclip size={14} className="text-slate-400 shrink-0" />
                                <div className="flex-1 min-w-0">
                                    {a.url ? (
                                        <a href={a.url} target="_blank" rel="noreferrer" className="text-sm text-sky-700 hover:underline truncate block">{a.nome_file || "Apri"}</a>
                                    ) : (
                                        <span className="text-sm text-slate-700 truncate block">{a.nome_file || "—"}</span>
                                    )}
                                    {a.descrizione && <div className="text-[11px] text-slate-500 truncate">{a.descrizione}</div>}
                                    <div className="flex flex-wrap items-center gap-1.5 mt-1">
                                        {a.data_rilascio && <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">Rilascio: {new Date(a.data_rilascio + "T00:00:00").toLocaleDateString("it-IT")}</span>}
                                        {sc && <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${sc.cls}`} data-testid={`${testidPrefix}-scadenza-${a.id}`}>{sc.label}</span>}
                                        {avvisoEntita && <AvvisoScadenzaControl entita={avvisoEntita} entitaId={avvisoEntitaId} item={a} onChange={onAvviso} />}
                                    </div>
                                </div>
                                <button onClick={() => onDelete(a.id)} className="text-red-600 hover:bg-red-50 p-1.5 rounded shrink-0" data-testid={`${testidPrefix}-del-${a.id}`}>
                                    <Trash2 size={13} />
                                </button>
                            </div>
                        );
                    })}

                    {!adding ? (
                        <label className="block w-full p-2.5 text-center border-2 border-dashed border-slate-300 rounded cursor-pointer hover:bg-sky-50 hover:border-sky-300 text-xs text-slate-500 transition"
                            data-testid={`${testidPrefix}-upload-${slug}`}>
                            <Upload size={13} className="inline mr-1" /> Carica documento
                            <input type="file" accept=".pdf,image/*" hidden
                                onChange={(e) => { setFile(e.target.files?.[0] || null); setAdding(true); }} />
                        </label>
                    ) : (
                        <div className="border border-slate-200 rounded-md p-2.5 bg-slate-50 space-y-2" data-testid={`${testidPrefix}-form-${slug}`}>
                            <div className="text-[11px] font-medium text-slate-600 flex items-center gap-1 truncate">
                                <Paperclip size={12} /> {file?.name || "Nessun file selezionato"}
                            </div>
                            <Input type="file" accept=".pdf,image/*" className="h-8 text-xs"
                                onChange={(e) => setFile(e.target.files?.[0] || null)} data-testid={`${testidPrefix}-form-file-${slug}`} />
                            <Input placeholder="Descrizione (facoltativa)" value={descrizione}
                                onChange={(e) => setDescrizione(e.target.value)} className="h-8 text-xs" data-testid={`${testidPrefix}-form-descr-${slug}`} />
                            <div className="grid grid-cols-2 gap-2">
                                <div><Label className="text-[10px] text-slate-500">Rilascio</Label><DateInputIt value={dataRilascio} onChange={setDataRilascio} data-testid={`${testidPrefix}-form-rilascio-${slug}`} /></div>
                                <div><Label className="text-[10px] text-slate-500">Scadenza</Label><DateInputIt value={dataScadenza} onChange={setDataScadenza} data-testid={`${testidPrefix}-form-scadenza-${slug}`} /></div>
                            </div>
                            <div className="flex items-center gap-2">
                                <Button size="sm" className="h-7 bg-sky-700 hover:bg-sky-800 text-xs" onClick={carica} disabled={busy} data-testid={`${testidPrefix}-form-save-${slug}`}>
                                    {busy ? "Caricamento…" : "Carica"}
                                </Button>
                                <button onClick={reset} className="text-xs text-slate-500 hover:text-slate-700 inline-flex items-center gap-0.5" data-testid={`${testidPrefix}-form-cancel-${slug}`}>
                                    <X size={12} /> Annulla
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            )}
        </Card>
    );
}
