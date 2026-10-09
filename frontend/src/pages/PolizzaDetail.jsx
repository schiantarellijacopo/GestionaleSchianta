import { useEffect, useState } from "react";
import { useParams, Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, fmtDate, fmtEur } from "@/lib/api";
import { PageHeader, StatusBadge, Loading } from "@/components/Shared";
import CollaboratoreInlineSelect from "@/components/CollaboratoreInlineSelect";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { ArrowLeft, Car, ShieldCheck, Banknote, FileText, Info, Pencil, Trash2, AlertTriangle, Zap, ClipboardList } from "lucide-react";
import { toast } from "sonner";
import useMezziPagamento from "@/hooks/useMezziPagamento";
import { useAuth } from "@/contexts/AuthContext";
import DialogIncassoCopertura from "@/components/DialogIncassoCopertura";
import DialogLetteraAbbuono from "@/components/DialogLetteraAbbuono";
import LibroMatricolaTab from "@/components/LibroMatricolaTab";
import AssicuratiTab from "@/components/AssicuratiTab";
import RegolazionePolizzaTab from "@/components/RegolazionePolizzaTab";
import { QuestionariViewer } from "@/components/Questionari";
import RegolazionePremioDialog from "@/components/RegolazionePremioDialog";
import TargaConflictWidget from "@/components/TargaConflictWidget";
import TargaSearchWithLentina from "@/components/TargaSearchWithLentina";
import SelectTipoPagamento from "@/components/SelectTipoPagamento";
import TitoloDialog from "@/components/TitoloDialog";
import IntestatarioAutocomplete from "@/components/IntestatarioAutocomplete";
import DocumentiPolizzaTab from "@/components/DocumentiPolizzaTab";
import { GeneraDocumentoButton } from "@/components/GeneraDocumentoButton";
import { TaskCollegati } from "@/components/TaskCollegati";
import DocumentiSezioneSplit from "@/components/DocumentiSezioneSplit";
import TagsEditor from "@/components/TagsEditor";
import AzioniPolizzaTab from "@/components/AzioniPolizzaTab";
import AllegatiCell from "@/components/AllegatiCell";

export default function PolizzaDetail() {
    const { id } = useParams();
    const navigate = useNavigate();
    const { user } = useAuth();
    const [pol, setPol] = useState(null);
    const [editOpen, setEditOpen] = useState(false);
    const [premiEdit, setPremiEdit] = useState(false);
    const [premiForm, setPremiForm] = useState(null);
    const [premiSaving, setPremiSaving] = useState(false);
    const [librettoUp, setLibrettoUp] = useState(false);
    const [veicoloEdit, setVeicoloEdit] = useState(false);
    const [veicoloForm, setVeicoloForm] = useState(null);
    const [veicoloSaving, setVeicoloSaving] = useState(false);
    const [provvEdit, setProvvEdit] = useState(false);
    const [provvVal, setProvvVal] = useState("");
    const [provvSaving, setProvvSaving] = useState(false);
    const [mupBusy, setMupBusy] = useState(false);
    const [mupFirmaMenu, setMupFirmaMenu] = useState(false);
    const [mupOpen, setMupOpen] = useState(false);
    const [mupArea, setMupArea] = useState("");
    const [mupRighe, setMupRighe] = useState([]);
    const [mupModelli, setMupModelli] = useState([]);
    const [mupModelloId, setMupModelloId] = useState("");

    const apriMup = async () => {
        setMupBusy(true);
        try {
            const r = await api.get(`/polizze/${id}/mup/righe-default`);
            setMupArea(r.data.area); setMupRighe(r.data.righe || []);
            setMupModelli(r.data.modelli || []); setMupModelloId(r.data.modello_id || "");
            setMupOpen(true);
        } catch { toast.error("Errore caricamento MUP"); } finally { setMupBusy(false); }
    };

    const cambiaModelloMup = async (mid) => {
        setMupBusy(true);
        try {
            const r = await api.get(`/polizze/${id}/mup/righe-default`, { params: { modello_id: mid } });
            setMupArea(r.data.area); setMupRighe(r.data.righe || []); setMupModelloId(mid);
        } catch { toast.error("Errore caricamento modello"); } finally { setMupBusy(false); }
    };

    const toggleMup = (i, col) => setMupRighe((p) => p.map((r, idx) => idx === i ? { ...r, [col]: !r[col] } : r));

    const generaMup = async (salva) => {
        setMupBusy(true);
        try {
            if (salva) {
                const r = await api.post(`/polizze/${id}/mup/genera`, { area: mupArea, righe: mupRighe, modello_id: mupModelloId, salva: true });
                toast.success(`MUP archiviato nei documenti della polizza (${r.data.nome_file})`);
                setMupOpen(false);
            } else {
                const r = await api.post(`/polizze/${id}/mup/genera`, { area: mupArea, righe: mupRighe, modello_id: mupModelloId, salva: false }, { responseType: "blob" });
                const url = URL.createObjectURL(new Blob([r.data], { type: "application/pdf" }));
                const w = window.open(url, "_blank");
                if (!w) { const a = document.createElement("a"); a.href = url; a.download = "MUP.pdf"; a.click(); }
                setTimeout(() => URL.revokeObjectURL(url), 60000);
            }
        } catch { toast.error("Errore generazione MUP"); } finally { setMupBusy(false); }
    };

    const firmaMup = async (canali = { wa: true, email: true }) => {
        setMupBusy(true);
        try {
            // 1) Genera e archivia il MUP come allegato PDF della polizza
            const r0 = await api.post(`/polizze/${id}/mup/genera`, { area: mupArea, righe: mupRighe, modello_id: mupModelloId, salva: true });
            const allegatoId = r0.data.allegato_id;
            if (!allegatoId) throw new Error("MUP non archiviato");
            // 2) Invia per firma (OpenAPI eSignature, OTP SMS) con i canali scelti
            const r = await api.post("/esignature/invia", { allegato_id: allegatoId, invia_whatsapp: !!canali.wa, invia_email: !!canali.email });
            if (r.data.signing_url) window.open(r.data.signing_url, "_blank");
            const via = [canali.wa && "WhatsApp", canali.email && "Email"].filter(Boolean).join(" + ") || "solo link";
            toast.success(`MUP inviato per firma (${via}) + OTP SMS al contraente`);
            setMupOpen(false);
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || e.message || "Errore firma MUP");
        } finally { setMupBusy(false); setMupFirmaMenu(false); }
    };
    const [searchParams, setSearchParams] = useSearchParams();
    const [conti, setConti] = useState([]);
    const [paying, setPaying] = useState(null);
    const [letteraAbbuonoTitolo, setLetteraAbbuonoTitolo] = useState(null);
    const [titoloEditing, setTitoloEditing] = useState(null);
    const [regolazioneOpen, setRegolazioneOpen] = useState(false);
    const load = () => api.get(`/polizze/${id}`).then((r) => setPol(r.data));
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);
    useEffect(() => {
        if (pol && searchParams.get("edit") === "1") {
            setEditOpen(true);
            searchParams.delete("edit");
            setSearchParams(searchParams, { replace: true });
        }
        /* eslint-disable-next-line */
    }, [pol]);
    useEffect(() => {
        api.get("/librerie/conti-cassa", { params: { attivi: true } }).then((r) => setConti(r.data || [])).catch(() => {});
    }, []);
    if (!pol) return <Loading />;

    // Sezione Vita/Previdenza: solo per polizze del ramo vita/previdenza
    const _ramoTxt = `${pol.ramo || ""} ${pol.ramo_originale || ""} ${pol.prodotto || ""}`.toUpperCase();
    const isRamoVita = /VITA|PREVID|TCM|TEMPORANEA CASO MORTE/.test(_ramoTxt) || (pol.rendita_annua || 0) > 0;
    // Polizza non eliminabile se esistono titoli incassati o coperti
    const haTitoliBloccanti = (pol.titoli || []).some(
        (t) => t.stato === "incassato" || t.titolo_coperto || t.data_copertura,
    );

    const canEdit = ["admin", "collaboratore", "dipendente"].includes(user?.role);
    const isVeicoloPolRaw = /rca|rc\s*auto|autovettur|autocarr|motocicl|ciclomotor|\bauto\b|\bmoto\b|veicol|natant|imbarcaz/i
        .test(`${pol.ramo || ""} ${pol.prodotto || ""}`);
    // Su polizze Libro Matricola / cumulative NON si mostra la singola tab "Veicolo"
    // (si usa la tab Libro Matricola / Assicurati con applicazioni per veicolo/persona).
    const isVeicoloPol = (isVeicoloPolRaw || !!pol.prodotto_mostra_veicolo) && !pol.is_libro_matricola && !pol.is_cumulativa_assicurati;
    const defaultTab = pol.is_libro_matricola ? "libro-matricola"
        : pol.is_cumulativa_assicurati ? "assicurati"
        : isVeicoloPol ? "veicolo" : "garanzie";
    const canDelete = user?.role === "admin";

    const incassa = async (tid) => {
        try { await api.post(`/titoli/${tid}/incassa`, { mezzo_pagamento: "bonifico" }); toast.success("Incassato"); load(); }
        catch { toast.error("Errore"); }
    };

    const marcaSospeso = async (tid) => {
        if (!window.confirm("Segnare questo titolo come SOSPESO (coperto dall'agenzia)? Se era incassato, l'incasso verrà annullato.")) return;
        try { await api.post(`/titoli/${tid}/marca-sospeso`); toast.success("Titolo segnato come sospeso"); load(); }
        catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const stornaCopertura = async (tid) => {
        if (!window.confirm("Stornare la copertura di questo titolo? I relativi movimenti in Prima Nota verranno rimossi.")) return;
        try { await api.post(`/titoli/${tid}/storna-copertura`); toast.success("Copertura stornata"); load(); }
        catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const rimettiArretrato = async (tid) => {
        if (!window.confirm("Riportare questo titolo in ARRETRATO (da incassare)? Verranno annullati incasso e copertura e rimossi i relativi movimenti in Prima Nota.")) return;
        try { await api.post(`/titoli/${tid}/rimetti-arretrato`); toast.success("Titolo riportato in arretrato"); load(); }
        catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const stornaTitolo = async (tid) => {
        if (!window.confirm("Stornare questo titolo in arretrato? Verrà escluso dagli incassi (stato 'stornato'), lo storico resta consultabile. Nessun movimento di Prima Nota.")) return;
        try { await api.post(`/titoli/${tid}/storna`); toast.success("Titolo stornato"); load(); }
        catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const startPremiEdit = () => {
        setPremiForm({
            premio_netto: pol.premio_netto ?? 0,
            premio_imposte: pol.premio_imposte ?? 0,
            premio_ssn: pol.premio_ssn ?? 0,
            premio_accessori: pol.premio_accessori ?? 0,
            premio_addizionale: pol.premio_addizionale ?? 0,
            diritti: pol.diritti ?? 0,
        });
        setPremiEdit(true);
    };
    const calcLordo = (f) => Math.round((
        (parseFloat(f.premio_netto) || 0) +
        (parseFloat(f.premio_imposte) || 0) +
        (parseFloat(f.premio_ssn) || 0) +
        (parseFloat(f.premio_accessori) || 0) +
        (parseFloat(f.premio_addizionale) || 0)
    ) * 100) / 100;
    const savePremi = async () => {
        setPremiSaving(true);
        try {
            const payload = {};
            Object.entries(premiForm).forEach(([k, v]) => { payload[k] = parseFloat(v) || 0; });
            payload.premio_lordo = calcLordo(premiForm);
            await api.put(`/polizze/${pol.id}`, payload);
            toast.success("Premi aggiornati");
            setPremiEdit(false);
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        } finally { setPremiSaving(false); }
    };

    const uploadLibretto = async (file) => {
        if (!file) return;
        setLibrettoUp(true);
        try {
            const fd = new FormData();
            fd.append("file", file);
            fd.append("polizza_id", pol.id);
            const r = await api.post(`/ocr/libretto`, fd, { headers: { "Content-Type": "multipart/form-data" } });
            const dati = r.data?.dati || {};
            const campi = Object.keys(dati).filter((k) => dati[k] !== null && dati[k] !== "" && dati[k] !== undefined);
            if (campi.length) {
                await api.post(`/ocr/libretto/apply`, {
                    polizza_id: pol.id,
                    dati,
                    allegato_id: r.data?.allegato_id,
                    campi,
                });
            }
            toast.success("Libretto caricato e dati veicolo aggiornati");
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore caricamento libretto");
        } finally { setLibrettoUp(false); }
    };

    const VEICOLO_NUM_FIELDS = ["veicolo_quintali", "franchigia", "valore_veicolo", "valore_residuo_veicolo", "valore_accessori"];
    const startVeicoloEdit = () => {
        setVeicoloForm({
            targa: pol.targa || "",
            veicolo_marca: pol.veicolo_marca || "",
            veicolo_modello: pol.veicolo_modello || "",
            veicolo_tipo: pol.veicolo_tipo || "",
            veicolo_alimentazione: pol.veicolo_alimentazione || "",
            veicolo_uso: pol.veicolo_uso || "",
            veicolo_data_immatricolazione: pol.veicolo_data_immatricolazione || "",
            veicolo_cv_fiscali: pol.veicolo_cv_fiscali || "",
            veicolo_kw: pol.veicolo_kw || "",
            veicolo_quintali: pol.veicolo_quintali ?? "",
            veicolo_cilindrata: pol.veicolo_cilindrata || "",
            veicolo_posti: pol.veicolo_posti || "",
            veicolo_gancio_traino: !!pol.veicolo_gancio_traino,
            veicolo_targa_rimorchio: pol.veicolo_targa_rimorchio || "",
            tipo_tariffa: pol.tipo_tariffa || "",
            bm_provenienza: pol.bm_provenienza || "",
            bm_assegnata: pol.bm_assegnata || "",
            bm_assegnata_cu: pol.bm_assegnata_cu || "",
            pejus: pol.pejus ?? "",
            franchigia: pol.franchigia ?? 0,
            valore_veicolo: pol.valore_veicolo ?? 0,
            valore_residuo_veicolo: pol.valore_residuo_veicolo ?? 0,
            valore_accessori: pol.valore_accessori ?? 0,
            guida_esperta: !!pol.guida_esperta,
            guida_esclusiva: !!pol.guida_esclusiva,
            rinuncia_rivalsa: !!pol.rinuncia_rivalsa,
            intestatario: pol.intestatario || "",
            provincia_intestatario: pol.provincia_intestatario || "",
            massimali: pol.massimali || "",
            massimale_cose: pol.massimale_cose != null ? Number(pol.massimale_cose).toLocaleString("it-IT") : "",
            massimale_persone: pol.massimale_persone != null ? Number(pol.massimale_persone).toLocaleString("it-IT") : "",
        });
        setVeicoloEdit(true);
    };
    const setVeic = (k, v) => setVeicoloForm((p) => ({ ...p, [k]: v }));
    const saveVeicolo = async () => {
        setVeicoloSaving(true);
        try {
            const payload = { ...veicoloForm };
            VEICOLO_NUM_FIELDS.forEach((k) => {
                payload[k] = (payload[k] === "" || payload[k] === null || payload[k] === undefined)
                    ? (k === "veicolo_quintali" ? null : 0) : parseFloat(payload[k]) || 0;
            });
            // Massimali: convertono la stringa formattata (es. "15.000.000") in numero
            const _mnum = (s) => { const d = String(s ?? "").replace(/\D/g, ""); return d ? Number(d) : null; };
            payload.massimale_cose = _mnum(veicoloForm.massimale_cose);
            payload.massimale_persone = _mnum(veicoloForm.massimale_persone);
            await api.put(`/polizze/${pol.id}`, payload);
            const tg = (veicoloForm.targa || "").trim();
            if (tg) {
                try {
                    await api.put(`/veicoli/by-targa/${encodeURIComponent(tg)}`, {
                        marca: veicoloForm.veicolo_marca,
                        modello: veicoloForm.veicolo_modello,
                        tipo_veicolo: veicoloForm.veicolo_tipo,
                        alimentazione: veicoloForm.veicolo_alimentazione,
                        uso: veicoloForm.veicolo_uso,
                        data_immatricolazione: veicoloForm.veicolo_data_immatricolazione,
                        cv: veicoloForm.veicolo_cv_fiscali,
                        kw: veicoloForm.veicolo_kw,
                        quintali: veicoloForm.veicolo_quintali,
                        cilindrata: veicoloForm.veicolo_cilindrata,
                        posti: veicoloForm.veicolo_posti,
                        targa_rimorchio: veicoloForm.veicolo_targa_rimorchio,
                        proprietario: veicoloForm.intestatario,
                        provincia: veicoloForm.provincia_intestatario,
                    });
                } catch (_) { /* sync archivio best-effort */ }
            }
            toast.success("Dati veicolo aggiornati (anche in archivio)");
            setVeicoloEdit(false);
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        } finally { setVeicoloSaving(false); }
    };

    const startProvvEdit = () => {
        setProvvVal(pol.provvigioni != null ? String(pol.provvigioni) : "");
        setProvvEdit(true);
    };
    const saveProvv = async () => {
        setProvvSaving(true);
        try {
            const num = parseFloat((provvVal || "").replace(",", ".").replace(/[€\s]/g, "")) || 0;
            await api.put(`/polizze/${pol.id}`, { provvigioni: num });
            toast.success("Provvigioni aggiornate");
            setProvvEdit(false);
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        } finally { setProvvSaving(false); }
    };

    const handleDelete = async () => {
        if (!window.confirm(`Eliminare definitivamente la polizza N. ${pol.numero_polizza}?\n\nVerranno eliminati anche tutti i titoli e sinistri collegati. Operazione non reversibile.`)) return;
        try {
            await api.delete(`/polizze/${id}`);
            toast.success("Polizza eliminata");
            navigate("/polizze");
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        }
    };

    return (
        <div data-testid="polizza-detail-page">
            <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                <Link to="/polizze" className="text-sm text-slate-500 hover:text-sky-700 inline-flex items-center gap-1">
                    <ArrowLeft size={14} /> Torna alle polizze
                </Link>
                <div className="flex gap-2">
                    {pol.regolazione_premio && (
                        <Button variant="outline" size="sm"
                            onClick={() => setRegolazioneOpen(true)}
                            className="border-violet-300 text-violet-700 hover:bg-violet-50"
                            data-testid="pol-regolazione-btn">
                            <Zap size={14} className="mr-1" /> Regolazione premio
                        </Button>
                    )}
                    {canEdit && (
                        <Button variant="outline" size="sm" onClick={() => setEditOpen(true)} data-testid="pol-edit-button">
                            <Pencil size={14} className="mr-1" /> Modifica polizza
                        </Button>
                    )}
                    <Button variant="outline" size="sm" onClick={apriMup} disabled={mupBusy}
                            className="border-indigo-300 text-indigo-700 hover:bg-indigo-50" data-testid="pol-mup-button">
                        📋 {mupBusy ? "…" : "MUP precontrattuale"}
                    </Button>
                    <GeneraDocumentoButton sezione="polizza" entitaId={id} firmatarioId={pol.contraente_id} onSaved={load} />
                    {canDelete && (
                        <Button variant="outline" size="sm" onClick={handleDelete}
                                disabled={haTitoliBloccanti}
                                title={haTitoliBloccanti
                                    ? "Polizza con titoli incassati o coperti: non eliminabile, usa Annulla o Sostituisci"
                                    : "Elimina polizza"}
                                className="text-rose-700 hover:bg-rose-50 hover:text-rose-800 disabled:opacity-50" data-testid="pol-delete-button">
                            <Trash2 size={14} className="mr-1" /> Elimina
                        </Button>
                    )}
                </div>
            </div>

            {/* Header tipo Cattolica */}
            <Card className="border-slate-200 mb-4 overflow-hidden">
                <div className="bg-gradient-to-r from-sky-900 to-slate-900 text-slate-100 px-6 py-5 flex items-center justify-between flex-wrap gap-4">
                    <div className="flex items-center gap-3">
                        {pol.compagnia?.logo_url && (
                            <img src={pol.compagnia.logo_url} alt={pol.compagnia?.ragione_sociale || "logo compagnia"}
                                className="h-11 w-auto max-w-[130px] object-contain bg-white rounded-md p-1 shrink-0"
                                data-testid="pol-compagnia-logo" />
                        )}
                        <div>
                            <div className="text-[10px] uppercase tracking-widest text-sky-300">{pol.compagnia?.ragione_sociale || "—"}</div>
                            <div className="text-xl font-semibold mt-0.5">{pol.ramo || "—"}{pol.prodotto ? ` · ${pol.prodotto}` : ""}</div>
                            <div className="text-lg font-semibold text-slate-100 mt-1 tracking-wide">N. {pol.numero_polizza}</div>
                            {pol.mandato && (
                                <div className="text-xs text-sky-200 mt-0.5" data-testid="pol-header-agenzia-partner">
                                    Agenzia partner: <span className="font-medium text-slate-100">{pol.mandato}</span>
                                </div>
                            )}
                            <div className="mt-2 inline-flex items-center gap-2 bg-white/10 rounded-lg px-2.5 py-1" data-testid="pol-header-operatore">
                                <CollaboratoreInlineSelect
                                    entita="polizze"
                                    id={pol.id}
                                    value={pol.collaboratore_id}
                                    fallbackName={pol.collaboratore_nome}
                                    canEdit={canEdit}
                                    onSaved={load}
                                    label="Operatore"
                                />
                            </div>
                        </div>
                    </div>
                    <div className="flex gap-6 text-xs">
                        <Hd label="Ultimo premio pagato" value={<span className="text-base font-semibold text-emerald-300 num">{fmtEur(pol.ultimo_premio_pagato ?? pol.ultimo_titolo_importo)}</span>} />
                        <Hd label="Ultimo titolo" value={fmtDate(pol.ultimo_titolo_scadenza || pol.titoli?.[0]?.data_incasso || pol.effetto)} />
                        <Hd label="Stato" value={<StatusBadge stato={pol.stato} />} />
                        <Hd label="Copertura" value={fmtDate(pol.copertura_fino_a || pol.scadenza_copertura || pol.scadenza)} />
                        <div className="flex flex-col justify-center">
                            <span className="text-[10px] uppercase tracking-wide text-slate-400 mb-1">Regolazione premio</span>
                            {canEdit ? (
                                <div className="flex items-center gap-1.5">
                                    <div className="inline-flex rounded-full border border-white/20 overflow-hidden" data-testid="pol-header-regolazione-toggle">
                                        <button
                                            onClick={async () => {
                                                if (pol.regolazione_premio) return;
                                                try { await api.put(`/polizze/${pol.id}`, { regolazione_premio: true }); toast.success("Polizza soggetta a regolazione premio"); load(); }
                                                catch { toast.error("Errore"); }
                                            }}
                                            className={`px-3 py-1 text-xs font-medium transition-colors ${pol.regolazione_premio ? "bg-violet-500/30 text-violet-100" : "bg-white/5 text-slate-300 hover:bg-white/10"}`}
                                            data-testid="pol-header-regolazione-si">
                                            Sì
                                        </button>
                                        <button
                                            onClick={async () => {
                                                if (!pol.regolazione_premio) return;
                                                try { await api.put(`/polizze/${pol.id}`, { regolazione_premio: false }); toast.success("Regolazione premio disattivata"); load(); }
                                                catch { toast.error("Errore"); }
                                            }}
                                            className={`px-3 py-1 text-xs font-medium transition-colors ${!pol.regolazione_premio ? "bg-white/25 text-white" : "bg-white/5 text-slate-300 hover:bg-white/10"}`}
                                            data-testid="pol-header-regolazione-no">
                                            No
                                        </button>
                                    </div>
                                    {pol.regolazione_premio && (
                                        <button
                                            onClick={() => setRegolazioneOpen(true)}
                                            className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-violet-500/20 border border-violet-300/40 text-violet-100 hover:bg-violet-500/30 transition-colors text-xs font-medium"
                                            data-testid="pol-header-regolazione-on">
                                            <Zap size={12} /> gestisci
                                        </button>
                                    )}
                                </div>
                            ) : (
                                <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium ${pol.regolazione_premio ? "bg-violet-500/20 border border-violet-300/40 text-violet-100" : "text-slate-300"}`}>
                                    {pol.regolazione_premio ? <><Zap size={12} /> Sì</> : "No"}
                                </span>
                            )}
                        </div>
                    </div>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-x-6 gap-y-3 px-6 py-4 text-sm">
                    <F label="N° contratto" value={pol.numero_polizza} mono />
                    <F label="Sostituisce" value={pol.sostituisce_numero
                        ? <Link to={`/polizze/${pol.sostituisce_polizza_id || pol.sostituisce_polizza}`} className="text-sky-700 hover:underline" data-testid="pol-sostituisce-link">N. {pol.sostituisce_numero}</Link>
                        : pol.sostituisce_polizza} />
                    <F label="Pagamento preferito" value={pol.mezzo_pagamento_preferito
                        ? pol.mezzo_pagamento_preferito.toUpperCase()
                        : (pol.ultimo_mezzo_pagamento ? `${pol.ultimo_mezzo_pagamento} (ultimo usato)` : null)} />
                    <F label="Compagnia" value={pol.compagnia?.ragione_sociale} />
                    <F label="Contraente" value={<Link to={`/anagrafiche/${pol.contraente?.id}`} className="text-sky-700 hover:underline">{pol.contraente?.ragione_sociale}</Link>} />
                    <F label="Iter" value={pol.iter_status} />
                    <F label="Frazionamento" value={pol.frazionamento ? `${pol.frazionamento}${pol.tacito_rinnovo ? " · tacito rinnovo" : ""}` : "—"} />
                    <F label="Effetto" value={fmtDate(pol.effetto)} />
                    {pol.data_emissione && <F label="Data emissione" value={fmtDate(pol.data_emissione)} />}
                    <F label="Presa in carico" value={fmtDate(pol.presa_in_carico)} />
                    <F label="Prossima quietanza" value={fmtDate(pol.prossima_quietanza)} />
                    <F label="Scad. copertura" value={fmtDate(pol.copertura_fino_a || pol.scadenza_copertura || pol.scadenza)} />
                    <F label="Scad. contratto" value={fmtDate(pol.scadenza)} />
                    <F label="Termini mora" value={pol.termini_mora_giorni ? `${pol.termini_mora_giorni} gg` : "—"} />
                    <F label="Termini disdetta" value={pol.termini_disdetta_giorni ? `${pol.termini_disdetta_giorni} gg` : "—"} />
                    <F label="Oggetto assicurato" value={pol.oggetto_assicurato || pol.targa} />
                </div>
            </Card>

            <Card className="p-4" data-testid="polizza-tags-card">
                <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Tag polizza</span>
                    {(pol.tags || []).length > 0 && <span className="text-[10px] text-slate-400">{pol.tags.length}</span>}
                </div>
                {canEdit ? (
                    <TagsEditor
                        value={pol.tags || []}
                        testid="polizza-tags"
                        placeholder="Aggiungi tag alla polizza..."
                        onChange={async (tags) => {
                            setPol((p) => ({ ...p, tags }));
                            try { await api.put(`/polizze/${id}/tags`, { tags }); }
                            catch { toast.error("Errore salvataggio tag"); }
                        }}
                    />
                ) : (
                    <div className="flex flex-wrap gap-1.5">
                        {(pol.tags || []).length === 0 ? <span className="text-xs text-slate-400">Nessun tag</span>
                            : pol.tags.map((t) => <span key={t} className="text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-sky-100 text-sky-700 border border-sky-200">{t}</span>)}
                    </div>
                )}
            </Card>

            {pol.targa && (
                <TargaConflictWidget targa={pol.targa} excludeId={pol.id} compact />
            )}

            <TaskCollegati entitaTipo="polizza" entitaId={id} />

            <Tabs defaultValue={defaultTab}>
                <TabsList className="bg-slate-100 flex-wrap h-auto">
                    {isVeicoloPol && <TabsTrigger value="veicolo"><Car size={13} className="mr-1" />Veicolo</TabsTrigger>}
                    <TabsTrigger value="garanzie"><ShieldCheck size={13} className="mr-1" />Garanzie</TabsTrigger>
                    <TabsTrigger value="premi"><Banknote size={13} className="mr-1" />Premi</TabsTrigger>
                    <TabsTrigger value="provvigioni"><Banknote size={13} className="mr-1" />Provvigioni</TabsTrigger>
                    <TabsTrigger value="titoli"><FileText size={13} className="mr-1" />Titoli ({pol.titoli?.length || 0})</TabsTrigger>
                    <TabsTrigger value="documenti" data-testid="tab-documenti">
                        <FileText size={13} className="mr-1" />Documenti
                    </TabsTrigger>
                    <TabsTrigger value="sinistri" data-testid="tab-sinistri">
                        <AlertTriangle size={13} className="mr-1" />Sinistri ({pol.sinistri?.length || 0})
                    </TabsTrigger>
                    {pol.is_libro_matricola && (
                        <TabsTrigger value="libro-matricola" data-testid="tab-libro-matricola">
                            <Car size={13} className="mr-1" />Libro Matricola
                        </TabsTrigger>
                    )}
                    {pol.is_cumulativa_assicurati && (
                        <TabsTrigger value="assicurati" data-testid="tab-assicurati">
                            <ShieldCheck size={13} className="mr-1" />Assicurati
                        </TabsTrigger>
                    )}
                    {pol.regolazione_premio && (
                        <TabsTrigger value="regolazione" data-testid="tab-regolazione" className="text-violet-700 data-[state=active]:bg-violet-50">
                            <Zap size={13} className="mr-1" />Regolazione
                        </TabsTrigger>
                    )}
                    <TabsTrigger value="altri"><Info size={13} className="mr-1" />Altri dati</TabsTrigger>
                    <TabsTrigger value="questionari" data-testid="tab-questionari"><ClipboardList size={13} className="mr-1" />Questionari</TabsTrigger>
                    <TabsTrigger value="azioni" data-testid="tab-azioni" className="text-rose-700 data-[state=active]:bg-rose-50">
                        <Zap size={13} className="mr-1" />Azioni
                    </TabsTrigger>
                </TabsList>

                {isVeicoloPol && (
                    <TabsContent value="veicolo">
                        <Card className="p-6 border-slate-200 mt-4">
                            <div className="flex items-center justify-between mb-3">
                                <SezioneTitolo titolo="Dati veicolo" />
                                <div className="flex items-center gap-2">
                                    {!veicoloEdit && (
                                        <label className="text-xs px-3 py-1.5 rounded-md border border-sky-300 text-sky-700 hover:bg-sky-50 cursor-pointer flex items-center gap-1" data-testid="veicolo-libretto-upload">
                                            <FileText size={13} /> {librettoUp ? "Carico…" : "Carica libretto"}
                                            <input type="file" hidden disabled={librettoUp}
                                                onChange={(e) => uploadLibretto(e.target.files?.[0])} />
                                        </label>
                                    )}
                                    {canEdit && !veicoloEdit && (
                                        <Button size="sm" onClick={startVeicoloEdit} data-testid="veicolo-edit-btn" className="bg-sky-700 hover:bg-sky-800">
                                            <Pencil size={13} className="mr-1" /> Modifica veicolo
                                        </Button>
                                    )}
                                    {canEdit && veicoloEdit && (
                                        <>
                                            <Button size="sm" variant="ghost" onClick={() => setVeicoloEdit(false)} disabled={veicoloSaving} data-testid="veicolo-cancel-btn">Annulla</Button>
                                            <Button size="sm" onClick={saveVeicolo} disabled={veicoloSaving} className="bg-sky-700 hover:bg-sky-800" data-testid="veicolo-save-btn">{veicoloSaving ? "Salvo…" : "Salva"}</Button>
                                        </>
                                    )}
                                </div>
                            </div>
                            {!veicoloEdit ? (
                                <>
                                    <p className="text-[11px] text-slate-500 -mt-2 mb-3">Da "Modifica veicolo" puoi modificare i dati direttamente qui. Il libretto caricato viene salvato nei Documenti (categoria "Libretto veicolo").</p>
                                    <Grid items={[
                                        ["Targa", pol.targa],
                                        ["Marca", pol.veicolo_marca],
                                        ["Modello", pol.veicolo_modello],
                                        ["Tipo veicolo", pol.veicolo_tipo],
                                        ["Alimentazione", pol.veicolo_alimentazione],
                                        ["Tipo uso", pol.veicolo_uso],
                                        ["Immatricolazione", fmtDate(pol.veicolo_data_immatricolazione)],
                                        ["CV fiscali", pol.veicolo_cv_fiscali],
                                        ["KW", pol.veicolo_kw],
                                        ["Quintali P.C.", pol.veicolo_quintali],
                                        ["Cilindrata", pol.veicolo_cilindrata],
                                        ["Numero posti", pol.veicolo_posti],
                                        ["Gancio traino", pol.veicolo_gancio_traino ? "SÌ" : "NO"],
                                        ["Targa rimorchio", pol.veicolo_targa_rimorchio],
                                    ]} />
                                    <SezioneTitolo titolo="Dati associazione contratto" extra />
                                    <Grid items={[
                                        ["Tipo tariffa", pol.tipo_tariffa],
                                        ["B-M provenienza", pol.bm_provenienza],
                                        ["B-M assegnata", pol.bm_assegnata],
                                        ["B-M ass. CU", pol.bm_assegnata_cu],
                                        ["Pejus", pol.pejus],
                                        ["Franchigia", fmtEur(pol.franchigia)],
                                        ["Valore veicolo", fmtEur(pol.valore_veicolo)],
                                        ["Valore residuo", fmtEur(pol.valore_residuo_veicolo)],
                                        ["Valore accessori", fmtEur(pol.valore_accessori)],
                                        ["Guida esperta", pol.guida_esperta ? "SÌ" : "NO"],
                                        ["Guida esclusiva", pol.guida_esclusiva ? "SÌ" : "NO"],
                                        ["Rinuncia rivalsa", pol.rinuncia_rivalsa ? "SÌ" : "NO"],
                                        ["Intestatario", pol.intestatario],
                                        ["Prov. intestatario", pol.provincia_intestatario],
                                        ["Massimale cose", pol.massimale_cose != null ? fmtEur(pol.massimale_cose) : null],
                                        ["Massimale persone", pol.massimale_persone != null ? fmtEur(pol.massimale_persone) : null],
                                    ]} />
                                </>
                            ) : (
                                <div className="space-y-4">
                                    <div className="max-w-md">
                                        <TargaSearchWithLentina
                                            value={veicoloForm.targa}
                                            onChange={(targa, veicolo) => setVeicoloForm((p) => {
                                                if (!veicolo) return { ...p, targa: targa || "" };
                                                const pick = (...vals) => {
                                                    for (const v of vals) if (v !== undefined && v !== null && v !== "") return v;
                                                    return "";
                                                };
                                                const s = (v) => (v === "" || v === undefined || v === null ? "" : String(v));
                                                return {
                                                    ...p,
                                                    targa: targa || "",
                                                    veicolo_marca: s(pick(veicolo.marca)),
                                                    veicolo_modello: s(pick(veicolo.modello)),
                                                    veicolo_tipo: s(pick(veicolo.tipo_veicolo, veicolo.tipo, veicolo.categoria, veicolo.codice_oggetto)),
                                                    veicolo_alimentazione: s(pick(veicolo.alimentazione)),
                                                    veicolo_uso: s(pick(veicolo.uso, veicolo.codice_uso)),
                                                    veicolo_data_immatricolazione: s(pick(veicolo.data_immatricolazione, veicolo.anno_immatricolazione)),
                                                    veicolo_cv_fiscali: s(pick(veicolo.cv, veicolo.cv_fiscali, veicolo.potenza_cv)),
                                                    veicolo_kw: s(pick(veicolo.kw, veicolo.potenza_kw)),
                                                    veicolo_quintali: s(pick(veicolo.quintali)),
                                                    veicolo_cilindrata: s(pick(veicolo.cilindrata)),
                                                    veicolo_posti: s(pick(veicolo.posti, veicolo.numero_posti)),
                                                    veicolo_targa_rimorchio: s(pick(veicolo.targa_rimorchio)),
                                                    veicolo_gancio_traino: !!(veicolo.rimorchio || veicolo.gancio_traino),
                                                    intestatario: veicolo.proprietario ? String(veicolo.proprietario) : p.intestatario,
                                                    provincia_intestatario: veicolo.provincia ? String(veicolo.provincia) : p.provincia_intestatario,
                                                };
                                            })}
                                        />
                                    </div>
                                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                                        {[
                                            ["veicolo_marca", "Marca", "text"],
                                            ["veicolo_modello", "Modello", "text"],
                                            ["veicolo_tipo", "Tipo veicolo", "text"],
                                            ["veicolo_alimentazione", "Alimentazione", "text"],
                                            ["veicolo_uso", "Tipo uso", "text"],
                                            ["veicolo_data_immatricolazione", "Immatricolazione", "date"],
                                            ["veicolo_cv_fiscali", "CV fiscali", "text"],
                                            ["veicolo_kw", "KW", "text"],
                                            ["veicolo_quintali", "Quintali P.C.", "number"],
                                            ["veicolo_cilindrata", "Cilindrata", "text"],
                                            ["veicolo_posti", "Numero posti", "text"],
                                            ["veicolo_targa_rimorchio", "Targa rimorchio", "text"],
                                        ].map(([k, lbl, type]) => (
                                            <div key={k}>
                                                <Label className="text-xs text-slate-500">{lbl}</Label>
                                                <Input type={type} value={veicoloForm[k]}
                                                    onChange={(e) => setVeic(k, e.target.value)}
                                                    data-testid={`veicolo-input-${k}`} />
                                            </div>
                                        ))}
                                        <label className="flex items-center gap-2 mt-6 text-sm cursor-pointer">
                                            <input type="checkbox" checked={veicoloForm.veicolo_gancio_traino}
                                                onChange={(e) => setVeic("veicolo_gancio_traino", e.target.checked)}
                                                data-testid="veicolo-input-veicolo_gancio_traino" />
                                            Gancio traino
                                        </label>
                                    </div>
                                    <SezioneTitolo titolo="Dati associazione contratto" extra />
                                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                                        {[
                                            ["tipo_tariffa", "Tipo tariffa", "text"],
                                            ["bm_provenienza", "B-M provenienza", "text"],
                                            ["bm_assegnata", "B-M assegnata", "text"],
                                            ["bm_assegnata_cu", "B-M ass. CU", "text"],
                                            ["pejus", "Pejus", "text"],
                                            ["franchigia", "Franchigia", "number"],
                                            ["valore_veicolo", "Valore veicolo", "number"],
                                            ["valore_residuo_veicolo", "Valore residuo", "number"],
                                            ["valore_accessori", "Valore accessori", "number"],
                                            ["intestatario", "Intestatario", "text"],
                                            ["provincia_intestatario", "Prov. intestatario", "text"],
                                        ].map(([k, lbl, type]) => (
                                            <div key={k}>
                                                <Label className="text-xs text-slate-500">{lbl}</Label>
                                                <Input type={type} value={veicoloForm[k]}
                                                    onChange={(e) => setVeic(k, e.target.value)}
                                                    data-testid={`veicolo-input-${k}`} />
                                            </div>
                                        ))}
                                        <div>
                                            <Label className="text-xs text-slate-500">Massimale cose</Label>
                                            <Input type="text" inputMode="numeric"
                                                value={(() => { const d = String(veicoloForm.massimale_cose ?? "").replace(/\D/g, ""); return d ? Number(d).toLocaleString("it-IT") : ""; })()}
                                                onChange={(e) => { const d = e.target.value.replace(/\D/g, ""); setVeic("massimale_cose", d ? Number(d).toLocaleString("it-IT") : ""); }}
                                                placeholder="es. 6.000.000"
                                                data-testid="veicolo-input-massimale-cose" />
                                        </div>
                                        <div>
                                            <Label className="text-xs text-slate-500">Massimale persone</Label>
                                            <Input type="text" inputMode="numeric"
                                                value={(() => { const d = String(veicoloForm.massimale_persone ?? "").replace(/\D/g, ""); return d ? Number(d).toLocaleString("it-IT") : ""; })()}
                                                onChange={(e) => { const d = e.target.value.replace(/\D/g, ""); setVeic("massimale_persone", d ? Number(d).toLocaleString("it-IT") : ""); }}
                                                placeholder="es. 6.000.000"
                                                data-testid="veicolo-input-massimale-persone" />
                                        </div>
                                        {[
                                            ["guida_esperta", "Guida esperta"],
                                            ["guida_esclusiva", "Guida esclusiva"],
                                            ["rinuncia_rivalsa", "Rinuncia rivalsa"],
                                        ].map(([k, lbl]) => (
                                            <label key={k} className="flex items-center gap-2 mt-6 text-sm cursor-pointer">
                                                <input type="checkbox" checked={veicoloForm[k]}
                                                    onChange={(e) => setVeic(k, e.target.checked)}
                                                    data-testid={`veicolo-input-${k}`} />
                                                {lbl}
                                            </label>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </Card>
                    </TabsContent>
                )}

                <TabsContent value="premi">
                    <Card className="p-4">
                        <div className="flex items-center justify-between mb-3">
                            <div className="text-sm font-semibold text-slate-800 flex items-center gap-1.5"><Banknote size={15} /> Premi di polizza</div>
                            {canEdit && !premiEdit && (
                                <Button size="sm" variant="outline" onClick={startPremiEdit} data-testid="premi-edit-btn">Modifica premi</Button>
                            )}
                            {canEdit && premiEdit && (
                                <div className="flex gap-2">
                                    <Button size="sm" variant="ghost" onClick={() => setPremiEdit(false)} disabled={premiSaving} data-testid="premi-cancel-btn">Annulla</Button>
                                    <Button size="sm" onClick={savePremi} disabled={premiSaving} className="bg-sky-700 hover:bg-sky-800" data-testid="premi-save-btn">{premiSaving ? "Salvo…" : "Salva"}</Button>
                                </div>
                            )}
                        </div>
                        {!premiEdit ? (
                            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                                <F label="Premio netto" value={fmtEur(pol.premio_netto)} />
                                <F label="Imposte" value={fmtEur(pol.premio_imposte)} />
                                <F label="SSN" value={fmtEur(pol.premio_ssn)} />
                                <F label="Accessori" value={fmtEur(pol.premio_accessori)} />
                                <F label="Addizionale" value={fmtEur(pol.premio_addizionale)} />
                                <F label="Diritti" value={fmtEur(pol.diritti)} />
                                <F label="Premio lordo" value={<span className="font-semibold text-slate-900 num">{fmtEur(pol.premio_lordo)}</span>} />
                            </div>
                        ) : (
                            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                                {[
                                    ["premio_netto", "Premio netto"],
                                    ["premio_imposte", "Imposte"],
                                    ["premio_ssn", "SSN"],
                                    ["premio_accessori", "Accessori"],
                                    ["premio_addizionale", "Addizionale"],
                                    ["diritti", "Diritti"],
                                ].map(([k, lbl]) => (
                                    <div key={k}>
                                        <Label className="text-xs text-slate-500">{lbl}</Label>
                                        <Input type="number" step="0.01" value={premiForm[k]}
                                            onChange={(e) => setPremiForm((p) => ({ ...p, [k]: e.target.value }))}
                                            data-testid={`premi-input-${k}`} />
                                    </div>
                                ))}
                                <div>
                                    <Label className="text-xs text-slate-500">Premio lordo (automatico)</Label>
                                    <Input type="number" step="0.01" readOnly disabled
                                        value={calcLordo(premiForm).toFixed(2)}
                                        className="bg-slate-100 font-semibold"
                                        data-testid="premi-input-premio_lordo" />
                                    <div className="text-[10px] text-slate-400 mt-0.5">Netto + Imposte + SSN + Accessori + Addizionale</div>
                                </div>
                            </div>
                        )}
                    </Card>
                </TabsContent>

                <TabsContent value="garanzie">
                    {isRamoVita && (
                    <Card className="p-6 border-slate-200 mt-4">
                        <SezioneTitolo titolo="Vita / Previdenza" />
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                            <div>
                                <div className="text-[10px] uppercase tracking-widest text-slate-500">Rendita annua</div>
                                <RenditaCell polizzaId={pol.id} current={pol.rendita_annua}
                                             canEdit={canEdit} onSaved={load} />
                            </div>
                            <F label="Capitale assicurato" value={fmtEur(pol.capitale_assicurato)} mono />
                        </div>
                    </Card>
                    )}

                    <Card className="border-slate-200 mt-4 overflow-hidden">
                        {(!pol.garanzie || pol.garanzie.length === 0) ? (
                            <div className="p-8 text-center text-slate-500 text-sm">Nessuna garanzia di dettaglio importata.</div>
                        ) : (
                            <table className="tbl w-full">
                                <thead>
                                    <tr>
                                        <th>Garanzia</th>
                                        <th className="text-right">Massimali / Capitali</th>
                                        <th className="text-right">Netto</th>
                                        <th className="text-right">Accessori</th>
                                        <th className="text-right">Imposte</th>
                                        <th className="text-right">SSN</th>
                                        <th className="text-right">Lordo</th>
                                        <th className="text-right">Diritti</th>
                                        <th className="text-right">Provvigione</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {pol.garanzie.map((g, i) => {
                                        // Massimale della singola garanzia (fallback su vari nomi
                                        // usati dai flussi import ANIA / OMNIA)
                                        let mx = g.massimale ?? g.capitale ?? g.capitale_assicurato
                                                    ?? g.somma_assicurata ?? g.massimali;
                                        // 🆕 Fallback: se la garanzia non ha massimale ma la polizza
                                        // sì (campo intestazione `massimali` / `capitale_assicurato`)
                                        // ed è l'UNICA garanzia oppure è una garanzia RCA/RC principale,
                                        // riporta il valore della polizza come massimale di garanzia.
                                        const isRcaLike = /^rc[a\s]|rc\s|rc$|motocicl|autov|autocarr/i
                                            .test(g.garanzia || g.garanzia_originale || "");
                                        if ((mx == null || mx === "" || mx === 0)
                                            && (pol.garanzie.length === 1 || isRcaLike)) {
                                            mx = pol.massimali || pol.capitale_assicurato;
                                        }
                                        return (
                                            <tr key={i}>
                                                <td className="font-medium">{g.garanzia || g.garanzia_originale || g.codice_ania || "—"}</td>
                                                <td className="num text-right text-sky-700 font-medium">
                                                    <MassimaleCell polizzaId={pol.id} index={i}
                                                                   current={mx}
                                                                   canEdit={canEdit}
                                                                   onSaved={load} />
                                                </td>
                                                <td className="num text-right">{fmtEur(g.netto)}</td>
                                                <td className="num text-right text-slate-600">{fmtEur(g.accessori)}</td>
                                                <td className="num text-right text-slate-600">{fmtEur(g.imposte)}</td>
                                                <td className="num text-right text-slate-600">{fmtEur(g.ssn)}</td>
                                                <td className="num text-right font-semibold">{fmtEur(g.lordo)}</td>
                                                <td className="num text-right text-slate-600">{fmtEur(g.diritti)}</td>
                                                <td className="num text-right text-emerald-700">{fmtEur(g.provvigione)}</td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                                <tfoot>
                                    <tr className="bg-slate-50 font-semibold">
                                        <td>TOTALE</td>
                                        <td></td>
                                        <td className="num text-right">{fmtEur(pol.garanzie.reduce((s, g) => s + (g.netto || 0), 0))}</td>
                                        <td className="num text-right">{fmtEur(pol.garanzie.reduce((s, g) => s + (g.accessori || 0), 0))}</td>
                                        <td className="num text-right">{fmtEur(pol.garanzie.reduce((s, g) => s + (g.imposte || 0), 0))}</td>
                                        <td className="num text-right">{fmtEur(pol.garanzie.reduce((s, g) => s + (g.ssn || 0), 0))}</td>
                                        <td className="num text-right">{fmtEur(pol.premio_lordo)}</td>
                                        <td className="num text-right">{fmtEur(pol.diritti || 0)}</td>
                                        <td className="num text-right p-0">
                                            <ProvvigioniTotaleCell polizzaId={pol.id} current={pol.provvigioni} canEdit={canEdit} onSaved={load} />
                                        </td>
                                    </tr>
                                </tfoot>
                            </table>
                        )}
                    </Card>

                    {pol.addizionali && pol.addizionali.length > 0 && (
                        <Card className="border-slate-200 mt-4 p-6">
                            <SezioneTitolo titolo="Addizionali" />
                            <Grid items={pol.addizionali.map((a) => [a.descrizione, fmtEur(a.importo)])} />
                        </Card>
                    )}
                </TabsContent>

                <TabsContent value="provvigioni">
                    <Card className="p-6 border-slate-200 mt-4">
                        <div className="flex items-center justify-between mb-3">
                            <div className="text-sm font-semibold text-slate-800 flex items-center gap-1.5"><Banknote size={15} /> Provvigioni</div>
                            {canEdit && !provvEdit && (
                                <Button size="sm" variant="outline" onClick={startProvvEdit} data-testid="provv-edit-btn"><Pencil size={13} className="mr-1" /> Modifica</Button>
                            )}
                            {canEdit && provvEdit && (
                                <div className="flex gap-2">
                                    <Button size="sm" variant="ghost" onClick={() => setProvvEdit(false)} disabled={provvSaving} data-testid="provv-cancel-btn">Annulla</Button>
                                    <Button size="sm" onClick={saveProvv} disabled={provvSaving} className="bg-sky-700 hover:bg-sky-800" data-testid="provv-save-btn">{provvSaving ? "Salvo…" : "Salva"}</Button>
                                </div>
                            )}
                        </div>
                        {provvEdit ? (
                            <div className="max-w-xs">
                                <Label className="text-xs text-slate-500">Provv. totali (agenzia) €</Label>
                                <Input type="number" step="0.01" value={provvVal}
                                    onChange={(e) => setProvvVal(e.target.value)}
                                    data-testid="provv-totali-input" autoFocus />
                                <p className="text-[11px] text-slate-400 mt-1">Le quote collaboratore e margine vengono ricalcolate in automatico dallo schema provvigionale al salvataggio.</p>
                            </div>
                        ) : (
                        <Grid items={[
                            [
                                "Provv. totali (agenzia)",
                                <span key="provv-totali" className="font-semibold text-emerald-700 num" data-testid="provv-totali">
                                    {fmtEur(pol.provvigione_totale ?? pol.provvigioni ?? 0)}
                                </span>,
                            ],
                            [
                                "Provv. collaboratore",
                                <span key="provv-collab" className="num font-semibold text-sky-700" data-testid="provv-collab">
                                    {fmtEur(pol.provvigione_collaboratore || 0)}
                                    {pol.provvigione_pct_collab > 0 && (
                                        <span className="text-[10px] ml-2 text-slate-500 font-normal">
                                            ({pol.provvigione_pct_collab}% — {pol.provvigione_schema_nome || "schema"})
                                        </span>
                                    )}
                                </span>,
                            ],
                            [
                                "Provv. margine (agenzia netto)",
                                <span key="provv-margine" className="num font-semibold text-amber-700" data-testid="provv-margine">
                                    {fmtEur(pol.provvigione_margine ?? ((pol.provvigione_totale ?? pol.provvigioni ?? 0) - (pol.provvigione_collaboratore || 0)))}
                                </span>,
                            ],
                        ]} />
                        )}
                        {pol.collaboratore_nome && (
                            <div className="mt-2 text-xs text-slate-600 flex items-center flex-wrap gap-2">
                                <span>Collaboratore polizza: <strong>{pol.collaboratore_nome}</strong></span>
                                <span className="inline-flex items-center gap-1 bg-sky-50 border border-sky-200 text-sky-700 rounded px-2 py-0.5 font-medium" data-testid="pol-collab-provv-inline">
                                    <Banknote size={11} /> Provv. collaboratore: {fmtEur(pol.provvigione_collaboratore || 0)}
                                    {pol.provvigione_pct_collab > 0 && (
                                        <span className="text-[10px] text-sky-500">({pol.provvigione_pct_collab}%)</span>
                                    )}
                                </span>
                            </div>
                        )}
                        <ProvvigioniOperatoriEditor pol={pol} canEdit={canEdit} onSaved={load} />
                    </Card>
                </TabsContent>

                <TabsContent value="titoli">
                    <Card className="border-slate-200 mt-4 overflow-hidden">
                        <div className="p-3 border-b border-slate-200 flex justify-between items-center bg-slate-50">
                            <div className="text-xs text-slate-600">
                                {pol.titoli?.length || 0} titoli su questa polizza
                            </div>
                            <Button
                                size="sm"
                                className="bg-sky-700 hover:bg-sky-800"
                                onClick={() => setTitoloEditing({
                                    _new: true, polizza_id: pol.id,
                                    ...((pol.titoli?.length || 0) === 0 ? {
                                        tipo: "nuova",
                                        effetto: pol.effetto || "",
                                        scadenza: pol.scadenza || "",
                                        importo_lordo: pol.premio_lordo || 0,
                                        importo_netto: pol.premio_netto || 0,
                                        imposte: pol.premio_imposte || 0,
                                        provvigioni: pol.provvigioni || 0,
                                    } : {}),
                                })}
                                data-testid="new-titolo-btn"
                            >+ Nuovo titolo</Button>
                        </div>
                        {pol.titoli?.length === 0 ? (
                            <div className="p-8 text-center text-slate-500 text-sm">Nessun titolo.</div>
                        ) : (
                            <div className="overflow-x-auto">
                            <table className="tbl w-full min-w-[1100px]">
                                <thead><tr><th>Tipo</th><th>N° Polizza</th><th>Effetto</th><th>Scadenza</th><th>Stato</th><th className="text-right">Lordo</th><th className="text-right">Provv. tot.</th><th className="text-right">Provv. collab.</th><th className="text-right">Margine</th><th>Coperto il</th><th>Pagato il</th><th>Nota</th><th className="text-center">Allegati</th><th className="text-center w-40 col-azioni">Azioni</th></tr></thead>
                                <tbody>
                                    {pol.titoli?.map((t) => (
                                        <tr key={t.id}
                                            className={`hover:bg-sky-50 cursor-pointer ${t.polizza_origine_id ? "bg-amber-50/40" : ""}`}
                                            onClick={(e) => {
                                                // ignora click sui pulsanti azione
                                                if (e.target.closest("button")) return;
                                                setTitoloEditing(t);
                                            }}
                                            data-testid={`titolo-row-${t.id}`}
                                        >
                                            <td>
                                                <TipoTitoloBadge tipo={t.tipo} />
                                                {t.polizza_origine_numero && (
                                                    <div className="text-[9px] text-amber-700 italic" title="Titolo della polizza precedente (sostituita)">
                                                        polizza prec. {t.polizza_origine_numero}
                                                    </div>
                                                )}
                                            </td>
                                            <td className="num text-xs" data-testid={`titolo-numpol-${t.id}`}>
                                                {t.polizza_origine_numero || t.numero_polizza || pol.numero_polizza}
                                            </td>
                                            <td className="num">{fmtDate(t.effetto)}</td>
                                            <td className="num">{fmtDate(t.scadenza)}</td>
                                            <td><StatusBadge stato={t.stato} titolo_coperto={t.titolo_coperto} data_copertura={t.data_copertura} /></td>
                                            <td className="num text-right font-medium">{fmtEur(t.importo_lordo)}</td>
                                            <td className="num text-right text-slate-600">{fmtEur(t.provvigione_totale ?? t.provvigioni ?? 0)}</td>
                                            <td className="num text-right text-sky-700 font-medium" data-testid={`titolo-provv-collab-${t.id}`}>{fmtEur(t.provvigione_collaboratore || 0)}</td>
                                            <td className="num text-right text-amber-700 font-medium" data-testid={`titolo-provv-margine-${t.id}`}>{fmtEur(t.provvigione_margine ?? ((t.provvigione_totale ?? t.provvigioni ?? 0) - (t.provvigione_collaboratore || 0)))}</td>
                                            <td className="num text-xs text-emerald-700" data-testid={`titolo-coperto-${t.id}`}>{t.data_copertura ? fmtDate(t.data_copertura) : (t.coperto_fino_a ? fmtDate(t.coperto_fino_a) : "—")}</td>
                                            <td className="num text-xs" data-testid={`titolo-pagato-${t.id}`}>{t.stato === "incassato" ? fmtDate(t.data_incasso) : "—"}</td>
                                            <td className="text-xs max-w-[180px]" data-testid={`titolo-nota-${t.id}`} title={t.nota || ""}>
                                                {t.nota ? (
                                                    <span className="inline-flex items-start gap-1 text-amber-800 bg-amber-50 border border-amber-200 rounded px-1.5 py-0.5 italic leading-tight truncate max-w-full">
                                                        📝 <span className="truncate">{t.nota}</span>
                                                    </span>
                                                ) : <span className="text-slate-300">—</span>}
                                            </td>
                                            <td className="text-center" onClick={(e) => e.stopPropagation()}>
                                                <AllegatiCell
                                                    entita_tipo="titolo"
                                                    entita_id={t.id}
                                                    count={t.allegati_count}
                                                    hint={t.data_incasso ? "Allega ricevuta bonifico / assegno" : "Allega documento"}
                                                    onChange={load}
                                                />
                                            </td>
                                            <td className="text-center col-azioni">
                                                <div className="flex gap-1 justify-center">
                                                    {t.stato !== "incassato" && t.stato !== "stornato" && (
                                                        <Button
                                                            size="sm"
                                                            className="h-7 px-2 text-xs bg-emerald-600 hover:bg-emerald-700"
                                                            onClick={() => setPaying({
                                                                ...t,
                                                                numero_polizza: pol.numero_polizza,
                                                                ramo: pol.ramo,
                                                                contraente_id: pol.contraente_id,
                                                                contraente_nome: pol.contraente?.ragione_sociale,
                                                                compagnia_nome: pol.compagnia?.ragione_sociale,
                                                            })}
                                                            data-testid={`pol-titolo-incassa-${t.id}`}
                                                            title="Incasso/Copertura"
                                                        >€</Button>
                                                    )}
                                                    {t.stato !== "stornato" && (t.stato === "incassato" || (!t.titolo_coperto && !t.data_copertura)) && (
                                                        <Button
                                                            size="sm" variant="outline"
                                                            className="h-7 px-2 text-xs text-amber-700 hover:bg-amber-50 border-amber-300"
                                                            onClick={() => marcaSospeso(t.id)}
                                                            data-testid={`pol-titolo-sospeso-${t.id}`}
                                                            title={t.stato === "incassato" ? "Rimetti coperto (annulla incasso, torna sospeso)" : "Segna come sospeso (coperto dall'agenzia)"}
                                                        >⏸</Button>
                                                    )}
                                                    {(t.titolo_coperto || t.data_copertura) && t.stato !== "incassato" && (
                                                        <Button
                                                            size="sm" variant="outline"
                                                            className="h-7 px-2 text-xs text-orange-700 hover:bg-orange-50 border-orange-300"
                                                            onClick={() => stornaCopertura(t.id)}
                                                            data-testid={`pol-titolo-storna-cop-${t.id}`}
                                                            title="Storna copertura"
                                                        >↺</Button>
                                                    )}
                                                    {t.stato === "incassato" && (
                                                        <Button
                                                            size="sm" variant="outline"
                                                            className="h-7 px-2 text-xs text-slate-700 hover:bg-slate-100 border-slate-300"
                                                            onClick={() => rimettiArretrato(t.id)}
                                                            data-testid={`pol-titolo-arretrato-${t.id}`}
                                                            title="Rimetti in arretrato (da incassare)"
                                                        >↩</Button>
                                                    )}
                                                    {["da_incassare", "insoluto", "sospeso"].includes(t.stato) && (
                                                        <Button
                                                            size="sm" variant="outline"
                                                            className="h-7 px-2 text-xs text-rose-700 hover:bg-rose-50 border-rose-300"
                                                            onClick={() => stornaTitolo(t.id)}
                                                            data-testid={`pol-titolo-storna-${t.id}`}
                                                            title="Storna titolo in arretrato (stato: stornato)"
                                                        >⊘</Button>
                                                    )}
                                                    {(t.sconto_applicato || 0) > 0 && (
                                                        <Button
                                                            size="sm"
                                                            className="h-7 px-2 text-xs bg-amber-500 hover:bg-amber-600 text-white"
                                                            onClick={() => setLetteraAbbuonoTitolo(t.id)}
                                                            data-testid={`pol-titolo-abbuono-${t.id}`}
                                                            title="Lettera di abbuono / firma"
                                                        >📜</Button>
                                                    )}
                                                    <Button
                                                        size="sm" variant="outline"
                                                        className="h-7 px-2 text-xs"
                                                        onClick={() => setTitoloEditing(t)}
                                                        data-testid={`titolo-edit-${t.id}`}
                                                        title="Modifica"
                                                    >✎</Button>
                                                    <Button
                                                        size="sm" variant="outline"
                                                        className="h-7 px-2 text-xs text-sky-700 hover:bg-sky-50"
                                                        onClick={() => setTitoloEditing({
                                                            ...t,
                                                            _new: true,
                                                            id: undefined,
                                                            numero_titolo: undefined,
                                                            stato: "da_incassare",
                                                            titolo_coperto: false,
                                                            data_incasso: null,
                                                            data_copertura: null,
                                                            importo_pagato: null,
                                                            conto_cassa_id: null,
                                                        })}
                                                        data-testid={`titolo-copy-${t.id}`}
                                                        title="Copia titolo (crea un nuovo titolo con gli stessi dati)"
                                                    >⧉</Button>
                                                    <Button
                                                        size="sm" variant="outline"
                                                        className="h-7 px-2 text-xs text-rose-700 hover:bg-rose-50"
                                                        onClick={async () => {
                                                            if (!window.confirm(`Eliminare il titolo ${t.tipo} ${fmtDate(t.effetto)}?`)) return;
                                                            try {
                                                                await api.delete(`/titoli/${t.id}`);
                                                                toast.success("Titolo eliminato");
                                                                load();
                                                            } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
                                                        }}
                                                        data-testid={`titolo-delete-${t.id}`}
                                                        title="Elimina"
                                                    >🗑</Button>
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                            </div>
                        )}
                    </Card>
                </TabsContent>

                {pol.is_libro_matricola && (
                    <TabsContent value="libro-matricola">
                        <LibroMatricolaTab polizzaId={pol.id} polizza={pol} />
                    </TabsContent>
                )}
                {pol.is_cumulativa_assicurati && (
                    <TabsContent value="assicurati">
                        <AssicuratiTab polizzaId={pol.id} />
                    </TabsContent>
                )}
                {pol.regolazione_premio && (
                    <TabsContent value="regolazione">
                        <RegolazionePolizzaTab
                            pol={pol}
                            onReload={load}
                            onCalcola={() => setRegolazioneOpen(true)}
                            onGeneraTitolo={() => setTitoloEditing({
                                _new: true,
                                polizza_id: pol.id,
                                numero_polizza: pol.numero_polizza,
                                tipo: "regolazione",
                                importo_lordo: pol.regolazione_dovuto || 0,
                                importo_netto: pol.regolazione_dovuto || 0,
                                effetto: new Date().toISOString().slice(0, 10),
                                scadenza: new Date().toISOString().slice(0, 10),
                            })}
                        />
                    </TabsContent>
                )}

                <TabsContent value="documenti">
                    {canEdit && (
                        <div className="mb-3 flex items-center justify-between flex-wrap gap-2 bg-blue-50 border border-blue-200 rounded-lg p-3">
                            <div className="text-xs text-blue-900">
                                <strong>Documenti da Google Drive</strong>: cerca i PDF che contengono il numero di questa polizza e allegali automaticamente.
                            </div>
                            <Button
                                size="sm"
                                className="bg-blue-600 hover:bg-blue-700 shrink-0"
                                data-testid="cerca-drive-polizza-btn"
                                onClick={async () => {
                                    const t = toast.loading("Cerco i documenti su Google Drive…");
                                    try {
                                        const r = await api.post(`/librerie/cloud-storage/cerca-documenti-polizza/${pol.id}`);
                                        const n = r.data.salvati?.length || 0;
                                        toast.success(
                                            n > 0
                                                ? `Trovati ${r.data.trovati} file · ${n} nuovi documenti allegati`
                                                : `Nessun nuovo documento (${r.data.gia_presenti} già presenti)`,
                                            { id: t });
                                        load();
                                    } catch (e) {
                                        toast.error(e.response?.data?.detail || "Errore ricerca su Drive", { id: t });
                                    }
                                }}
                            >
                                🔍 Cerca su Google Drive
                            </Button>
                        </div>
                    )}
                    <DocumentiPolizzaTab polizzaId={pol.id} canEdit={canEdit} onAfterOCR={load} />
                    <div className="mt-4">
                        <DocumentiSezioneSplit
                            entita_tipo="polizza"
                            entita_id={pol.id}
                            canEdit={canEdit}
                            layout="quadrotti"
                            titolo="Documenti polizza"
                            sottotitolo="Documenti organizzati per categoria. Polizza, condizioni, quietanze, libretto e atto di vendita sono di default visibili al cliente; preventivi, appunti e regolazione restano interni."
                            categorie={[
                                { key: "polizza", label: "Polizza", icon: "📄", default_visibile: true, multiple: true },
                                { key: "condizioni", label: "Condizioni", icon: "📜", default_visibile: true, multiple: true },
                                { key: "appendici", label: "Appendici", icon: "➕", default_visibile: true, multiple: true, descrizione: "Appendici / variazioni di polizza" },
                                { key: "libretto_veicolo", label: "Libretto veicolo", icon: "📕", default_visibile: true, multiple: true, descrizione: "Libretto di circolazione del veicolo" },
                                { key: "atto_vendita", label: "Atto di vendita", icon: "🖊️", default_visibile: true, multiple: true, descrizione: "Atto di vendita / passaggio proprietà" },
                                { key: "quietanza", label: "Quietanze", icon: "🧾", default_visibile: true, multiple: true, descrizione: "Documenti di pagamento rilasciati al cliente (più quietanze secondo frazionamento)" },
                                { key: "mup", label: "MUP", icon: "📋", default_visibile: true, multiple: true, descrizione: "Modulo Unico Precontrattuale (IVASS) — generato dalla polizza e firmabile" },
                                { key: "questionario", label: "Questionario", icon: "🗒️", default_visibile: true, multiple: true, descrizione: "Questionario assuntivo / adeguatezza compilato e firmato dal cliente" },
                                { key: "regolazione", label: "Regolazione", icon: "🧮", default_visibile: false, multiple: true, descrizione: "Documentazione della regolazione premio (dati consuntivi, comunicazioni, calcoli)" },
                                { key: "preventivo", label: "Preventivi", icon: "📋", default_visibile: false, multiple: true },
                                { key: "appunti", label: "Appunti", icon: "📝", default_visibile: false, multiple: true },
                                { key: "altri", label: "Documenti altri (foto)", icon: "🖼️", default_visibile: false, multiple: true, descrizione: "Altri documenti / foto ad uso interno" },
                            ]}
                        />
                    </div>
                </TabsContent>

                <TabsContent value="sinistri">
                    <Card className="border-slate-200 mt-4 overflow-hidden" data-testid="sinistri-tab-card">
                        <div className="p-3 border-b border-slate-200 flex justify-between items-center bg-slate-50">
                            <div className="text-xs text-slate-600">
                                {pol.sinistri?.length || 0} sinistri su questa polizza
                            </div>
                            <Link
                                to={`/sinistri?polizza_id=${pol.id}`}
                                className="text-xs text-sky-700 hover:underline"
                                data-testid="sinistri-fulllist-link"
                            >
                                Apri elenco completo →
                            </Link>
                        </div>
                        {(!pol.sinistri || pol.sinistri.length === 0) ? (
                            <div className="p-8 text-center text-slate-500 text-sm">Nessun sinistro registrato su questa polizza.</div>
                        ) : (
                            <table className="tbl w-full">
                                <thead><tr>
                                    <th>N. sinistro</th>
                                    <th>Data avv.</th>
                                    <th>Data den.</th>
                                    <th>Stato</th>
                                    <th>Luogo</th>
                                    <th className="text-right">Riserva</th>
                                    <th className="text-right">Liquidato</th>
                                    <th className="text-center w-24">Azione</th>
                                </tr></thead>
                                <tbody>
                                    {pol.sinistri.map((s) => (
                                        <tr key={s.id} className="hover:bg-rose-50/40" data-testid={`sinistro-row-${s.id}`}>
                                            <td className="num font-medium text-rose-700">{s.numero_sinistro || "—"}</td>
                                            <td className="num">{fmtDate(s.data_avvenimento)}</td>
                                            <td className="num">{fmtDate(s.data_denuncia)}</td>
                                            <td><StatusBadge stato={s.stato} /></td>
                                            <td className="text-xs text-slate-600">{s.luogo || "—"}</td>
                                            <td className="num text-right">{fmtEur(s.riserva || 0)}</td>
                                            <td className="num text-right text-emerald-700 font-medium">{fmtEur(s.liquidazione || 0)}</td>
                                            <td className="text-center">
                                                <Link
                                                    to={`/sinistri?focus=${s.id}`}
                                                    className="text-xs text-sky-700 hover:underline"
                                                    data-testid={`sinistro-open-${s.id}`}
                                                >
                                                    Apri
                                                </Link>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </Card>
                </TabsContent>


                <TabsContent value="altri">
                    <Card className="p-6 border-slate-200 mt-4 space-y-3">
                        <SezioneTitolo titolo="Note polizza" />
                        <div className="text-xs text-slate-500 -mt-3">
                            💡 Sezione unificata e modificabile. Annota qui informazioni libere sulla polizza (caratteristiche, da restituire, note interne, appunti).
                        </div>
                        <NotePolizzaEditor pol={pol} canEdit={canEdit} onSaved={load} />
                    </Card>
                </TabsContent>

                <TabsContent value="azioni">
                    <AzioniPolizzaTab polizza={pol} onChanged={load} canEdit={canEdit} />
                </TabsContent>

                <TabsContent value="questionari">
                    <Card className="p-6 border-slate-200 mt-4 space-y-3">
                        <SezioneTitolo titolo="Questionari" />
                        <QuestionariViewer entita="polizza" />
                    </Card>
                </TabsContent>
            </Tabs>
            {editOpen && (
                <EditPolizzaDialog pol={pol} onClose={() => setEditOpen(false)} onSaved={() => { setEditOpen(false); load(); }} />
            )}
            {paying && (
                <DialogIncassoCopertura
                    titolo={paying}
                    conti={conti}
                    onClose={() => { setPaying(null); load(); }}
                    onDone={() => load()}
                />
            )}
            {letteraAbbuonoTitolo && (
                <DialogLetteraAbbuono
                    titoloId={letteraAbbuonoTitolo}
                    onClose={() => { setLetteraAbbuonoTitolo(null); load(); }}
                />
            )}
            {titoloEditing && (
                <TitoloDialog
                    titolo={titoloEditing}
                    conti={conti}
                    onClose={() => { setTitoloEditing(null); load(); }}
                    onDelete={() => { setTitoloEditing(null); load(); }}
                />
            )}
            <Dialog open={mupOpen} onOpenChange={(o) => !o && setMupOpen(false)}>
                <DialogContent className="max-w-2xl max-h-[88vh] overflow-y-auto" data-testid="mup-dialog">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">📋 Modulo Unico Precontrattuale (MUP)</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-3 py-1">
                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <label className="text-xs font-medium text-slate-600">Modello (libreria)</label>
                                <Select value={mupModelloId || "auto"} onValueChange={(v) => cambiaModelloMup(v === "auto" ? "" : v)}>
                                    <SelectTrigger data-testid="mup-modello-select"><SelectValue placeholder="Automatico da ramo" /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="auto">Automatico (in base al ramo)</SelectItem>
                                        {mupModelli.map((m) => <SelectItem key={m.id} value={m.id}>{m.nome} — {m.area}</SelectItem>)}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div>
                                <label className="text-xs font-medium text-slate-600">Area di tutela</label>
                                <div className="h-9 flex items-center px-3 rounded-md bg-slate-50 border border-slate-200 text-sm text-slate-700">{mupArea || "—"}</div>
                            </div>
                        </div>
                        <div className="text-[11px] text-slate-500">
                            Spunta le garanzie richieste dal cliente, proposte dall'intermediario e confermate in polizza.
                            I modelli si gestiscono in <strong>Librerie → Modelli MUP</strong>.
                        </div>
                        <div className="border border-slate-200 rounded-md overflow-hidden">
                            <table className="w-full text-xs">
                                <thead className="bg-slate-800 text-white">
                                    <tr>
                                        <th className="text-left px-2 py-1.5">Garanzia</th>
                                        <th className="text-center px-2 py-1.5 w-24">Richiesta</th>
                                        <th className="text-center px-2 py-1.5 w-24">Proposta</th>
                                        <th className="text-center px-2 py-1.5 w-24">Confermata</th>
                                    </tr>
                                </thead>
                                <tbody data-testid="mup-righe">
                                    {mupRighe.length === 0 ? (
                                        <tr><td colSpan={4} className="text-center text-slate-400 py-4">Nessuna garanzia per questo modello</td></tr>
                                    ) : mupRighe.map((r, i) => (
                                        <tr key={i} className={i % 2 ? "bg-slate-50" : "bg-white"} data-testid={`mup-riga-${i}`}>
                                            <td className="px-2 py-1.5 text-slate-700">{r.nome}</td>
                                            {["richiesta", "proposta", "confermata"].map((col) => (
                                                <td key={col} className="text-center px-2 py-1.5">
                                                    <input type="checkbox" checked={!!r[col]} onChange={() => toggleMup(i, col)}
                                                        data-testid={`mup-chk-${i}-${col}`} className="w-4 h-4 accent-indigo-600 cursor-pointer" />
                                                </td>
                                            ))}
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                    <DialogFooter className="gap-2 flex-wrap">
                        <Button variant="outline" onClick={() => setMupOpen(false)}>Chiudi</Button>
                        <Button variant="outline" onClick={() => generaMup(false)} disabled={mupBusy}
                            className="border-slate-300" data-testid="mup-anteprima-btn">Anteprima PDF</Button>
                        <div className="relative">
                            <Button variant="outline" onClick={() => setMupFirmaMenu((v) => !v)} disabled={mupBusy}
                                className="border-emerald-300 text-emerald-700 hover:bg-emerald-50" data-testid="mup-firma-btn">
                                {mupBusy ? "Invio…" : "Genera e invia per firma ▾"}
                            </Button>
                            {mupFirmaMenu && (
                                <div className="absolute bottom-full right-0 mb-1 w-56 bg-white border border-slate-200 rounded-md shadow-lg z-50 overflow-hidden" data-testid="mup-firma-menu">
                                    <div className="px-3 py-1.5 text-[10px] uppercase text-slate-400 bg-slate-50">Invia il link di firma via…</div>
                                    <button onClick={() => firmaMup({ wa: true, email: false })} className="w-full text-left px-3 py-2 text-sm hover:bg-slate-50" data-testid="mup-firma-wa">🟢 WhatsApp</button>
                                    <button onClick={() => firmaMup({ wa: false, email: true })} className="w-full text-left px-3 py-2 text-sm hover:bg-slate-50" data-testid="mup-firma-email">✉️ Email</button>
                                    <button onClick={() => firmaMup({ wa: true, email: true })} className="w-full text-left px-3 py-2 text-sm hover:bg-slate-50" data-testid="mup-firma-both">📨 WhatsApp + Email</button>
                                </div>
                            )}
                        </div>
                        <Button onClick={() => generaMup(true)} disabled={mupBusy}
                            className="bg-indigo-700 hover:bg-indigo-800" data-testid="mup-archivia-btn">
                            {mupBusy ? "…" : "Genera e archivia"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

        </div>
    );
}

function EditPolizzaDialog({ pol, onClose, onSaved }) {
    const { mezzi } = useMezziPagamento();
    const [collaboratori, setCollaboratori] = useState([]);
    const [rami, setRami] = useState([]);
    const [prodotti, setProdotti] = useState([]);
    useEffect(() => {
        api.get("/auth/users", { params: { role: "collaboratore" } })
            .then((r) => setCollaboratori((r.data || []).filter((u) => u.attivo !== false)))
            .catch(() => setCollaboratori([]));
        api.get("/librerie/rami?dedup=1").then((r) => setRami(r.data || []));
    }, []);
    const [f, setF] = useState({
        numero_polizza: pol.numero_polizza || "",
        contraente_id: pol.contraente_id || pol.contraente?.id || "",
        contraente_nome: pol.contraente?.ragione_sociale || pol.contraente?.cognome_nome || "",
        stato: pol.stato || "attiva",
        ramo: pol.ramo || "",
        prodotto: pol.prodotto || "",
        collaboratore_id: pol.collaboratore_id || "",
        effetto: pol.effetto || "",
        scadenza: pol.scadenza || "",
        scadenza_copertura: pol.scadenza_copertura || "",
        prossima_quietanza: pol.prossima_quietanza || "",
        frazionamento: pol.frazionamento || "annuale",
        tacito_rinnovo: !!pol.tacito_rinnovo,
        termini_mora_giorni: pol.termini_mora_giorni ?? 15,
        termini_disdetta_giorni: pol.termini_disdetta_giorni ?? 0,
        mandato: pol.mandato || "",
        sostituisce_polizza: pol.sostituisce_polizza || "",
        iter_status: pol.iter_status || "",
        oggetto_assicurato: pol.oggetto_assicurato || "",
        premio_netto: pol.premio_netto || 0,
        premio_tasse: pol.premio_tasse || 0,
        premio_imposte: pol.premio_imposte || 0,
        premio_ssn: pol.premio_ssn || 0,
        premio_accessori: pol.premio_accessori || 0,
        premio_addizionale: pol.premio_addizionale || 0,
        premio_lordo: pol.premio_lordo || 0,
        provvigioni: pol.provvigioni || 0,
        targa: pol.targa || "",
        mezzo_pagamento_preferito: pol.mezzo_pagamento_preferito || "",
        veicolo_marca: pol.veicolo_marca || "",
        veicolo_modello: pol.veicolo_modello || "",
        veicolo_tipo: pol.veicolo_tipo || "",
        veicolo_alimentazione: pol.veicolo_alimentazione || "",
        veicolo_uso: pol.veicolo_uso || "",
        veicolo_data_immatricolazione: pol.veicolo_data_immatricolazione || "",
        veicolo_cv_fiscali: pol.veicolo_cv_fiscali || "",
        veicolo_kw: pol.veicolo_kw || "",
        veicolo_cilindrata: pol.veicolo_cilindrata || "",
        veicolo_posti: pol.veicolo_posti || "",
        veicolo_quintali: pol.veicolo_quintali ?? "",
        veicolo_gancio_traino: !!pol.veicolo_gancio_traino,
        veicolo_targa_rimorchio: pol.veicolo_targa_rimorchio || "",
        // Dati associazione contratto (RCA)
        tipo_tariffa: pol.tipo_tariffa || "",
        bm_provenienza: pol.bm_provenienza || "",
        bm_assegnata: pol.bm_assegnata || "",
        bm_assegnata_cu: pol.bm_assegnata_cu || "",
        pejus: pol.pejus ?? "",
        franchigia: pol.franchigia ?? 0,
        valore_veicolo: pol.valore_veicolo ?? 0,
        valore_residuo_veicolo: pol.valore_residuo_veicolo ?? 0,
        valore_accessori: pol.valore_accessori ?? 0,
        guida_esperta: !!pol.guida_esperta,
        guida_esclusiva: !!pol.guida_esclusiva,
        rinuncia_rivalsa: !!pol.rinuncia_rivalsa,
        intestatario: pol.intestatario || "",
        provincia_intestatario: pol.provincia_intestatario || "",
        massimali: pol.massimali || "",
        note: pol.note || "",
        is_cumulativa_assicurati: !!pol.is_cumulativa_assicurati,
        // Regolazione premio
        regolazione_premio: !!pol.regolazione_premio,
        regolazione_base: pol.regolazione_base || "",
        regolazione_tasso: pol.regolazione_tasso ?? "",
        regolazione_minima: pol.regolazione_minima ?? "",
        regolazione_periodicita: pol.regolazione_periodicita || "annuale",
        regolazione_giorni_invio: pol.regolazione_giorni_invio ?? 30,
        regolazione_base_preventivo: pol.regolazione_base_preventivo ?? "",
    });
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
    // Premio lordo = netto + imposte + ssn + accessori + addizionale (auto-calcolato)
    const setEcon = (k, v) => setF((p) => {
        const n = { ...p, [k]: v };
        n.premio_lordo = Math.round(((parseFloat(n.premio_netto) || 0) + (parseFloat(n.premio_imposte) || 0)
            + (parseFloat(n.premio_ssn) || 0) + (parseFloat(n.premio_accessori) || 0)
            + (parseFloat(n.premio_addizionale) || 0)) * 100) / 100;
        return n;
    });

    // Calcola la prossima scadenza quietanza = effetto + intervallo frazionamento
    const MESI_FRAZ = { annuale: 12, semestrale: 6, quadrimestrale: 4, trimestrale: 3, mensile: 1, unica: 12 };
    const calcQuietanza = (effetto, fraz) => {
        if (!effetto) return "";
        const mesi = MESI_FRAZ[fraz] ?? 12;
        const d = new Date(effetto + "T00:00:00");
        if (isNaN(d.getTime())) return "";
        d.setMonth(d.getMonth() + mesi);
        return d.toISOString().slice(0, 10);
    };
    const setEffetto = (v) => setF((p) => ({ ...p, effetto: v, prossima_quietanza: calcQuietanza(v, p.frazionamento) }));
    const setFrazionamento = (v) => setF((p) => ({ ...p, frazionamento: v, prossima_quietanza: calcQuietanza(p.effetto, v) }));

    const save = async () => {
        try {
            const payload = { ...f };
            delete payload.contraente_nome;  // campo display, non persistito (si deriva da contraente_id)
            ["premio_netto", "premio_tasse", "premio_imposte", "premio_ssn", "premio_accessori", "premio_addizionale", "premio_lordo",
             "provvigioni", "termini_mora_giorni", "termini_disdetta_giorni",
             "pejus", "franchigia", "valore_veicolo", "valore_residuo_veicolo", "valore_accessori"].forEach((k) => {
                if (payload[k] !== "" && payload[k] !== null && payload[k] !== undefined) {
                    payload[k] = parseFloat(payload[k]) || 0;
                }
            });
            // Quintali numeric (nullable)
            if (payload.veicolo_quintali === "" || payload.veicolo_quintali === null) {
                payload.veicolo_quintali = null;
            } else if (payload.veicolo_quintali !== undefined) {
                payload.veicolo_quintali = parseFloat(payload.veicolo_quintali) || 0;
            }
            // Regolazione premio numerici (nullable)
            ["regolazione_tasso", "regolazione_minima"].forEach((k) => {
                payload[k] = (payload[k] === "" || payload[k] === null || payload[k] === undefined)
                    ? null : parseFloat(payload[k]);
            });
            payload.regolazione_base_preventivo = parseFloat(payload.regolazione_base_preventivo) || 0;
            payload.regolazione_giorni_invio = parseInt(payload.regolazione_giorni_invio, 10) || 30;
            if (!payload.regolazione_base) payload.regolazione_base = null;
            await api.put(`/polizze/${pol.id}`, payload);
            toast.success("Polizza aggiornata");
            onSaved();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        }
    };

    // Carica prodotti quando cambia il ramo
    useEffect(() => {
        if (!f.ramo) { setProdotti([]); return; }
        api.get("/librerie/prodotti", { params: { ramo: f.ramo, attivi: true } })
            .then((r) => setProdotti(r.data || []))
            .catch(() => setProdotti([]));
    }, [f.ramo]);

    const _selProd = prodotti.find((p) => p.nome === f.prodotto);
    const isRCA = (((f.ramo || "") + " " + (f.prodotto || "")).toUpperCase().includes("RCA"))
        || !!_selProd?.mostra_sezione_veicolo
        || (!_selProd && !!pol.prodotto_mostra_veicolo);

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
                <DialogHeader><DialogTitle>Modifica polizza {pol.numero_polizza}</DialogTitle></DialogHeader>
                <Tabs defaultValue="anagrafica" className="py-2">
                    <TabsList className="bg-slate-100">
                        <TabsTrigger value="anagrafica">Anagrafica</TabsTrigger>
                        <TabsTrigger value="economici">Economici</TabsTrigger>
                        {isRCA && <TabsTrigger value="veicolo">Veicolo</TabsTrigger>}
                        <TabsTrigger value="altri">Altri</TabsTrigger>
                    </TabsList>

                    <TabsContent value="anagrafica">
                        <div className="grid grid-cols-2 gap-3 py-3">
                            <div><Label>N. polizza</Label><Input value={f.numero_polizza} onChange={(e) => set("numero_polizza", e.target.value)} data-testid="edit-pol-numero" /></div>
                            <div>
                                <Label>Stato</Label>
                                <Select value={f.stato} onValueChange={(v) => set("stato", v)}>
                                    <SelectTrigger><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        {["attiva", "sospesa", "in_emissione", "scaduta", "annullata", "sostituita"].map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="col-span-2">
                                <Label>Contraente</Label>
                                <IntestatarioAutocomplete
                                    value={f.contraente_nome}
                                    anagraficaId={f.contraente_id}
                                    onChange={(name, aid) => setF((p) => ({ ...p, contraente_nome: name, contraente_id: aid || "" }))}
                                />
                                <div className="text-[10px] text-slate-400 mt-0.5">Cerca e collega un'altra anagrafica per cambiare il contraente della polizza</div>
                            </div>
                            <div>
                                <Label>Ramo</Label>
                                <Select value={f.ramo || ""} onValueChange={(v) => { set("ramo", v); set("prodotto", ""); }}>
                                    <SelectTrigger data-testid="edit-pol-ramo"><SelectValue placeholder="Seleziona ramo" /></SelectTrigger>
                                    <SelectContent>
                                        {rami.map((r) => (
                                            <SelectItem key={r.id || r.nome} value={r.nome}>{r.nome}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div>
                                <Label>Prodotto</Label>
                                <Select
                                    value={f.prodotto || ""}
                                    onValueChange={(v) => set("prodotto", v)}
                                    disabled={!f.ramo}
                                >
                                    <SelectTrigger data-testid="edit-pol-prodotto">
                                        <SelectValue placeholder={f.ramo ? (prodotti.length ? "Seleziona prodotto" : "Nessun prodotto per questo ramo") : "Scegli prima un ramo"} />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {prodotti.map((p) => (
                                            <SelectItem key={p.id || p.nome} value={p.nome}>{p.nome}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div>
                                <Label>Collaboratore (Operatore)</Label>
                                <Select
                                    value={f.collaboratore_id || "__none__"}
                                    onValueChange={(v) => set("collaboratore_id", v === "__none__" ? "" : v)}
                                >
                                    <SelectTrigger data-testid="edit-pol-collab"><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="__none__">— nessuno —</SelectItem>
                                        {collaboratori.map((c) => (
                                            <SelectItem key={c.id} value={c.id}>{c.name || c.email}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div><Label>Effetto</Label><Input type="date" value={f.effetto} onChange={(e) => setEffetto(e.target.value)} /></div>
                            <div><Label>Scadenza</Label><Input type="date" value={f.scadenza} onChange={(e) => set("scadenza", e.target.value)} /></div>
                            <div><Label>Scad. copertura</Label><Input type="date" value={f.scadenza_copertura} onChange={(e) => set("scadenza_copertura", e.target.value)} /></div>
                            <div><Label>Prossima quietanza</Label><Input type="date" value={f.prossima_quietanza} onChange={(e) => set("prossima_quietanza", e.target.value)} data-testid="edit-pol-prossima-quietanza" /><div className="text-[10px] text-slate-400 mt-0.5">Calcolata da effetto + frazionamento (modificabile)</div></div>
                            <div>
                                <Label>Frazionamento</Label>
                                <Select value={f.frazionamento} onValueChange={(v) => setFrazionamento(v)}>
                                    <SelectTrigger><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        {["annuale", "semestrale", "quadrimestrale", "trimestrale", "mensile", "unica"].map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="flex items-center gap-2 mt-6">
                                <input type="checkbox" id="tacito" checked={f.tacito_rinnovo} onChange={(e) => set("tacito_rinnovo", e.target.checked)} />
                                <Label htmlFor="tacito" className="cursor-pointer">Tacito rinnovo</Label>
                            </div>
                            <div><Label>Agenzia partner</Label><Input value={f.mandato} onChange={(e) => set("mandato", e.target.value)} /></div>
                            <div><Label>Sostituisce polizza</Label><Input value={f.sostituisce_polizza} onChange={(e) => set("sostituisce_polizza", e.target.value)} /></div>
                            <div><Label>Stato iter</Label><Input value={f.iter_status} onChange={(e) => set("iter_status", e.target.value)} /></div>
                            <div><Label>Oggetto assicurato</Label><Input value={f.oggetto_assicurato} onChange={(e) => set("oggetto_assicurato", e.target.value)} /></div>
                            <div><Label>Termini mora (gg)</Label><Input type="number" value={f.termini_mora_giorni} onChange={(e) => set("termini_mora_giorni", e.target.value)} /></div>
                            <div><Label>Termini disdetta (gg)</Label><Input type="number" value={f.termini_disdetta_giorni} onChange={(e) => set("termini_disdetta_giorni", e.target.value)} /></div>
                            <div>
                                <Label>Tipo pagamento preferito (questa polizza)</Label>
                                <SelectTipoPagamento
                                    value={f.mezzo_pagamento_preferito || ""}
                                    onChange={(v) => set("mezzo_pagamento_preferito", v)}
                                    placeholder="Auto (segue ultimo incasso)"
                                    testid="polizza-mezzo-preferito"
                                />
                                {pol.ultimo_mezzo_pagamento && (
                                    <div className="text-[10px] text-slate-500 mt-1">
                                        Ultimo incasso: <strong>{pol.ultimo_mezzo_pagamento}</strong>
                                        {pol.ultimo_mezzo_pagamento_data && ` (${pol.ultimo_mezzo_pagamento_data})`}
                                    </div>
                                )}
                            </div>
                        </div>
                    </TabsContent>

                    <TabsContent value="economici">
                        <div className="grid grid-cols-2 gap-3 py-3">
                            <div><Label>Premio netto €</Label><Input type="number" step="0.01" value={f.premio_netto} onChange={(e) => setEcon("premio_netto", e.target.value)} data-testid="edit-pol-premio-netto" /></div>
                            <div><Label>Imposte €</Label><Input type="number" step="0.01" value={f.premio_imposte} onChange={(e) => setEcon("premio_imposte", e.target.value)} data-testid="edit-pol-imposte" /></div>
                            <div><Label>SSN €</Label><Input type="number" step="0.01" value={f.premio_ssn} onChange={(e) => setEcon("premio_ssn", e.target.value)} data-testid="edit-pol-ssn" /></div>
                            <div><Label>Accessori €</Label><Input type="number" step="0.01" value={f.premio_accessori} onChange={(e) => setEcon("premio_accessori", e.target.value)} data-testid="edit-pol-accessori" /></div>
                            <div><Label>Addizionale €</Label><Input type="number" step="0.01" value={f.premio_addizionale} onChange={(e) => setEcon("premio_addizionale", e.target.value)} data-testid="edit-pol-addizionale" /></div>
                            <div>
                                <Label>Premio lordo € (automatico)</Label>
                                <Input type="number" step="0.01" readOnly disabled value={f.premio_lordo}
                                    className="bg-slate-100 font-semibold" data-testid="edit-pol-premio-lordo" />
                                <div className="text-[10px] text-slate-400 mt-0.5">Netto + Imposte + SSN + Accessori + Addizionale</div>
                            </div>
                            <div>
                                <Label>Provvigioni €</Label>
                                <div className="flex gap-2">
                                    <Input type="number" step="0.01" value={f.provvigioni}
                                        onChange={(e) => set("provvigioni", e.target.value)}
                                        data-testid="edit-pol-provv" />
                                    <Button
                                        variant="outline" size="sm"
                                        onClick={async () => {
                                            try {
                                                const r = await api.get("/provvigioni/calcola", {
                                                    params: {
                                                        premio_lordo: f.premio_lordo || 0,
                                                        collaboratore_id: f.collaboratore_id || undefined,
                                                        compagnia_id: pol.compagnia_id,
                                                        ramo: f.ramo,
                                                    },
                                                });
                                                if (r.data.provvigione_totale > 0) {
                                                    set("provvigioni", r.data.provvigione_totale);
                                                    toast.success(`Provvigione: ${r.data.provvigione_totale}€ (schema: ${r.data.schema_nome})`);
                                                } else {
                                                    toast.warning("Nessuno schema provvigionale applicabile");
                                                }
                                            } catch { toast.error("Errore calcolo"); }
                                        }}
                                        data-testid="recalc-provv-btn"
                                    >
                                        Auto
                                    </Button>
                                </div>
                                <div className="text-[10px] text-slate-500 mt-1">
                                    Click <em>Auto</em> per ricalcolare dal premio lordo + collaboratore (via schema provvigionale)
                                </div>
                            </div>
                        </div>
                    </TabsContent>

                    {isRCA && (
                        <TabsContent value="veicolo">
                            <div className="text-[11px] uppercase tracking-wide text-sky-700 font-semibold pt-3 pb-1">Dati veicolo</div>
                            <div className="grid grid-cols-2 gap-3 pb-3">
                                <div className="col-span-2">
                                    <TargaSearchWithLentina
                                        value={f.targa}
                                        showVehicleData={true}
                                        onChange={(targa, v) => {
                                            setF((prev) => ({
                                                ...prev,
                                                targa,
                                                ...(v ? {
                                                    veicolo_marca: prev.veicolo_marca || v.marca || "",
                                                    veicolo_modello: prev.veicolo_modello || v.modello || "",
                                                    veicolo_alimentazione: prev.veicolo_alimentazione || v.alimentazione || "",
                                                    veicolo_kw: prev.veicolo_kw || v.kw || "",
                                                    veicolo_cilindrata: prev.veicolo_cilindrata || v.cilindrata || "",
                                                    veicolo_data_immatricolazione: prev.veicolo_data_immatricolazione || v.data_immatricolazione || "",
                                                    veicolo_uso: prev.veicolo_uso || v.uso || "",
                                                    veicolo_posti: prev.veicolo_posti || v.posti || "",
                                                    veicolo_quintali: prev.veicolo_quintali || v.quintali || "",
                                                    telaio: prev.telaio || v.telaio || "",
                                                    veicolo_id: v.id,
                                                } : {}),
                                            }));
                                        }}
                                    />
                                </div>
                                <div><Label>Marca</Label><Input value={f.veicolo_marca} onChange={(e) => set("veicolo_marca", e.target.value)} data-testid="edit-pol-marca" /></div>
                                <div><Label>Modello</Label><Input value={f.veicolo_modello} onChange={(e) => set("veicolo_modello", e.target.value)} data-testid="edit-pol-modello" /></div>
                                <div><Label>Tipo veicolo</Label><Input value={f.veicolo_tipo} onChange={(e) => set("veicolo_tipo", e.target.value)} /></div>
                                <div><Label>Alimentazione</Label><Input value={f.veicolo_alimentazione} onChange={(e) => set("veicolo_alimentazione", e.target.value)} /></div>
                                <div><Label>Tipo uso</Label><Input value={f.veicolo_uso} onChange={(e) => set("veicolo_uso", e.target.value)} /></div>
                                <div><Label>Immatricolazione</Label><Input type="date" value={f.veicolo_data_immatricolazione} onChange={(e) => set("veicolo_data_immatricolazione", e.target.value)} /></div>
                                <div><Label>CV fiscali</Label><Input value={f.veicolo_cv_fiscali} onChange={(e) => set("veicolo_cv_fiscali", e.target.value)} /></div>
                                <div><Label>KW</Label><Input value={f.veicolo_kw} onChange={(e) => set("veicolo_kw", e.target.value)} /></div>
                                <div><Label>Quintali P.C.</Label><Input type="number" step="0.01" value={f.veicolo_quintali} onChange={(e) => set("veicolo_quintali", e.target.value)} data-testid="edit-pol-quintali" /></div>
                                <div><Label>Cilindrata</Label><Input value={f.veicolo_cilindrata} onChange={(e) => set("veicolo_cilindrata", e.target.value)} /></div>
                                <div><Label>Numero posti</Label><Input value={f.veicolo_posti} onChange={(e) => set("veicolo_posti", e.target.value)} /></div>
                                <div className="flex items-center gap-2 mt-6">
                                    <input type="checkbox" id="gancio-traino" checked={f.veicolo_gancio_traino} onChange={(e) => set("veicolo_gancio_traino", e.target.checked)} data-testid="edit-pol-gancio" />
                                    <Label htmlFor="gancio-traino" className="cursor-pointer">Gancio traino</Label>
                                </div>
                                <div><Label>Targa rimorchio</Label><Input value={f.veicolo_targa_rimorchio} onChange={(e) => set("veicolo_targa_rimorchio", e.target.value.toUpperCase())} data-testid="edit-pol-targa-rim" /></div>
                            </div>

                            <div className="text-[11px] uppercase tracking-wide text-sky-700 font-semibold pt-2 pb-1 border-t border-slate-200">Dati associazione contratto</div>
                            <div className="grid grid-cols-2 gap-3 pb-3 pt-2">
                                <div><Label>Tipo tariffa</Label><Input value={f.tipo_tariffa} onChange={(e) => set("tipo_tariffa", e.target.value)} data-testid="edit-pol-tipo-tariffa" /></div>
                                <div><Label>B-M provenienza</Label><Input value={f.bm_provenienza} onChange={(e) => set("bm_provenienza", e.target.value)} data-testid="edit-pol-bm-prov" /></div>
                                <div><Label>B-M assegnata</Label><Input value={f.bm_assegnata} onChange={(e) => set("bm_assegnata", e.target.value)} data-testid="edit-pol-bm-ass" /></div>
                                <div><Label>B-M ass. CU</Label><Input value={f.bm_assegnata_cu} onChange={(e) => set("bm_assegnata_cu", e.target.value)} data-testid="edit-pol-bm-cu" /></div>
                                <div><Label>Pejus</Label><Input type="number" step="0.01" value={f.pejus} onChange={(e) => set("pejus", e.target.value)} data-testid="edit-pol-pejus" /></div>
                                <div><Label>Franchigia €</Label><Input type="number" step="0.01" value={f.franchigia} onChange={(e) => set("franchigia", e.target.value)} data-testid="edit-pol-franchigia" /></div>
                                <div><Label>Valore veicolo €</Label><Input type="number" step="0.01" value={f.valore_veicolo} onChange={(e) => set("valore_veicolo", e.target.value)} data-testid="edit-pol-valore-veicolo" /></div>
                                <div><Label>Valore residuo €</Label><Input type="number" step="0.01" value={f.valore_residuo_veicolo} onChange={(e) => set("valore_residuo_veicolo", e.target.value)} data-testid="edit-pol-valore-residuo" /></div>
                                <div><Label>Valore accessori €</Label><Input type="number" step="0.01" value={f.valore_accessori} onChange={(e) => set("valore_accessori", e.target.value)} data-testid="edit-pol-valore-accessori" /></div>
                                <div className="flex items-center gap-2 mt-6">
                                    <input type="checkbox" id="guida-esperta" checked={f.guida_esperta} onChange={(e) => set("guida_esperta", e.target.checked)} data-testid="edit-pol-guida-esperta" />
                                    <Label htmlFor="guida-esperta" className="cursor-pointer">Guida esperta</Label>
                                </div>
                                <div className="flex items-center gap-2 mt-6">
                                    <input type="checkbox" id="guida-esclusiva" checked={f.guida_esclusiva} onChange={(e) => set("guida_esclusiva", e.target.checked)} data-testid="edit-pol-guida-esclusiva" />
                                    <Label htmlFor="guida-esclusiva" className="cursor-pointer">Guida esclusiva</Label>
                                </div>
                                <div className="flex items-center gap-2 mt-6">
                                    <input type="checkbox" id="rinuncia-rivalsa" checked={f.rinuncia_rivalsa} onChange={(e) => set("rinuncia_rivalsa", e.target.checked)} data-testid="edit-pol-rinuncia-rivalsa" />
                                    <Label htmlFor="rinuncia-rivalsa" className="cursor-pointer">Rinuncia rivalsa</Label>
                                </div>
                                <div><Label>Intestatario</Label><Input value={f.intestatario} onChange={(e) => set("intestatario", e.target.value)} data-testid="edit-pol-intestatario" /></div>
                                <div><Label>Prov. intestatario</Label><Input maxLength={2} value={f.provincia_intestatario} onChange={(e) => set("provincia_intestatario", e.target.value.toUpperCase())} data-testid="edit-pol-prov-intest" /></div>
                                <div className="col-span-2"><Label>Massimali</Label><Input value={f.massimali} onChange={(e) => set("massimali", e.target.value)} data-testid="edit-pol-massimali" /></div>
                            </div>
                        </TabsContent>
                    )}

                    <TabsContent value="altri">
                        <div className="py-3">
                            <Label>Note</Label>
                            <textarea
                                rows={5}
                                className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm"
                                value={f.note} onChange={(e) => set("note", e.target.value)}
                            />
                        </div>
                        <div className="border-t border-slate-200 pt-3 mt-1">
                            <div className="flex items-center gap-2 mb-3">
                                <input type="checkbox" id="cumulativa-assic" checked={f.is_cumulativa_assicurati}
                                    onChange={(e) => set("is_cumulativa_assicurati", e.target.checked)}
                                    data-testid="edit-pol-cumulativa-flag" />
                                <Label htmlFor="cumulativa-assic" className="cursor-pointer font-semibold text-teal-700">
                                    Gestione cumulativa assicurati (es. Ritiro Patente)
                                </Label>
                            </div>
                            <div className="text-[11px] text-slate-500 -mt-2 mb-3">
                                Abilita la scheda "Assicurati" nella polizza per gestire l'elenco cumulativo delle persone assicurate (con import da Excel).
                            </div>
                        </div>
                        <div className="border-t border-slate-200 pt-3 mt-1">
                            <div className="flex items-center gap-2 mb-3">
                                <input type="checkbox" id="reg-premio" checked={f.regolazione_premio}
                                    onChange={(e) => set("regolazione_premio", e.target.checked)}
                                    data-testid="edit-pol-regolazione-flag" />
                                <Label htmlFor="reg-premio" className="cursor-pointer font-semibold text-violet-700">
                                    Soggetta a regolazione premio
                                </Label>
                            </div>
                            {f.regolazione_premio && (
                                <div className="grid grid-cols-2 gap-3 bg-violet-50/50 border border-violet-100 rounded-lg p-3">
                                    <div>
                                        <Label>Base di calcolo</Label>
                                        <Select value={f.regolazione_base || "fatturato"} onValueChange={(v) => set("regolazione_base", v)}>
                                            <SelectTrigger data-testid="edit-pol-reg-base"><SelectValue /></SelectTrigger>
                                            <SelectContent>
                                                {[["fatturato", "Fatturato"], ["mercedi", "Monte mercedi"], ["addetti", "N. addetti"], ["ricavi", "Ricavi"], ["altro", "Altro"]].map(([v, l]) => (
                                                    <SelectItem key={v} value={v}>{l}</SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div>
                                        <Label>Periodicità</Label>
                                        <Select value={f.regolazione_periodicita || "annuale"} onValueChange={(v) => set("regolazione_periodicita", v)}>
                                            <SelectTrigger data-testid="edit-pol-reg-periodicita"><SelectValue /></SelectTrigger>
                                            <SelectContent>
                                                {["annuale", "biennale"].map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div><Label>Tasso (%)</Label><Input type="number" step="0.001" value={f.regolazione_tasso} onChange={(e) => set("regolazione_tasso", e.target.value)} placeholder="Es. 1.5" data-testid="edit-pol-reg-tasso" /></div>
                                    <div><Label>Base di polizza (preventivo)</Label><Input type="number" step="0.01" value={f.regolazione_base_preventivo} onChange={(e) => set("regolazione_base_preventivo", e.target.value)} placeholder="Es. 100000" data-testid="edit-pol-reg-preventivo" /></div>
                                    <div><Label>Premio minimo non rimb. €</Label><Input type="number" step="0.01" value={f.regolazione_minima} onChange={(e) => set("regolazione_minima", e.target.value)} data-testid="edit-pol-reg-minima" /></div>
                                    <div className="col-span-2">
                                        <Label>Giorni dopo scadenza per invio lettera</Label>
                                        <Input type="number" value={f.regolazione_giorni_invio} onChange={(e) => set("regolazione_giorni_invio", e.target.value)} data-testid="edit-pol-reg-giorni" />
                                        <div className="text-[10px] text-slate-500 mt-1">La lettera di richiesta dati sarà segnalata come "da inviare" trascorsi questi giorni dalla scadenza.</div>
                                    </div>
                                </div>
                            )}
                        </div>
                    </TabsContent>
                </Tabs>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Annulla</Button>
                    <Button onClick={save} className="bg-sky-700 hover:bg-sky-800" data-testid="edit-pol-save">Salva modifiche</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

// Editor multi-collaboratore delle provvigioni (% o importo fisso, con sottorete piramidale)
function ProvvigioniOperatoriEditor({ pol, canEdit, onSaved }) {
    const totale = Number(pol.provvigione_totale ?? pol.provvigioni ?? 0);
    const [users, setUsers] = useState([]);
    const [rows, setRows] = useState([]);
    const [saving, setSaving] = useState(false);
    const [provvStruttura, setProvvStruttura] = useState(pol.provv_struttura ?? 0);

    useEffect(() => {
        api.get("/auth/users")
            .then((r) => setUsers(r.data.filter((u) => u.role !== "cliente" && u.attivo !== false)))
            .catch(() => {});
    }, []);
    useEffect(() => {
        setProvvStruttura(pol.provv_struttura ?? 0);
        setRows((pol.provvigioni_operatori || []).map((o) => ({
            collaboratore_id: o.collaboratore_id || "",
            operatore_nome: o.operatore_nome || "",
            tipo: o.tipo || "importo",
            valore: o.valore ?? o.provvigione ?? 0,
            provvigione_addizionali: o.provvigione_addizionali ?? 0,
            origine: o.origine || "manuale",
        })));
    }, [pol.id, pol.provvigioni_operatori, pol.provv_struttura]);

    const importoRiga = (r) => {
        const v = parseFloat(r.valore) || 0;
        return Math.round((r.tipo === "percentuale" ? (totale * v) / 100 : v) * 100) / 100;
    };
    const totAssegnato = rows.reduce((s, r) => s + importoRiga(r), 0);
    const margine = Math.round((totale - totAssegnato) * 100) / 100;

    const patch = (i, p) => setRows((rs) => rs.map((x, j) => (j === i ? { ...x, ...p } : x)));

    const selezionaCollab = async (i, uid) => {
        const u = users.find((x) => x.id === uid);
        if (!u) return;
        patch(i, {
            collaboratore_id: u.id,
            operatore_nome: u.name,
            tipo: rows[i].tipo,
            valore: rows[i].valore || u.perc_provvigione_default || 0,
            ...(rows[i].valore ? {} : { tipo: "percentuale" }),
        });
        // SOTTORETE (da campo utente): se il collaboratore riporta a qualcuno
        if (u.parent_collaboratore_id && !rows.some((r) => r.collaboratore_id === u.parent_collaboratore_id)) {
            const padre = users.find((x) => x.id === u.parent_collaboratore_id);
            if (padre) {
                setRows((rs) => [...rs, {
                    collaboratore_id: padre.id,
                    operatore_nome: padre.name,
                    tipo: "percentuale",
                    valore: u.parent_provvigione_pct || 0,
                    origine: "sottorete",
                }]);
                toast.info(`Sottorete: aggiunto ${padre.name} (${u.parent_provvigione_pct || 0}%) — rimuovilo se non dovuto`);
            }
        }
        // RETE PIRAMIDALE (da schema provvigionale): proponi i livelli superiori (upline)
        try {
            const r = await api.get("/librerie/schema-provvigionale", { params: { collaboratore_id: uid } });
            const schemi = r.data || [];
            const schema = schemi.find((s) => s.attivo !== false) || schemi[0];
            const upline = (schema?.upline || []).filter((up) => up.operatore_id && (parseFloat(up.percentuale) || 0) > 0);
            if (upline.length) {
                setRows((rs) => {
                    const nuovi = upline
                        .filter((up) => !rs.some((row) => row.collaboratore_id === up.operatore_id))
                        .map((up) => ({
                            collaboratore_id: up.operatore_id,
                            operatore_nome: up.operatore_nome || (users.find((x) => x.id === up.operatore_id)?.name) || "Livello superiore",
                            tipo: "percentuale",
                            valore: parseFloat(up.percentuale) || 0,
                            origine: "upline",
                        }));
                    return nuovi.length ? [...rs, ...nuovi] : rs;
                });
                const nomi = upline.map((up) => `${up.operatore_nome || "superiore"} (${up.percentuale}%)`).join(", ");
                toast.info(`Rete piramidale: aggiunti livelli superiori — ${nomi}. Rimuovili se non dovuti.`);
            }
        } catch (_) { /* nessuno schema o errore: ignora */ }
    };

    const salva = async () => {
        setSaving(true);
        try {
            await api.put(`/polizze/${pol.id}`, {
                provv_struttura: parseFloat(provvStruttura) || 0,
                provvigioni_operatori: rows
                    .filter((r) => r.operatore_nome || r.collaboratore_id)
                    .map((r) => ({
                        collaboratore_id: r.collaboratore_id || null,
                        operatore_nome: r.operatore_nome,
                        tipo: r.tipo,
                        valore: parseFloat(r.valore) || 0,
                        provvigione: importoRiga(r),
                        provvigione_addizionali: parseFloat(r.provvigione_addizionali) || 0,
                        origine: r.origine || "manuale",
                    })),
            });
            toast.success("Ripartizione provvigioni salvata");
            onSaved?.();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore salvataggio provvigioni"); }
        finally { setSaving(false); }
    };

    return (
        <div className="mt-4 border-t border-slate-100 pt-3" data-testid="provv-operatori-editor">
            <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
                <SezioneTitolo titolo="Ripartizione provvigioni per operatore" extra />
                <div className="flex items-center gap-3">
                    <label className="flex items-center gap-1.5 text-xs text-slate-600">
                        <span className="uppercase tracking-wide text-[10px] text-slate-400">Provv. totali rata (agenzia)</span>
                        <Input type="number" step="0.01" value={provvStruttura}
                            onChange={(e) => setProvvStruttura(e.target.value)} readOnly={!canEdit}
                            className="h-8 w-28 text-xs text-right" data-testid="provv-struttura-input" />
                    </label>
                    {canEdit && (
                        <button type="button"
                            onClick={() => setRows((rs) => [...rs, { collaboratore_id: "", operatore_nome: "", tipo: "percentuale", valore: 0, provvigione_addizionali: 0, origine: "manuale" }])}
                            className="inline-flex items-center gap-1 text-xs font-medium bg-sky-700 hover:bg-sky-800 text-white rounded px-2.5 py-1.5" data-testid="provv-op-add">
                            + Aggiungi
                        </button>
                    )}
                </div>
            </div>
            {rows.length === 0 ? (
                <div className="text-xs text-slate-400 italic">Nessuna ripartizione — le provvigioni seguono lo schema provvigionale standard.</div>
            ) : (
                <table className="tbl w-full text-xs">
                    <thead>
                        <tr className="bg-slate-800 text-slate-100">
                            <th className="w-10 text-center">#</th>
                            <th className="text-left">Operatore</th>
                            <th className="w-28">Calcolo</th>
                            <th className="w-24 text-right">Valore</th>
                            <th className="w-32 text-right">Provvigione €</th>
                            <th className="w-36 text-right">Provv. su addizionali €</th>
                            <th className="w-16 text-center">Azioni</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((r, i) => (
                            <tr key={i} className={i % 2 ? "bg-slate-50" : ""}>
                                <td className="text-center text-slate-400">{i + 1}</td>
                                <td>
                                    {canEdit ? (
                                        <select value={r.collaboratore_id || ""} onChange={(e) => selezionaCollab(i, e.target.value)}
                                            className="w-full h-8 px-1.5 text-xs border border-slate-200 rounded bg-white"
                                            data-testid={`provv-op-collab-${i}`}>
                                            <option value="">{r.operatore_nome || "— Seleziona —"}</option>
                                            {users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
                                        </select>
                                    ) : (r.operatore_nome || "—")}
                                    {r.origine === "sottorete" && (
                                        <span className="ml-1 text-[9px] px-1 py-0.5 rounded bg-violet-100 text-violet-700">sottorete</span>
                                    )}
                                    {r.origine === "upline" && (
                                        <span className="ml-1 text-[9px] px-1 py-0.5 rounded bg-amber-100 text-amber-700">livello superiore</span>
                                    )}
                                </td>
                                <td>
                                    <select value={r.tipo} onChange={(e) => patch(i, { tipo: e.target.value })} disabled={!canEdit}
                                        className="w-full h-8 px-1 text-xs border border-slate-200 rounded bg-white"
                                        data-testid={`provv-op-tipo-${i}`}>
                                        <option value="percentuale">% su provv.</option>
                                        <option value="importo">Importo €</option>
                                    </select>
                                </td>
                                <td>
                                    <Input type="number" step="0.01" value={r.valore}
                                        onChange={(e) => patch(i, { valore: e.target.value })} readOnly={!canEdit}
                                        className="h-8 text-xs text-right" data-testid={`provv-op-valore-${i}`} />
                                </td>
                                <td className="num text-right font-medium text-emerald-700" data-testid={`provv-op-importo-${i}`}>
                                    {fmtEur(importoRiga(r))}
                                </td>
                                <td>
                                    <Input type="number" step="0.01" value={r.provvigione_addizionali ?? 0}
                                        onChange={(e) => patch(i, { provvigione_addizionali: e.target.value })} readOnly={!canEdit}
                                        className="h-8 text-xs text-right" data-testid={`provv-op-addizionali-${i}`} />
                                </td>
                                <td className="text-center">
                                    {canEdit && (
                                        <button type="button" onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}
                                            className="text-rose-500 hover:text-rose-700 text-sm" data-testid={`provv-op-del-${i}`}>✕</button>
                                    )}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
            {rows.length > 0 && (
                <div className="flex items-center justify-between mt-2 text-xs">
                    <div className="text-slate-600">
                        Assegnato: <strong className="num">{fmtEur(totAssegnato)}</strong> su <strong className="num">{fmtEur(totale)}</strong>
                        {" "}· Margine agenzia residuo:{" "}
                        <strong className={`num ${margine < 0 ? "text-rose-600" : "text-amber-700"}`} data-testid="provv-op-margine">{fmtEur(margine)}</strong>
                        {margine < 0 && <span className="text-rose-600 ml-1">⚠ superi la provvigione totale</span>}
                    </div>
                    {canEdit && (
                        <Button size="sm" onClick={salva} disabled={saving} className="bg-sky-700 hover:bg-sky-800 h-7 text-xs" data-testid="provv-op-salva">
                            {saving ? "Salvataggio…" : "Salva ripartizione"}
                        </Button>
                    )}
                </div>
            )}
        </div>
    );
}

// Editor inline delle note polizza (sezione unificata, scrivibile)
function NotePolizzaEditor({ pol, canEdit, onSaved }) {
    const initial = [pol.note_interne, pol.note, pol.caratteristiche, pol.da_restituire]
        .filter(Boolean).join("\n\n");
    const [txt, setTxt] = useState(initial);
    const [saving, setSaving] = useState(false);
    useEffect(() => { setTxt(initial); }, [initial]);
    const dirty = txt !== initial;
    const salva = async () => {
        setSaving(true);
        try {
            // consolida tutto nel campo `note` e svuota i campi legacy per evitare duplicati
            await api.put(`/polizze/${pol.id}`, {
                note: txt, note_interne: "", caratteristiche: "", da_restituire: "",
            });
            toast.success("Note polizza salvate");
            onSaved?.();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore salvataggio note"); }
        finally { setSaving(false); }
    };
    return (
        <div className="space-y-2">
            <Textarea
                value={txt}
                onChange={(e) => setTxt(e.target.value)}
                rows={7}
                readOnly={!canEdit}
                placeholder="Scrivi qui le note della polizza…"
                className="text-sm min-h-[140px] bg-slate-50 focus:bg-white"
                data-testid="polizza-note-textarea"
            />
            {canEdit && (
                <div className="flex justify-end">
                    <Button size="sm" onClick={salva} disabled={saving || !dirty}
                        className="bg-sky-700 hover:bg-sky-800"
                        data-testid="polizza-note-salva">
                        {saving ? "Salvataggio…" : "Salva note"}
                    </Button>
                </div>
            )}
        </div>
    );
}

function Hd({ label, value }) {
    return (
        <div>
            <div className="text-[10px] uppercase tracking-widest text-sky-300/80">{label}</div>
            <div className="text-sm mt-0.5">{value || "—"}</div>
        </div>
    );
}

const _TIPO_TITOLO_STYLE = {
    sostituzione: "bg-violet-100 text-violet-700 border-violet-200",
    sospensione: "bg-amber-100 text-amber-700 border-amber-200",
    ripresa: "bg-emerald-100 text-emerald-700 border-emerald-200",
    storno: "bg-rose-100 text-rose-700 border-rose-200",
    annullo: "bg-rose-100 text-rose-700 border-rose-200",
    regolazione: "bg-sky-100 text-sky-700 border-sky-200",
};
function TipoTitoloBadge({ tipo }) {
    if (!tipo) return <span>—</span>;
    const cls = _TIPO_TITOLO_STYLE[tipo] || "bg-slate-100 text-slate-600 border-slate-200";
    return (
        <span className={`inline-block text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded border ${cls}`}
            data-testid={`titolo-tipo-badge-${tipo}`}>
            {tipo}
        </span>
    );
}

function F({ label, value, mono }) {
    return (
        <div>
            <div className="text-[10px] uppercase tracking-widest text-slate-500">{label}</div>
            <div className={`text-sm mt-0.5 text-slate-900 ${mono ? "num font-medium" : ""}`}>{value || "—"}</div>
        </div>
    );
}

function SezioneTitolo({ titolo, extra }) {
    return (
        <div className={`text-xs uppercase tracking-widest font-semibold text-slate-500 ${extra ? "mt-6" : ""} mb-3 pb-1 border-b border-slate-100`}>
            {titolo}
        </div>
    );
}

function Grid({ items }) {
    return (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-x-6 gap-y-3">
            {items.map(([k, v], i) => (
                <div key={i}>
                    <div className="text-[10px] uppercase tracking-widest text-slate-500">{k}</div>
                    <div className="text-sm text-slate-900 mt-0.5">{v || "—"}</div>
                </div>
            ))}
        </div>
    );
}

// ─────────────────────────────────────────────────────────────────────
// MassimaleCell — Cella editable inline per il massimale della singola
// garanzia. Se manca il valore mostra "+ Inserisci" cliccabile che
// diventa input numerico; salva via PATCH /api/polizze/{pid}/garanzie/{i}.
// ─────────────────────────────────────────────────────────────────────
function RenditaCell({ polizzaId, current, canEdit, onSaved }) {
    const [editing, setEditing] = useState(false);
    const [val, setVal] = useState("");
    const [saving, setSaving] = useState(false);

    const salva = async () => {
        const num = parseFloat(String(val).replace(",", "."));
        if (isNaN(num)) { setEditing(false); return; }
        setSaving(true);
        try {
            await api.put(`/polizze/${polizzaId}`, { rendita_annua: num });
            toast.success("Rendita annua aggiornata");
            setEditing(false);
            onSaved?.();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore salvataggio"); }
        finally { setSaving(false); }
    };

    if (!editing) {
        return (
            <button
                type="button"
                disabled={!canEdit}
                onClick={() => { setVal(current ? String(current) : ""); setEditing(true); }}
                className={`text-sm mt-0.5 num font-medium ${canEdit ? "text-sky-700 hover:underline" : "text-slate-900"}`}
                data-testid="rendita-annua-value"
            >
                {current ? fmtEur(current) : (canEdit ? "+ Inserisci" : "—")}
            </button>
        );
    }
    return (
        <div className="flex items-center gap-1 mt-0.5">
            <Input type="number" step="0.01" value={val} autoFocus
                onChange={(e) => setVal(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") salva(); if (e.key === "Escape") setEditing(false); }}
                className="h-7 w-28 text-sm" data-testid="rendita-annua-input" />
            <Button size="sm" className="h-7 px-2 bg-sky-700 hover:bg-sky-800" disabled={saving}
                onClick={salva} data-testid="rendita-annua-salva">OK</Button>
            <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => setEditing(false)}
                data-testid="rendita-annua-annulla">✕</Button>
        </div>
    );
}

function MassimaleCell({ polizzaId, index, current, canEdit, onSaved }) {
    const [editing, setEditing] = useState(false);
    const [val, setVal] = useState("");
    const [saving, setSaving] = useState(false);

    const display = typeof current === "number" && current > 0
        ? fmtEur(current)
        : (current && String(current).trim()) ? String(current) : null;

    const start = () => {
        if (!canEdit) return;
        setVal(typeof current === "number" ? String(current) : (current || ""));
        setEditing(true);
    };

    const commit = async () => {
        setEditing(false);
        const num = parseFloat((val || "").replace(",", ".").replace(/[€\s]/g, ""));
        const patch = { massimale: isNaN(num) ? val : num, capitale_assicurato: isNaN(num) ? undefined : num };
        setSaving(true);
        try {
            await api.patch(`/polizze/${polizzaId}/garanzie/${index}`, patch);
            toast.success("Massimale salvato");
            onSaved && onSaved();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore salvataggio massimale");
        } finally { setSaving(false); }
    };

    if (editing) {
        return (
            <input autoFocus value={val} onChange={(e) => setVal(e.target.value)}
                   onBlur={commit}
                   onKeyDown={(e) => { if (e.key === "Enter") commit();
                                        if (e.key === "Escape") setEditing(false); }}
                   data-testid={`massimale-input-${index}`}
                   placeholder="es. 500000"
                   className="w-32 text-sm border border-sky-300 rounded px-2 py-0.5 text-right focus:outline-none focus:ring-2 focus:ring-sky-200" />
        );
    }
    if (saving) return <span className="text-slate-400 italic">salvo…</span>;
    return (
        <button onClick={start} disabled={!canEdit}
                data-testid={`massimale-cell-${index}`}
                className={`w-full text-right ${display ? "hover:bg-sky-50 rounded px-2 py-0.5" : "text-slate-400 hover:text-sky-600"}`}>
            {display || (canEdit ? <span className="text-[11px]">+ inserisci</span> : <span className="text-slate-300">—</span>)}
        </button>
    );
}


function ProvvigioniTotaleCell({ polizzaId, current, canEdit, onSaved }) {
    const [editing, setEditing] = useState(false);
    const [val, setVal] = useState("");
    const [saving, setSaving] = useState(false);

    const start = () => {
        if (!canEdit) return;
        setVal(current != null ? String(current) : "");
        setEditing(true);
    };

    const commit = async () => {
        setEditing(false);
        const num = parseFloat((val || "").replace(",", ".").replace(/[€\s]/g, "")) || 0;
        setSaving(true);
        try {
            await api.put(`/polizze/${polizzaId}`, { provvigioni: num });
            toast.success("Provvigioni salvate");
            onSaved && onSaved();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore salvataggio provvigioni");
        } finally { setSaving(false); }
    };

    if (editing) {
        return (
            <input autoFocus value={val} onChange={(e) => setVal(e.target.value)}
                   onBlur={commit}
                   onKeyDown={(e) => { if (e.key === "Enter") commit();
                                        if (e.key === "Escape") setEditing(false); }}
                   data-testid="provvigioni-totale-input"
                   placeholder="es. 120,50"
                   className="w-28 text-sm border border-sky-300 rounded px-2 py-0.5 text-right focus:outline-none focus:ring-2 focus:ring-sky-200" />
        );
    }
    if (saving) return <span className="text-slate-400 italic pr-2">salvo…</span>;
    return (
        <button onClick={start} disabled={!canEdit}
                data-testid="provvigioni-totale-cell"
                className="w-full text-right hover:bg-sky-50 rounded px-2 py-0.5 inline-flex items-center justify-end gap-1">
            {fmtEur(current || 0)}
            {canEdit && <Pencil size={11} className="text-slate-400" />}
        </button>
    );
}

