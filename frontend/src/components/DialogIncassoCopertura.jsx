/**
 * DialogIncassoCopertura — Replica del facsimile "Incasso / Copertura".
 *
 * Flusso unificato sui titoli:
 *  1) Si controllano e si modificano i dati del titolo (Tipo, date)
 *  2) Si può attivare la "Copertura" (l'agenzia anticipa per il cliente)
 *      con sub-opzioni: invio email a operatori/contraenti, pagamento in direzione
 *  3) Si può attivare l'"Incasso" che apre i campi importo pagato + radio
 *      sconto/sospeso (residuo)
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { api, fmtEur } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import {
    RadioGroup, RadioGroupItem,
} from "@/components/ui/radio-group";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { X } from "lucide-react";
import { toast } from "sonner";
import SelectTipoPagamento from "@/components/SelectTipoPagamento";
import DialogLetteraAbbuono from "@/components/DialogLetteraAbbuono";
import ChiusuraGiornoBanner from "@/components/ChiusuraGiornoBanner";

const TIPO_TITOLO_OPTS = [
    { v: "quietanza", l: "Quietanza" },
    { v: "rinnovo", l: "Rinnovo" },
    { v: "nuova", l: "Nuova" },
    { v: "appendice", l: "Appendice" },
    { v: "regolazione", l: "Regolazione" },
    { v: "storno", l: "Storno" },
];

function addDays(iso, days) {
    if (!iso) return "";
    const d = new Date(`${iso}T00:00:00`);
    d.setDate(d.getDate() + days);
    return d.toISOString().slice(0, 10);
}

export default function DialogIncassoCopertura({ titolo, conti, onClose, onDone }) {
    const now = new Date();
    const today = now.toISOString().slice(0, 10);
    const nowTime = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
    const lordo = parseFloat(titolo.importo_lordo) || 0;
    const [pref, setPref] = useState(null);
    const [showLettera, setShowLettera] = useState(null); // titolo_id quando aprire lettera abbuono

    useEffect(() => {
        if (titolo.contraente_id) {
            api.get(`/anagrafiche/${titolo.contraente_id}`).then((r) => setPref(r.data)).catch(() => {});
        }
    }, [titolo.contraente_id]);

    const giaCoperto = !!titolo.titolo_coperto;
    const giaIncassato = titolo.stato === "incassato";

    // --- DATI BASE titolo
    // Data emissione / Rata del / Data competenza / Scadenza mora → SEMPRE dal titolo
    // Solo "Dalle ore" (ora_effetto) → default ora corrente (istante di copertura)
    const [f, setF] = useState({
        tipo: titolo.tipo || "quietanza",
        data_emissione: titolo.data_emissione || titolo.effetto || today,
        effetto: titolo.effetto || today,
        ora_effetto: nowTime,
        data_competenza: titolo.data_competenza || titolo.effetto || today,
        scadenza_mora: titolo.scadenza_mora || addDays(titolo.effetto || today, 15),
    });
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    // --- COPERTURA
    const [copertura, setCopertura] = useState(!giaCoperto); // default check se non ancora coperto
    // Date di copertura (Data Copertura / Comunicazione incasso / Data Contabile) → default oggi
    const [dataCopertura, setDataCopertura] = useState(today);
    const [comunicazioneIncasso, setComunicazioneIncasso] = useState(today);
    const [dataContabile, setDataContabile] = useState(today);
    // "Data Copertura" è la data GUIDA: modificandola si aggiornano a cascata
    // anche Comunicazione incasso, Data Contabile e le date di incasso (Pagamento/Co.Ge.).
    // Le singole date restano comunque modificabili individualmente dopo.
    const onChangeDataCopertura = (v) => {
        setDataCopertura(v);
        setComunicazioneIncasso(v);
        setDataContabile(v);
        setInc((p) => ({ ...p, data_incasso: v, data_coge: v }));
    };
    // Allega documento + firma
    const [allegatoFile, setAllegatoFile] = useState(null);
    // Toggle email/stampa copertura
    const [emailContraente, setEmailContraente] = useState(false);
    const [emailOperatoreAccount, setEmailOperatoreAccount] = useState(false);
    const [stampaCopertura, setStampaCopertura] = useState(false);
    const [emailSegnalazione, setEmailSegnalazione] = useState(false);
    // Legacy toggles (già esistenti)
    const [emailOperatori, setEmailOperatori] = useState(false);
    const [emailContraenti, setEmailContraenti] = useState(false);
    const [inDirezione, setInDirezione] = useState(false);
    // Nota titolo (visibile anche nella scheda Polizza → Titoli)
    const [notaTitolo, setNotaTitolo] = useState(titolo.nota || "");
    // Snapshot dei dati base all'apertura: il PUT verrà inviato SOLO se l'utente
    // li modifica davvero (evita il blocco "Prima Nota chiusa" su titoli vecchi).
    const baseIniziale = useRef(null);
    useEffect(() => {
        baseIniziale.current = {
            tipo: f.tipo, data_emissione: f.data_emissione, effetto: f.effetto,
            ora_effetto: f.ora_effetto, data_competenza: f.data_competenza,
            scadenza_mora: f.scadenza_mora, nota: notaTitolo || "",
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // --- INCASSO
    const [incasso, setIncasso] = useState(false);
    // Default mezzo pagamento (priorità):
    //  1. polizza.mezzo_pagamento_preferito (specifico di questa polizza)
    //  2. polizza.ultimo_mezzo_pagamento
    //  3. anagrafica preferenza_pagamento
    //  4. anagrafica ultimo_mezzo_pagamento
    //  5. "contanti"
    const polizzaPreferito = titolo.mezzo_pagamento_preferito || titolo.ultimo_mezzo_pagamento;
    const defaultMezzoPol = polizzaPreferito
        || pref?.preferenza_pagamento
        || pref?.ultimo_mezzo_pagamento
        || "contanti";

    const [inc, setInc] = useState({
        data_incasso: today,
        data_coge: today,
        mezzo_pagamento: defaultMezzoPol,
        conto_cassa_id: conti?.[0]?.id || "",
        importo_pagato: lordo,
        tipo_chiusura: "sconto",
        gestione_eccedenza: "maggiorazione",
        motivo_sconto: "",
    });
    useEffect(() => {
        if (polizzaPreferito) {
            setInc((p) => ({ ...p, mezzo_pagamento: polizzaPreferito }));
        } else if (pref?.preferenza_pagamento) {
            setInc((p) => ({ ...p, mezzo_pagamento: pref.preferenza_pagamento }));
        }
    }, [pref, polizzaPreferito]);
    const setI = (k, v) => setInc((p) => ({ ...p, [k]: v }));

    const residuo = useMemo(
        () => Math.max(0, lordo - (parseFloat(inc.importo_pagato) || 0)),
        [lordo, inc.importo_pagato],
    );
    const hasResiduo = residuo > 0.005;
    const eccedenza = useMemo(
        () => Math.max(0, (parseFloat(inc.importo_pagato) || 0) - lordo),
        [lordo, inc.importo_pagato],
    );
    const hasEccedenza = eccedenza > 0.005;

    const conferma = async () => {
        try {
            // 1) AGGIORNA DATI BASE (tipo + date + nota) SOLO se effettivamente cambiati.
            //    Evita il blocco "Prima Nota chiusa" quando si vuole solo incassare/coprire
            //    un titolo la cui data di competenza cade in un periodo già chiuso.
            const b = baseIniziale.current || {};
            const baseChanged = (
                f.tipo !== b.tipo
                || (f.data_emissione || "") !== (b.data_emissione || "")
                || (f.effetto || "") !== (b.effetto || "")
                || (f.ora_effetto || "") !== (b.ora_effetto || "")
                || (f.data_competenza || "") !== (b.data_competenza || "")
                || (f.scadenza_mora || "") !== (b.scadenza_mora || "")
                || (notaTitolo || "") !== (b.nota || "")
            );
            if (baseChanged) {
                await api.put(`/titoli/${titolo.id}`, {
                    tipo: f.tipo,
                    data_emissione: f.data_emissione,
                    effetto: f.effetto,
                    ora_effetto: f.ora_effetto,
                    data_competenza: f.data_competenza,
                    scadenza_mora: f.scadenza_mora,
                    nota: notaTitolo || null,
                });
            }

            // 2) COPERTURA (solo se richiesta, non già coperto E NON si sta incassando).
            //    Se si incassa nello stesso momento, l'incasso registra già l'intera
            //    entrata (Entrate/Provvigioni/Saldo/Banca) in UN'UNICA riga: la copertura
            //    separata creerebbe una seconda riga (copertura_titolo + incasso_coperto).
            if (copertura && !giaCoperto && !incasso) {
                await api.post(`/titoli/bulk-copertura`, {
                    ids: [titolo.id],
                    data_copertura: dataCopertura,
                    comunicazione_incasso: comunicazioneIncasso,
                    data_contabile: dataContabile,
                });
                if (emailOperatori || emailContraenti || emailContraente || emailOperatoreAccount || emailSegnalazione) {
                    try {
                        await api.post(`/titoli/notifica-copertura`, {
                            id: titolo.id,
                            a_operatori: emailOperatori || emailOperatoreAccount,
                            a_contraenti: emailContraenti || emailContraente,
                            stampa: stampaCopertura,
                            segnalazione: emailSegnalazione,
                        });
                    } catch { /* non bloccante */ }
                }
            }

            // 3) INCASSO (se richiesto)
            let letteraId = null;
            if (incasso && !giaIncassato) {
                const r = await api.post(`/titoli/${titolo.id}/incassa`, {
                    data_incasso: inc.data_incasso,
                    data_coge: inc.data_coge,
                    data_copertura: (copertura && !giaCoperto) ? dataCopertura : undefined,
                    mezzo_pagamento: inc.mezzo_pagamento,
                    conto_cassa_id: null,
                    importo_pagato: parseFloat(inc.importo_pagato) || 0,
                    tipo_chiusura: hasResiduo ? inc.tipo_chiusura : "sconto",
                    gestione_eccedenza: hasEccedenza ? inc.gestione_eccedenza : "maggiorazione",
                    motivo_sconto:
                        hasResiduo && inc.tipo_chiusura === "sconto"
                            ? (inc.motivo_sconto || "Sconto applicato")
                            : null,
                });
                letteraId = r.data?.lettera_abbuono_id || null;
            }

            // Allega documento → salvato sulla POLIZZA in categoria "quietanza",
            // così compare nella sezione Documenti > Quietanze (sempre, sia in
            // copertura sia in incasso).
            // Upload in BACKGROUND: l'operazione (incasso/copertura) è già salvata,
            // quindi chiudiamo subito il dialog e carichiamo il file senza far
            // attendere l'utente (con toast di esito a fine caricamento).
            if (allegatoFile && titolo.polizza_id) {
                const fd = new FormData();
                fd.append("file", allegatoFile);
                const upToast = toast.loading("Caricamento allegato in corso…");
                api.post("/allegati", fd, {
                    params: {
                        entita_tipo: "polizza",
                        entita_id: titolo.polizza_id,
                        categoria: "quietanza",
                        visibile_cliente: true,
                        descrizione: "Quietanza (da incasso/copertura)",
                    },
                    headers: { "Content-Type": "multipart/form-data" },
                })
                    .then(() => toast.success("Allegato caricato", { id: upToast }))
                    .catch(() => toast.error("Allegato NON caricato — riprova dalla scheda polizza", { id: upToast }));
            }

            const msg = [
                copertura && !giaCoperto && !incasso ? "copertura registrata" : null,
                incasso && !giaIncassato
                    ? (hasEccedenza
                        ? (inc.gestione_eccedenza === "credito"
                            ? `incassato ${fmtEur(inc.importo_pagato)} (eccedenza ${fmtEur(eccedenza)} a credito cliente)`
                            : `incassato ${fmtEur(inc.importo_pagato)} (maggiorazione ${fmtEur(eccedenza)} in prima nota)`)
                        : hasResiduo
                            ? (inc.tipo_chiusura === "sospeso"
                                ? `incassato ${fmtEur(inc.importo_pagato)} (residuo ${fmtEur(residuo)} a sospeso)`
                                : `incassato ${fmtEur(inc.importo_pagato)} (sconto ${fmtEur(residuo)})`)
                            : `incassato ${fmtEur(inc.importo_pagato)}`)
                    : null,
            ].filter(Boolean).join(" — ");
            toast.success(msg || "Salvato");
            if (letteraId) {
                // Auto-apri la lettera di abbuono per la doppia firma
                setShowLettera(titolo.id);
                if (onDone) onDone();
                return;
            }
            if (onDone) onDone();
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore salvataggio");
        }
    };

    // Stile tabella ottimizzato: celle compatte, allineate, contrasto migliore
    const cellLabel = "bg-slate-50 text-slate-600 font-medium text-right px-2 py-1.5 align-middle border border-slate-200 text-xs w-[140px] whitespace-nowrap";
    const cellValueRO = "bg-cyan-50/60 text-slate-800 px-2 py-1.5 align-middle border border-slate-200 text-sm";
    const cellValueEdit = "bg-cyan-50/40 px-1.5 py-1 align-middle border border-slate-200";

    return (
        <>
        {showLettera && (
            <DialogLetteraAbbuono
                titoloId={showLettera}
                onClose={() => { setShowLettera(null); onClose(); }}
            />
        )}
        <Dialog open onOpenChange={onClose}>
            <DialogContent
                className="max-w-2xl p-0 overflow-hidden bg-white"
                data-testid="dialog-incasso-copertura"
            >
                {/* Header stile facsimile */}
                <DialogHeader className="px-6 py-3 border-b border-slate-200 bg-white flex flex-row items-center justify-between">
                    <DialogTitle className="text-slate-800 font-semibold">
                        Incasso / Copertura
                    </DialogTitle>
                    <button
                        onClick={onClose}
                        className="text-slate-400 hover:text-slate-600"
                        data-testid="dialog-close"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </DialogHeader>

                <div className="px-6 py-3 max-h-[82vh] overflow-y-auto [&_input]:h-8 [&_[role=combobox]]:h-8">
                    {/* ---- Tabella anagrafica ---- */}
                    <table className="w-full border-collapse text-sm">
                        <tbody>
                            <tr>
                                <td className={cellLabel}>Num. Contratto</td>
                                <td className={cellValueRO} data-testid="ico-num-contratto">
                                    <span className="text-slate-700 underline">{titolo.numero_polizza || titolo.polizza_numero || "—"}</span>
                                </td>
                            </tr>
                            <tr>
                                <td className={cellLabel}>Contraente</td>
                                <td className={cellValueRO} data-testid="ico-contraente">
                                    {titolo.contraente_nome || "—"}
                                </td>
                            </tr>
                            <tr>
                                <td className={cellLabel}>Compagnia</td>
                                <td className={cellValueRO} data-testid="ico-compagnia">
                                    {titolo.compagnia_nome || "—"}
                                </td>
                            </tr>
                            <tr>
                                <td className={cellLabel}>Tipo</td>
                                <td className={cellValueRO}>{titolo.ramo || "—"}</td>
                            </tr>

                            <tr>
                                <td className={cellLabel}>Tipo titolo</td>
                                <td className={cellValueEdit}>
                                    <Select value={f.tipo} onValueChange={(v) => set("tipo", v)}>
                                        <SelectTrigger className="bg-white" data-testid="ico-tipo-titolo">
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {TIPO_TITOLO_OPTS.map((o) => (
                                                <SelectItem key={o.v} value={o.v}>{o.l}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </td>
                            </tr>

                            <tr>
                                <td className={cellLabel}>Data emissione</td>
                                <td className={cellValueEdit}>
                                    <Input
                                        type="date" value={f.data_emissione}
                                        onChange={(e) => set("data_emissione", e.target.value)}
                                        className="bg-white" data-testid="ico-data-emissione"
                                    />
                                </td>
                            </tr>
                        </tbody>
                    </table>

                    {/* ---- Rata del / Dalle ore / Data competenza / Scadenza mora ---- */}
                    <table className="w-full border-collapse text-sm mt-4">
                        <tbody>
                            <tr>
                                <td className={cellLabel}>Rata del</td>
                                <td className={cellValueEdit}>
                                    <Input
                                        type="date" value={f.effetto}
                                        onChange={(e) => set("effetto", e.target.value)}
                                        className="bg-white" data-testid="ico-rata-del"
                                    />
                                </td>
                                <td className={cellLabel + " w-[120px]"}>Dalle ore</td>
                                <td className={cellValueEdit + " w-[120px]"}>
                                    <Input
                                        type="time" value={f.ora_effetto}
                                        onChange={(e) => set("ora_effetto", e.target.value)}
                                        className="bg-white" data-testid="ico-ora"
                                    />
                                </td>
                            </tr>
                            <tr>
                                <td className={cellLabel}>Data competenza</td>
                                <td className={cellValueEdit}>
                                    <Input
                                        type="date" value={f.data_competenza}
                                        onChange={(e) => set("data_competenza", e.target.value)}
                                        className="bg-white" data-testid="ico-data-competenza"
                                    />
                                </td>
                                <td className={cellLabel}>Scadenza mora</td>
                                <td className={cellValueEdit}>
                                    <Input
                                        type="date" value={f.scadenza_mora}
                                        onChange={(e) => set("scadenza_mora", e.target.value)}
                                        className="bg-white" data-testid="ico-scadenza-mora"
                                    />
                                </td>
                            </tr>
                        </tbody>
                    </table>

                    {/* ---- COPERTURA ---- */}
                    <div className="mt-6">
                        <label
                            htmlFor="cb-copertura"
                            className="flex items-center gap-3 cursor-pointer"
                        >
                            <Checkbox
                                id="cb-copertura"
                                checked={copertura}
                                onCheckedChange={(v) => setCopertura(v === true)}
                                disabled={giaCoperto}
                                data-testid="cb-copertura"
                            />
                            <span className="text-cyan-700 font-semibold text-lg">
                                Copertura {giaCoperto && <span className="text-emerald-700 text-xs ml-2">(già coperto)</span>}
                            </span>
                        </label>
                        {copertura && (
                            <div className="pl-8 mt-3 space-y-3" data-testid="copertura-options">
                                <ChiusuraGiornoBanner data={dataCopertura} />

                                {/* Data Copertura / Comunicazione incasso / Data Contabile */}
                                <table className="w-full border-collapse text-sm">
                                    <tbody>
                                        <tr>
                                            <td className={cellLabel}>Data Copertura</td>
                                            <td className={cellValueEdit} colSpan={3}>
                                                <Input type="date" value={dataCopertura}
                                                    onChange={(e) => onChangeDataCopertura(e.target.value)}
                                                    className="bg-white" data-testid="ico-data-copertura" />
                                            </td>
                                        </tr>
                                        <tr>
                                            <td className={cellLabel}>Comunicazione incasso</td>
                                            <td className={cellValueEdit}>
                                                <Input type="date" value={comunicazioneIncasso}
                                                    onChange={(e) => setComunicazioneIncasso(e.target.value)}
                                                    className="bg-white" data-testid="ico-comunicazione-incasso" />
                                            </td>
                                            <td className={cellLabel}>Data Contabile</td>
                                            <td className={cellValueEdit}>
                                                <Input type="date" value={dataContabile}
                                                    onChange={(e) => setDataContabile(e.target.value)}
                                                    className="bg-white" data-testid="ico-data-contabile" />
                                            </td>
                                        </tr>
                                    </tbody>
                                </table>

                                {/* Allega documento */}
                                <div className="border border-cyan-200 bg-cyan-50/40 rounded p-3 space-y-2">
                                    <div className="text-cyan-800 font-medium text-sm">Allega documento</div>
                                    <div className="flex items-center gap-2">
                                        <input
                                            type="file"
                                            accept=".pdf,.jpg,.jpeg,.png,.doc,.docx"
                                            onChange={(e) => setAllegatoFile(e.target.files?.[0] || null)}
                                            className="text-xs"
                                            data-testid="ico-allega-file"
                                        />
                                    </div>
                                    <div className="text-[11px] text-slate-500">
                                        File di firma: <span className="italic">{allegatoFile ? allegatoFile.name : "(nessun file di firma)"}</span>
                                    </div>
                                    <label className="flex items-center gap-2 text-cyan-700 text-sm cursor-pointer">
                                        <Checkbox
                                            checked={emailContraente}
                                            onCheckedChange={(v) => setEmailContraente(v === true)}
                                            data-testid="cb-email-contraente-single"
                                        />
                                        Invia email a contraente
                                    </label>
                                    <label className="flex items-center gap-2 text-cyan-700 text-sm cursor-pointer">
                                        <Checkbox
                                            checked={emailOperatoreAccount}
                                            onCheckedChange={(v) => setEmailOperatoreAccount(v === true)}
                                            data-testid="cb-email-op-account"
                                        />
                                        Invia email a operatore account
                                    </label>
                                </div>

                                {/* Toggle stampa / email segnalazione */}
                                <label className="flex items-center gap-2 text-slate-700 text-sm cursor-pointer">
                                    <Checkbox
                                        checked={stampaCopertura}
                                        onCheckedChange={(v) => setStampaCopertura(v === true)}
                                        data-testid="cb-stampa-copertura"
                                    />
                                    Stampa documento copertura contraente
                                </label>
                                <label className="flex items-center gap-2 text-slate-700 text-sm cursor-pointer">
                                    <Checkbox
                                        checked={emailSegnalazione}
                                        onCheckedChange={(v) => setEmailSegnalazione(v === true)}
                                        data-testid="cb-email-segnalazione"
                                    />
                                    Invia email segnalazione copertura
                                </label>

                                <div className="border-t border-slate-200 my-2" />

                                <label className="flex items-center gap-2 text-cyan-700 text-sm cursor-pointer">
                                    <Checkbox
                                        checked={emailOperatori}
                                        onCheckedChange={(v) => setEmailOperatori(v === true)}
                                        data-testid="cb-email-op"
                                    />
                                    Invia email di notifica a operatori
                                </label>
                                <label className="flex items-center gap-2 text-cyan-700 text-sm cursor-pointer">
                                    <Checkbox
                                        checked={emailContraenti}
                                        onCheckedChange={(v) => setEmailContraenti(v === true)}
                                        data-testid="cb-email-cnt"
                                    />
                                    Invia email di notifica a contraenti
                                </label>
                            </div>
                        )}
                    </div>

                    {/* ---- NOTA TITOLO ---- */}
                    <div className="mt-4 border border-amber-200 bg-amber-50/40 rounded p-3">
                        <label className="text-xs font-semibold text-amber-800 flex items-center gap-1 mb-1">
                            📝 Nota sul titolo
                            <span className="text-[10px] text-slate-500 font-normal ml-1">
                                (visibile nella scheda polizza → sezione Titoli)
                            </span>
                        </label>
                        <textarea
                            value={notaTitolo}
                            onChange={(e) => setNotaTitolo(e.target.value)}
                            placeholder="Es. Il cliente ha chiesto di aspettare la scadenza mora, contattato il 22/07…"
                            className="w-full text-sm border border-slate-300 rounded p-2 min-h-[60px] bg-white"
                            data-testid="ico-nota-titolo"
                        />
                    </div>

                    {/* ---- INCASSO ---- */}
                    <div className="mt-4">
                        <label
                            htmlFor="cb-incasso"
                            className="flex items-center gap-3 cursor-pointer"
                        >
                            <Checkbox
                                id="cb-incasso"
                                checked={incasso}
                                onCheckedChange={(v) => setIncasso(v === true)}
                                disabled={giaIncassato}
                                data-testid="cb-incasso"
                            />
                            <span className="text-cyan-700 font-semibold text-lg">
                                Incasso {giaIncassato && <span className="text-emerald-700 text-xs ml-2">(già incassato)</span>}
                            </span>
                        </label>

                        {incasso && (
                            <div className="pl-8 mt-3 space-y-3" data-testid="incasso-options">
                                <ChiusuraGiornoBanner data={inc.data_incasso} />
                                <table className="w-full border-collapse text-sm">
                                    <tbody>
                                        <tr>
                                            <td className={cellLabel}>Data Pagamento</td>
                                            <td className={cellValueEdit}>
                                                <Input
                                                    type="date" value={inc.data_incasso}
                                                    onChange={(e) => setI("data_incasso", e.target.value)}
                                                    className="bg-white" data-testid="ico-data-incasso"
                                                />
                                            </td>
                                            <td className={cellLabel}>Data Co.Ge.</td>
                                            <td className={cellValueEdit}>
                                                <Input
                                                    type="date" value={inc.data_coge}
                                                    onChange={(e) => setI("data_coge", e.target.value)}
                                                    className="bg-white" data-testid="ico-data-coge"
                                                />
                                            </td>
                                        </tr>
                                    </tbody>
                                </table>
                                <div>
                                    <div className="text-xs text-slate-600 mb-1">Tipo pagamento</div>
                                    <SelectTipoPagamento
                                        value={inc.mezzo_pagamento}
                                        onChange={(v) => setI("mezzo_pagamento", v)}
                                        testid="ico-mezzo"
                                    />
                                    {polizzaPreferito && (
                                        <div className="text-[10px] text-emerald-700 mt-1" data-testid="hint-mezzo-polizza">
                                            ★ Preferito su questa polizza: <strong>{polizzaPreferito}</strong>
                                        </div>
                                    )}
                                </div>
                                <div className="text-[10px] text-slate-500">
                                    Il conto/banca viene determinato automaticamente dal mezzo di pagamento (vedi Librerie → Conti cassa).
                                </div>

                                <div className="bg-emerald-50 border border-emerald-200 rounded p-3">
                                    <div className="text-xs text-emerald-900 font-semibold mb-1">
                                        Importo pagato dal cliente (premio: {fmtEur(lordo)})
                                    </div>
                                    <Input
                                        type="number" step="0.01"
                                        value={inc.importo_pagato}
                                        onChange={(e) => setI("importo_pagato", e.target.value)}
                                        className="text-lg font-semibold bg-white"
                                        data-testid="ico-importo-pagato"
                                    />

                                    {hasResiduo && (
                                        <div
                                            className="bg-white border border-amber-300 rounded p-2 mt-2 space-y-2"
                                            data-testid="residuo-section"
                                        >
                                            <div className="flex justify-between items-center font-semibold text-amber-800 text-sm">
                                                <span>Residuo:</span>
                                                <span className="num">{fmtEur(residuo)}</span>
                                            </div>
                                            <RadioGroup
                                                value={inc.tipo_chiusura}
                                                onValueChange={(v) => setI("tipo_chiusura", v)}
                                                className="space-y-1"
                                            >
                                                <label
                                                    htmlFor="opt-sc"
                                                    className={`flex items-start gap-2 p-2 rounded border cursor-pointer ${
                                                        inc.tipo_chiusura === "sconto"
                                                            ? "border-amber-400 bg-amber-50"
                                                            : "border-slate-200 hover:bg-slate-50"
                                                    }`}
                                                >
                                                    <RadioGroupItem id="opt-sc" value="sconto" data-testid="opt-sconto" />
                                                    <span className="text-xs">
                                                        <strong>Applica sconto</strong> — {fmtEur(residuo)} in Prima Nota uscita
                                                    </span>
                                                </label>
                                                <label
                                                    htmlFor="opt-sp"
                                                    className={`flex items-start gap-2 p-2 rounded border cursor-pointer ${
                                                        inc.tipo_chiusura === "sospeso"
                                                            ? "border-amber-400 bg-amber-50"
                                                            : "border-slate-200 hover:bg-slate-50"
                                                    }`}
                                                >
                                                    <RadioGroupItem id="opt-sp" value="sospeso" data-testid="opt-sospeso" />
                                                    <span className="text-xs">
                                                        <strong>Lascia a sospeso</strong> — nuovo titolo residuo da {fmtEur(residuo)}
                                                    </span>
                                                </label>
                                            </RadioGroup>
                                            {inc.tipo_chiusura === "sconto" && (
                                                <Input
                                                    placeholder="Motivo sconto (opzionale)"
                                                    value={inc.motivo_sconto}
                                                    onChange={(e) => setI("motivo_sconto", e.target.value)}
                                                    className="text-xs bg-white"
                                                    data-testid="ico-motivo-sconto"
                                                />
                                            )}
                                        </div>
                                    )}

                                    {hasEccedenza && (
                                        <div
                                            className="bg-white border border-sky-300 rounded p-2 mt-2 space-y-2"
                                            data-testid="eccedenza-section"
                                        >
                                            <div className="flex justify-between items-center font-semibold text-sky-800 text-sm">
                                                <span>Eccedenza (pagato oltre il premio):</span>
                                                <span className="num" data-testid="ico-eccedenza">{fmtEur(eccedenza)}</span>
                                            </div>
                                            <RadioGroup
                                                value={inc.gestione_eccedenza}
                                                onValueChange={(v) => setI("gestione_eccedenza", v)}
                                                className="space-y-1"
                                            >
                                                <label
                                                    htmlFor="opt-ecc-mag"
                                                    className={`flex items-start gap-2 p-2 rounded border cursor-pointer ${
                                                        inc.gestione_eccedenza === "maggiorazione"
                                                            ? "border-sky-400 bg-sky-50"
                                                            : "border-slate-200 hover:bg-slate-50"
                                                    }`}
                                                >
                                                    <RadioGroupItem id="opt-ecc-mag" value="maggiorazione" data-testid="ico-ecc-maggiorazione" />
                                                    <span className="text-xs">
                                                        <strong>Registra come maggiorazione</strong> — {fmtEur(eccedenza)} entra in Prima Nota come entrata extra
                                                    </span>
                                                </label>
                                                <label
                                                    htmlFor="opt-ecc-cred"
                                                    className={`flex items-start gap-2 p-2 rounded border cursor-pointer ${
                                                        inc.gestione_eccedenza === "credito"
                                                            ? "border-sky-400 bg-sky-50"
                                                            : "border-slate-200 hover:bg-slate-50"
                                                    }`}
                                                >
                                                    <RadioGroupItem id="opt-ecc-cred" value="credito" data-testid="ico-ecc-credito" />
                                                    <span className="text-xs">
                                                        <strong>Lascia a credito del cliente</strong> — nuovo titolo credito da {fmtEur(eccedenza)}
                                                    </span>
                                                </label>
                                            </RadioGroup>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>

                    {/* ---- Totale ---- */}
                    <div className="mt-6 border-t border-slate-200 pt-3 flex justify-end items-center gap-3">
                        <span className="text-slate-700 font-medium">Totale:</span>
                        <span
                            className="bg-cyan-50 border border-slate-200 px-3 py-1.5 text-base num font-semibold text-cyan-900"
                            data-testid="ico-totale"
                        >
                            {fmtEur(lordo)}
                        </span>
                    </div>
                </div>

                {/* ---- Footer ---- */}
                <div className="px-6 py-3 border-t border-slate-200 bg-slate-50 flex justify-end gap-2">
                    <Button
                        variant="outline" onClick={onClose}
                        data-testid="ico-chiudi"
                    >Chiudi</Button>
                    <Button
                        onClick={conferma}
                        className="bg-slate-800 hover:bg-slate-900"
                        data-testid="ico-conferma"
                    >Conferma</Button>
                </div>
            </DialogContent>
        </Dialog>
        </>
    );
}
