/**
 * Centro Alert — gestione regole automatismi.
 *
 * Tabella con le 11 regole preset (sinistro aperto/chiuso, polizza emessa,
 * compleanno, documento scaduto, sospesi/arretrati settimanali, ecc.) +
 * regole custom. Toggle on/off, editor template, canali multipli, invio test.
 *
 * Tabs:
 *  - Regole: lista regole con toggle
 *  - Storico: log degli ultimi invii (alert_events)
 */
import { useEffect, useMemo, useState } from "react";
import { api, fmtDate } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import {
    Bell, Mail, MessageCircle, Smartphone, Edit3, Send,
    CheckCircle2, AlertTriangle, History, Zap, Calendar,
} from "lucide-react";
import { toast } from "sonner";

const CANALI_META = {
    inapp: { label: "In-app", icon: Bell, color: "text-sky-700 bg-sky-50 border-sky-200" },
    email: { label: "Email", icon: Mail, color: "text-violet-700 bg-violet-50 border-violet-200" },
    sms: { label: "SMS", icon: Smartphone, color: "text-amber-700 bg-amber-50 border-amber-200" },
    whatsapp: { label: "WhatsApp", icon: MessageCircle, color: "text-emerald-700 bg-emerald-50 border-emerald-200" },
};

const TIPO_META = {
    evento: { label: "Evento", icon: Zap, color: "bg-rose-100 text-rose-700 border-rose-200" },
    schedule: { label: "Schedule", icon: Calendar, color: "bg-sky-100 text-sky-700 border-sky-200" },
    soglia: { label: "Soglia", icon: AlertTriangle, color: "bg-amber-100 text-amber-700 border-amber-200" },
};

export default function Alert() {
    const [tab, setTab] = useState("regole");
    const [rules, setRules] = useState(null);
    const [events, setEvents] = useState([]);
    const [editing, setEditing] = useState(null);
    const [filterTipo, setFilterTipo] = useState("tutti");

    const loadRules = async () => {
        try {
            const r = await api.get("/alert-rules");
            setRules(r.data);
        } catch (e) { toast.error("Errore caricamento regole"); }
    };
    const loadEvents = async () => {
        try {
            const r = await api.get("/alert-events?limit=100");
            setEvents(r.data);
        } catch (e) { /* swallow */ }
    };

    useEffect(() => { loadRules(); }, []);
    useEffect(() => { if (tab === "storico") loadEvents(); }, [tab]);

    const toggle = async (rid) => {
        try {
            const r = await api.post(`/alert-rules/${rid}/toggle`);
            setRules((rs) => rs.map((x) => x.id === rid ? { ...x, attivo: r.data.attivo } : x));
            toast.success(r.data.attivo ? "Regola attivata" : "Regola disattivata");
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        }
    };

    const test = async (rid) => {
        try {
            const r = await api.post(`/alert-rules/${rid}/test`, {});
            toast.success(`Test inviato (in-app: ${r.data.sent}, errori: ${r.data.errors})`);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore test");
        }
    };

    const filteredRules = useMemo(() => {
        if (!rules) return [];
        if (filterTipo === "tutti") return rules;
        return rules.filter((r) => r.tipo === filterTipo);
    }, [rules, filterTipo]);

    const stats = useMemo(() => {
        if (!rules) return { totali: 0, attive: 0, invii: 0 };
        return {
            totali: rules.length,
            attive: rules.filter((r) => r.attivo).length,
            invii: rules.reduce((s, r) => s + (r.invii_totali || 0), 0),
        };
    }, [rules]);

    if (!rules) return <Loading />;

    return (
        <div data-testid="alert-page">
            <PageHeader
                title="Alert & Automazioni"
                subtitle="Notifiche automatiche multi-canale per clienti, collaboratori e agenzia"
            />

            {/* Stats */}
            <div className="grid grid-cols-3 gap-4 mb-4">
                <Card className="p-4">
                    <div className="text-xs text-slate-500 uppercase">Regole totali</div>
                    <div className="text-2xl font-bold mt-1" data-testid="stat-totali">{stats.totali}</div>
                </Card>
                <Card className="p-4">
                    <div className="text-xs text-slate-500 uppercase">Attive</div>
                    <div className="text-2xl font-bold mt-1 text-emerald-700" data-testid="stat-attive">{stats.attive}</div>
                </Card>
                <Card className="p-4">
                    <div className="text-xs text-slate-500 uppercase">Invii totali</div>
                    <div className="text-2xl font-bold mt-1 text-sky-700" data-testid="stat-invii">{stats.invii}</div>
                </Card>
            </div>

            {/* Tabs */}
            <div className="flex gap-2 mb-4 border-b">
                {["regole", "storico"].map((t) => (
                    <button
                        key={t}
                        onClick={() => setTab(t)}
                        className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${tab === t ? "border-sky-600 text-sky-700" : "border-transparent text-slate-500 hover:text-slate-700"}`}
                        data-testid={`alert-tab-${t}`}
                    >
                        {t === "regole" ? "Regole" : <><History size={14} className="inline mr-1" /> Storico invii</>}
                    </button>
                ))}
            </div>

            {tab === "regole" && (
                <>
                    {/* filtro tipo */}
                    <div className="flex gap-2 mb-3">
                        {[
                            { v: "tutti", label: "Tutti" },
                            { v: "evento", label: "Eventi" },
                            { v: "schedule", label: "Schedule" },
                            { v: "soglia", label: "Soglia" },
                        ].map((f) => (
                            <button
                                key={f.v}
                                onClick={() => setFilterTipo(f.v)}
                                className={`text-xs px-3 py-1.5 rounded border transition-colors ${filterTipo === f.v ? "bg-slate-900 text-white border-slate-900" : "bg-white text-slate-700 border-slate-300 hover:bg-slate-50"}`}
                                data-testid={`filter-${f.v}`}
                            >
                                {f.label}
                            </button>
                        ))}
                    </div>

                    {filteredRules.length === 0 ? <Empty label="Nessuna regola" /> : (
                        <div className="space-y-3">
                            {filteredRules.map((r) => {
                                const TipoIcon = (TIPO_META[r.tipo] || TIPO_META.evento).icon;
                                return (
                                    <Card key={r.id} className="p-4" data-testid={`alert-rule-${r.preset_key || r.id}`}>
                                        <div className="flex items-start gap-3">
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2 flex-wrap">
                                                    <span className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border ${(TIPO_META[r.tipo] || TIPO_META.evento).color}`}>
                                                        <TipoIcon size={10} /> {(TIPO_META[r.tipo] || TIPO_META.evento).label}
                                                    </span>
                                                    <h3 className="font-semibold text-slate-800">{r.nome}</h3>
                                                    {r.is_preset && <span className="text-[10px] text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded">preset</span>}
                                                </div>
                                                {r.descrizione && <p className="text-sm text-slate-600 mt-1">{r.descrizione}</p>}
                                                <div className="flex items-center gap-3 mt-2 flex-wrap">
                                                    {(r.canali || []).map((c) => {
                                                        const CMeta = CANALI_META[c];
                                                        if (!CMeta) return null;
                                                        const CIcon = CMeta.icon;
                                                        return (
                                                            <span key={c} className={`inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded border ${CMeta.color}`}>
                                                                <CIcon size={11} /> {CMeta.label}
                                                            </span>
                                                        );
                                                    })}
                                                    {r.invii_totali > 0 && (
                                                        <span className="text-[10px] text-slate-400">
                                                            {r.invii_totali} invii · {r.errori_totali || 0} errori
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                            <div className="flex flex-col items-end gap-2">
                                                <Switch
                                                    checked={r.attivo}
                                                    onCheckedChange={() => toggle(r.id)}
                                                    data-testid={`toggle-${r.preset_key || r.id}`}
                                                />
                                                <div className="flex gap-1">
                                                    <Button size="sm" variant="outline" onClick={() => test(r.id)} data-testid={`test-${r.preset_key || r.id}`}>
                                                        <Send size={13} className="mr-1" /> Test
                                                    </Button>
                                                    <Button size="sm" variant="outline" onClick={() => setEditing(r)} data-testid={`edit-${r.preset_key || r.id}`}>
                                                        <Edit3 size={13} />
                                                    </Button>
                                                </div>
                                            </div>
                                        </div>
                                    </Card>
                                );
                            })}
                        </div>
                    )}
                </>
            )}

            {tab === "storico" && (
                <Card className="p-4">
                    {events.length === 0 ? <Empty label="Nessun invio registrato" /> : (
                        <table className="data-table">
                            <thead><tr>
                                <th>Quando</th><th>Regola</th><th>Canale</th>
                                <th>Destinatario</th><th>Esito</th>
                            </tr></thead>
                            <tbody>
                                {events.map((e) => (
                                    <tr key={e.id} data-testid={`event-${e.id}`}>
                                        <td className="text-xs whitespace-nowrap">{fmtDate(e.created_at)} {(e.created_at || "").slice(11, 16)}</td>
                                        <td className="text-sm">{e.rule_nome}</td>
                                        <td>
                                            <span className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border ${(CANALI_META[e.canale] || {}).color || ""}`}>
                                                {e.canale}
                                            </span>
                                        </td>
                                        <td className="text-xs">{e.destinatario_label || e.destinatario_indirizzo || "—"}</td>
                                        <td>
                                            {e.status === "ok" && <span className="inline-flex items-center gap-1 text-emerald-700 text-xs"><CheckCircle2 size={12} /> Inviata</span>}
                                            {e.status === "skipped" && <span className="text-amber-700 text-xs" title={e.error_message}>⊘ Skipped</span>}
                                            {e.status === "errore" && <span className="text-rose-700 text-xs" title={e.error_message}>✕ Errore</span>}
                                            {e.status === "pending" && <span className="text-slate-500 text-xs">…</span>}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </Card>
            )}

            {editing && <RuleEditor rule={editing} onClose={() => { setEditing(null); loadRules(); }} />}
        </div>
    );
}


function RuleEditor({ rule, onClose }) {
    const [f, setF] = useState({ ...rule });
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
    const toggleCanale = (c) => {
        const cur = f.canali || [];
        set("canali", cur.includes(c) ? cur.filter((x) => x !== c) : [...cur, c]);
    };
    const toggleDest = (d) => {
        const cur = f.destinatari || [];
        set("destinatari", cur.includes(d) ? cur.filter((x) => x !== d) : [...cur, d]);
    };

    const save = async () => {
        try {
            await api.put(`/alert-rules/${rule.id}`, {
                nome: f.nome,
                descrizione: f.descrizione,
                canali: f.canali, destinatari: f.destinatari,
                template_oggetto: f.template_oggetto, template_corpo: f.template_corpo,
                soglia_giorni: f.soglia_giorni ? parseInt(f.soglia_giorni) : undefined,
            });
            toast.success("Regola aggiornata");
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-2xl">
                <DialogHeader><DialogTitle>Modifica regola: {rule.nome}</DialogTitle></DialogHeader>
                <div className="space-y-4 py-2 max-h-[70vh] overflow-y-auto pr-1">
                    <div>
                        <Label>Nome</Label>
                        <Input value={f.nome || ""} onChange={(e) => set("nome", e.target.value)} />
                    </div>
                    <div>
                        <Label>Descrizione</Label>
                        <Textarea rows={2} value={f.descrizione || ""} onChange={(e) => set("descrizione", e.target.value)} />
                    </div>
                    <div>
                        <Label>Canali di invio</Label>
                        <div className="flex gap-2 flex-wrap mt-2">
                            {Object.entries(CANALI_META).map(([c, m]) => {
                                const Icon = m.icon;
                                const active = (f.canali || []).includes(c);
                                return (
                                    <button
                                        key={c}
                                        type="button"
                                        onClick={() => toggleCanale(c)}
                                        className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-sm border rounded transition-colors ${active ? m.color : "bg-white text-slate-500 border-slate-300"}`}
                                        data-testid={`canale-toggle-${c}`}
                                    >
                                        <Icon size={14} /> {m.label}
                                    </button>
                                );
                            })}
                        </div>
                        <p className="text-[10px] text-slate-500 mt-1">SMS/WhatsApp predisposti — richiedono provider Twilio configurato.</p>
                    </div>
                    <div>
                        <Label>Destinatari</Label>
                        <div className="flex gap-2 flex-wrap mt-2">
                            {["cliente", "collaboratore", "collaboratore_sinistri", "admin"].map((d) => {
                                const active = (f.destinatari || []).includes(d);
                                return (
                                    <button
                                        key={d}
                                        type="button"
                                        onClick={() => toggleDest(d)}
                                        className={`px-3 py-1.5 text-sm border rounded transition-colors ${active ? "bg-slate-900 text-white border-slate-900" : "bg-white text-slate-500 border-slate-300"}`}
                                        data-testid={`dest-toggle-${d}`}
                                    >
                                        {d.replace(/_/g, " ")}
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                    {(rule.tipo === "soglia" || rule.schedule_kind === "titolo_scaduto_oltre") && (
                        <div>
                            <Label>Soglia giorni</Label>
                            <Input type="number" value={f.soglia_giorni || ""} onChange={(e) => set("soglia_giorni", e.target.value)} className="w-32" />
                        </div>
                    )}
                    <div>
                        <Label>Oggetto template <span className="text-[10px] text-slate-500">— placeholder: {"{nome}, {numero_polizza}, {numero_sinistro}, {importo_lordo}, {scadenza}, ..."}</span></Label>
                        <Input value={f.template_oggetto || ""} onChange={(e) => set("template_oggetto", e.target.value)} />
                    </div>
                    <div>
                        <Label>Corpo template</Label>
                        <Textarea rows={6} value={f.template_corpo || ""} onChange={(e) => set("template_corpo", e.target.value)} />
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Annulla</Button>
                    <Button onClick={save} className="bg-sky-700 hover:bg-sky-800" data-testid="rule-save-btn">Salva</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
