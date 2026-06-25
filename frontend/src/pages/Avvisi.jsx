import { useEffect, useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { api, fmtDate, fmtEur } from "@/lib/api";
import { PageHeader, Loading } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Bell, Mail, MessageCircle, Smartphone, FileText, Receipt } from "lucide-react";
import { toast } from "sonner";

const PRESETS = [
    { v: 7, label: "7 giorni" },
    { v: 15, label: "15 giorni" },
    { v: 30, label: "30 giorni" },
    { v: 60, label: "60 giorni" },
    { v: 90, label: "90 giorni" },
];

export default function Avvisi() {
    const [giorni, setGiorni] = useState(30);
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [emailTarget, setEmailTarget] = useState(null);
    const [tab, setTab] = useState("polizze");

    const load = async () => {
        setLoading(true);
        try {
            const r = await api.get("/avvisi-scadenze/preview", { params: { giorni } });
            setData(r.data);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore nel caricamento avvisi");
        } finally {
            setLoading(false);
        }
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [giorni]);

    const totali = useMemo(() => {
        if (!data) return { polizze: 0, titoli: 0, premio: 0, importi: 0 };
        const premio = (data.polizze || []).reduce((s, p) => s + (p.premio_lordo || 0), 0);
        const importi = (data.titoli || []).reduce((s, t) => s + (t.importo_lordo || 0), 0);
        return {
            polizze: data.polizze?.length || 0,
            titoli: data.titoli?.length || 0,
            premio, importi,
        };
    }, [data]);

    return (
        <div data-testid="avvisi-page">
            <PageHeader
                title={<><Bell className="inline mr-2 -mt-1" size={20} />Avvisi & Scadenze</>}
                subtitle="Polizze e titoli in scadenza · invia notifiche al cliente"
                actions={(
                    <div className="flex items-center gap-2">
                        <Label className="text-xs text-slate-500">Periodo:</Label>
                        <Select value={String(giorni)} onValueChange={(v) => setGiorni(Number(v))}>
                            <SelectTrigger className="w-36" data-testid="periodo-select">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                {PRESETS.map((p) => (
                                    <SelectItem key={p.v} value={String(p.v)}>{p.label}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                )}
            />

            {/* KPI */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                <KpiCard
                    icon={<FileText size={16} />}
                    label="Polizze in scadenza"
                    value={totali.polizze}
                    accent="rose"
                    testid="kpi-polizze-scadenza"
                />
                <KpiCard
                    icon={<Receipt size={16} />}
                    label="Titoli da incassare"
                    value={totali.titoli}
                    accent="amber"
                    testid="kpi-titoli-scadenza"
                />
                <KpiCard
                    label="Premio a rischio"
                    value={fmtEur(totali.premio)}
                    accent="sky"
                    testid="kpi-premio-rischio"
                    monetary
                />
                <KpiCard
                    label="Importi da incassare"
                    value={fmtEur(totali.importi)}
                    accent="emerald"
                    testid="kpi-importi-incasso"
                    monetary
                />
            </div>

            {/* Tab switcher */}
            <div className="flex gap-2 mb-3 border-b border-slate-200">
                <TabBtn active={tab === "polizze"} onClick={() => setTab("polizze")} testid="tab-avvisi-polizze">
                    Polizze ({totali.polizze})
                </TabBtn>
                <TabBtn active={tab === "titoli"} onClick={() => setTab("titoli")} testid="tab-avvisi-titoli">
                    Titoli ({totali.titoli})
                </TabBtn>
            </div>

            {loading || !data ? <Loading /> : (
                tab === "polizze" ? (
                    <AvvisiTable
                        items={data.polizze || []}
                        type="polizza"
                        onEmail={setEmailTarget}
                        emptyLabel={`Nessuna polizza in scadenza nei prossimi ${giorni} giorni.`}
                    />
                ) : (
                    <AvvisiTable
                        items={data.titoli || []}
                        type="titolo"
                        onEmail={setEmailTarget}
                        emptyLabel={`Nessun titolo in scadenza nei prossimi ${giorni} giorni.`}
                    />
                )
            )}

            {emailTarget && (
                <EmailAvvisoDialog
                    item={emailTarget}
                    onClose={() => setEmailTarget(null)}
                />
            )}
        </div>
    );
}

function KpiCard({ icon, label, value, accent = "slate", testid, monetary }) {
    const colors = {
        rose: "border-l-rose-500 text-rose-700",
        amber: "border-l-amber-500 text-amber-700",
        sky: "border-l-sky-500 text-sky-700",
        emerald: "border-l-emerald-500 text-emerald-700",
        slate: "border-l-slate-500 text-slate-700",
    };
    return (
        <Card className={`border border-slate-200 border-l-4 ${colors[accent]} p-3`} data-testid={testid}>
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-wider text-slate-500">
                {icon}{label}
            </div>
            <div className={`mt-1 font-semibold ${monetary ? "num" : ""} text-xl text-slate-900`}>
                {value}
            </div>
        </Card>
    );
}

function TabBtn({ active, onClick, children, testid }) {
    return (
        <button
            type="button"
            onClick={onClick}
            data-testid={testid}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${active
                ? "border-sky-600 text-sky-700"
                : "border-transparent text-slate-600 hover:text-slate-900"}`}
        >
            {children}
        </button>
    );
}

function AvvisiTable({ items, type, onEmail, emptyLabel }) {
    if (!items.length) {
        return (
            <Card className="p-8 text-center text-slate-500 border-slate-200" data-testid={`empty-${type}`}>
                {emptyLabel}
            </Card>
        );
    }
    return (
        <Card className="border-slate-200 overflow-x-auto" data-testid={`avvisi-table-${type}`}>
            <table className="tbl w-full min-w-[1100px]">
                <thead>
                    <tr>
                        <th>Contraente</th>
                        <th>{type === "polizza" ? "Polizza" : "Titolo (polizza)"}</th>
                        <th>Compagnia</th>
                        <th>Ramo</th>
                        <th>Scadenza</th>
                        <th className="text-center">GG</th>
                        <th className="text-right">{type === "polizza" ? "Premio €" : "Importo €"}</th>
                        <th className="text-center w-[170px]">Notifica</th>
                    </tr>
                </thead>
                <tbody>
                    {items.map((it) => (
                        <RigaAvviso
                            key={it.id}
                            item={it}
                            type={type}
                            onEmail={onEmail}
                        />
                    ))}
                </tbody>
            </table>
        </Card>
    );
}

function RigaAvviso({ item, type, onEmail }) {
    const gg = item.giorni_alla_scadenza;
    const ggColor =
        gg === null || gg === undefined ? "text-slate-400" :
            gg < 0 ? "text-rose-700 font-bold" :
                gg <= 3 ? "text-rose-600 font-semibold" :
                    gg <= 7 ? "text-amber-600 font-semibold" :
                        "text-slate-700";
    const ggLabel = gg === null || gg === undefined ? "—" : gg < 0 ? `scaduta da ${Math.abs(gg)}gg` : `${gg}gg`;

    const cell = item.contraente_cellulare?.replace(/[^\d+]/g, "");
    const polUrl = type === "polizza" ? `/polizze/${item.id}` : `/polizze/${item.polizza_id}`;
    const importo = type === "polizza" ? item.premio_lordo : item.importo_lordo;

    const waMessage = type === "polizza"
        ? `Buongiorno ${item.contraente_nome || ""}, le ricordo che la sua polizza ${item.numero_polizza || ""} (${item.compagnia_nome || ""}) scade il ${fmtDate(item.scadenza)}. Premio: ${fmtEur(item.premio_lordo)}.`
        : `Buongiorno ${item.contraente_nome || ""}, le ricordo che il titolo della polizza ${item.numero_polizza || ""} (${item.compagnia_nome || ""}) scade il ${fmtDate(item.scadenza)}. Importo: ${fmtEur(item.importo_lordo)}.`;

    const openWA = () => {
        if (!cell) {
            toast.error("Nessun cellulare per questo cliente");
            return;
        }
        const url = `https://wa.me/${cell}?text=${encodeURIComponent(waMessage)}`;
        window.open(url, "_blank", "noopener,noreferrer");
    };

    const sendSMS = () => {
        toast.info("Integrazione SMS (Twilio) prevista a fine progetto.");
    };

    return (
        <tr data-testid={`avviso-row-${item.id}`}>
            <td>
                <Link to={`/anagrafiche/${item.contraente_id}`} className="text-sky-700 hover:underline font-medium">
                    {item.contraente_nome || "—"}
                </Link>
                <div className="text-[10px] text-slate-500">
                    {item.contraente_email || ""}{item.contraente_email && cell ? " · " : ""}{cell || ""}
                </div>
            </td>
            <td>
                <Link to={polUrl} className="text-amber-700 hover:underline font-medium num">
                    {item.numero_polizza || "—"}
                </Link>
                {item.targa && <div className="text-xs text-sky-700 num">{item.targa}</div>}
            </td>
            <td className="text-xs">{item.compagnia_nome || "—"}</td>
            <td className="text-xs">{item.ramo || "—"}</td>
            <td className="num">{fmtDate(item.scadenza)}</td>
            <td className={`num text-center ${ggColor}`}>{ggLabel}</td>
            <td className="num text-right font-medium">{fmtEur(importo)}</td>
            <td>
                <div className="flex justify-center gap-1">
                    <Button
                        size="sm"
                        variant="outline"
                        className="h-7 w-7 p-0"
                        title="Email"
                        onClick={() => onEmail({ ...item, type, waMessage })}
                        disabled={!item.contraente_email}
                        data-testid={`btn-email-${item.id}`}
                    >
                        <Mail size={13} className={item.contraente_email ? "text-sky-700" : "text-slate-300"} />
                    </Button>
                    <Button
                        size="sm"
                        variant="outline"
                        className="h-7 w-7 p-0"
                        title="WhatsApp"
                        onClick={openWA}
                        disabled={!cell}
                        data-testid={`btn-whatsapp-${item.id}`}
                    >
                        <MessageCircle size={13} className={cell ? "text-emerald-600" : "text-slate-300"} />
                    </Button>
                    <Button
                        size="sm"
                        variant="outline"
                        className="h-7 w-7 p-0"
                        title="SMS (fine progetto)"
                        onClick={sendSMS}
                        data-testid={`btn-sms-${item.id}`}
                    >
                        <Smartphone size={13} className="text-slate-400" />
                    </Button>
                </div>
            </td>
        </tr>
    );
}

function EmailAvvisoDialog({ item, onClose }) {
    const isPol = item.type === "polizza";
    const defSubject = isPol
        ? `Promemoria scadenza polizza ${item.numero_polizza || ""}`
        : `Promemoria scadenza titolo polizza ${item.numero_polizza || ""}`;
    const defBody = isPol
        ? `Gentile ${item.contraente_nome || "cliente"},\n\nle segnaliamo che la polizza n. ${item.numero_polizza || "—"} (${item.compagnia_nome || ""}, ramo ${item.ramo || ""}) è in scadenza il ${fmtDate(item.scadenza)}.\nPremio: ${fmtEur(item.premio_lordo)}.\n\nLa invitiamo a contattarci per il rinnovo.\n\nCordiali saluti,\nL'agenzia`
        : `Gentile ${item.contraente_nome || "cliente"},\n\nle segnaliamo che il titolo della polizza n. ${item.numero_polizza || "—"} (${item.compagnia_nome || ""}) è in scadenza il ${fmtDate(item.scadenza)}.\nImporto: ${fmtEur(item.importo_lordo)}.\n\nLa invitiamo a procedere con il pagamento.\n\nCordiali saluti,\nL'agenzia`;
    const [to, setTo] = useState(item.contraente_email || "");
    const [subject, setSubject] = useState(defSubject);
    const [body, setBody] = useState(defBody);
    const [sending, setSending] = useState(false);

    const send = async () => {
        if (!to) { toast.error("Destinatario obbligatorio"); return; }
        setSending(true);
        try {
            await api.post("/email/invia-singola", { to, subject, body });
            toast.success("Email inviata");
            onClose();
        } catch (e) {
            // Fallback: apri client mail di default se SMTP non configurato
            if (e.response?.status === 404 || e.response?.status === 503) {
                const url = `mailto:${to}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
                window.location.href = url;
                toast.message("Aperto client email locale");
                onClose();
            } else {
                toast.error(e.response?.data?.detail || "Errore invio email");
            }
        } finally {
            setSending(false);
        }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-2xl" data-testid="email-avviso-dialog">
                <DialogHeader>
                    <DialogTitle>Invia avviso via email</DialogTitle>
                </DialogHeader>
                <div className="space-y-3 py-2">
                    <div>
                        <Label>Destinatario</Label>
                        <Input
                            value={to}
                            onChange={(e) => setTo(e.target.value)}
                            type="email"
                            data-testid="email-to"
                        />
                    </div>
                    <div>
                        <Label>Oggetto</Label>
                        <Input
                            value={subject}
                            onChange={(e) => setSubject(e.target.value)}
                            data-testid="email-subject"
                        />
                    </div>
                    <div>
                        <Label>Corpo</Label>
                        <Textarea
                            value={body}
                            onChange={(e) => setBody(e.target.value)}
                            rows={10}
                            className="font-mono text-sm"
                            data-testid="email-body"
                        />
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Annulla</Button>
                    <Button
                        onClick={send}
                        disabled={sending}
                        className="bg-sky-700 hover:bg-sky-800"
                        data-testid="email-send-btn"
                    >
                        {sending ? "Invio…" : "Invia"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
