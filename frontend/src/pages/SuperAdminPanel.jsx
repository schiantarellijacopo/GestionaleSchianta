import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Building2, Users, CreditCard, Package, Headphones, Plus, Play, Pause, RotateCcw, Loader2, TrendingUp, Send, Activity, Download, Search } from "lucide-react";

const TABS = [
    { id: "agenzie", label: "Agenzie Clienti", icon: Building2 },
    { id: "abbonamenti", label: "Abbonamenti", icon: CreditCard },
    { id: "transazioni", label: "Transazioni", icon: TrendingUp },
    { id: "marketplace", label: "Marketplace", icon: Package },
    { id: "tickets", label: "Ticket Helpdesk", icon: Headphones },
    { id: "logs", label: "Log Piattaforma", icon: Activity },
];

const STATO_COLORS = {
    attiva: "bg-emerald-100 text-emerald-700 border-emerald-200",
    in_prova: "bg-amber-100 text-amber-700 border-amber-200",
    sospesa: "bg-rose-100 text-rose-700 border-rose-200",
    scaduta: "bg-slate-200 text-slate-700 border-slate-300",
    cancellata: "bg-slate-100 text-slate-500 border-slate-200",
    aperto: "bg-amber-100 text-amber-700 border-amber-200",
    in_lavorazione: "bg-sky-100 text-sky-700 border-sky-200",
    risolto: "bg-emerald-100 text-emerald-700 border-emerald-200",
    chiuso: "bg-slate-100 text-slate-500 border-slate-200",
    richiesto: "bg-amber-100 text-amber-700 border-amber-200",
    non_attivo: "bg-slate-100 text-slate-500 border-slate-200",
    rifiutato: "bg-rose-100 text-rose-700 border-rose-200",
};

export default function SuperAdminPanel() {
    const [tab, setTab] = useState("agenzie");
    const [stats, setStats] = useState(null);

    useEffect(() => {
        api.get("/super-admin/stats").then((r) => setStats(r.data)).catch(() => {});
    }, [tab]);

    return (
        <div className="p-4 sm:p-6 max-w-7xl mx-auto" data-testid="super-admin-panel">
            <div className="mb-6">
                <h1 className="text-2xl font-bold text-slate-800 mb-1">Pannello Super Admin</h1>
                <p className="text-sm text-slate-500">Gestione piattaforma SaaS — Agenzie, Licenze, Marketplace, Ticket</p>
                <div className="mt-2 text-xs bg-amber-50 border border-amber-200 rounded-md px-3 py-2 text-amber-800">
                    🔒 <b>Privacy GDPR</b>: per riservatezza commerciale, da questo pannello NON è possibile accedere ai dati sensibili (clienti/polizze/incassi/documenti) delle agenzie tenant.
                </div>
            </div>

            {stats && <StatsRow stats={stats} />}

            <div className="border-b border-slate-200 mb-4 flex gap-1 overflow-x-auto">
                {TABS.map((t) => {
                    const Icon = t.icon;
                    return (
                        <button key={t.id} onClick={() => setTab(t.id)}
                            className={`flex items-center gap-1.5 px-3 py-2 text-sm font-medium transition-colors border-b-2 whitespace-nowrap ${
                                tab === t.id
                                    ? "border-violet-600 text-violet-700"
                                    : "border-transparent text-slate-600 hover:text-slate-900 hover:border-slate-300"
                            }`}
                            data-testid={`sa-tab-${t.id}`}>
                            <Icon size={14} /> {t.label}
                        </button>
                    );
                })}
            </div>

            {tab === "agenzie" && <AgenzieTab />}
            {tab === "abbonamenti" && <AbbonamentiTab />}
            {tab === "transazioni" && <TransazioniTab />}
            {tab === "marketplace" && <MarketplaceTab />}
            {tab === "tickets" && <TicketsTab />}
            {tab === "logs" && <LogsTab />}
        </div>
    );
}

function StatsRow({ stats }) {
    const cards = [
        { label: "Totale Agenzie", val: stats.totale_agenzie, cls: "bg-slate-100 text-slate-800" },
        { label: "Attive", val: stats.attive, cls: "bg-emerald-100 text-emerald-800" },
        { label: "In Prova", val: stats.in_prova, cls: "bg-amber-100 text-amber-800" },
        { label: "Sospese", val: stats.sospese, cls: "bg-rose-100 text-rose-800" },
        { label: "MRR", val: `€ ${stats.mrr_eur?.toFixed(0)}`, cls: "bg-violet-100 text-violet-800" },
        { label: "ARR", val: `€ ${stats.arr_eur?.toFixed(0)}`, cls: "bg-sky-100 text-sky-800" },
    ];
    return (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2 mb-6">
            {cards.map((c) => (
                <div key={c.label} className={`${c.cls} rounded-lg px-3 py-2`}>
                    <div className="text-[10px] uppercase tracking-wider font-semibold opacity-70">{c.label}</div>
                    <div className="text-xl font-bold">{c.val}</div>
                </div>
            ))}
        </div>
    );
}

function AgenzieTab() {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(false);
    const [showNew, setShowNew] = useState(false);

    const load = () => {
        setLoading(true);
        api.get("/super-admin/agenzie").then((r) => setItems(r.data || []))
            .finally(() => setLoading(false));
    };
    useEffect(() => { load(); }, []);

    const azione = async (id, endpoint, msg) => {
        try {
            await api.post(`/super-admin/agenzie/${id}/${endpoint}`);
            toast.success(msg);
            load();
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Errore");
        }
    };

    return (
        <div>
            <div className="flex justify-between items-center mb-3">
                <h2 className="text-sm font-semibold text-slate-700">{items.length} agenzie registrate</h2>
                <button onClick={() => setShowNew(true)}
                    className="text-xs font-semibold px-3 py-1.5 rounded-md bg-violet-600 text-white hover:bg-violet-700 flex items-center gap-1"
                    data-testid="sa-new-agenzia-btn">
                    <Plus size={14} /> Nuova Agenzia
                </button>
            </div>
            {loading && <Loader2 className="animate-spin text-slate-400 mx-auto my-8" />}
            <div className="border border-slate-200 rounded-lg overflow-hidden">
                <table className="w-full text-sm">
                    <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-600">
                        <tr>
                            <th className="text-left px-3 py-2">Agenzia</th>
                            <th className="text-left px-3 py-2">P.IVA</th>
                            <th className="text-left px-3 py-2">Piano</th>
                            <th className="text-left px-3 py-2">Stato</th>
                            <th className="text-right px-3 py-2">Utenti</th>
                            <th className="text-right px-3 py-2">Clienti</th>
                            <th className="text-right px-3 py-2">Polizze</th>
                            <th className="text-right px-3 py-2">€/mese</th>
                            <th className="text-right px-3 py-2">Azioni</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                        {items.map((a) => (
                            <tr key={a.id} className="hover:bg-slate-50" data-testid={`sa-agenzia-${a.id}`}>
                                <td className="px-3 py-2">
                                    <div className="font-medium text-slate-800">{a.ragione_sociale}</div>
                                    <div className="text-[11px] text-slate-500">{a.tipo} · {a.email || "-"}</div>
                                </td>
                                <td className="px-3 py-2 text-slate-600">{a.partita_iva || "-"}</td>
                                <td className="px-3 py-2 uppercase text-xs font-semibold">{a.piano}</td>
                                <td className="px-3 py-2">
                                    <span className={`text-[10px] uppercase font-semibold px-2 py-0.5 rounded border ${STATO_COLORS[a.stato_abbonamento]}`}>
                                        {a.stato_abbonamento}
                                    </span>
                                </td>
                                <td className="px-3 py-2 text-right num">{a.stats?.utenti ?? 0}</td>
                                <td className="px-3 py-2 text-right num">{a.stats?.anagrafiche ?? 0}</td>
                                <td className="px-3 py-2 text-right num">{a.stats?.polizze ?? 0}</td>
                                <td className="px-3 py-2 text-right num">€ {a.prezzo_mensile_eur?.toFixed(2)}</td>
                                <td className="px-3 py-2 text-right space-x-1">
                                    {a.stato_abbonamento === "sospesa" && (
                                        <button onClick={() => azione(a.id, "attiva", "Agenzia attivata")}
                                            title="Riattiva"
                                            className="p-1 text-emerald-600 hover:bg-emerald-50 rounded"
                                            data-testid={`sa-attiva-${a.id}`}>
                                            <Play size={14} />
                                        </button>
                                    )}
                                    {a.stato_abbonamento !== "sospesa" && a.tipo !== "principale" && (
                                        <button onClick={() => azione(a.id, "sospendi", "Agenzia sospesa")}
                                            title="Sospendi"
                                            className="p-1 text-rose-600 hover:bg-rose-50 rounded"
                                            data-testid={`sa-sospendi-${a.id}`}>
                                            <Pause size={14} />
                                        </button>
                                    )}
                                    <button onClick={() => azione(a.id, "estendi-prova", "Prova estesa +30gg")}
                                        title="Estendi prova"
                                        className="p-1 text-sky-600 hover:bg-sky-50 rounded"
                                        data-testid={`sa-estendi-${a.id}`}>
                                        <RotateCcw size={14} />
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            {showNew && <NuovaAgenziaDialog onClose={() => setShowNew(false)} onCreated={() => { setShowNew(false); load(); }} />}
        </div>
    );
}

function NuovaAgenziaDialog({ onClose, onCreated }) {
    const [f, setF] = useState({
        ragione_sociale: "", partita_iva: "", email: "", referente: "",
        piano: "trial", giorni_prova: 30, prezzo_mensile_eur: 99,
        max_utenti: 5, template: "clean",
        admin_email: "", admin_password: "", admin_name: "",
    });
    const [saving, setSaving] = useState(false);
    const save = async (e) => {
        e.preventDefault();
        if (!f.ragione_sociale.trim()) { toast.error("Ragione sociale obbligatoria"); return; }
        setSaving(true);
        try {
            await api.post("/super-admin/agenzie", f);
            toast.success("Agenzia creata!");
            onCreated();
        } catch (err) {
            toast.error(err?.response?.data?.detail || "Errore creazione");
        } finally { setSaving(false); }
    };
    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50">
            <form onSubmit={save} className="bg-white rounded-lg shadow-xl w-full max-w-2xl p-5 max-h-[90vh] overflow-y-auto"
                data-testid="sa-nuova-agenzia-form">
                <h3 className="text-lg font-semibold mb-4">Nuova Agenzia Cliente</h3>
                <div className="grid grid-cols-2 gap-3 text-sm">
                    <FormField label="Ragione Sociale *" value={f.ragione_sociale} onChange={(v) => setF({ ...f, ragione_sociale: v })} testid="sa-form-ragione" />
                    <FormField label="P.IVA" value={f.partita_iva} onChange={(v) => setF({ ...f, partita_iva: v })} testid="sa-form-piva" />
                    <FormField label="Referente" value={f.referente} onChange={(v) => setF({ ...f, referente: v })} testid="sa-form-referente" />
                    <FormField label="Email" value={f.email} onChange={(v) => setF({ ...f, email: v })} testid="sa-form-email" />
                    <div>
                        <label className="text-xs font-semibold text-slate-600 block mb-1">Piano</label>
                        <select value={f.piano} onChange={(e) => setF({ ...f, piano: e.target.value })}
                            className="w-full px-3 py-1.5 text-sm border border-slate-300 rounded-md bg-white">
                            <option value="trial">Trial</option>
                            <option value="starter">Starter</option>
                            <option value="professional">Professional</option>
                            <option value="enterprise">Enterprise</option>
                        </select>
                    </div>
                    <FormField label="Prezzo mensile €" type="number" value={f.prezzo_mensile_eur} onChange={(v) => setF({ ...f, prezzo_mensile_eur: parseFloat(v) || 0 })} testid="sa-form-prezzo" />
                    <FormField label="Max utenti" type="number" value={f.max_utenti} onChange={(v) => setF({ ...f, max_utenti: parseInt(v) || 5 })} testid="sa-form-utenti" />
                    <div>
                        <label className="text-xs font-semibold text-slate-600 block mb-1">Template</label>
                        <select value={f.template} onChange={(e) => setF({ ...f, template: e.target.value })}
                            className="w-full px-3 py-1.5 text-sm border border-slate-300 rounded-md bg-white">
                            <option value="clean">Clean (vuoto)</option>
                            <option value="demo">Demo (con dati fittizi)</option>
                        </select>
                    </div>
                </div>
                <div className="border-t border-slate-100 mt-4 pt-3">
                    <div className="text-xs font-semibold text-slate-500 uppercase mb-2">Utente admin iniziale (opzionale)</div>
                    <div className="grid grid-cols-2 gap-3 text-sm">
                        <FormField label="Nome" value={f.admin_name} onChange={(v) => setF({ ...f, admin_name: v })} testid="sa-form-adminname" />
                        <FormField label="Email admin" value={f.admin_email} onChange={(v) => setF({ ...f, admin_email: v })} testid="sa-form-adminemail" />
                        <FormField label="Password" type="password" value={f.admin_password} onChange={(v) => setF({ ...f, admin_password: v })} testid="sa-form-adminpwd" />
                    </div>
                </div>
                <div className="flex justify-end gap-2 mt-5">
                    <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm border border-slate-300 rounded-md">Annulla</button>
                    <button type="submit" disabled={saving}
                        className="px-3 py-1.5 text-sm bg-violet-600 text-white rounded-md disabled:opacity-60"
                        data-testid="sa-form-submit">
                        {saving ? "Creazione…" : "Crea Agenzia"}
                    </button>
                </div>
            </form>
        </div>
    );
}

function FormField({ label, value, onChange, type = "text", testid }) {
    return (
        <div>
            <label className="text-xs font-semibold text-slate-600 block mb-1">{label}</label>
            <input type={type} value={value} onChange={(e) => onChange(e.target.value)}
                data-testid={testid}
                className="w-full px-3 py-1.5 text-sm border border-slate-300 rounded-md focus:border-violet-500 outline-none" />
        </div>
    );
}

function AbbonamentiTab() {
    const [items, setItems] = useState([]);
    useEffect(() => { api.get("/super-admin/abbonamenti").then((r) => setItems(r.data || [])); }, []);
    return (
        <div className="border border-slate-200 rounded-lg overflow-hidden">
            {items.length === 0 && <div className="p-6 text-center text-slate-500 text-sm">Nessun abbonamento registrato.</div>}
            <table className="w-full text-sm">
                <thead className="bg-slate-50 text-xs uppercase text-slate-600">
                    <tr><th className="text-left px-3 py-2">Agenzia</th><th className="text-left px-3 py-2">Piano</th><th className="text-left px-3 py-2">Stato</th><th className="text-right px-3 py-2">€/mese</th><th className="text-left px-3 py-2">Inizio</th><th className="text-left px-3 py-2">Rinnovo</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                    {items.map((s) => (
                        <tr key={s.id}>
                            <td className="px-3 py-2 font-medium">{s.tenant_ragione_sociale}</td>
                            <td className="px-3 py-2 uppercase">{s.piano}</td>
                            <td className="px-3 py-2"><span className={`text-[10px] font-semibold px-2 py-0.5 rounded border ${STATO_COLORS[s.stato]}`}>{s.stato}</span></td>
                            <td className="px-3 py-2 text-right">€ {s.prezzo_mensile_eur?.toFixed(2)}</td>
                            <td className="px-3 py-2">{s.data_inizio}</td>
                            <td className="px-3 py-2">{s.data_prossimo_rinnovo || "-"}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

function TransazioniTab() {
    const [items, setItems] = useState([]);
    useEffect(() => { api.get("/super-admin/transazioni").then((r) => setItems(r.data || [])); }, []);
    return (
        <div className="border border-slate-200 rounded-lg overflow-hidden">
            {items.length === 0 && <div className="p-6 text-center text-slate-500 text-sm">Nessuna transazione registrata.</div>}
            <table className="w-full text-sm">
                <thead className="bg-slate-50 text-xs uppercase text-slate-600">
                    <tr><th className="text-left px-3 py-2">Data</th><th className="text-left px-3 py-2">Agenzia</th><th className="text-right px-3 py-2">Importo</th><th className="text-left px-3 py-2">Stato</th><th className="text-left px-3 py-2">Metodo</th><th className="text-left px-3 py-2">Descrizione</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                    {items.map((t) => (
                        <tr key={t.id}>
                            <td className="px-3 py-2">{t.data_transazione}</td>
                            <td className="px-3 py-2 font-medium">{t.tenant_ragione_sociale}</td>
                            <td className="px-3 py-2 text-right">€ {t.importo_eur?.toFixed(2)}</td>
                            <td className="px-3 py-2">{t.stato}</td>
                            <td className="px-3 py-2">{t.metodo_pagamento || "-"}</td>
                            <td className="px-3 py-2 text-xs text-slate-600">{t.descrizione || "-"}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

function MarketplaceTab() {
    const [items, setItems] = useState([]);
    const load = () => api.get("/super-admin/marketplace/richieste").then((r) => setItems(r.data || []));
    useEffect(() => { load(); }, []);

    const toggle = async (id, stato) => {
        try {
            await api.patch(`/super-admin/marketplace/richieste/${id}/toggle`, { stato });
            toast.success("Aggiornato");
            load();
        } catch (e) { toast.error(e?.response?.data?.detail || "Errore"); }
    };

    return (
        <div className="border border-slate-200 rounded-lg overflow-hidden">
            {items.length === 0 && <div className="p-6 text-center text-slate-500 text-sm">Nessuna richiesta di attivazione.</div>}
            <table className="w-full text-sm">
                <thead className="bg-slate-50 text-xs uppercase text-slate-600">
                    <tr><th className="text-left px-3 py-2">Data</th><th className="text-left px-3 py-2">Agenzia</th><th className="text-left px-3 py-2">Modulo</th><th className="text-right px-3 py-2">Prezzo</th><th className="text-left px-3 py-2">Stato</th><th className="text-right px-3 py-2">Azioni</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                    {items.map((r) => (
                        <tr key={r.id} data-testid={`sa-marketplace-req-${r.id}`}>
                            <td className="px-3 py-2 text-xs">{new Date(r.created_at).toLocaleDateString("it-IT")}</td>
                            <td className="px-3 py-2 font-medium">{r.tenant_ragione_sociale}</td>
                            <td className="px-3 py-2">{r.module_nome}</td>
                            <td className="px-3 py-2 text-right">€ {r.prezzo_concordato_eur?.toFixed(2)}</td>
                            <td className="px-3 py-2"><span className={`text-[10px] font-semibold px-2 py-0.5 rounded border ${STATO_COLORS[r.stato]}`}>{r.stato}</span></td>
                            <td className="px-3 py-2 text-right">
                                {r.stato !== "attivo" && (
                                    <button onClick={() => toggle(r.id, "attivo")}
                                        className="text-xs px-2 py-1 rounded bg-emerald-600 text-white hover:bg-emerald-700"
                                        data-testid={`sa-toggle-on-${r.id}`}>Attiva</button>
                                )}
                                {r.stato === "attivo" && (
                                    <button onClick={() => toggle(r.id, "non_attivo")}
                                        className="text-xs px-2 py-1 rounded bg-slate-500 text-white hover:bg-slate-600"
                                        data-testid={`sa-toggle-off-${r.id}`}>Disattiva</button>
                                )}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

function LogsTab() {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(false);
    const [actionTypes, setActionTypes] = useState([]);
    const [filter, setFilter] = useState({ q: "", action_type: "", agency_id: "", from_date: "", to_date: "" });
    const [agenzie, setAgenzie] = useState([]);

    const load = () => {
        setLoading(true);
        const params = Object.fromEntries(Object.entries(filter).filter(([, v]) => v));
        api.get("/super-admin/logs", { params })
            .then((r) => setItems(r.data || []))
            .finally(() => setLoading(false));
    };
    useEffect(() => {
        api.get("/super-admin/logs/action-types").then((r) => setActionTypes(r.data || []));
        api.get("/super-admin/agenzie").then((r) => setAgenzie(r.data || []));
        load();
    }, []);

    const exportCsv = async () => {
        const params = Object.fromEntries(Object.entries(filter).filter(([k, v]) => v && k !== "q"));
        try {
            const res = await api.get("/super-admin/logs/export/csv", { params, responseType: "blob" });
            const url = URL.createObjectURL(res.data);
            const a = document.createElement("a");
            a.href = url;
            a.download = `super_admin_logs_${new Date().toISOString().slice(0, 10)}.csv`;
            a.click();
            URL.revokeObjectURL(url);
            toast.success("Log esportato");
        } catch { toast.error("Errore export"); }
    };

    return (
        <div>
            <div className="grid grid-cols-1 md:grid-cols-5 gap-2 mb-3">
                <div className="relative md:col-span-2">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                    <input type="text" value={filter.q}
                        onChange={(e) => setFilter({ ...filter, q: e.target.value })}
                        placeholder="Cerca per agenzia, email, dettagli..."
                        className="w-full pl-9 pr-3 py-1.5 text-sm border border-slate-300 rounded-md"
                        data-testid="sa-logs-search" />
                </div>
                <select value={filter.action_type}
                    onChange={(e) => setFilter({ ...filter, action_type: e.target.value })}
                    className="px-3 py-1.5 text-sm border border-slate-300 rounded-md bg-white"
                    data-testid="sa-logs-action-filter">
                    <option value="">Tutte le azioni</option>
                    {actionTypes.map((a) => <option key={a.code} value={a.code}>{a.label}</option>)}
                </select>
                <select value={filter.agency_id}
                    onChange={(e) => setFilter({ ...filter, agency_id: e.target.value })}
                    className="px-3 py-1.5 text-sm border border-slate-300 rounded-md bg-white"
                    data-testid="sa-logs-agency-filter">
                    <option value="">Tutte le agenzie</option>
                    {agenzie.map((a) => <option key={a.id} value={a.id}>{a.ragione_sociale}</option>)}
                </select>
                <div className="flex gap-1">
                    <button onClick={load}
                        className="flex-1 text-xs font-semibold px-3 py-1.5 rounded-md bg-slate-800 text-white hover:bg-slate-900"
                        data-testid="sa-logs-apply-btn">Filtra</button>
                    <button onClick={exportCsv}
                        className="text-xs font-semibold px-3 py-1.5 rounded-md border border-emerald-600 text-emerald-700 hover:bg-emerald-50 flex items-center gap-1"
                        data-testid="sa-logs-export-btn">
                        <Download size={12} /> CSV
                    </button>
                </div>
            </div>
            {loading && <Loader2 className="animate-spin text-slate-400 mx-auto my-8" />}
            <div className="border border-slate-200 rounded-lg overflow-hidden">
                <table className="w-full text-sm">
                    <thead className="bg-slate-50 text-xs uppercase text-slate-600">
                        <tr>
                            <th className="text-left px-3 py-2">Timestamp</th>
                            <th className="text-left px-3 py-2">Super Admin</th>
                            <th className="text-left px-3 py-2">Azione</th>
                            <th className="text-left px-3 py-2">Agenzia Target</th>
                            <th className="text-left px-3 py-2">IP</th>
                            <th className="text-left px-3 py-2">Dettagli</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                        {items.length === 0 && !loading && (
                            <tr><td colSpan={6} className="text-center py-6 text-slate-500 text-sm">Nessun log presente.</td></tr>
                        )}
                        {items.map((l) => (
                            <tr key={l.id} className="hover:bg-slate-50" data-testid={`sa-log-${l.id}`}>
                                <td className="px-3 py-2 text-xs font-mono text-slate-600">
                                    {new Date(l.timestamp).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                                </td>
                                <td className="px-3 py-2 text-xs">{l.super_admin_email || "-"}</td>
                                <td className="px-3 py-2">
                                    <span className="text-[10px] font-mono uppercase tracking-wider bg-violet-100 text-violet-800 px-1.5 py-0.5 rounded">
                                        {l.action_type}
                                    </span>
                                    <div className="text-[11px] text-slate-500 mt-0.5">{l.action_label}</div>
                                </td>
                                <td className="px-3 py-2 text-xs">{l.target_agency_name || "-"}</td>
                                <td className="px-3 py-2 text-xs font-mono text-slate-500">{l.ip_address || "-"}</td>
                                <td className="px-3 py-2 text-xs text-slate-600">{l.details || "-"}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}


function TicketsTab() {
    const [items, setItems] = useState([]);
    const [selected, setSelected] = useState(null);
    const [reply, setReply] = useState("");
    const [msgs, setMsgs] = useState([]);

    const load = () => api.get("/super-admin/tickets").then((r) => setItems(r.data || []));
    useEffect(() => { load(); }, []);

    const openDetail = async (t) => {
        setSelected(t);
        const res = await api.get(`/super-admin/tickets/${t.id}`);
        setMsgs(res.data.messages || []);
    };

    const rispondi = async (stato) => {
        if (!reply.trim()) { toast.error("Scrivi una risposta"); return; }
        try {
            await api.post(`/super-admin/tickets/${selected.id}/rispondi`, { messaggio: reply, stato });
            toast.success("Risposta inviata");
            setReply("");
            const res = await api.get(`/super-admin/tickets/${selected.id}`);
            setMsgs(res.data.messages || []);
            load();
        } catch (e) { toast.error(e?.response?.data?.detail || "Errore"); }
    };

    return (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="md:col-span-1 border border-slate-200 rounded-lg overflow-hidden max-h-[70vh] overflow-y-auto">
                {items.length === 0 && <div className="p-6 text-center text-slate-500 text-sm">Nessun ticket aperto.</div>}
                {items.map((t) => (
                    <button key={t.id} onClick={() => openDetail(t)}
                        className={`w-full text-left px-3 py-2 border-b border-slate-100 hover:bg-slate-50 ${selected?.id === t.id ? "bg-sky-50" : ""}`}
                        data-testid={`sa-ticket-${t.numero}`}>
                        <div className="flex items-center justify-between mb-1">
                            <span className="text-[10px] font-mono text-slate-500">{t.numero}</span>
                            <span className={`text-[10px] uppercase font-semibold px-1.5 py-0.5 rounded border ${STATO_COLORS[t.stato]}`}>{t.stato}</span>
                        </div>
                        <div className="text-sm font-semibold text-slate-800 truncate">{t.oggetto}</div>
                        <div className="text-[11px] text-slate-500 mt-0.5">{t.tenant_ragione_sociale} · {t.priorita}</div>
                    </button>
                ))}
            </div>
            <div className="md:col-span-2 border border-slate-200 rounded-lg p-4">
                {!selected && <div className="text-center text-slate-500 text-sm py-10">Seleziona un ticket dalla lista</div>}
                {selected && (
                    <div>
                        <div className="mb-3">
                            <div className="text-xs text-slate-500 font-mono">{selected.numero} · {selected.tenant_ragione_sociale}</div>
                            <h3 className="text-lg font-semibold">{selected.oggetto}</h3>
                            <div className="text-xs text-slate-500 uppercase mt-1">{selected.categoria} · Priorità {selected.priorita}</div>
                        </div>
                        <div className="space-y-3 max-h-[40vh] overflow-y-auto mb-3">
                            {msgs.map((m) => (
                                <div key={m.id} className={`p-3 rounded-lg text-sm ${m.autore_ruolo === "super_admin" ? "bg-violet-50 border border-violet-200" : "bg-slate-50 border border-slate-200"}`}>
                                    <div className="text-[10px] uppercase font-semibold text-slate-500 mb-1">
                                        {m.autore_ruolo === "super_admin" ? "Super Admin" : m.autore_email} · {new Date(m.created_at).toLocaleString("it-IT")}
                                    </div>
                                    <div className="whitespace-pre-wrap text-slate-800">{m.messaggio}</div>
                                </div>
                            ))}
                        </div>
                        <textarea rows={3} value={reply} onChange={(e) => setReply(e.target.value)}
                            placeholder="Scrivi una risposta…"
                            className="w-full px-3 py-2 text-sm border border-slate-300 rounded-md focus:border-violet-500 outline-none"
                            data-testid="sa-reply-input" />
                        <div className="flex gap-2 justify-end mt-2">
                            <button onClick={() => rispondi("in_lavorazione")}
                                className="text-xs font-semibold px-3 py-1.5 rounded-md bg-sky-600 text-white hover:bg-sky-700 flex items-center gap-1"
                                data-testid="sa-reply-inlavor">
                                <Send size={12} /> Rispondi (in lavorazione)
                            </button>
                            <button onClick={() => rispondi("risolto")}
                                className="text-xs font-semibold px-3 py-1.5 rounded-md bg-emerald-600 text-white hover:bg-emerald-700 flex items-center gap-1"
                                data-testid="sa-reply-risolto">
                                <Send size={12} /> Rispondi e Risolvi
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
