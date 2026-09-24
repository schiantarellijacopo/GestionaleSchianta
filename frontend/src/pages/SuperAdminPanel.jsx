import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Building2, Users, CreditCard, Package, Headphones, Plus, Play, Pause, RotateCcw, Loader2, TrendingUp, Send, Activity, Download, Search, Pencil, Flame, AlertTriangle, Globe, ArrowRightLeft, Check, X, Copy, KeyRound, BookMarked, Coins, ListChecks, Trash2, Wrench } from "lucide-react";

const TABS = [
    { id: "agenzie", label: "Agenzie Clienti", icon: Building2 },
    { id: "biblioteca", label: "Biblioteca & Schede Calcolo", icon: BookMarked, route: "/super-admin/biblioteca" },
    { id: "scambi", label: "Scambi Dati", icon: ArrowRightLeft },
    { id: "abbonamenti", label: "Abbonamenti", icon: CreditCard },
    { id: "transazioni", label: "Transazioni", icon: TrendingUp },
    { id: "marketplace", label: "Marketplace", icon: Package },
    { id: "chiavi", label: "Chiavi API", icon: KeyRound },
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
    const navigate = useNavigate();
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
                        <button key={t.id} onClick={() => t.route ? navigate(t.route) : setTab(t.id)}
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
            {tab === "scambi" && <ScambiTab />}
            {tab === "abbonamenti" && <AbbonamentiTab />}
            {tab === "transazioni" && <TransazioniTab />}
            {tab === "marketplace" && <MarketplaceTab />}
            {tab === "chiavi" && <ChiaviApiTab />}
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
    const [editAgenzia, setEditAgenzia] = useState(null);
    const [resetAgenzia, setResetAgenzia] = useState(null);
    const [eliminaAgenzia, setEliminaAgenzia] = useState(null);
    const [dominiAgenzia, setDominiAgenzia] = useState(null);
    const [creditoAgenzia, setCreditoAgenzia] = useState(null);
    const [showListino, setShowListino] = useState(false);
    const [bonificando, setBonificando] = useState(false);

    const bonificaScadenzeGlobale = async () => {
        setBonificando(true);
        try {
            const prev = await api.post("/manutenzione/correggi-scadenze-titoli?dry_run=true&tutti_tenant=true");
            const { duplicati_eliminati = 0, scadenze_corrette = 0 } = prev.data || {};
            if (!duplicati_eliminati && !scadenze_corrette) {
                toast.info("Nessuna correzione necessaria: scadenze e doppioni sono già a posto su tutte le agenzie.");
                return;
            }
            const ok = window.confirm(
                "Bonifica titoli importati — TUTTE le agenzie:\n\n" +
                `• Doppioni "da incassare" da eliminare: ${duplicati_eliminati}\n` +
                `• Scadenze da ricalcolare (effetto + frazionamento): ${scadenze_corrette}\n\n` +
                "I titoli già incassati/coperti NON vengono toccati. Procedere?",
            );
            if (!ok) return;
            const res = await api.post("/manutenzione/correggi-scadenze-titoli?tutti_tenant=true");
            const r = res.data || {};
            toast.success(`Bonifica globale completata: ${r.duplicati_eliminati} doppioni eliminati, ${r.scadenze_corrette} scadenze corrette`);
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Errore durante la bonifica");
        } finally {
            setBonificando(false);
        }
    };

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
            {/* Demo Credentials — quick reference per QA/test */}
            <div className="mb-4 border border-sky-200 bg-sky-50/60 rounded-lg p-3" data-testid="sa-demo-credentials">
                <div className="flex items-center gap-2 mb-2">
                    <Users size={14} className="text-sky-700" />
                    <div className="text-xs font-semibold text-sky-800 uppercase tracking-wider">Account Demo — tenant principale (assicura)</div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-2">
                    {[
                        { role: "Admin", email: "admin@assicura.it", pass: "Admin123!", color: "violet" },
                        { role: "Collaboratore", email: "collaboratore@assicura.it", pass: "Collab123!", color: "sky" },
                        { role: "Dipendente", email: "dipendente@assicura.it", pass: "Dipendente123!", color: "amber" },
                        { role: "Cliente", email: "cliente@assicura.it", pass: "Cliente123!", color: "emerald" },
                    ].map((c) => (
                        <div key={c.email} className="bg-white border border-slate-200 rounded-md p-2 text-xs flex items-start gap-2"
                            data-testid={`demo-cred-${c.role.toLowerCase()}`}>
                            <span className={`inline-block text-[9px] uppercase font-semibold px-1.5 py-0.5 rounded text-${c.color}-700 bg-${c.color}-100`}>{c.role}</span>
                            <div className="flex-1 min-w-0">
                                <button type="button" onClick={() => { navigator.clipboard.writeText(c.email); toast.success("Email copiata"); }}
                                    className="font-mono text-slate-700 truncate block hover:text-violet-700 text-left"
                                    title="Click per copiare">
                                    {c.email}
                                </button>
                                <button type="button" onClick={() => { navigator.clipboard.writeText(c.pass); toast.success("Password copiata"); }}
                                    className="font-mono text-slate-500 truncate block hover:text-violet-700 text-left"
                                    title="Click per copiare">
                                    🔑 {c.pass}
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            <div className="flex justify-between items-center mb-3">
                <h2 className="text-sm font-semibold text-slate-700">{items.length} agenzie registrate</h2>
                <div className="flex items-center gap-2">
                    <button onClick={bonificaScadenzeGlobale} disabled={bonificando}
                        className="text-xs font-semibold px-3 py-1.5 rounded-md bg-amber-100 text-amber-800 hover:bg-amber-200 disabled:opacity-50 flex items-center gap-1"
                        title="Corregge scadenze errate (= effetto) e rimuove i doppioni da incassare su TUTTE le agenzie"
                        data-testid="sa-bonifica-scadenze-btn">
                        {bonificando ? <Loader2 size={14} className="animate-spin" /> : <Wrench size={14} />} Correggi scadenze (tutte le agenzie)
                    </button>
                    <button onClick={() => setShowListino(true)}
                        className="text-xs font-semibold px-3 py-1.5 rounded-md bg-slate-100 text-slate-700 hover:bg-slate-200 flex items-center gap-1"
                        data-testid="sa-listino-openapi-btn">
                        <ListChecks size={14} /> Listino OpenAPI
                    </button>
                    <button onClick={() => setShowNew(true)}
                        className="text-xs font-semibold px-3 py-1.5 rounded-md bg-violet-600 text-white hover:bg-violet-700 flex items-center gap-1"
                        data-testid="sa-new-agenzia-btn">
                        <Plus size={14} /> Nuova Agenzia
                    </button>
                </div>
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
                            <th className="text-right px-3 py-2">Credito API</th>
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
                                <td className="px-3 py-2 text-right num" data-testid={`sa-credito-${a.id}`}>
                                    {a.openapi_credito_eur === null || a.openapi_credito_eur === undefined
                                        ? <span className="text-[11px] text-slate-400">non attivo</span>
                                        : <span className={`font-semibold ${a.openapi_credito_eur > 5 ? "text-emerald-700" : "text-rose-600"}`}>€ {Number(a.openapi_credito_eur).toFixed(2)}</span>}
                                </td>
                                <td className="px-3 py-2 text-right space-x-1">
                                    <button onClick={() => setCreditoAgenzia(a)}
                                        title="Credito OpenAPI (imposta/ricarica)"
                                        className="p-1 text-amber-600 hover:bg-amber-50 rounded"
                                        data-testid={`sa-credito-btn-${a.id}`}>
                                        <Coins size={14} />
                                    </button>
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
                                    <button onClick={() => setDominiAgenzia(a)}
                                        title="Dominio & credenziali dedicate"
                                        className="p-1 text-violet-600 hover:bg-violet-50 rounded"
                                        data-testid={`sa-dominio-${a.id}`}>
                                        <Globe size={14} />
                                    </button>
                                    <button onClick={() => setEditAgenzia(a)}
                                        title="Modifica agenzia"
                                        className="p-1 text-slate-600 hover:bg-slate-100 rounded"
                                        data-testid={`sa-edit-${a.id}`}>
                                        <Pencil size={14} />
                                    </button>
                                    <button onClick={() => setResetAgenzia(a)}
                                        title="🔥 Reset dati tenant"
                                        className="p-1 text-rose-600 hover:bg-rose-50 rounded"
                                        data-testid={`sa-reset-${a.id}`}>
                                        <Flame size={14} />
                                    </button>
                                    <button onClick={() => azione(a.id, "estendi-prova", "Prova estesa +30gg")}
                                        title="Estendi prova"
                                        className="p-1 text-sky-600 hover:bg-sky-50 rounded"
                                        data-testid={`sa-estendi-${a.id}`}>
                                        <RotateCcw size={14} />
                                    </button>
                                    <button onClick={() => setEliminaAgenzia(a)}
                                        title="🗑️ Elimina definitivamente"
                                        className="p-1 text-rose-700 hover:bg-rose-100 rounded"
                                        data-testid={`sa-elimina-${a.id}`}>
                                        <Trash2 size={14} />
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            {showNew && <NuovaAgenziaDialog onClose={() => setShowNew(false)} onCreated={() => { setShowNew(false); load(); }} />}
            {editAgenzia && <EditAgenziaDialog agenzia={editAgenzia} onClose={() => setEditAgenzia(null)} onSaved={() => { setEditAgenzia(null); load(); }} />}
            {resetAgenzia && <ResetDatiDialog agenzia={resetAgenzia} onClose={() => setResetAgenzia(null)} onDone={() => { setResetAgenzia(null); load(); }} />}
            {eliminaAgenzia && <EliminaDefinitivaDialog agenzia={eliminaAgenzia} onClose={() => setEliminaAgenzia(null)} onDone={() => { setEliminaAgenzia(null); load(); }} />}
            {dominiAgenzia && <DominiCredenzialiDialog agenzia={dominiAgenzia} onClose={() => { setDominiAgenzia(null); load(); }} />}
            {creditoAgenzia && <CreditoOpenApiDialog agenzia={creditoAgenzia} onSaved={load} onClose={() => { setCreditoAgenzia(null); load(); }} />}
            {showListino && <ListinoOpenApiDialog onClose={() => setShowListino(false)} />}
        </div>
    );
}

function CreditoOpenApiDialog({ agenzia, onClose, onSaved }) {
    const [importo, setImporto] = useState("");
    const [modo, setModo] = useState("add");
    const [saving, setSaving] = useState(false);
    const [storico, setStorico] = useState(null);
    const attuale = agenzia.openapi_credito_eur;

    const loadStorico = () => {
        api.get(`/super-admin/agenzie/${agenzia.id}/openapi-storico`).then((r) => setStorico(r.data)).catch(() => setStorico(null));
    };
    useEffect(() => { loadStorico(); }, []);

    const salva = async () => {
        const val = parseFloat(String(importo).replace(",", "."));
        if (isNaN(val) || val < 0) { toast.error("Importo non valido"); return; }
        setSaving(true);
        try {
            const r = await api.post(`/super-admin/agenzie/${agenzia.id}/openapi-credito`, { importo: val, modo });
            toast.success(`Credito aggiornato: € ${Number(r.data.credito_eur).toFixed(2)}`);
            setImporto("");
            loadStorico();
            onSaved?.();
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Errore");
        } finally { setSaving(false); }
    };

    const fmtDt = (s) => s ? String(s).slice(0, 16).replace("T", " ") : "";

    return (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" data-testid="sa-credito-dialog">
            <div className="bg-white rounded-xl p-6 max-w-lg w-full max-h-[90vh] overflow-y-auto">
                <h3 className="font-semibold text-lg mb-1 flex items-center gap-2"><Coins size={18} className="text-amber-600" /> Credito OpenAPI</h3>
                <p className="text-sm text-slate-600 mb-4">{agenzia.ragione_sociale}</p>
                <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 mb-4 text-sm flex items-center justify-between">
                    <span>Credito attuale:{" "}
                        <span className="font-semibold">
                            {(storico?.credito_eur ?? attuale) === null || (storico?.credito_eur ?? attuale) === undefined ? "non attivo" : `€ ${Number(storico?.credito_eur ?? attuale).toFixed(2)}`}
                        </span>
                    </span>
                    {storico && (
                        <span className="text-[11px] text-slate-500">
                            Ricaricato: <b className="text-emerald-700">€{Number(storico.totale_ricaricato || 0).toFixed(2)}</b>
                            {" · "}Consumato: <b className="text-rose-600">€{Number(storico.totale_consumato || 0).toFixed(2)}</b>
                        </span>
                    )}
                </div>
                <div className="space-y-3">
                    <div className="flex gap-2">
                        <button onClick={() => setModo("add")} data-testid="sa-credito-modo-add"
                            className={`flex-1 text-sm px-3 py-2 rounded-md border ${modo === "add" ? "bg-emerald-600 text-white border-emerald-600" : "bg-white text-slate-600 border-slate-300"}`}>
                            Aggiungi (ricarica)
                        </button>
                        <button onClick={() => setModo("set")} data-testid="sa-credito-modo-set"
                            className={`flex-1 text-sm px-3 py-2 rounded-md border ${modo === "set" ? "bg-sky-600 text-white border-sky-600" : "bg-white text-slate-600 border-slate-300"}`}>
                            Imposta (saldo esatto)
                        </button>
                    </div>
                    <div className="flex items-end gap-2">
                        <div className="flex-1">
                            <label className="text-xs text-slate-500">Importo €</label>
                            <input type="number" step="0.01" min="0" value={importo} onChange={(e) => setImporto(e.target.value)}
                                className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm" placeholder="es. 100.00"
                                data-testid="sa-credito-importo" />
                        </div>
                        <button onClick={salva} disabled={saving} className="text-sm px-4 py-2 rounded-md bg-amber-600 text-white hover:bg-amber-700 whitespace-nowrap" data-testid="sa-credito-salva">
                            {saving ? "…" : "Salva"}
                        </button>
                    </div>
                </div>

                {/* STORICO */}
                <div className="mt-5 border-t border-slate-200 pt-4" data-testid="sa-credito-storico">
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <div className="text-[10px] uppercase font-semibold text-emerald-700 mb-1">Ricariche</div>
                            {!storico?.ricariche?.length ? (
                                <div className="text-xs text-slate-400">Nessuna ricarica.</div>
                            ) : (
                                <div className="space-y-1 max-h-40 overflow-y-auto">
                                    {storico.ricariche.map((r, i) => (
                                        <div key={i} className="text-xs flex justify-between border-b border-slate-100 pb-1">
                                            <span className="text-slate-500">{fmtDt(r.data)}<div className="text-[10px] text-slate-400">{r.modo === "set" ? "imposta" : "ricarica"} · {r.by || "—"}</div></span>
                                            <span className={`font-semibold ${r.importo >= 0 ? "text-emerald-700" : "text-rose-600"}`}>{r.importo >= 0 ? "+" : ""}{Number(r.importo).toFixed(2)}€</span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                        <div>
                            <div className="text-[10px] uppercase font-semibold text-rose-600 mb-1">Consumi (estrazioni)</div>
                            {!storico?.movimenti?.length ? (
                                <div className="text-xs text-slate-400">Nessun consumo.</div>
                            ) : (
                                <div className="space-y-1 max-h-40 overflow-y-auto">
                                    {storico.movimenti.map((m, i) => (
                                        <div key={i} className="text-xs flex justify-between border-b border-slate-100 pb-1">
                                            <span className="text-slate-500">{fmtDt(m.data)}<div className="text-[10px] text-slate-400">{m.operazione}</div></span>
                                            <span className="font-semibold text-rose-600">{Number(m.importo).toFixed(2)}€</span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                <div className="flex justify-end gap-2 mt-5">
                    <button onClick={onClose} className="text-sm px-4 py-2 rounded-md border border-slate-300 text-slate-600">Chiudi</button>
                </div>
            </div>
        </div>
    );
}

function ListinoOpenApiDialog({ onClose }) {
    const [costi, setCosti] = useState(null);
    const [labels, setLabels] = useState({});
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        api.get("/super-admin/openapi-listino").then((r) => { setCosti(r.data.costi || {}); setLabels(r.data.labels || {}); });
    }, []);

    const salva = async () => {
        setSaving(true);
        try {
            const clean = {};
            Object.entries(costi).forEach(([k, v]) => { clean[k] = parseFloat(String(v).replace(",", ".")) || 0; });
            const r = await api.put("/super-admin/openapi-listino", { costi: clean });
            setCosti(r.data.costi);
            toast.success("Listino aggiornato");
            onClose();
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Errore");
        } finally { setSaving(false); }
    };

    return (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" data-testid="sa-listino-dialog">
            <div className="bg-white rounded-xl p-6 max-w-md w-full">
                <h3 className="font-semibold text-lg mb-1 flex items-center gap-2"><ListChecks size={18} className="text-slate-600" /> Listino costi OpenAPI</h3>
                <p className="text-sm text-slate-600 mb-4">Costo per singola estrazione (scalato dal credito dell'agenzia).</p>
                {!costi ? <Loader2 className="animate-spin text-slate-400 mx-auto my-6" /> : (
                    <div className="space-y-2">
                        {Object.keys(costi).map((k) => (
                            <div key={k} className="flex items-center justify-between gap-3">
                                <label className="text-sm text-slate-700">{labels[k] || k}</label>
                                <div className="flex items-center gap-1">
                                    <span className="text-slate-400 text-sm">€</span>
                                    <input type="number" step="0.01" min="0" value={costi[k]}
                                        onChange={(e) => setCosti((p) => ({ ...p, [k]: e.target.value }))}
                                        className="w-24 border border-slate-300 rounded-md px-2 py-1 text-sm text-right"
                                        data-testid={`sa-listino-${k}`} />
                                </div>
                            </div>
                        ))}
                    </div>
                )}
                <div className="flex justify-end gap-2 mt-5">
                    <button onClick={onClose} className="text-sm px-4 py-2 rounded-md border border-slate-300 text-slate-600">Annulla</button>
                    <button onClick={salva} disabled={saving || !costi} className="text-sm px-4 py-2 rounded-md bg-slate-800 text-white hover:bg-slate-900" data-testid="sa-listino-salva">
                        {saving ? "Salvataggio…" : "Salva listino"}
                    </button>
                </div>
            </div>
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

function EditAgenziaDialog({ agenzia, onClose, onSaved }) {
    const [f, setF] = useState({
        ragione_sociale: agenzia.ragione_sociale || "",
        partita_iva: agenzia.partita_iva || "",
        codice_fiscale: agenzia.codice_fiscale || "",
        referente: agenzia.referente || "",
        email: agenzia.email || "",
        telefono: agenzia.telefono || "",
        indirizzo: agenzia.indirizzo || "",
        citta: agenzia.citta || "",
        provincia: agenzia.provincia || "",
        piano: agenzia.piano || "trial",
        stato_abbonamento: agenzia.stato_abbonamento || "in_prova",
        prezzo_mensile_eur: agenzia.prezzo_mensile_eur ?? 99,
        max_utenti: agenzia.max_utenti ?? 5,
        note: agenzia.note || "",
    });
    const [saving, setSaving] = useState(false);

    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const save = async (e) => {
        e.preventDefault();
        setSaving(true);
        try {
            const body = { ...f };
            body.prezzo_mensile_eur = parseFloat(body.prezzo_mensile_eur) || 0;
            body.max_utenti = parseInt(body.max_utenti) || 1;
            await api.patch(`/super-admin/agenzie/${agenzia.id}`, body);
            toast.success("Agenzia aggiornata");
            onSaved();
        } catch (err) {
            toast.error(err.response?.data?.detail || "Errore aggiornamento");
        } finally { setSaving(false); }
    };

    return (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
            <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full max-h-[92vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
                <form onSubmit={save} className="p-6">
                    <h3 className="text-lg font-semibold mb-1">Modifica Agenzia</h3>
                    <p className="text-xs text-slate-500 mb-4">Tenant ID: <span className="font-mono">{agenzia.id}</span> · Tipo: <b>{agenzia.tipo}</b></p>

                    <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-2 mt-2">Anagrafica</div>
                    <div className="grid grid-cols-2 gap-3">
                        <FormField label="Ragione sociale *" value={f.ragione_sociale} onChange={(v) => set("ragione_sociale", v)} testid="ea-ragione" />
                        <FormField label="Referente" value={f.referente} onChange={(v) => set("referente", v)} testid="ea-referente" />
                        <FormField label="P.IVA" value={f.partita_iva} onChange={(v) => set("partita_iva", v)} testid="ea-piva" />
                        <FormField label="Codice fiscale" value={f.codice_fiscale} onChange={(v) => set("codice_fiscale", v)} testid="ea-cf" />
                        <FormField label="Email" value={f.email} onChange={(v) => set("email", v)} testid="ea-email" />
                        <FormField label="Telefono" value={f.telefono} onChange={(v) => set("telefono", v)} testid="ea-tel" />
                        <FormField label="Indirizzo" value={f.indirizzo} onChange={(v) => set("indirizzo", v)} testid="ea-indirizzo" />
                        <div className="grid grid-cols-2 gap-2">
                            <FormField label="Città" value={f.citta} onChange={(v) => set("citta", v)} testid="ea-citta" />
                            <FormField label="Prov." value={f.provincia} onChange={(v) => set("provincia", v.toUpperCase())} testid="ea-prov" />
                        </div>
                    </div>

                    <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-2 mt-4">Abbonamento</div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="text-xs font-semibold text-slate-600 block mb-1">Piano</label>
                            <select value={f.piano} onChange={(e) => set("piano", e.target.value)}
                                data-testid="ea-piano"
                                className="w-full px-3 py-1.5 text-sm border border-slate-300 rounded-md">
                                <option value="trial">Trial</option>
                                <option value="starter">Starter</option>
                                <option value="pro">Pro</option>
                                <option value="enterprise">Enterprise</option>
                                <option value="custom">Custom</option>
                            </select>
                        </div>
                        <div>
                            <label className="text-xs font-semibold text-slate-600 block mb-1">Stato</label>
                            <select value={f.stato_abbonamento} onChange={(e) => set("stato_abbonamento", e.target.value)}
                                data-testid="ea-stato"
                                className="w-full px-3 py-1.5 text-sm border border-slate-300 rounded-md">
                                <option value="in_prova">In prova</option>
                                <option value="attiva">Attiva</option>
                                <option value="sospesa">Sospesa</option>
                                <option value="scaduta">Scaduta</option>
                                <option value="cancellata">Cancellata</option>
                            </select>
                        </div>
                        <FormField label="Prezzo €/mese" value={f.prezzo_mensile_eur} onChange={(v) => set("prezzo_mensile_eur", v)} type="number" testid="ea-prezzo" />
                        <FormField label="Max utenti" value={f.max_utenti} onChange={(v) => set("max_utenti", v)} type="number" testid="ea-max-utenti" />
                    </div>

                    <div className="mt-4">
                        <label className="text-xs font-semibold text-slate-600 block mb-1">Note interne</label>
                        <textarea value={f.note} onChange={(e) => set("note", e.target.value)}
                            data-testid="ea-note"
                            rows={2}
                            className="w-full px-3 py-1.5 text-sm border border-slate-300 rounded-md" />
                    </div>

                    <div className="flex justify-end gap-2 mt-6 pt-4 border-t border-slate-200">
                        <button type="button" onClick={onClose}
                            className="px-4 py-2 text-sm border border-slate-300 rounded-md hover:bg-slate-50" data-testid="ea-cancel">
                            Annulla
                        </button>
                        <button type="submit" disabled={saving}
                            className="px-4 py-2 text-sm bg-violet-600 hover:bg-violet-700 text-white rounded-md disabled:opacity-50" data-testid="ea-save">
                            {saving ? "Salvataggio…" : "Salva modifiche"}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}

function ResetDatiDialog({ agenzia, onClose, onDone }) {
    const [password, setPassword] = useState("");
    const [conferma, setConferma] = useState("");
    const [mantieniAdmin, setMantieniAdmin] = useState(true);
    const [confirmText, setConfirmText] = useState("");
    const [step, setStep] = useState(1);   // 1=warning, 2=inputs, 3=in corso
    const [saving, setSaving] = useState(false);
    const [result, setResult] = useState(null);

    const canProceed = confirmText === "RESET DATI" && password.length > 0 && conferma === agenzia.ragione_sociale;

    const doReset = async () => {
        if (!canProceed) return;
        setSaving(true);
        try {
            const r = await api.post(`/super-admin/agenzie/${agenzia.id}/reset-dati`, {
                password_custode: password,
                mantieni_admin: mantieniAdmin,
                conferma_ragione_sociale: conferma,
            });
            setResult(r.data);
            setStep(3);
            toast.success(`Reset completato: ${r.data.totale_record_eliminati} record eliminati`);
        } catch (err) {
            toast.error(err.response?.data?.detail || "Reset fallito");
        } finally { setSaving(false); }
    };

    return (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={step !== 3 ? undefined : onClose}>
            <div className="bg-white rounded-xl shadow-2xl max-w-lg w-full" onClick={(e) => e.stopPropagation()}>
                {step === 1 && (
                    <div className="p-6">
                        <div className="flex items-center gap-3 mb-4">
                            <div className="w-12 h-12 bg-rose-100 rounded-full flex items-center justify-center">
                                <Flame size={24} className="text-rose-600" />
                            </div>
                            <div>
                                <h3 className="text-lg font-bold text-rose-900">Reset dati agenzia</h3>
                                <p className="text-xs text-slate-500">Operazione irreversibile</p>
                            </div>
                        </div>
                        <div className="bg-rose-50 border border-rose-200 rounded-md p-3 mb-4">
                            <div className="flex items-start gap-2">
                                <AlertTriangle size={16} className="text-rose-600 shrink-0 mt-0.5" />
                                <div className="text-xs text-rose-800 space-y-2">
                                    <p>Stai per <b>cancellare TUTTI i dati operativi</b> di:</p>
                                    <p className="font-semibold text-sm">🏢 {agenzia.ragione_sociale}</p>
                                    <p>Verranno rimossi in modo permanente:</p>
                                    <ul className="list-disc pl-4 space-y-0.5">
                                        <li>Anagrafiche, Polizze, Titoli, Sinistri</li>
                                        <li>Movimenti Prima Nota, Allegati, Veicoli</li>
                                        <li>Diario cliente, Avvisi, Notifiche</li>
                                        <li>Chat AI Copilot, Whatsapp, Importazioni</li>
                                        <li>Utenti non-admin (collaboratori/dipendenti/clienti)</li>
                                    </ul>
                                    <p className="mt-2"><b>Restano intatti:</b> tenant, configurazione, utenti admin, libreria conti/compagnie/collaboratori.</p>
                                </div>
                            </div>
                        </div>
                        <div className="flex justify-end gap-2">
                            <button onClick={onClose} className="px-4 py-2 text-sm border border-slate-300 rounded-md hover:bg-slate-50" data-testid="reset-cancel-1">Annulla</button>
                            <button onClick={() => setStep(2)} className="px-4 py-2 text-sm bg-rose-600 hover:bg-rose-700 text-white rounded-md font-semibold" data-testid="reset-continue">
                                Ho capito, continua →
                            </button>
                        </div>
                    </div>
                )}
                {step === 2 && (
                    <div className="p-6">
                        <div className="flex items-center gap-2 mb-4">
                            <Flame size={20} className="text-rose-600" />
                            <h3 className="text-lg font-bold">Conferma reset — {agenzia.ragione_sociale}</h3>
                        </div>
                        <div className="space-y-3">
                            <div>
                                <label className="text-xs font-semibold text-slate-600 block mb-1">
                                    1️⃣ Digita <span className="font-mono bg-slate-100 px-1.5">RESET DATI</span> per confermare
                                </label>
                                <input type="text" value={confirmText} onChange={(e) => setConfirmText(e.target.value)}
                                    placeholder="RESET DATI"
                                    autoComplete="off"
                                    className="w-full px-3 py-1.5 text-sm border border-slate-300 rounded-md font-mono"
                                    data-testid="reset-confirm-text" />
                            </div>
                            <div>
                                <label className="text-xs font-semibold text-slate-600 block mb-1">
                                    2️⃣ Digita la ragione sociale <span className="font-mono bg-slate-100 px-1.5">{agenzia.ragione_sociale}</span>
                                </label>
                                <input type="text" value={conferma} onChange={(e) => setConferma(e.target.value)}
                                    autoComplete="off"
                                    className="w-full px-3 py-1.5 text-sm border border-slate-300 rounded-md"
                                    data-testid="reset-confirm-name" />
                            </div>
                            <div>
                                <label className="text-xs font-semibold text-slate-600 block mb-1">
                                    3️⃣ Password custode
                                </label>
                                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                                    autoComplete="new-password"
                                    className="w-full px-3 py-1.5 text-sm border border-slate-300 rounded-md"
                                    data-testid="reset-password" />
                            </div>
                            <label className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer">
                                <input type="checkbox" checked={mantieniAdmin} onChange={(e) => setMantieniAdmin(e.target.checked)}
                                    data-testid="reset-mantieni-admin" />
                                Mantieni gli utenti Admin del tenant (consigliato)
                            </label>
                        </div>
                        <div className="flex justify-end gap-2 mt-6">
                            <button onClick={() => setStep(1)} className="px-4 py-2 text-sm border border-slate-300 rounded-md" data-testid="reset-back">← Indietro</button>
                            <button onClick={doReset} disabled={!canProceed || saving}
                                className="px-4 py-2 text-sm bg-rose-600 hover:bg-rose-700 text-white rounded-md font-semibold disabled:opacity-40 disabled:cursor-not-allowed"
                                data-testid="reset-execute">
                                {saving ? <><Loader2 size={14} className="animate-spin inline mr-1" /> Reset in corso…</> : "🔥 ESEGUI RESET"}
                            </button>
                        </div>
                    </div>
                )}
                {step === 3 && result && (
                    <div className="p-6">
                        <div className="flex items-center gap-3 mb-4">
                            <div className="w-12 h-12 bg-emerald-100 rounded-full flex items-center justify-center">
                                <Flame size={24} className="text-emerald-600" />
                            </div>
                            <div>
                                <h3 className="text-lg font-bold text-emerald-900">Reset completato</h3>
                                <p className="text-xs text-slate-500">{result.totale_record_eliminati} record eliminati</p>
                            </div>
                        </div>
                        <div className="bg-slate-50 border border-slate-200 rounded-md p-3 mb-4 max-h-56 overflow-y-auto">
                            <div className="text-xs font-semibold text-slate-600 mb-1">Dettaglio:</div>
                            <table className="w-full text-xs">
                                <tbody>
                                    {Object.entries(result.dettaglio || {}).map(([k, v]) => (
                                        <tr key={k} className="border-b border-slate-100">
                                            <td className="py-1 font-mono">{k}</td>
                                            <td className="py-1 text-right font-mono text-rose-700">-{v}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                        <div className="flex justify-end">
                            <button onClick={onDone} className="px-4 py-2 text-sm bg-slate-800 hover:bg-slate-900 text-white rounded-md" data-testid="reset-close">
                                Chiudi
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}


function EliminaDefinitivaDialog({ agenzia, onClose, onDone }) {
    const [step, setStep] = useState(1);
    const [confirmText, setConfirmText] = useState("");
    const [conferma, setConferma] = useState("");
    const [password, setPassword] = useState("");
    const [saving, setSaving] = useState(false);
    const [result, setResult] = useState(null);

    const canProceed = confirmText === "ELIMINA" && password.length > 0 && conferma === agenzia.ragione_sociale;

    const doElimina = async () => {
        if (!canProceed) return;
        setSaving(true);
        try {
            const r = await api.post(`/super-admin/agenzie/${agenzia.id}/elimina-definitiva`, {
                password_custode: password,
                conferma_ragione_sociale: conferma,
            });
            setResult(r.data);
            setStep(3);
            toast.success(`Agenzia eliminata: ${r.data.totale_record_eliminati} record rimossi`);
        } catch (err) {
            toast.error(err.response?.data?.detail || "Eliminazione fallita");
        } finally { setSaving(false); }
    };

    return (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={step !== 3 ? undefined : onClose}>
            <div className="bg-white rounded-xl shadow-2xl max-w-lg w-full" onClick={(e) => e.stopPropagation()}>
                {step === 1 && (
                    <div className="p-6">
                        <div className="flex items-center gap-3 mb-4">
                            <div className="w-12 h-12 bg-rose-100 rounded-full flex items-center justify-center">
                                <Trash2 size={24} className="text-rose-700" />
                            </div>
                            <div>
                                <h3 className="text-lg font-bold text-rose-900">Elimina definitivamente</h3>
                                <p className="text-xs text-slate-500">Operazione IRREVERSIBILE</p>
                            </div>
                        </div>
                        <div className="bg-rose-50 border border-rose-200 rounded-md p-3 mb-4">
                            <div className="flex items-start gap-2">
                                <AlertTriangle size={16} className="text-rose-600 shrink-0 mt-0.5" />
                                <div className="text-xs text-rose-800 space-y-2">
                                    <p>Stai per <b>ELIMINARE PER SEMPRE</b> l'agenzia:</p>
                                    <p className="font-semibold text-sm">🏢 {agenzia.ragione_sociale}</p>
                                    <p>Verranno rimossi in modo permanente:</p>
                                    <ul className="list-disc pl-4 space-y-0.5">
                                        <li>Tutti i dati (anagrafiche, polizze, titoli, sinistri, movimenti…)</li>
                                        <li>La configurazione (conti, compagnie, agenzie, modelli)</li>
                                        <li><b>TUTTI gli utenti</b> del tenant (admin inclusi)</li>
                                        <li>Il record dell'agenzia (sparisce dalla lista)</li>
                                    </ul>
                                    <p className="mt-2">Viene creato automaticamente un <b>backup</b> scaricabile prima dell'eliminazione.</p>
                                </div>
                            </div>
                        </div>
                        <div className="flex justify-end gap-2">
                            <button onClick={onClose} className="px-4 py-2 text-sm border border-slate-300 rounded-md hover:bg-slate-50" data-testid="elimina-cancel-1">Annulla</button>
                            <button onClick={() => setStep(2)} className="px-4 py-2 text-sm bg-rose-700 hover:bg-rose-800 text-white rounded-md font-semibold" data-testid="elimina-continue">
                                Ho capito, continua →
                            </button>
                        </div>
                    </div>
                )}
                {step === 2 && (
                    <div className="p-6">
                        <div className="flex items-center gap-2 mb-4">
                            <Trash2 size={20} className="text-rose-700" />
                            <h3 className="text-lg font-bold">Conferma eliminazione — {agenzia.ragione_sociale}</h3>
                        </div>
                        <div className="space-y-3">
                            <div>
                                <label className="text-xs font-semibold text-slate-600 block mb-1">
                                    1️⃣ Digita <span className="font-mono bg-slate-100 px-1.5">ELIMINA</span> per confermare
                                </label>
                                <input type="text" value={confirmText} onChange={(e) => setConfirmText(e.target.value)}
                                    placeholder="ELIMINA" autoComplete="off"
                                    className="w-full px-3 py-1.5 text-sm border border-slate-300 rounded-md font-mono"
                                    data-testid="elimina-confirm-text" />
                            </div>
                            <div>
                                <label className="text-xs font-semibold text-slate-600 block mb-1">
                                    2️⃣ Digita la ragione sociale <span className="font-mono bg-slate-100 px-1.5">{agenzia.ragione_sociale}</span>
                                </label>
                                <input type="text" value={conferma} onChange={(e) => setConferma(e.target.value)}
                                    autoComplete="off"
                                    className="w-full px-3 py-1.5 text-sm border border-slate-300 rounded-md"
                                    data-testid="elimina-confirm-name" />
                            </div>
                            <div>
                                <label className="text-xs font-semibold text-slate-600 block mb-1">3️⃣ Password custode</label>
                                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                                    autoComplete="new-password"
                                    className="w-full px-3 py-1.5 text-sm border border-slate-300 rounded-md"
                                    data-testid="elimina-password" />
                            </div>
                        </div>
                        <div className="flex justify-end gap-2 mt-6">
                            <button onClick={() => setStep(1)} className="px-4 py-2 text-sm border border-slate-300 rounded-md" data-testid="elimina-back">← Indietro</button>
                            <button onClick={doElimina} disabled={!canProceed || saving}
                                className="px-4 py-2 text-sm bg-rose-700 hover:bg-rose-800 text-white rounded-md font-semibold disabled:opacity-40 disabled:cursor-not-allowed"
                                data-testid="elimina-execute">
                                {saving ? <><Loader2 size={14} className="animate-spin inline mr-1" /> Eliminazione…</> : "🗑️ ELIMINA DEFINITIVAMENTE"}
                            </button>
                        </div>
                    </div>
                )}
                {step === 3 && result && (
                    <div className="p-6">
                        <div className="flex items-center gap-3 mb-4">
                            <div className="w-12 h-12 bg-emerald-100 rounded-full flex items-center justify-center">
                                <Check size={24} className="text-emerald-600" />
                            </div>
                            <div>
                                <h3 className="text-lg font-bold text-emerald-900">Agenzia eliminata</h3>
                                <p className="text-xs text-slate-500">{result.totale_record_eliminati} record rimossi</p>
                            </div>
                        </div>
                        {result.backup?.download_url && (
                            <a href={result.backup.download_url} className="text-xs text-sky-600 underline block mb-3" data-testid="elimina-backup-link">
                                ⬇ Scarica backup ({result.backup.size_kb} KB)
                            </a>
                        )}
                        <div className="flex justify-end">
                            <button onClick={onDone} className="px-4 py-2 text-sm bg-slate-800 hover:bg-slate-900 text-white rounded-md" data-testid="elimina-close">Chiudi</button>
                        </div>
                    </div>
                )}
            </div>
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
    const [subTab, setSubTab] = useState("richieste"); // richieste | catalogo
    const [richieste, setRichieste] = useState([]);
    const [moduli, setModuli] = useState([]);
    const [filterTipo, setFilterTipo] = useState("all");
    const [editing, setEditing] = useState(null);

    const loadRichieste = () => api.get("/super-admin/marketplace/richieste").then((r) => setRichieste(r.data || []));
    const loadModuli = () => api.get("/super-admin/marketplace/moduli").then((r) => setModuli(r.data || []));
    useEffect(() => { loadRichieste(); loadModuli(); }, []);

    const toggle = async (id, stato) => {
        try {
            await api.patch(`/super-admin/marketplace/richieste/${id}/toggle`, { stato });
            toast.success("Aggiornato");
            loadRichieste();
        } catch (e) { toast.error(e?.response?.data?.detail || "Errore"); }
    };

    const filtered = moduli.filter((m) => filterTipo === "all" || m.tipo_modulo === filterTipo);

    return (
        <div>
            <div className="flex gap-1 mb-4 border-b border-slate-100">
                <button onClick={() => setSubTab("richieste")}
                    className={`px-3 py-1.5 text-sm font-medium border-b-2 -mb-px ${subTab === "richieste" ? "border-violet-600 text-violet-700" : "border-transparent text-slate-600"}`}
                    data-testid="sa-mkt-subtab-richieste">
                    Richieste attivazione ({richieste.length})
                </button>
                <button onClick={() => setSubTab("catalogo")}
                    className={`px-3 py-1.5 text-sm font-medium border-b-2 -mb-px ${subTab === "catalogo" ? "border-violet-600 text-violet-700" : "border-transparent text-slate-600"}`}
                    data-testid="sa-mkt-subtab-catalogo">
                    Catalogo moduli ({moduli.length})
                </button>
            </div>

            {subTab === "richieste" && (
                <div className="border border-slate-200 rounded-lg overflow-hidden">
                    {richieste.length === 0 && <div className="p-6 text-center text-slate-500 text-sm">Nessuna richiesta di attivazione.</div>}
                    <table className="w-full text-sm">
                        <thead className="bg-slate-50 text-xs uppercase text-slate-600">
                            <tr><th className="text-left px-3 py-2">Data</th><th className="text-left px-3 py-2">Agenzia</th><th className="text-left px-3 py-2">Modulo</th><th className="text-right px-3 py-2">Prezzo</th><th className="text-left px-3 py-2">Stato</th><th className="text-right px-3 py-2">Azioni</th></tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {richieste.map((r) => (
                                <tr key={r.id} data-testid={`sa-marketplace-req-${r.id}`}>
                                    <td className="px-3 py-2 text-xs">{new Date(r.created_at).toLocaleDateString("it-IT")}</td>
                                    <td className="px-3 py-2 font-medium">{r.tenant_ragione_sociale}</td>
                                    <td className="px-3 py-2">{r.module_nome}</td>
                                    <td className="px-3 py-2 text-right">€ {r.prezzo_concordato_eur?.toFixed(2)}</td>
                                    <td className="px-3 py-2"><span className={`text-[10px] font-semibold px-2 py-0.5 rounded border ${STATO_COLORS[r.stato]}`}>{r.stato}</span></td>
                                    <td className="px-3 py-2 text-right">
                                        {r.stato !== "attivo" ? (
                                            <button onClick={() => toggle(r.id, "attivo")}
                                                className="text-xs px-2 py-1 rounded bg-emerald-600 text-white hover:bg-emerald-700"
                                                data-testid={`sa-toggle-on-${r.id}`}>Attiva</button>
                                        ) : (
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
            )}

            {subTab === "catalogo" && (
                <div>
                    <div className="flex items-center justify-between mb-3">
                        <div className="flex gap-2">
                            <button onClick={() => setFilterTipo("all")}
                                className={`text-xs px-3 py-1 rounded-full ${filterTipo === "all" ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-700"}`}
                                data-testid="sa-mkt-filter-all">Tutti ({moduli.length})</button>
                            <button onClick={() => setFilterTipo("core")}
                                className={`text-xs px-3 py-1 rounded-full ${filterTipo === "core" ? "bg-emerald-600 text-white" : "bg-emerald-50 text-emerald-700"}`}
                                data-testid="sa-mkt-filter-core">Core inclusi ({moduli.filter(m => m.tipo_modulo === "core").length})</button>
                            <button onClick={() => setFilterTipo("estensione")}
                                className={`text-xs px-3 py-1 rounded-full ${filterTipo === "estensione" ? "bg-violet-600 text-white" : "bg-violet-50 text-violet-700"}`}
                                data-testid="sa-mkt-filter-estensione">Estensioni ({moduli.filter(m => m.tipo_modulo === "estensione").length})</button>
                        </div>
                        <button onClick={() => setEditing({})}
                            className="text-xs font-semibold px-3 py-1.5 rounded-md bg-violet-600 text-white hover:bg-violet-700 flex items-center gap-1"
                            data-testid="sa-mkt-new-btn">
                            <Plus size={14} /> Nuovo Modulo
                        </button>
                    </div>
                    <div className="border border-slate-200 rounded-lg overflow-hidden">
                        <table className="w-full text-sm">
                            <thead className="bg-slate-50 text-xs uppercase text-slate-600">
                                <tr>
                                    <th className="text-left px-3 py-2">Codice</th>
                                    <th className="text-left px-3 py-2">Nome</th>
                                    <th className="text-left px-3 py-2">Tipo</th>
                                    <th className="text-left px-3 py-2">Categoria</th>
                                    <th className="text-right px-3 py-2">Prezzo</th>
                                    <th className="text-left px-3 py-2">Attivo</th>
                                    <th className="text-right px-3 py-2">Azioni</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                                {filtered.map((m) => (
                                    <tr key={m.id} className="hover:bg-slate-50" data-testid={`sa-mkt-module-${m.codice}`}>
                                        <td className="px-3 py-2 font-mono text-xs">{m.codice}</td>
                                        <td className="px-3 py-2 font-medium">{m.nome}<div className="text-[11px] text-slate-500 truncate max-w-xs">{m.descrizione}</div></td>
                                        <td className="px-3 py-2">
                                            <span className={`text-[10px] uppercase font-semibold px-2 py-0.5 rounded border ${m.tipo_modulo === "core" ? "bg-emerald-50 text-emerald-700 border-emerald-200" : "bg-violet-50 text-violet-700 border-violet-200"}`}>
                                                {m.tipo_modulo === "core" ? "CORE" : "ESTENSIONE"}
                                            </span>
                                        </td>
                                        <td className="px-3 py-2 text-xs">{m.categoria || "-"}</td>
                                        <td className="px-3 py-2 text-right">{m.prezzo_eur === 0 ? "Incluso" : `€ ${m.prezzo_eur.toFixed(2)}`}</td>
                                        <td className="px-3 py-2"><span className={`text-[10px] font-semibold ${m.attivo ? "text-emerald-700" : "text-slate-400"}`}>{m.attivo ? "✓ attivo" : "✗ nascosto"}</span></td>
                                        <td className="px-3 py-2 text-right">
                                            <button onClick={() => setEditing(m)}
                                                className="text-xs px-2 py-1 rounded bg-slate-100 hover:bg-slate-200"
                                                data-testid={`sa-mkt-edit-${m.codice}`}>Modifica</button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {editing !== null && (
                <ModuloForm modulo={editing} onClose={() => setEditing(null)}
                    onSaved={() => { setEditing(null); loadModuli(); }} />
            )}
        </div>
    );
}

function ModuloForm({ modulo, onClose, onSaved }) {
    const isNew = !modulo?.id;
    const [f, setF] = useState({
        codice: modulo?.codice || "",
        nome: modulo?.nome || "",
        descrizione: modulo?.descrizione || "",
        prezzo_eur: modulo?.prezzo_eur ?? 0,
        tipo_modulo: modulo?.tipo_modulo || "estensione",
        tipo: modulo?.tipo || "ricorrente",
        categoria: modulo?.categoria || "",
        icona: modulo?.icona || "",
        attivo: modulo?.attivo ?? true,
        ordine: modulo?.ordine ?? 0,
    });
    const [saving, setSaving] = useState(false);
    const save = async (e) => {
        e.preventDefault();
        if (!f.codice.trim() || !f.nome.trim()) { toast.error("Codice e nome obbligatori"); return; }
        setSaving(true);
        try {
            if (isNew) {
                await api.post("/super-admin/marketplace/moduli", f);
                toast.success("Modulo creato!");
            } else {
                await api.patch(`/super-admin/marketplace/moduli/${modulo.id}`, f);
                toast.success("Modulo aggiornato!");
            }
            onSaved();
        } catch (err) {
            toast.error(err?.response?.data?.detail || "Errore");
        } finally { setSaving(false); }
    };
    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
            <form onSubmit={save} className="bg-white rounded-lg shadow-xl w-full max-w-2xl p-5 max-h-[90vh] overflow-y-auto"
                data-testid="sa-mkt-form">
                <h3 className="text-lg font-semibold mb-4">{isNew ? "Nuovo Modulo" : `Modifica: ${modulo.nome}`}</h3>
                <div className="grid grid-cols-2 gap-3 text-sm">
                    <FormField label="Codice *" value={f.codice} onChange={(v) => setF({ ...f, codice: v.toUpperCase() })} testid="sa-mkt-form-codice" />
                    <FormField label="Nome *" value={f.nome} onChange={(v) => setF({ ...f, nome: v })} testid="sa-mkt-form-nome" />
                    <div className="col-span-2">
                        <label className="text-xs font-semibold text-slate-600 block mb-1">Descrizione</label>
                        <textarea rows={2} value={f.descrizione} onChange={(e) => setF({ ...f, descrizione: e.target.value })}
                            className="w-full px-3 py-1.5 text-sm border border-slate-300 rounded-md focus:border-violet-500 outline-none"
                            data-testid="sa-mkt-form-descrizione" />
                    </div>
                    <div>
                        <label className="text-xs font-semibold text-slate-600 block mb-1">Tipo Modulo *</label>
                        <select value={f.tipo_modulo} onChange={(e) => setF({ ...f, tipo_modulo: e.target.value, prezzo_eur: e.target.value === "core" ? 0 : f.prezzo_eur })}
                            className="w-full px-3 py-1.5 text-sm border border-slate-300 rounded-md bg-white"
                            data-testid="sa-mkt-form-tipo-modulo">
                            <option value="core">Core (incluso nel pacchetto)</option>
                            <option value="estensione">Estensione (a pagamento)</option>
                        </select>
                    </div>
                    <div>
                        <label className="text-xs font-semibold text-slate-600 block mb-1">Modello prezzo</label>
                        <select value={f.tipo} onChange={(e) => setF({ ...f, tipo: e.target.value })}
                            className="w-full px-3 py-1.5 text-sm border border-slate-300 rounded-md bg-white"
                            data-testid="sa-mkt-form-tipo">
                            <option value="ricorrente">Mensile ricorrente</option>
                            <option value="una_tantum">Una tantum</option>
                            <option value="consumo">A consumo (pacchetto)</option>
                        </select>
                    </div>
                    <FormField label="Prezzo €" type="number" value={f.prezzo_eur} onChange={(v) => setF({ ...f, prezzo_eur: parseFloat(v) || 0 })} testid="sa-mkt-form-prezzo" />
                    <FormField label="Categoria" value={f.categoria} onChange={(v) => setF({ ...f, categoria: v })} testid="sa-mkt-form-categoria" />
                    <FormField label="Icona (lucide name)" value={f.icona} onChange={(v) => setF({ ...f, icona: v })} testid="sa-mkt-form-icona" />
                    <FormField label="Ordine" type="number" value={f.ordine} onChange={(v) => setF({ ...f, ordine: parseInt(v) || 0 })} testid="sa-mkt-form-ordine" />
                    <label className="flex items-center gap-2 mt-2 col-span-2">
                        <input type="checkbox" checked={f.attivo} onChange={(e) => setF({ ...f, attivo: e.target.checked })}
                            data-testid="sa-mkt-form-attivo" />
                        <span className="text-sm">Attivo (visibile alle agenzie)</span>
                    </label>
                </div>
                <div className="flex justify-end gap-2 mt-5">
                    <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm border border-slate-300 rounded-md">Annulla</button>
                    <button type="submit" disabled={saving}
                        className="px-3 py-1.5 text-sm bg-violet-600 text-white rounded-md disabled:opacity-60"
                        data-testid="sa-mkt-form-submit">
                        {saving ? "Salvo…" : (isNew ? "Crea Modulo" : "Aggiorna")}
                    </button>
                </div>
            </form>
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

// ============================================================
// DOMINI & CREDENZIALI — sottodominio dedicato + accessi agenzia
// ============================================================
function DominiCredenzialiDialog({ agenzia, onClose }) {
    const [slug, setSlug] = useState(agenzia.sottodominio || "");
    const [attivo, setAttivo] = useState(agenzia.dominio_attivo !== false);
    const [url, setUrl] = useState(null);
    const [savingDom, setSavingDom] = useState(false);
    const [credEmail, setCredEmail] = useState(agenzia.email || "");
    const [credRole, setCredRole] = useState("admin");
    const [credResult, setCredResult] = useState(null);
    const [savingCred, setSavingCred] = useState(false);
    const [utenti, setUtenti] = useState([]);

    const loadUtenti = () => api.get(`/super-admin/agenzie/${agenzia.id}/utenti`).then((r) => setUtenti(r.data || []));
    useEffect(() => { loadUtenti(); }, []); // eslint-disable-line

    const salvaDominio = async () => {
        setSavingDom(true);
        try {
            const r = await api.post(`/super-admin/agenzie/${agenzia.id}/dominio`, { sottodominio: slug, attivo });
            setUrl(r.data.url);
            toast.success(`Sottodominio "${r.data.sottodominio}" attivato`);
        } catch (e) { toast.error(e?.response?.data?.detail || "Errore"); }
        finally { setSavingDom(false); }
    };

    const generaCredenziali = async () => {
        if (!credEmail.trim()) { toast.error("Inserisci l'email"); return; }
        setSavingCred(true);
        try {
            const r = await api.post(`/super-admin/agenzie/${agenzia.id}/credenziali`, { email: credEmail, role: credRole });
            setCredResult(r.data);
            loadUtenti();
            toast.success(r.data.azione === "creato" ? "Credenziali create" : "Password resettata");
        } catch (e) { toast.error(e?.response?.data?.detail || "Errore"); }
        finally { setSavingCred(false); }
    };

    const copia = (txt) => { navigator.clipboard.writeText(txt); toast.success("Copiato"); };

    return (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
            <div className="bg-white rounded-xl shadow-xl w-full max-w-lg max-h-[85vh] overflow-y-auto p-5"
                 onClick={(e) => e.stopPropagation()} data-testid="sa-domini-dialog">
                <div className="flex items-center gap-2 mb-4">
                    <Globe size={18} className="text-violet-600" />
                    <h3 className="font-bold text-slate-800">Dominio & credenziali — {agenzia.ragione_sociale}</h3>
                </div>

                {/* SOTTODOMINIO */}
                <div className="border border-slate-200 rounded-lg p-3 mb-4">
                    <div className="text-xs font-semibold text-slate-600 uppercase mb-2">Sottodominio dedicato</div>
                    <div className="flex items-center gap-2">
                        <input value={slug} onChange={(e) => setSlug(e.target.value.toLowerCase())}
                               placeholder="es. agenzia-rossi"
                               className="flex-1 border border-slate-300 rounded px-2 py-1.5 text-sm font-mono"
                               data-testid="sa-dominio-input" />
                        <label className="flex items-center gap-1 text-xs text-slate-600">
                            <input type="checkbox" checked={attivo} onChange={(e) => setAttivo(e.target.checked)} /> Attivo
                        </label>
                        <button onClick={salvaDominio} disabled={savingDom || slug.length < 3}
                                className="text-xs font-semibold px-3 py-1.5 rounded bg-violet-600 text-white hover:bg-violet-700 disabled:opacity-50"
                                data-testid="sa-dominio-salva">
                            {savingDom ? "…" : "Attiva"}
                        </button>
                    </div>
                    {(url || agenzia.sottodominio) && (
                        <div className="mt-2 flex items-center gap-2 text-xs bg-violet-50 border border-violet-200 rounded p-2">
                            <span className="font-mono text-violet-800 truncate" data-testid="sa-dominio-url">
                                {url || `https://${agenzia.sottodominio}.…`}
                            </span>
                            {url && <button onClick={() => copia(url)} className="text-violet-600 hover:text-violet-900"><Copy size={12} /></button>}
                        </div>
                    )}
                    <div className="text-[10px] text-slate-400 mt-1.5">
                        In produzione richiede un record DNS wildcard (*.tuodominio.it) puntato al server.
                    </div>
                </div>

                {/* CREDENZIALI */}
                <div className="border border-slate-200 rounded-lg p-3 mb-4">
                    <div className="text-xs font-semibold text-slate-600 uppercase mb-2 flex items-center gap-1">
                        <KeyRound size={12} /> Credenziali dedicate
                    </div>
                    <div className="flex items-center gap-2">
                        <input value={credEmail} onChange={(e) => setCredEmail(e.target.value)}
                               placeholder="admin@agenzia.it" type="email"
                               className="flex-1 border border-slate-300 rounded px-2 py-1.5 text-sm"
                               data-testid="sa-cred-email" />
                        <select value={credRole} onChange={(e) => setCredRole(e.target.value)}
                                className="border border-slate-300 rounded px-2 py-1.5 text-xs">
                            <option value="admin">Admin</option>
                            <option value="collaboratore">Collaboratore</option>
                            <option value="dipendente">Dipendente</option>
                        </select>
                        <button onClick={generaCredenziali} disabled={savingCred}
                                className="text-xs font-semibold px-3 py-1.5 rounded bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
                                data-testid="sa-cred-genera">
                            {savingCred ? "…" : "Genera"}
                        </button>
                    </div>
                    {credResult && (
                        <div className="mt-2 bg-emerald-50 border border-emerald-200 rounded p-2 text-xs space-y-1"
                             data-testid="sa-cred-result">
                            <div className="font-semibold text-emerald-800">
                                Credenziali {credResult.azione === "creato" ? "create" : "resettate"} — salvale ora, la password non sarà più visibile:
                            </div>
                            <div className="flex items-center gap-2 font-mono">
                                <span>{credResult.email}</span>
                                <button onClick={() => copia(credResult.email)} className="text-emerald-600"><Copy size={11} /></button>
                            </div>
                            <div className="flex items-center gap-2 font-mono">
                                <span>🔑 {credResult.password}</span>
                                <button onClick={() => copia(credResult.password)} className="text-emerald-600"><Copy size={11} /></button>
                            </div>
                        </div>
                    )}
                </div>

                {/* UTENTI ESISTENTI */}
                <div className="border border-slate-200 rounded-lg p-3">
                    <div className="text-xs font-semibold text-slate-600 uppercase mb-2">Utenti dell'agenzia ({utenti.length})</div>
                    {utenti.length === 0 ? (
                        <div className="text-xs text-slate-400">Nessun utente ancora.</div>
                    ) : utenti.map((u) => (
                        <div key={u.id} className="flex items-center gap-2 text-xs py-1 border-b border-slate-50 last:border-0">
                            <span className="font-mono text-slate-700 truncate flex-1">{u.email}</span>
                            <span className="uppercase text-[9px] font-semibold px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">{u.role}</span>
                            <span className={`text-[9px] ${u.attivo ? "text-emerald-600" : "text-rose-500"}`}>{u.attivo ? "attivo" : "disattivo"}</span>
                        </div>
                    ))}
                </div>

                <div className="flex justify-end mt-4">
                    <button onClick={onClose} className="text-xs font-semibold px-4 py-2 rounded border border-slate-300 hover:bg-slate-50">
                        Chiudi
                    </button>
                </div>
            </div>
        </div>
    );
}

// ============================================================
// SCAMBI DATI — console approvazione scambi tra agenzie
// ============================================================
function ScambiTab() {
    const [items, setItems] = useState(null);
    const [busy, setBusy] = useState(null);

    const load = () => api.get("/super-admin/scambi").then((r) => setItems(r.data || [])).catch(() => setItems([]));
    useEffect(() => { load(); }, []);

    const approva = async (r) => {
        if (!window.confirm(`Approvare ed eseguire lo scambio richiesto da ${r.agenzia_richiedente_nome} (operatore ${r.operatore_email})?`)) return;
        setBusy(r.id);
        try {
            const res = await api.post(`/super-admin/scambi/${r.id}/approva`);
            const k = res.data.risultato || {};
            toast.success(`Scambio eseguito: ${k.anagrafiche || 0} anagrafiche, ${k.polizze || 0} polizze, ${k.titoli || 0} titoli`);
            load();
        } catch (e) { toast.error(e?.response?.data?.detail || "Errore"); }
        finally { setBusy(null); }
    };

    const rifiuta = async (r) => {
        const motivo = window.prompt("Motivo del rifiuto (facoltativo):") ?? null;
        if (motivo === null) return;
        setBusy(r.id);
        try {
            await api.post(`/super-admin/scambi/${r.id}/rifiuta`, { motivo });
            toast.success("Richiesta rifiutata");
            load();
        } catch (e) { toast.error(e?.response?.data?.detail || "Errore"); }
        finally { setBusy(null); }
    };

    if (items === null) return <Loader2 className="animate-spin text-slate-400 mx-auto my-8" />;

    const inAttesa = items.filter((i) => i.stato === "in_attesa");
    const storico = items.filter((i) => i.stato !== "in_attesa");

    const RigaScambio = ({ r, azioni }) => (
        <tr className="hover:bg-slate-50" data-testid={`sa-scambio-${r.id}`}>
            <td className="px-3 py-2 text-xs">{new Date(r.richiesto_at).toLocaleString("it-IT")}</td>
            <td className="px-3 py-2">
                <div className="font-medium text-slate-800 text-xs">{r.agenzia_richiedente_nome}</div>
                <div className="text-[10px] text-slate-500">{r.richiesto_da_email}</div>
            </td>
            <td className="px-3 py-2 text-xs">{r.agenzia_sorgente_nome}</td>
            <td className="px-3 py-2 font-mono text-xs">{r.operatore_email}</td>
            <td className="px-3 py-2 text-[10px] text-slate-500">
                {["importa_anagrafiche", "importa_polizze", "importa_titoli", "importa_sinistri", "importa_documenti"]
                    .filter((k) => r[k]).map((k) => k.replace("importa_", "")).join(", ")}
            </td>
            <td className="px-3 py-2">
                <span className={`text-[10px] uppercase font-semibold px-2 py-0.5 rounded ${
                    r.stato === "in_attesa" ? "bg-amber-100 text-amber-700"
                        : r.stato === "eseguito" ? "bg-emerald-100 text-emerald-700"
                        : "bg-rose-100 text-rose-700"
                }`}>{r.stato.replace("_", " ")}</span>
                {r.stato === "eseguito" && r.risultato && (
                    <div className="text-[10px] text-slate-500 mt-0.5">
                        {r.risultato.anagrafiche}a · {r.risultato.polizze}p · {r.risultato.titoli}t
                    </div>
                )}
                {r.stato === "rifiutato" && r.motivo_rifiuto && (
                    <div className="text-[10px] text-rose-500 mt-0.5 max-w-[150px] truncate" title={r.motivo_rifiuto}>{r.motivo_rifiuto}</div>
                )}
            </td>
            <td className="px-3 py-2 text-right">
                {azioni && (
                    <div className="flex justify-end gap-1">
                        <button onClick={() => approva(r)} disabled={busy === r.id}
                                title="Approva ed esegui"
                                className="p-1.5 text-emerald-600 hover:bg-emerald-50 rounded border border-emerald-200"
                                data-testid={`sa-scambio-approva-${r.id}`}>
                            {busy === r.id ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
                        </button>
                        <button onClick={() => rifiuta(r)} disabled={busy === r.id}
                                title="Rifiuta"
                                className="p-1.5 text-rose-600 hover:bg-rose-50 rounded border border-rose-200"
                                data-testid={`sa-scambio-rifiuta-${r.id}`}>
                            <X size={13} />
                        </button>
                    </div>
                )}
            </td>
        </tr>
    );

    const Tabella = ({ rows, azioni }) => (
        <div className="border border-slate-200 rounded-lg overflow-hidden">
            <table className="w-full text-sm">
                <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-600">
                    <tr>
                        <th className="text-left px-3 py-2">Data</th>
                        <th className="text-left px-3 py-2">Richiedente</th>
                        <th className="text-left px-3 py-2">Sorgente</th>
                        <th className="text-left px-3 py-2">Operatore</th>
                        <th className="text-left px-3 py-2">Dati</th>
                        <th className="text-left px-3 py-2">Stato</th>
                        <th className="text-right px-3 py-2">Azioni</th>
                    </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                    {rows.map((r) => <RigaScambio key={r.id} r={r} azioni={azioni} />)}
                </tbody>
            </table>
        </div>
    );

    return (
        <div data-testid="sa-scambi-tab">
            <div className="mb-4 border border-amber-200 bg-amber-50/60 rounded-lg p-3 text-xs text-amber-900">
                <strong>Scambio controllato:</strong> le agenzie richiedono lo scambio dati dalla loro pagina
                "Scambio Dati"; qui approvi o rifiuti. All'approvazione l'importazione viene eseguita subito
                (i titoli importati restano "da pagare arretrato").
            </div>
            <h2 className="text-sm font-semibold text-slate-700 mb-2">
                In attesa di approvazione ({inAttesa.length})
            </h2>
            {inAttesa.length === 0
                ? <div className="text-xs text-slate-400 mb-4" data-testid="sa-scambi-vuoto">Nessuna richiesta in attesa.</div>
                : <div className="mb-5"><Tabella rows={inAttesa} azioni /></div>}
            {storico.length > 0 && (
                <>
                    <h2 className="text-sm font-semibold text-slate-700 mb-2">Storico decisioni ({storico.length})</h2>
                    <Tabella rows={storico} azioni={false} />
                </>
            )}
        </div>
    );
}

// ─── CHIAVI API — visibili SOLO al super admin ───────────────────────
function ChiaviApiTab() {
    const [f, setF] = useState(null);
    const [saving, setSaving] = useState(false);
    const [testingWa, setTestingWa] = useState(false);

    useEffect(() => {
        api.get("/super-admin/chiavi-api")
            .then((r) => setF(r.data))
            .catch((e) => toast.error(e?.response?.data?.detail || "Errore caricamento chiavi"));
    }, []);

    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const salva = async () => {
        setSaving(true);
        try {
            await api.put("/super-admin/chiavi-api", f);
            toast.success("Chiavi API salvate");
        } catch (e) { toast.error(e?.response?.data?.detail || "Errore salvataggio"); }
        finally { setSaving(false); }
    };

    const testWa = async () => {
        setTestingWa(true);
        try {
            const r = await api.post("/super-admin/chiavi-api/test-whatsapp");
            if (r.data.ok) toast.success(`Evolution OK — ${r.data.istanze_sul_server} istanze sul server`);
            else toast.error("Test fallito: " + (r.data.error || "errore sconosciuto"));
        } catch (e) { toast.error(e?.response?.data?.detail || "Errore test"); }
        finally { setTestingWa(false); }
    };

    if (!f) return <div className="text-slate-400 text-sm py-8 text-center">Caricamento…</div>;

    return (
        <div className="space-y-4 max-w-4xl" data-testid="sa-chiavi-api">
            <div className="text-xs bg-violet-50 border border-violet-200 rounded-md px-3 py-2 text-violet-800">
                🔑 Queste credenziali sono visibili <b>solo al super admin</b>. Le agenzie clienti usano i servizi
                (firma digitale, SMS, WhatsApp) senza mai vedere chiavi, token o URL dei server.
            </div>

            {/* FIRMA ELETTRONICA */}
            <div className="bg-white border border-slate-200 rounded-lg p-4" data-testid="sa-chiavi-firma">
                <div className="font-semibold text-slate-800 text-sm">✍️ Firma Elettronica — Namirial eSignAnyWhere</div>
                <div className="text-[11px] text-slate-500">Le agenzie firmano documenti (OTP, grafometrica, link remoto) senza vedere queste credenziali.</div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
                    <div>
                        <label className="text-xs font-semibold text-slate-600 block mb-1">Ambiente</label>
                        <select value={f.firma_environment || "sandbox"} onChange={(e) => set("firma_environment", e.target.value)}
                            className="w-full px-3 py-1.5 text-sm border border-slate-300 rounded-md focus:border-violet-500 outline-none bg-white"
                            data-testid="sa-firma-env">
                            <option value="sandbox">Sandbox (demo)</option>
                            <option value="production">Produzione</option>
                        </select>
                    </div>
                    <FormField label="URL API Base" value={f.firma_base_url || ""} onChange={(v) => set("firma_base_url", v)} testid="sa-firma-url" />
                    <FormField label="API Token" type="password" value={f.firma_api_token || ""} onChange={(v) => set("firma_api_token", v)} testid="sa-firma-token" />
                    <FormField label="Webhook Secret (opzionale)" type="password" value={f.firma_webhook_secret || ""} onChange={(v) => set("firma_webhook_secret", v)} testid="sa-firma-webhook" />
                </div>
            </div>

            {/* TWILIO SMS */}
            <div className="bg-white border border-slate-200 rounded-lg p-4" data-testid="sa-chiavi-twilio">
                <div className="font-semibold text-slate-800 text-sm">📱 SMS — Twilio</div>
                <div className="text-[11px] text-slate-500">Usato dall&apos;invio massa avvisi via SMS delle agenzie.</div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
                    <FormField label="Account SID" value={f.twilio_account_sid || ""} onChange={(v) => set("twilio_account_sid", v)} testid="sa-twilio-sid" />
                    <FormField label="Auth Token" type="password" value={f.twilio_auth_token || ""} onChange={(v) => set("twilio_auth_token", v)} testid="sa-twilio-token" />
                    <FormField label="Numero SMS mittente" value={f.twilio_sms_from || ""} onChange={(v) => set("twilio_sms_from", v)} testid="sa-twilio-sms" />
                    <FormField label="Numero WhatsApp Twilio (opz.)" value={f.twilio_whatsapp_from || ""} onChange={(v) => set("twilio_whatsapp_from", v)} testid="sa-twilio-wa" />
                </div>
            </div>

            {/* SPOKI */}
            <div className="bg-white border border-slate-200 rounded-lg p-4" data-testid="sa-chiavi-spoki">
                <div className="font-semibold text-slate-800 text-sm">💬 Spoki (opzionale)</div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
                    <FormField label="API Key" type="password" value={f.spoki_api_key || ""} onChange={(v) => set("spoki_api_key", v)} testid="sa-spoki-key" />
                    <FormField label="Nome mittente" value={f.spoki_sender_name || ""} onChange={(v) => set("spoki_sender_name", v)} testid="sa-spoki-sender" />
                </div>
            </div>

            {/* WHATSAPP */}
            <div className="bg-white border border-slate-200 rounded-lg p-4" data-testid="sa-chiavi-whatsapp">
                <div className="font-semibold text-slate-800 text-sm">🟢 WhatsApp — modalità e server</div>
                <div className="text-[11px] text-slate-500 mb-3">
                    <b>wa.me</b> = gratuito, link precompilato (per agenzie che non pagano Evolution).{" "}
                    <b>Evolution</b> = invio automatico con numero collegato via QR (l&apos;agenzia vede solo il QR).
                </div>
                <div className="flex gap-2 mb-3">
                    {[["wame", "🔗 wa.me (gratis)"], ["evolution", "⚡ Evolution API (auto)"]].map(([v, l]) => (
                        <button key={v} type="button" onClick={() => set("whatsapp_provider", v)}
                            className={`px-3 py-2 text-sm border rounded-md transition-colors ${
                                (f.whatsapp_provider || "wame") === v
                                    ? "bg-emerald-600 text-white border-emerald-600"
                                    : "bg-white text-slate-700 border-slate-300 hover:border-emerald-500"}`}
                            data-testid={`sa-wa-provider-${v}`}>
                            {l}
                        </button>
                    ))}
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <FormField label="URL server Evolution API" value={f.evolution_server_url || ""} onChange={(v) => set("evolution_server_url", v)} testid="sa-evo-url" />
                    <FormField label="API Key Evolution (AUTHENTICATION_API_KEY)" type="password" value={f.evolution_api_key || ""} onChange={(v) => set("evolution_api_key", v)} testid="sa-evo-key" />
                </div>
                <button onClick={testWa} disabled={testingWa}
                    className="mt-3 px-3 py-1.5 text-xs border border-slate-300 rounded-md hover:bg-slate-50 text-slate-700"
                    data-testid="sa-evo-test">
                    {testingWa ? "Verifica…" : "Test connessione Evolution"}
                </button>
            </div>

            <div className="flex justify-end">
                <button onClick={salva} disabled={saving}
                    className="bg-violet-600 hover:bg-violet-700 text-white text-sm font-medium px-5 py-2 rounded-md disabled:opacity-50"
                    data-testid="sa-chiavi-salva">
                    {saving ? "Salvataggio…" : "Salva chiavi API"}
                </button>
            </div>
        </div>
    );
}
