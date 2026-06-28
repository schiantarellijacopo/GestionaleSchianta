/**
 * Posta — Inbox del collaboratore con smistamento per alias.
 *
 * - Tab "Personale" → email indirizzate al mio alias aziendale
 * - Tab "Condivisa" → email arrivate all'indirizzo generico assicurazioni@…
 *
 * Le email sono popolate dal poller IMAP backend ogni 5 minuti
 * (in attesa di attivazione del polling, le KPI mostrano 0).
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Mail, MailOpen, Users, Inbox, Paperclip, Search, RefreshCw, AlertCircle } from "lucide-react";
import { toast } from "sonner";

const fmtDate = (iso) => {
    if (!iso) return "—";
    try {
        const d = new Date(iso);
        const now = new Date();
        const sameDay = d.toDateString() === now.toDateString();
        if (sameDay) return d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
        return d.toLocaleDateString("it-IT", { day: "2-digit", month: "short" });
    } catch { return iso; }
};

function KpiCard({ icon, label, value, sub, color = "sky", testid }) {
    const colors = {
        sky: "bg-sky-50 text-sky-700 border-sky-200",
        emerald: "bg-emerald-50 text-emerald-700 border-emerald-200",
        amber: "bg-amber-50 text-amber-700 border-amber-200",
        violet: "bg-violet-50 text-violet-700 border-violet-200",
        rose: "bg-rose-50 text-rose-700 border-rose-200",
    };
    return (
        <Card className={`p-4 border ${colors[color]} relative overflow-hidden`} data-testid={testid}>
            <div className="flex items-start justify-between">
                <div>
                    <div className="text-xs font-medium uppercase tracking-wider opacity-70">{label}</div>
                    <div className="text-3xl font-bold mt-1">{value ?? "—"}</div>
                    {sub && <div className="text-[11px] opacity-70 mt-0.5">{sub}</div>}
                </div>
                <div className="opacity-60">{icon}</div>
            </div>
        </Card>
    );
}

export default function Posta() {
    const [tab, setTab] = useState("personale");
    const [stats, setStats] = useState(null);
    const [items, setItems] = useState(null);
    const [q, setQ] = useState("");
    const [syncing, setSyncing] = useState(false);
    const [selected, setSelected] = useState(null);

    const loadStats = async () => {
        try { setStats((await api.get("/email/inbox/stats")).data); } catch { /* ignore */ }
    };
    const loadList = async () => {
        try {
            const r = await api.get("/email/inbox", { params: { categoria: tab, q: q || undefined } });
            setItems(r.data || []);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore caricamento");
            setItems([]);
        }
    };

    useEffect(() => { loadStats(); loadList(); /* eslint-disable-next-line */ }, [tab]);
    const cerca = (e) => { e?.preventDefault?.(); loadList(); };

    const sync = async () => {
        setSyncing(true);
        try {
            // endpoint poller (in attesa di attivazione)
            await api.post("/email/sync");
            await loadStats(); await loadList();
            toast.success("Sincronizzazione completata");
        } catch (e) {
            toast.warning("IMAP non ancora attivo: configura Librerie → Comunicazioni → Posta in arrivo");
        }
        setSyncing(false);
    };

    const apri = async (it) => {
        setSelected(it);
        if (it.non_letta) {
            try { await api.post(`/email/inbox/${it.id}/leggi`); loadStats(); loadList(); } catch { /* ignore */ }
        }
    };

    const pers = stats?.personale || { totale: 0, non_lette: 0 };
    const cond = stats?.condivisa || { totale: 0, non_lette: 0 };

    const cassettaConfigured = useMemo(() => true, []);

    return (
        <div className="space-y-4" data-testid="posta-page">
            <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                    <h1 className="text-2xl font-semibold text-slate-900 flex items-center gap-2">
                        <Inbox className="text-sky-700" size={26} /> Posta
                    </h1>
                    <p className="text-sm text-slate-500">
                        Email aziendali smistate automaticamente in base all'alias destinatario.
                    </p>
                </div>
                <Button onClick={sync} disabled={syncing} variant="outline"
                    className="border-slate-300"
                    data-testid="posta-sync">
                    <RefreshCw size={14} className={`mr-1.5 ${syncing ? "animate-spin" : ""}`} />
                    {syncing ? "Sincronizzo…" : "Sincronizza ora"}
                </Button>
            </div>

            {/* INFOGRAFICA KPI */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                <KpiCard
                    icon={<Mail size={28} />}
                    label="Personali"
                    value={pers.totale}
                    sub={pers.non_lette ? `${pers.non_lette} non lette` : "tutte lette"}
                    color="sky"
                    testid="kpi-personali"
                />
                <KpiCard
                    icon={<Users size={28} />}
                    label="Condivise (tutti)"
                    value={cond.totale}
                    sub={cond.non_lette ? `${cond.non_lette} non lette` : "tutte lette"}
                    color="emerald"
                    testid="kpi-condivise"
                />
                <KpiCard
                    icon={<MailOpen size={28} />}
                    label="Non lette (mie)"
                    value={pers.non_lette + cond.non_lette}
                    sub="da gestire"
                    color="amber"
                    testid="kpi-nonlette"
                />
                <KpiCard
                    icon={<Inbox size={28} />}
                    label="Totale ricevute"
                    value={pers.totale + cond.totale}
                    sub="messaggi visibili"
                    color="violet"
                    testid="kpi-totale"
                />
            </div>

            {/* Banner avviso se inbox vuoto */}
            {items?.length === 0 && stats && (pers.totale + cond.totale) === 0 && (
                <Card className="p-4 border border-amber-200 bg-amber-50 flex items-start gap-3" data-testid="posta-empty-banner">
                    <AlertCircle size={20} className="text-amber-700 flex-shrink-0 mt-0.5" />
                    <div className="flex-1 text-sm">
                        <strong className="text-amber-900">Nessuna email ricevuta ancora.</strong>
                        <p className="text-amber-800 mt-1">
                            La cassetta è configurata in Librerie → Comunicazioni. Il poller IMAP scaricherà le email automaticamente ogni 5 minuti, oppure usa <strong>Sincronizza ora</strong>.
                        </p>
                        {!cassettaConfigured && (
                            <p className="text-amber-800 mt-1.5">
                                ⚠️ La cassetta IMAP non è ancora configurata. Vai in <strong>Librerie → Comunicazioni → Posta in arrivo</strong> e inserisci i dati.
                            </p>
                        )}
                    </div>
                </Card>
            )}

            {/* TAB selector + ricerca */}
            <Card className="border-slate-200 overflow-hidden">
                <div className="px-4 py-2.5 border-b border-slate-200 flex items-center gap-2 flex-wrap">
                    <div className="flex bg-slate-100 rounded-md p-0.5">
                        <button
                            onClick={() => setTab("personale")}
                            className={`px-4 py-1.5 text-sm font-medium rounded transition-colors inline-flex items-center gap-1.5 ${
                                tab === "personale" ? "bg-white shadow-sm text-sky-700" : "text-slate-600 hover:text-slate-800"
                            }`}
                            data-testid="posta-tab-personale"
                        >
                            <Mail size={14} /> Personale {pers.non_lette > 0 && <span className="bg-sky-600 text-white text-[10px] px-1.5 rounded-full font-semibold">{pers.non_lette}</span>}
                        </button>
                        <button
                            onClick={() => setTab("condivisa")}
                            className={`px-4 py-1.5 text-sm font-medium rounded transition-colors inline-flex items-center gap-1.5 ${
                                tab === "condivisa" ? "bg-white shadow-sm text-emerald-700" : "text-slate-600 hover:text-slate-800"
                            }`}
                            data-testid="posta-tab-condivisa"
                        >
                            <Users size={14} /> Condivisa {cond.non_lette > 0 && <span className="bg-emerald-600 text-white text-[10px] px-1.5 rounded-full font-semibold">{cond.non_lette}</span>}
                        </button>
                    </div>
                    <form onSubmit={cerca} className="flex items-center gap-2 ml-auto">
                        <div className="relative">
                            <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400" />
                            <Input
                                placeholder="Cerca oggetto, mittente…"
                                value={q}
                                onChange={(e) => setQ(e.target.value)}
                                className="pl-7 h-8 w-64 text-xs"
                                data-testid="posta-q"
                            />
                        </div>
                    </form>
                </div>

                {/* Lista email */}
                <div className="grid grid-cols-1 md:grid-cols-3 min-h-[400px]">
                    {/* Colonna lista */}
                    <div className="border-r border-slate-100 max-h-[70vh] overflow-y-auto">
                        {items === null && <div className="p-6 text-sm text-slate-500">Caricamento…</div>}
                        {items?.length === 0 && (
                            <div className="p-6 text-sm text-slate-500 text-center">
                                Nessuna email in {tab === "personale" ? "personale" : "condivisa"}
                            </div>
                        )}
                        {items?.map((it) => (
                            <button
                                key={it.id}
                                onClick={() => apri(it)}
                                className={`w-full text-left px-3 py-2.5 border-b border-slate-100 hover:bg-slate-50 transition-colors ${
                                    selected?.id === it.id ? "bg-sky-50" : ""
                                } ${it.non_letta ? "font-medium" : ""}`}
                                data-testid={`posta-item-${it.id}`}
                            >
                                <div className="flex items-center justify-between gap-2">
                                    <span className={`text-xs truncate ${it.non_letta ? "text-slate-900" : "text-slate-600"}`}>
                                        {it.from_name || it.from_address || "?"}
                                    </span>
                                    <span className="text-[10px] text-slate-400 whitespace-nowrap">{fmtDate(it.date)}</span>
                                </div>
                                <div className={`text-sm truncate mt-0.5 ${it.non_letta ? "text-slate-900" : "text-slate-700"}`}>
                                    {it.subject || "(senza oggetto)"}
                                </div>
                                <div className="flex items-center gap-2 mt-0.5">
                                    {it.has_attachments && <Paperclip size={11} className="text-slate-400" />}
                                    {it.anagrafica_id && (
                                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700">Cliente</span>
                                    )}
                                    {it.non_letta && <span className="ml-auto w-2 h-2 bg-sky-500 rounded-full"></span>}
                                </div>
                            </button>
                        ))}
                    </div>

                    {/* Colonna dettaglio */}
                    <div className="md:col-span-2 p-5 max-h-[70vh] overflow-y-auto">
                        {!selected && (
                            <div className="h-full flex items-center justify-center text-slate-400 text-sm flex-col gap-3">
                                <Mail size={40} className="opacity-40" />
                                Seleziona un&apos;email per leggerla
                            </div>
                        )}
                        {selected && <DettaglioEmail email={selected} />}
                    </div>
                </div>
            </Card>
        </div>
    );
}

function DettaglioEmail({ email }) {
    return (
        <div className="space-y-3" data-testid="posta-dettaglio">
            <div className="border-b border-slate-100 pb-3">
                <h2 className="text-lg font-semibold text-slate-900">{email.subject || "(senza oggetto)"}</h2>
                <div className="text-xs text-slate-500 mt-1">
                    <strong>Da:</strong> {email.from_name ? `${email.from_name} <${email.from_address}>` : email.from_address}
                </div>
                <div className="text-xs text-slate-500">
                    <strong>A:</strong> {(email.to_addresses || []).join(", ")}
                </div>
                {(email.cc_addresses || []).length > 0 && (
                    <div className="text-xs text-slate-500">
                        <strong>Cc:</strong> {email.cc_addresses.join(", ")}
                    </div>
                )}
                <div className="text-xs text-slate-400 mt-0.5">{email.date}</div>
            </div>
            {email.anagrafica_id && (
                <div className="bg-emerald-50 border border-emerald-200 rounded p-2 text-xs text-emerald-900 inline-flex items-center gap-2">
                    ✓ Email collegata automaticamente al diario del cliente
                </div>
            )}
            {(email.attachments || []).length > 0 && (
                <div className="flex flex-wrap gap-2">
                    {email.attachments.map((a, i) => (
                        <a key={i}
                            href={`/api/storage/${a.storage_path}`}
                            target="_blank" rel="noreferrer"
                            className="inline-flex items-center gap-1.5 text-xs px-2 py-1 border border-slate-300 rounded hover:bg-slate-50">
                            <Paperclip size={11} /> {a.filename}
                        </a>
                    ))}
                </div>
            )}
            <div
                className="prose prose-sm max-w-none text-slate-800"
                dangerouslySetInnerHTML={{
                    __html: email.body_html || `<pre style="white-space:pre-wrap;font-family:inherit">${(email.body_text || "").replace(/</g, "&lt;")}</pre>`,
                }}
            />
        </div>
    );
}
