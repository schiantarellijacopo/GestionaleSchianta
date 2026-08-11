/**
 * PortaleCliente — Dashboard self-service del cliente finale.
 *
 * Layout responsive: sidebar su desktop, hamburger menu su mobile.
 * Design fresh consumer-friendly con colori chiari.
 *
 * Sezioni: Profilo · Polizze · Titoli · Documenti · Sinistri · Servizi
 * Le polizze Libro Matricola mostrano inline le applicazioni (targhe/veicoli).
 */
import { useEffect, useState, useRef } from "react";
import { toast, Toaster } from "sonner";
import axios from "axios";
import {
    User, FileText, Wallet, FolderOpen, AlertCircle, Phone,
    Menu, X, LogOut, Upload, Download, ChevronRight, Building2, Car, MessageSquare, Send, Paperclip,
    Shield, ShieldCheck, Heart, Home, Clock, CheckCircle2,
} from "lucide-react";

const BACKEND = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND}/api/portale`;

// ── Client HTTP dedicato al portale (non usa il token del CRM) ───────
const clientApi = axios.create({ baseURL: API });
clientApi.interceptors.request.use((cfg) => {
    const t = localStorage.getItem("portale_token");
    if (t) cfg.headers.Authorization = `Bearer ${t}`;
    return cfg;
});

const SEZIONI = [
    { key: "profilo",  label: "Il mio profilo", icon: User },
    { key: "polizze",  label: "Le mie polizze", icon: FileText },
    { key: "titoli",   label: "Titoli & Quietanze", icon: Wallet },
    { key: "documenti", label: "Documenti & Upload", icon: FolderOpen },
    { key: "sinistri", label: "I miei sinistri", icon: AlertCircle },
    { key: "chat",     label: "Chat con l'agenzia", icon: MessageSquare },
    { key: "servizi",  label: "Servizi & Assistenza", icon: Phone },
];

export default function PortaleCliente() {
    const [token, setToken] = useState(() => localStorage.getItem("portale_token"));
    const [cliente, setCliente] = useState(null);
    const [agenzia, setAgenzia] = useState(null);
    const [sezione, setSezione] = useState("polizze");
    const [menuOpen, setMenuOpen] = useState(false);

    useEffect(() => {
        if (!token) return;
        clientApi.get("/me").then((r) => setCliente(r.data))
            .catch(() => { localStorage.removeItem("portale_token"); setToken(null); });
        clientApi.get("/agenzia").then((r) => setAgenzia(r.data)).catch(() => {});
    }, [token]);

    const logout = () => {
        localStorage.removeItem("portale_token");
        setToken(null); setCliente(null);
    };

    if (!token) return <LoginScreen onLogin={(t) => { localStorage.setItem("portale_token", t); setToken(t); }} />;
    if (!cliente) return <div className="p-8 text-slate-500 text-center">Caricamento…</div>;

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-50 via-sky-50/40 to-blue-100/50">
            <Toaster position="top-center" richColors />
            {/* Header mobile */}
            <header className="lg:hidden sticky top-0 z-40 bg-white/90 backdrop-blur border-b border-slate-200 p-3 flex items-center gap-3 shadow-sm">
                <button onClick={() => setMenuOpen(true)} className="p-2 rounded hover:bg-slate-100" aria-label="Menu">
                    <Menu size={22} />
                </button>
                {agenzia?.logo_url ? (
                    <img src={`${BACKEND}${agenzia.logo_url}`} alt="logo"
                         className="h-8 w-auto object-contain" />
                ) : (
                    <div className="flex-1 font-bold text-sky-700 text-sm truncate">{cliente.nome}</div>
                )}
                <button onClick={logout} className="p-2 rounded hover:bg-slate-100 text-slate-600 ml-auto" title="Esci">
                    <LogOut size={18} />
                </button>
            </header>

            <div className="flex">
                {/* Sidebar desktop */}
                <aside className="hidden lg:flex flex-col w-72 min-h-screen bg-white border-r border-slate-200 shadow-sm">
                    {/* Brand agenzia */}
                    <div className="px-5 py-6 border-b border-slate-100 bg-gradient-to-br from-sky-50 to-white">
                        {agenzia?.logo_url ? (
                            <div className="flex items-center justify-center mb-3">
                                <img src={`${BACKEND}${agenzia.logo_url}`} alt="logo"
                                     className="h-14 w-auto object-contain" />
                            </div>
                        ) : (
                            <div className="inline-flex w-12 h-12 rounded-xl bg-gradient-to-br from-sky-500 to-blue-600 items-center justify-center mb-3 shadow">
                                <Building2 className="text-white" size={22} />
                            </div>
                        )}
                        <div className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold">
                            {agenzia?.ragione_sociale || "Agenzia"}
                        </div>
                        {agenzia?.telefono && (
                            <a href={`tel:${agenzia.telefono}`}
                               className="text-[11px] text-sky-700 hover:underline block mt-0.5">
                                📞 {agenzia.telefono}
                            </a>
                        )}
                    </div>

                    {/* Info cliente */}
                    <div className="px-5 py-4 border-b border-slate-100 bg-white">
                        <div className="flex items-center gap-3">
                            <div className="w-11 h-11 rounded-full bg-gradient-to-br from-sky-500 to-blue-600 text-white flex items-center justify-center font-bold text-lg shadow">
                                {(cliente.nome || "?").charAt(0).toUpperCase()}
                            </div>
                            <div className="min-w-0 flex-1">
                                <div className="text-sm font-bold text-slate-800 truncate">{cliente.nome}</div>
                                {cliente.email && (
                                    <div className="text-[10px] text-slate-400 truncate">{cliente.email}</div>
                                )}
                            </div>
                        </div>
                    </div>

                    <div className="flex-1 p-4 overflow-y-auto">
                        <div className="text-[10px] uppercase text-slate-400 font-semibold tracking-wider mb-2 px-2">Menu</div>
                        <NavList sezione={sezione} onSelect={setSezione} />
                    </div>

                    <button onClick={logout}
                            className="mx-4 mb-4 py-2.5 flex items-center justify-center gap-2 text-sm text-slate-600 hover:text-white hover:bg-rose-500 border border-slate-200 rounded-lg transition-colors"
                            data-testid="portale-logout-btn">
                        <LogOut size={14} /> Esci
                    </button>
                </aside>

                {/* Drawer mobile */}
                {menuOpen && (
                    <div className="lg:hidden fixed inset-0 z-50 bg-black/40" onClick={() => setMenuOpen(false)}>
                        <aside className="w-80 h-full bg-white overflow-y-auto shadow-2xl" onClick={(e) => e.stopPropagation()}>
                            <div className="px-5 py-6 border-b bg-gradient-to-br from-sky-50 to-white">
                                <div className="flex items-center justify-between mb-3">
                                    {agenzia?.logo_url ? (
                                        <img src={`${BACKEND}${agenzia.logo_url}`} alt="logo"
                                             className="h-10 w-auto object-contain" />
                                    ) : (
                                        <div className="font-bold text-slate-800">{agenzia?.ragione_sociale}</div>
                                    )}
                                    <button onClick={() => setMenuOpen(false)}><X size={22} /></button>
                                </div>
                                <div className="text-sm font-semibold text-slate-800 truncate">{cliente.nome}</div>
                            </div>
                            <div className="p-4">
                                <NavList sezione={sezione} onSelect={(k) => { setSezione(k); setMenuOpen(false); }} />
                            </div>
                        </aside>
                    </div>
                )}

                {/* Content */}
                <main className="flex-1 p-4 sm:p-6 lg:p-10 max-w-6xl mx-auto w-full">
                    {sezione === "profilo" && <ProfiloView cliente={cliente} onReload={() => clientApi.get("/me").then((r) => setCliente(r.data))} />}
                    {sezione === "polizze" && <PolizzeView />}
                    {sezione === "titoli" && <TitoliView />}
                    {sezione === "documenti" && <DocumentiView />}
                    {sezione === "sinistri" && <SinistriView />}
                    {sezione === "chat" && <ChatView />}
                    {sezione === "servizi" && <ServiziView agenzia={agenzia} />}
                </main>
            </div>
        </div>
    );
}

// Colore accento per ogni sezione (usato in NavList + intestazioni pagine)
const SEZIONI_COLORS = {
    profilo: "from-sky-500 to-blue-600",
    polizze: "from-violet-500 to-purple-600",
    titoli: "from-emerald-500 to-teal-600",
    documenti: "from-amber-500 to-orange-600",
    sinistri: "from-rose-500 to-red-600",
    chat: "from-cyan-500 to-sky-600",
    servizi: "from-indigo-500 to-blue-600",
};

function NavList({ sezione, onSelect }) {
    return (
        <nav className="space-y-1">
            {SEZIONI.map((s) => {
                const Icon = s.icon;
                const active = sezione === s.key;
                const gradient = SEZIONI_COLORS[s.key] || "from-sky-500 to-blue-600";
                return (
                    <button key={s.key} onClick={() => onSelect(s.key)}
                        className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all
                            ${active
                                ? `bg-gradient-to-r ${gradient} text-white shadow-md font-semibold`
                                : "text-slate-700 hover:bg-slate-100"}`}
                        data-testid={`nav-${s.key}`}>
                        <Icon size={18} className={active ? "" : "text-slate-400"} />
                        <span>{s.label}</span>
                    </button>
                );
            })}
        </nav>
    );
}

// ─── LOGIN ────────────────────────────────────────────────────────────
function LoginScreen({ onLogin }) {
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [busy, setBusy] = useState(false);
    const submit = async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
            const r = await clientApi.post("/auth/login", { email, password });
            toast.success(`Benvenuto ${r.data.cliente.nome}`);
            onLogin(r.data.access_token);
        } catch (err) {
            toast.error(err.response?.data?.detail || "Login fallito");
        } finally { setBusy(false); }
    };
    return (
        <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-sky-100 via-white to-blue-100 p-4">
            <Toaster position="top-center" richColors />
            <div className="w-full max-w-md bg-white rounded-2xl shadow-xl p-8">
                <div className="text-center mb-6">
                    <div className="inline-flex w-16 h-16 rounded-full bg-sky-100 items-center justify-center mb-3">
                        <User className="text-sky-700" size={32} />
                    </div>
                    <h1 className="text-2xl font-bold text-slate-800">Portale Cliente</h1>
                    <p className="text-sm text-slate-500 mt-1">Accedi con le tue credenziali</p>
                </div>
                <form onSubmit={submit} className="space-y-4">
                    <div>
                        <label className="text-xs font-semibold text-slate-600 uppercase">Email</label>
                        <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                            placeholder="tua.email@esempio.it"
                            className="w-full mt-1 px-3 py-2.5 border border-slate-300 rounded-lg text-sm focus:border-sky-500 focus:ring-2 focus:ring-sky-200 outline-none"
                            data-testid="portale-email-input" />
                    </div>
                    <div>
                        <label className="text-xs font-semibold text-slate-600 uppercase">Password</label>
                        <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)}
                            placeholder="Codice Fiscale (privati) o P.IVA (aziende)"
                            className="w-full mt-1 px-3 py-2.5 border border-slate-300 rounded-lg text-sm focus:border-sky-500 focus:ring-2 focus:ring-sky-200 outline-none"
                            data-testid="portale-password-input" />
                        <div className="text-[10px] text-slate-400 mt-1">
                            La tua password iniziale è il tuo Codice Fiscale (privati) o Partita IVA (aziende).
                        </div>
                    </div>
                    <button type="submit" disabled={busy}
                        className="w-full py-3 rounded-lg bg-sky-600 hover:bg-sky-700 text-white font-semibold disabled:opacity-50"
                        data-testid="portale-login-btn">
                        {busy ? "Accesso…" : "Accedi"}
                    </button>
                </form>
            </div>
        </div>
    );
}

function ProfiloField({ label, defaultVal, onChange }) {
    return (
        <div>
            <div className="text-[10px] uppercase text-slate-500 font-semibold">{label}</div>
            <input defaultValue={defaultVal || ""}
                onChange={onChange}
                className="w-full text-sm py-2 px-3 border border-slate-200 rounded focus:border-sky-500 outline-none" />
        </div>
    );
}

// Header di sezione riusabile con icona colorata a gradient
function SectionHeader({ icon: Icon, title, subtitle, gradient = "from-sky-500 to-blue-600", right }) {
    return (
        <div className="mb-6 flex items-start gap-4">
            <div className={`w-14 h-14 rounded-2xl bg-gradient-to-br ${gradient} shadow-md flex items-center justify-center shrink-0`}>
                <Icon className="text-white" size={26} />
            </div>
            <div className="flex-1 min-w-0">
                <h2 className="text-2xl sm:text-3xl font-bold text-slate-800 leading-tight">{title}</h2>
                {subtitle && <div className="text-sm text-slate-500 mt-0.5">{subtitle}</div>}
            </div>
            {right}
        </div>
    );
}

// ─── PROFILO ──────────────────────────────────────────────────────────
function ProfiloView({ cliente }) {
    const [modifiche, setModifiche] = useState({});
    const richiedi = async () => {
        if (Object.keys(modifiche).length === 0) { toast.info("Nessuna modifica"); return; }
        try {
            await clientApi.put("/anagrafica/richiesta", modifiche);
            toast.success("Richiesta inviata all'agenzia");
            setModifiche({});
        } catch (e) { toast.error("Errore invio richiesta"); }
    };
    const onChange = (k) => (e) => setModifiche((m) => ({ ...m, [k]: e.target.value }));
    const isAzienda = cliente.tipo_soggetto === "giuridico" || cliente.partita_iva;
    return (
        <div>
            <SectionHeader icon={User} title="Il mio profilo"
                subtitle="Verifica i tuoi dati e richiedi eventuali modifiche"
                gradient={SEZIONI_COLORS.profilo} />

            {/* Card 1: Dati identificativi */}
            <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100 space-y-5">
                <div>
                    <div className="text-xs font-bold text-sky-700 uppercase tracking-wider mb-3">Dati identificativi</div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <ProfiloField label={isAzienda ? "Ragione Sociale" : "Nome e Cognome"} defaultVal={cliente.nome} onChange={onChange("ragione_sociale")} />
                        <ProfiloField label="Codice Fiscale" defaultVal={cliente.codice_fiscale} onChange={onChange("codice_fiscale")} />
                        {isAzienda && (
                            <ProfiloField label="Partita IVA" defaultVal={cliente.partita_iva} onChange={onChange("partita_iva")} />
                        )}
                        {!isAzienda && cliente.data_nascita && (
                            <ProfiloField label="Data di nascita" defaultVal={cliente.data_nascita} onChange={onChange("data_nascita")} />
                        )}
                        {!isAzienda && cliente.comune_nascita && (
                            <ProfiloField label="Comune di nascita" defaultVal={`${cliente.comune_nascita}${cliente.provincia_nascita ? ` (${cliente.provincia_nascita})` : ""}`} onChange={() => {}} />
                        )}
                    </div>
                </div>

                {/* Contatti */}
                <div className="border-t border-slate-100 pt-5">
                    <div className="text-xs font-bold text-emerald-700 uppercase tracking-wider mb-3">Contatti</div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <ProfiloField label="Email" defaultVal={cliente.email} onChange={onChange("email")} />
                        <ProfiloField label="PEC" defaultVal={cliente.pec} onChange={onChange("pec")} />
                        <ProfiloField label="Cellulare" defaultVal={cliente.cellulare} onChange={onChange("cellulare")} />
                        <ProfiloField label="Telefono" defaultVal={cliente.telefono} onChange={onChange("telefono")} />
                    </div>
                </div>

                {/* Residenza */}
                <div className="border-t border-slate-100 pt-5">
                    <div className="text-xs font-bold text-violet-700 uppercase tracking-wider mb-3">
                        {isAzienda ? "Sede legale" : "Residenza"}
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div className="sm:col-span-2">
                            <ProfiloField label="Indirizzo" defaultVal={cliente.indirizzo} onChange={onChange("indirizzo")} />
                        </div>
                        <ProfiloField label="Comune" defaultVal={cliente.comune} onChange={onChange("comune")} />
                        <ProfiloField label="Provincia" defaultVal={cliente.provincia} onChange={onChange("provincia")} />
                        <ProfiloField label="CAP" defaultVal={cliente.cap} onChange={onChange("cap")} />
                        <ProfiloField label="Nazione" defaultVal={cliente.nazione} onChange={onChange("nazione")} />
                    </div>
                </div>

                {/* Dati bancari */}
                <div className="border-t border-slate-100 pt-5">
                    <div className="text-xs font-bold text-amber-700 uppercase tracking-wider mb-3">Dati bancari</div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div className="sm:col-span-2">
                            <ProfiloField label="IBAN" defaultVal={cliente.iban} onChange={onChange("iban")} />
                        </div>
                        <ProfiloField label="Banca" defaultVal={cliente.banca} onChange={onChange("banca")} />
                    </div>
                </div>

                <div className="border-t border-slate-100 pt-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                    <div className="text-[11px] text-slate-400 italic max-w-md">
                        🔒 Le modifiche saranno verificate dall&apos;agenzia prima di essere applicate al tuo profilo.
                    </div>
                    <button onClick={richiedi}
                        className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-sky-500 to-blue-600 hover:from-sky-600 hover:to-blue-700 text-white text-sm font-semibold shadow-md transition-all"
                        data-testid="richiedi-modifica-btn">
                        Invia richiesta di modifica
                    </button>
                </div>
            </div>
        </div>
    );
}

import IconForRamoShared from "@/components/IconForRamo";
// eslint-disable-next-line no-unused-vars
const IconForRamo = ({ ramo, size = 20, className = "" }) => (
    <IconForRamoShared ramo={ramo} size={size} className={className} />
);

// ─── POLIZZE ──────────────────────────────────────────────────────────
function PolizzeView() {
    const [pols, setPols] = useState(null);
    const [filtro, setFiltro] = useState("attive"); // attive | scadute | tutte
    useEffect(() => { clientApi.get("/polizze").then((r) => setPols(r.data)); }, []);
    if (!pols) return <Loading />;
    const oggi = new Date().toISOString().slice(0, 10);
    const attive = pols.filter((p) => !p.is_scaduta);
    const scadute = pols.filter((p) => p.is_scaduta);
    const visibili = filtro === "attive" ? attive : filtro === "scadute" ? scadute : pols;
    const totalePremio = attive.reduce((s, p) => s + (Number(p.premio_lordo) || 0), 0);
    return (
        <div>
            <SectionHeader icon={FileText} title="Le mie polizze"
                subtitle={`${pols.length} polizze totali · Coperture attive per la tua tranquillità`}
                gradient={SEZIONI_COLORS.polizze} />

            {/* Stats cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
                <StatCard icon={ShieldCheck} value={attive.length} label="Attive" color="emerald" />
                <StatCard icon={Clock} value={scadute.length} label="Scadute" color="rose" />
                <StatCard icon={Wallet} value={`€ ${totalePremio.toFixed(0)}`} label="Premio annuo" color="violet" />
                <StatCard icon={AlertCircle} value={pols.reduce((s, p) => s + (p.stats_titoli?.arretrati || 0), 0)} label="Arretrati" color="amber" />
            </div>

            {/* Tab filtri */}
            <div className="flex gap-2 mb-4 overflow-x-auto pb-1">
                {[["attive", "Attive", attive.length], ["scadute", "Scadute", scadute.length], ["tutte", "Tutte", pols.length]].map(([k, l, n]) => (
                    <button key={k} onClick={() => setFiltro(k)}
                        data-testid={`pol-filter-${k}`}
                        className={`px-4 py-1.5 rounded-full text-sm font-medium transition-all whitespace-nowrap ${
                            filtro === k
                                ? "bg-gradient-to-r from-violet-500 to-purple-600 text-white shadow"
                                : "bg-white text-slate-600 border border-slate-200 hover:border-violet-400"
                        }`}>{l} · {n}</button>
                ))}
            </div>

            {visibili.length === 0 ? (
                <EmptyState icon={FileText} testo="Nessuna polizza in questa categoria" />
            ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    {visibili.map((p) => <PolizzaCard key={p.id} p={p} oggi={oggi} />)}
                </div>
            )}
        </div>
    );
}

function StatCard({ icon: Icon, value, label, color = "sky" }) {
    const bg = {
        sky: "from-sky-50 to-blue-50 border-sky-200 text-sky-700",
        emerald: "from-emerald-50 to-teal-50 border-emerald-200 text-emerald-700",
        rose: "from-rose-50 to-red-50 border-rose-200 text-rose-700",
        violet: "from-violet-50 to-purple-50 border-violet-200 text-violet-700",
        amber: "from-amber-50 to-orange-50 border-amber-200 text-amber-700",
    }[color] || "from-sky-50 to-blue-50 border-sky-200 text-sky-700";
    return (
        <div className={`bg-gradient-to-br ${bg} rounded-xl p-4 border shadow-sm`}>
            <Icon size={18} className="mb-1.5" />
            <div className="text-2xl font-bold leading-tight">{value}</div>
            <div className="text-[11px] uppercase tracking-wider mt-0.5 opacity-80">{label}</div>
        </div>
    );
}

function Loading() {
    return (
        <div className="flex items-center justify-center py-16 text-slate-400">
            <div className="animate-pulse text-sm">Caricamento…</div>
        </div>
    );
}

function PolizzaCard({ p, oggi }) {
    const [openApps, setOpenApps] = useState(false);
    const [openDocs, setOpenDocs] = useState(false);
    const [openTitoli, setOpenTitoli] = useState(false);
    const [docs, setDocs] = useState(null);
    const [titoli, setTitoli] = useState(null);
    const scaduta = p.scadenza && p.scadenza < oggi;
    const inScadenza = !scaduta && p.scadenza && p.scadenza <= addDaysISO(oggi, 60);
    const statoBadge = p.stato === "annullata" ? { l: "ANNULLATA", c: "bg-slate-200 text-slate-700" }
        : p.stato === "sospesa" ? { l: "SOSPESA", c: "bg-amber-100 text-amber-800" }
        : p.stato === "sostituita" ? { l: "SOSTITUITA", c: "bg-cyan-100 text-cyan-800" }
        : scaduta ? { l: "SCADUTA", c: "bg-rose-100 text-rose-700" }
        : inScadenza ? { l: "IN SCADENZA", c: "bg-amber-100 text-amber-800" }
        : { l: "ATTIVA", c: "bg-emerald-100 text-emerald-700" };

    const toggleDocs = async () => {
        const next = !openDocs;
        setOpenDocs(next);
        if (next && docs === null) {
            try {
                const r = await clientApi.get("/allegati/by-entita",
                    { params: { entita_tipo: "polizza", entita_id: p.id } });
                setDocs(r.data);
            } catch { setDocs([]); }
        }
    };

    const toggleTitoli = async () => {
        const next = !openTitoli;
        setOpenTitoli(next);
        if (next && titoli === null) {
            try {
                const r = await clientApi.get(`/polizze/${p.id}/titoli`);
                setTitoli(r.data);
            } catch { setTitoli([]); }
        }
    };

    return (
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden hover:shadow-md transition-shadow">
            {/* Header colorato con ramo icon */}
            <div className="bg-gradient-to-r from-violet-500/10 via-purple-500/5 to-transparent p-5 border-b border-slate-100">
                <div className="flex items-start gap-3">
                    <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center shadow shrink-0">
                        <IconForRamo ramo={p.ramo} className="text-white" />
                    </div>
                    <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap mb-1">
                            <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${statoBadge.c}`}>
                                {statoBadge.l}
                            </span>
                            {p.is_libro_matricola && (
                                <span className="text-[10px] bg-violet-100 text-violet-700 px-2 py-0.5 rounded-full font-bold">LIBRO MATRICOLA</span>
                            )}
                        </div>
                        <div className="font-mono font-bold text-slate-800 truncate">{p.numero_polizza}</div>
                        <div className="text-xs text-slate-600 mt-0.5">{p.ramo} · {p.prodotto || "—"}</div>
                        {p.compagnia_nome && (
                            <div className="text-[11px] text-slate-500 mt-1 flex items-center gap-1">
                                <Building2 size={11} /> {p.compagnia_nome}
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Corpo con dati */}
            <div className="p-5 space-y-3">
                <div className="grid grid-cols-2 gap-3 text-xs">
                    <InfoBlock label="Effetto" value={fmtDate(p.effetto)} />
                    <InfoBlock label="Scadenza" value={fmtDate(p.scadenza)} highlight={inScadenza ? "amber" : scaduta ? "rose" : null} />
                    <InfoBlock label="Frazionamento" value={p.frazionamento || "annuale"} />
                    <InfoBlock label="Premio annuo" value={`€ ${Number(p.premio_lordo || 0).toFixed(2)}`} bold />
                    {p.targa && <InfoBlock label="Targa" value={p.targa} mono />}
                </div>

                {/* Prossima quietanza / Arretrati */}
                {p.stats_titoli && (p.stats_titoli.da_pagare > 0 || p.stats_titoli.arretrati > 0) && (
                    <div className={`rounded-xl p-3 flex items-center gap-3 ${
                        p.stats_titoli.arretrati > 0 ? "bg-rose-50 border border-rose-200" : "bg-amber-50 border border-amber-200"
                    }`}>
                        <Wallet size={18} className={p.stats_titoli.arretrati > 0 ? "text-rose-600" : "text-amber-600"} />
                        <div className="flex-1 min-w-0 text-xs">
                            {p.stats_titoli.arretrati > 0 ? (
                                <div className="font-semibold text-rose-700">
                                    ⚠ {p.stats_titoli.arretrati} rat{p.stats_titoli.arretrati === 1 ? "a arretrata" : "e arretrate"}
                                </div>
                            ) : (
                                <div className="font-semibold text-amber-700">
                                    Prossima quietanza il {fmtDate(p.stats_titoli.prossima_scadenza)}
                                    {p.stats_titoli.prossimo_importo && ` — € ${Number(p.stats_titoli.prossimo_importo).toFixed(2)}`}
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {/* Azioni + toggle documenti */}
                <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-100 text-[11px] text-slate-500">
                    <button onClick={toggleTitoli}
                            data-testid={`polizza-titoli-toggle-${p.id}`}
                            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-semibold text-xs transition-all ${
                                openTitoli
                                    ? "bg-emerald-600 text-white shadow"
                                    : "bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                            }`}>
                        <Wallet size={12} /> Titoli & Quietanze
                        <ChevronRight size={12} className={`transition-transform ${openTitoli ? "rotate-90" : ""}`} />
                    </button>
                    {p.n_allegati > 0 && (
                        <button onClick={toggleDocs}
                                data-testid={`polizza-docs-toggle-${p.id}`}
                                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-semibold text-xs transition-all ${
                                    openDocs
                                        ? "bg-violet-600 text-white shadow"
                                        : "bg-violet-50 text-violet-700 hover:bg-violet-100"
                                }`}>
                            <FolderOpen size={12} /> {p.n_allegati} document{p.n_allegati === 1 ? "o" : "i"}
                            <ChevronRight size={12} className={`transition-transform ${openDocs ? "rotate-90" : ""}`} />
                        </button>
                    )}
                    {p.n_sinistri > 0 && (
                        <span className="inline-flex items-center gap-1 bg-rose-50 text-rose-700 px-2 py-1 rounded font-semibold">
                            <AlertCircle size={11} /> {p.n_sinistri} sinistr{p.n_sinistri === 1 ? "o" : "i"}
                        </span>
                    )}
                    <button
                        onClick={() => window.open(`${API}/polizze/${p.id}/pdf?token=${localStorage.getItem("portale_token")}`, "_blank")}
                        className="ml-auto text-xs px-3 py-1.5 rounded-lg bg-sky-50 text-sky-700 hover:bg-sky-100 inline-flex items-center gap-1 font-medium"
                        data-testid={`polizza-pdf-${p.id}`}>
                        <Download size={12} /> PDF Polizza
                    </button>
                </div>

                {/* Sezione titoli/quietanze espansa */}
                {openTitoli && (
                    <div className="bg-emerald-50/40 rounded-xl p-3 space-y-2 border border-emerald-100">
                        {titoli === null ? <div className="text-xs text-slate-400 py-2 text-center">Caricamento…</div>
                          : titoli.length === 0 ? <div className="text-xs text-slate-400 py-2 text-center">Nessun titolo</div>
                          : titoli.map((t) => <TitoloMini key={t.id} t={t} oggi={oggi} />)}
                    </div>
                )}

                {/* Sezione documenti espansa */}
                {openDocs && (
                    <div className="bg-violet-50/50 rounded-xl p-3 space-y-1.5 border border-violet-100">
                        {docs === null ? <div className="text-xs text-slate-400 py-2">Caricamento…</div>
                          : docs.length === 0 ? <div className="text-xs text-slate-400 py-2">Nessun documento condiviso dall&apos;agenzia</div>
                          : docs.map((d) => <AllegatoRow key={d.id} d={d} />)}
                    </div>
                )}

                {p.is_libro_matricola && (p.applicazioni?.length || 0) > 0 && (
                    <div className="pt-2 border-t border-slate-100">
                        <button onClick={() => setOpenApps(!openApps)}
                            className="text-xs text-violet-700 hover:underline inline-flex items-center gap-1 font-medium">
                            <Car size={12} /> {openApps ? "Nascondi" : "Mostra"} {p.applicazioni.length} veicoli
                            <ChevronRight size={12} className={`transition ${openApps ? "rotate-90" : ""}`} />
                        </button>
                        {openApps && (
                            <div className="mt-2 space-y-1.5 max-h-96 overflow-y-auto">
                                {p.applicazioni.filter((a) => (a.stato || "attiva") === "attiva").map((a) => (
                                    <VeicoloRow key={a.id} a={a} />
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}

// Riga compatta di un titolo dentro l'elenco storico di una polizza
function TitoloMini({ t, oggi }) {
    const [openQuiet, setOpenQuiet] = useState(false);
    const arretrato = t.stato === "da_incassare" && (t.scadenza || "") < oggi;
    const stato = arretrato ? { l: "ARRETRATO", c: "bg-rose-100 text-rose-800", ico: "⚠" }
        : t.stato === "incassato" ? { l: "PAGATO", c: "bg-emerald-100 text-emerald-800", ico: "✓" }
        : t.stato === "insoluto" ? { l: "INSOLUTO", c: "bg-rose-100 text-rose-800", ico: "✗" }
        : t.stato === "annullato" ? { l: "ANNULLATO", c: "bg-slate-100 text-slate-600", ico: "—" }
        : t.stato === "storno" ? { l: "STORNO", c: "bg-slate-100 text-slate-600", ico: "↺" }
        : { l: "DA PAGARE", c: "bg-amber-100 text-amber-800", ico: "◷" };
    return (
        <div className="bg-white rounded-lg border border-emerald-100 overflow-hidden">
            <div className="p-2.5 flex flex-wrap items-center gap-2">
                <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${stato.c}`}>
                    {stato.ico} {stato.l}
                </span>
                <span className="text-xs text-slate-500">
                    scad. <span className="font-semibold text-slate-700">{fmtDate(t.scadenza)}</span>
                </span>
                {t.data_incasso && (
                    <span className="text-xs text-emerald-700">
                        · pagato il <span className="font-semibold">{fmtDate(t.data_incasso)}</span>
                    </span>
                )}
                <span className="ml-auto text-sm font-bold text-emerald-700">
                    € {Number(t.importo_lordo || 0).toFixed(2)}
                </span>
                {t.n_allegati_cliente > 0 && (
                    <button onClick={() => setOpenQuiet(!openQuiet)}
                            data-testid={`titolo-quiet-${t.id}`}
                            className={`inline-flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-semibold transition-all ${
                                openQuiet
                                    ? "bg-emerald-600 text-white shadow"
                                    : "bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                            }`}>
                        <FolderOpen size={10} /> quietanza
                        <ChevronRight size={10} className={`transition-transform ${openQuiet ? "rotate-90" : ""}`} />
                    </button>
                )}
            </div>
            {openQuiet && (t.quietanze || []).length > 0 && (
                <div className="border-t border-slate-100 bg-emerald-50/40 p-2 space-y-1">
                    {t.quietanze.map((d) => <AllegatoRow key={d.id} d={d} small />)}
                </div>
            )}
        </div>
    );
}

// Riga singolo allegato (nome + tipo + download)
function AllegatoRow({ d, small }) {
    const ext = (d.nome_file || "").split(".").pop()?.toLowerCase();
    const isImg = /^(jpg|jpeg|png|webp|heic|gif)$/.test(ext);
    const isPdf = ext === "pdf";
    const color = isPdf ? "bg-red-100 text-red-600" :
                  isImg ? "bg-sky-100 text-sky-600" :
                  "bg-slate-100 text-slate-600";
    return (
        <a href={`${API}/allegati/${d.id}/download?token=${localStorage.getItem("portale_token")}`}
           target="_blank" rel="noreferrer"
           className={`flex items-center gap-2 bg-white rounded-lg hover:shadow-sm transition-shadow border border-slate-100 ${small ? "px-2 py-1.5" : "px-3 py-2"}`}
           data-testid={`allegato-${d.id}`}>
            <div className={`${small ? "w-7 h-7" : "w-8 h-8"} rounded-md ${color} flex items-center justify-center shrink-0`}>
                <FolderOpen size={small ? 12 : 14} />
            </div>
            <div className="flex-1 min-w-0">
                <div className={`${small ? "text-[11px]" : "text-xs"} font-medium text-slate-800 truncate`}>{d.nome_file}</div>
                <div className="text-[10px] text-slate-400 flex items-center gap-1.5">
                    <span className="uppercase">{d.categoria || (isPdf ? "PDF" : isImg ? "immagine" : "documento")}</span>
                    {d.created_at && <span>· {fmtDate(d.created_at)}</span>}
                </div>
            </div>
            <Download size={12} className="text-violet-600 shrink-0" />
        </a>
    );
}

// Riga veicolo (targa + modello + documenti espandibili)
function VeicoloRow({ a }) {
    const [openDocs, setOpenDocs] = useState(false);
    const [docs, setDocs] = useState(null);
    const toggleDocs = async () => {
        const next = !openDocs;
        setOpenDocs(next);
        if (next && docs === null) {
            try {
                const r = await clientApi.get("/allegati/by-entita",
                    { params: { entita_tipo: "applicazione_matricola", entita_id: a.id } });
                setDocs(r.data);
            } catch { setDocs([]); }
        }
    };
    return (
        <div className="bg-white rounded-lg border border-slate-100 overflow-hidden">
            <div className="p-2.5 flex flex-wrap gap-2 items-center">
                <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center shrink-0 shadow-sm">
                    <Car size={14} className="text-white" />
                </div>
                <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono font-bold text-violet-700 text-sm">{a.targa}</span>
                        {a.classe_veicolo && (
                            <span className="text-[10px] uppercase text-slate-400 tracking-wider">{a.classe_veicolo}</span>
                        )}
                    </div>
                    <div className="text-xs text-slate-600 truncate">
                        {[a.marca, a.modello].filter(Boolean).join(" ") || "—"}
                        {a.intestatario && <span className="text-slate-400"> · {a.intestatario}</span>}
                    </div>
                </div>
                <button onClick={toggleDocs}
                        data-testid={`veicolo-docs-${a.id}`}
                        className={`inline-flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-semibold transition-all ${
                            openDocs
                                ? "bg-violet-600 text-white shadow"
                                : "bg-violet-50 text-violet-700 hover:bg-violet-100"
                        }`}>
                    <FolderOpen size={10} />
                    documenti
                    <ChevronRight size={10} className={`transition-transform ${openDocs ? "rotate-90" : ""}`} />
                </button>
            </div>
            {openDocs && (
                <div className="border-t border-slate-100 bg-violet-50/40 p-2 space-y-1">
                    {docs === null ? <div className="text-[10px] text-slate-400 py-1 text-center">Caricamento…</div>
                      : docs.length === 0 ? <div className="text-[10px] text-slate-500 py-1 text-center">Nessun documento (libretto/atto vendita/…)</div>
                      : docs.map((d) => <AllegatoRow key={d.id} d={d} small />)}
                </div>
            )}
        </div>
    );
}

function InfoBlock({ label, value, highlight, bold, mono }) {
    const hl = highlight === "amber" ? "text-amber-700" :
                highlight === "rose" ? "text-rose-700" : "text-slate-700";
    return (
        <div>
            <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">{label}</div>
            <div className={`${hl} mt-0.5 ${bold ? "font-bold" : ""} ${mono ? "font-mono" : ""}`}>{value || "—"}</div>
        </div>
    );
}

function fmtDate(s) {
    if (!s) return "—";
    try {
        const d = new Date(s);
        if (isNaN(d.getTime())) return s;
        return d.toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric" });
    } catch { return s; }
}

function addDaysISO(iso, days) {
    try {
        const d = new Date(iso);
        d.setDate(d.getDate() + days);
        return d.toISOString().slice(0, 10);
    } catch { return iso; }
}

// ─── TITOLI ───────────────────────────────────────────────────────────
function TitoliView() {
    const [tits, setTits] = useState(null);
    const [filtro, setFiltro] = useState("da_pagare"); // da_pagare | pagati | tutti
    useEffect(() => { clientApi.get("/titoli").then((r) => setTits(r.data)); }, []);
    if (!tits) return <Loading />;

    const oggi = new Date().toISOString().slice(0, 10);
    const daPagare = tits.filter((t) => t.stato === "da_incassare");
    const arretrati = daPagare.filter((t) => (t.scadenza || "") < oggi);
    const pagati = tits.filter((t) => t.stato === "incassato");
    const visibili = filtro === "da_pagare" ? daPagare
                   : filtro === "pagati" ? pagati
                   : tits;
    const totDaPagare = daPagare.reduce((s, t) => s + (Number(t.importo_lordo) || 0), 0);

    return (
        <div>
            <SectionHeader icon={Wallet} title="Titoli & Quietanze"
                subtitle="Lo storico dei tuoi pagamenti e le rate in scadenza"
                gradient={SEZIONI_COLORS.titoli} />

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
                <StatCard icon={Clock} value={daPagare.length} label="Da pagare" color="amber" />
                <StatCard icon={AlertCircle} value={arretrati.length} label="Arretrati" color="rose" />
                <StatCard icon={CheckCircle2} value={pagati.length} label="Pagati" color="emerald" />
                <StatCard icon={Wallet} value={`€ ${totDaPagare.toFixed(0)}`} label="Totale dovuto" color="violet" />
            </div>

            <div className="flex gap-2 mb-4 overflow-x-auto pb-1">
                {[["da_pagare", "Da pagare", daPagare.length],
                  ["pagati", "Pagati", pagati.length],
                  ["tutti", "Tutti", tits.length]].map(([k, l, n]) => (
                    <button key={k} onClick={() => setFiltro(k)}
                        data-testid={`titoli-filter-${k}`}
                        className={`px-4 py-1.5 rounded-full text-sm font-medium transition-all whitespace-nowrap ${
                            filtro === k
                                ? "bg-gradient-to-r from-emerald-500 to-teal-600 text-white shadow"
                                : "bg-white text-slate-600 border border-slate-200 hover:border-emerald-400"
                        }`}>{l} · {n}</button>
                ))}
            </div>

            {visibili.length === 0 ? (
                <EmptyState icon={Wallet} testo="Nessun titolo in questa categoria" />
            ) : (
                <div className="space-y-3">
                    {visibili.map((t) => <TitoloCard key={t.id} t={t} oggi={oggi} />)}
                </div>
            )}
        </div>
    );
}

function TitoloCard({ t, oggi }) {
    const arretrato = t.stato === "da_incassare" && (t.scadenza || "") < oggi;
    const badge = arretrato ? { l: "ARRETRATO", c: "bg-rose-100 text-rose-800", icon: "⚠" }
        : t.stato === "incassato" ? { l: "PAGATO", c: "bg-emerald-100 text-emerald-800", icon: "✓" }
        : t.stato === "insoluto" ? { l: "INSOLUTO", c: "bg-rose-100 text-rose-800", icon: "✗" }
        : t.stato === "annullato" ? { l: "ANNULLATO", c: "bg-slate-100 text-slate-600", icon: "—" }
        : t.stato === "storno" ? { l: "STORNO", c: "bg-slate-100 text-slate-600", icon: "↺" }
        : { l: "DA PAGARE", c: "bg-amber-100 text-amber-800", icon: "◷" };

    return (
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-4 sm:p-5 hover:shadow-md transition-shadow">
            <div className="flex items-start gap-4">
                {/* Icona ramo */}
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center shadow shrink-0">
                    <IconForRamo ramo={t.polizza_ramo} className="text-white" />
                </div>

                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                        <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${badge.c}`}>
                            {badge.icon} {badge.l}
                        </span>
                        {t.polizza_ramo && (
                            <span className="text-[10px] uppercase text-slate-500 font-semibold">
                                {t.polizza_ramo}
                            </span>
                        )}
                        {t.polizza_targa && (
                            <span className="text-[10px] font-mono bg-slate-100 text-slate-700 px-2 py-0.5 rounded">
                                🚗 {t.polizza_targa}
                            </span>
                        )}
                    </div>

                    <div className="flex items-baseline gap-2 flex-wrap">
                        <span className="font-mono font-bold text-slate-800">
                            {t.polizza_numero || t.numero_titolo || "—"}
                        </span>
                        <span className="text-2xl font-bold text-emerald-700">
                            € {Number(t.importo_lordo || 0).toFixed(2)}
                        </span>
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-1 mt-2 text-xs text-slate-600">
                        <div>
                            <span className="text-slate-400">Scadenza: </span>
                            <span className={arretrato ? "text-rose-700 font-semibold" : "font-medium"}>
                                {fmtDate(t.scadenza)}
                            </span>
                        </div>
                        {t.data_incasso && (
                            <div>
                                <span className="text-slate-400">Pagato il: </span>
                                <span className="text-emerald-700 font-medium">{fmtDate(t.data_incasso)}</span>
                            </div>
                        )}
                        {t.mezzo_pagamento && (
                            <div>
                                <span className="text-slate-400">Metodo: </span>
                                <span className="capitalize">{t.mezzo_pagamento}</span>
                            </div>
                        )}
                        {t.compagnia_nome && (
                            <div className="truncate">
                                <span className="text-slate-400">Compagnia: </span>
                                <span>{t.compagnia_nome}</span>
                            </div>
                        )}
                    </div>

                    {t.n_allegati_cliente > 0 && (
                        <div className="mt-2 flex items-center gap-1 text-[11px] text-sky-700">
                            <FolderOpen size={12} /> {t.n_allegati_cliente} quietanz{t.n_allegati_cliente === 1 ? "a disponibile" : "e disponibili"}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

// ─── DOCUMENTI + UPLOAD ───────────────────────────────────────────────
function DocumentiView() {
    const [docs, setDocs] = useState(null);
    const [uploading, setUploading] = useState(false);
    const load = () => clientApi.get("/documenti").then((r) => setDocs(r.data));
    useEffect(() => { load(); }, []);
    const onFile = async (e) => {
        const f = e.target.files?.[0];
        if (!f) return;
        setUploading(true);
        try {
            const fd = new FormData();
            fd.append("file", f);
            fd.append("categoria", "caricato_da_cliente");
            await clientApi.post("/documenti/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
            toast.success("Documento caricato, l'agenzia lo verificherà");
            load();
        } catch (err) { toast.error("Errore upload"); }
        finally { setUploading(false); e.target.value = ""; }
    };
    return (
        <div>
            <SectionHeader icon={FolderOpen} title="Documenti"
                subtitle="Carica e consulta i tuoi documenti — Carta d&apos;identità, patente, contratti…"
                gradient={SEZIONI_COLORS.documenti} />

            {/* Upload hero */}
            <div className="bg-gradient-to-br from-amber-500 via-orange-500 to-red-500 rounded-2xl p-6 text-white shadow-lg mb-6 relative overflow-hidden">
                <div className="absolute -right-8 -top-8 w-40 h-40 rounded-full bg-white/10" />
                <div className="absolute -right-16 top-8 w-32 h-32 rounded-full bg-white/5" />
                <div className="relative">
                    <div className="flex items-center gap-3 mb-2">
                        <div className="w-11 h-11 rounded-xl bg-white/20 backdrop-blur flex items-center justify-center">
                            <Upload size={22} />
                        </div>
                        <div className="font-bold text-lg">Carica un documento</div>
                    </div>
                    <div className="text-sm text-white/90 mb-4">
                        📸 Scatta una foto o 📄 carica un PDF direttamente dal tuo dispositivo
                    </div>
                    <label className="inline-block cursor-pointer">
                        <input type="file" accept="application/pdf,image/*" capture="environment"
                            className="hidden" onChange={onFile} disabled={uploading}
                            data-testid="portale-upload-input" />
                        <span className="inline-flex items-center gap-2 px-5 py-2.5 bg-white text-orange-700 rounded-xl font-bold text-sm shadow-md hover:scale-105 transition-transform">
                            <Upload size={16} /> {uploading ? "Caricamento…" : "Scegli file"}
                        </span>
                    </label>
                </div>
            </div>

            <div className="flex items-center gap-2 mb-3">
                <FolderOpen size={16} className="text-slate-400" />
                <h3 className="text-sm font-semibold text-slate-600 uppercase tracking-wider">I miei documenti</h3>
                <span className="text-xs text-slate-400">({docs?.length || 0})</span>
            </div>
            {!docs ? <Loading />
              : docs.length === 0 ? <EmptyState icon={FolderOpen} testo="Nessun documento pubblicato dall'agenzia" />
              : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {docs.map((d) => {
                        const ext = (d.nome_file || "").split(".").pop()?.toLowerCase();
                        const isImg = /^(jpg|jpeg|png|webp|heic)$/.test(ext);
                        const isPdf = ext === "pdf";
                        const iconColor = isPdf ? "text-red-500 bg-red-50" : isImg ? "text-sky-500 bg-sky-50" : "text-slate-500 bg-slate-50";
                        return (
                            <div key={d.id} className="bg-white rounded-xl p-4 shadow-sm border border-slate-100 flex items-center gap-3 hover:shadow-md transition-shadow">
                                <div className={`w-11 h-11 rounded-xl ${iconColor} flex items-center justify-center shrink-0`}>
                                    <FolderOpen size={20} />
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="text-sm font-semibold truncate text-slate-800">{d.nome_file}</div>
                                    <div className="flex items-center gap-2 mt-0.5">
                                        <span className="text-[10px] text-slate-500 uppercase tracking-wider">{d.categoria || "documento"}</span>
                                        {d.created_at && (
                                            <span className="text-[10px] text-slate-400">· {fmtDate(d.created_at)}</span>
                                        )}
                                    </div>
                                </div>
                                <a href={`${API.replace('/portale','')}/allegati/${d.id}/download?token=${localStorage.getItem("portale_token")}`}
                                   target="_blank" rel="noreferrer"
                                   className="p-2 rounded-lg bg-amber-50 text-amber-700 hover:bg-amber-100 transition-colors"
                                   title="Scarica">
                                    <Download size={16} />
                                </a>
                            </div>
                        );
                    })}
                </div>
              )}
        </div>
    );
}

// ─── SINISTRI ─────────────────────────────────────────────────────────
function SinistriView() {
    const [sin, setSin] = useState(null);
    useEffect(() => { clientApi.get("/sinistri").then((r) => setSin(r.data)); }, []);
    if (!sin) return <Loading />;

    const aperti = sin.filter((s) => s.stato === "aperto" || s.stato === "in_istruttoria");
    const chiusi = sin.filter((s) => s.stato === "liquidato" || s.stato === "chiuso_senza_seguito");

    return (
        <div>
            <SectionHeader icon={AlertCircle} title="I miei sinistri"
                subtitle="Segui lo stato di ogni tuo sinistro"
                gradient={SEZIONI_COLORS.sinistri} />

            <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-6">
                <StatCard icon={AlertCircle} value={sin.length} label="Totali" color="rose" />
                <StatCard icon={Clock} value={aperti.length} label="In corso" color="amber" />
                <StatCard icon={CheckCircle2} value={chiusi.length} label="Chiusi" color="emerald" />
            </div>

            {sin.length === 0 ? (
                <EmptyState icon={AlertCircle} testo="Nessun sinistro registrato" />
            ) : (
                <div className="space-y-3">
                    {sin.map((s) => <SinistroCard key={s.id} s={s} />)}
                </div>
            )}
        </div>
    );
}

function SinistroCard({ s }) {
    const stato = s.stato || "aperto";
    const badge = stato === "aperto" ? { l: "APERTO", c: "bg-amber-100 text-amber-800" }
        : stato === "in_istruttoria" ? { l: "IN ISTRUTTORIA", c: "bg-sky-100 text-sky-800" }
        : stato === "liquidato" ? { l: "LIQUIDATO", c: "bg-emerald-100 text-emerald-800" }
        : stato === "chiuso_senza_seguito" ? { l: "CHIUSO", c: "bg-slate-100 text-slate-600" }
        : stato === "respinto" ? { l: "RESPINTO", c: "bg-rose-100 text-rose-700" }
        : { l: stato.toUpperCase(), c: "bg-slate-100 text-slate-600" };
    return (
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-4 sm:p-5 hover:shadow-md transition-shadow">
            <div className="flex items-start gap-4">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-rose-500 to-red-600 flex items-center justify-center shadow shrink-0">
                    <AlertCircle className="text-white" size={22} />
                </div>
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                        <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${badge.c}`}>
                            {badge.l}
                        </span>
                        {s.polizza_ramo && (
                            <span className="text-[10px] uppercase text-slate-500 font-semibold">{s.polizza_ramo}</span>
                        )}
                        {s.polizza_targa && (
                            <span className="text-[10px] font-mono bg-slate-100 text-slate-700 px-2 py-0.5 rounded">🚗 {s.polizza_targa}</span>
                        )}
                    </div>
                    <div className="font-mono font-bold text-slate-800">{s.numero_sinistro || s.numero_interno || "—"}</div>
                    {s.tipologia_sinistro && (
                        <div className="text-sm text-slate-600 mt-0.5">{s.tipologia_sinistro}</div>
                    )}
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1 mt-2 text-xs text-slate-600">
                        {s.data_avvenimento && (
                            <div><span className="text-slate-400">Evento: </span>{fmtDate(s.data_avvenimento)}</div>
                        )}
                        {s.data_denuncia && (
                            <div><span className="text-slate-400">Denuncia: </span>{fmtDate(s.data_denuncia)}</div>
                        )}
                        {s.polizza_numero && (
                            <div className="truncate"><span className="text-slate-400">Polizza: </span><span className="font-mono">{s.polizza_numero}</span></div>
                        )}
                        {s.compagnia_nome && (
                            <div className="truncate col-span-2"><span className="text-slate-400">Compagnia: </span>{s.compagnia_nome}</div>
                        )}
                        {s.luogo && (
                            <div className="truncate col-span-2"><span className="text-slate-400">Luogo: </span>{s.luogo}</div>
                        )}
                    </div>
                    {s.n_allegati > 0 && (
                        <div className="mt-2 text-[11px] text-sky-700 inline-flex items-center gap-1">
                            <FolderOpen size={12} /> {s.n_allegati} allegat{s.n_allegati === 1 ? "o" : "i"}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

// ─── SERVIZI ──────────────────────────────────────────────────────────
function ServiziView({ agenzia }) {
    const [srv, setSrv] = useState(null);
    useEffect(() => { clientApi.get("/servizi").then((r) => setSrv(r.data)); }, []);
    if (!srv) return <Loading />;
    return (
        <div>
            <SectionHeader icon={Phone} title="Servizi & Assistenza"
                subtitle="Contatti dell'agenzia e link utili"
                gradient={SEZIONI_COLORS.servizi} />

            {/* Card contatto agenzia */}
            {agenzia && (
                <div className="bg-gradient-to-br from-indigo-500 to-blue-600 rounded-2xl p-6 text-white shadow-lg mb-6 relative overflow-hidden">
                    <div className="absolute -right-8 -top-8 w-40 h-40 rounded-full bg-white/10" />
                    <div className="relative">
                        <div className="text-[11px] uppercase tracking-wider text-white/80 mb-1">La tua agenzia</div>
                        <div className="text-xl font-bold mb-3">{agenzia.ragione_sociale}</div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                            {agenzia.telefono && (
                                <a href={`tel:${agenzia.telefono}`} className="flex items-center gap-2 hover:underline">
                                    <Phone size={14} /> {agenzia.telefono}
                                </a>
                            )}
                            {agenzia.email && (
                                <a href={`mailto:${agenzia.email}`} className="flex items-center gap-2 hover:underline">
                                    <span className="text-xs">📧</span> {agenzia.email}
                                </a>
                            )}
                            {agenzia.indirizzo && (
                                <div className="flex items-center gap-2 col-span-2 text-white/90">
                                    <Building2 size={14} /> {agenzia.indirizzo}
                                    {agenzia.comune && `, ${agenzia.comune}`}
                                    {agenzia.provincia && ` (${agenzia.provincia})`}
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}

            {srv.length > 0 && (
                <>
                    <h3 className="text-sm font-semibold text-slate-600 uppercase tracking-wider mb-3">Link utili</h3>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {srv.map((s, i) => (
                            <a key={i} href={s.url} target="_blank" rel="noreferrer"
                               className="bg-white hover:bg-sky-50 rounded-xl p-4 shadow-sm border border-slate-100 flex items-center gap-3 transition hover:shadow-md">
                                <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-indigo-500 to-blue-600 text-white flex items-center justify-center">
                                    <Building2 size={20} />
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="font-semibold text-slate-800">{s.nome}</div>
                                    <div className="text-xs text-slate-500">{s.descrizione}</div>
                                </div>
                                <ChevronRight size={18} className="text-slate-400" />
                            </a>
                        ))}
                    </div>
                </>
            )}
        </div>
    );
}

function EmptyState({ icon: Icon, testo }) {
    return (
        <div className="text-center py-16 text-slate-400">
            <Icon size={48} className="mx-auto mb-3 opacity-50" />
            <div>{testo}</div>
        </div>
    );
}

// ─── CHAT — messaggistica col cliente ↔ agenzia ─────────────────────
function ChatView() {
    const [msgs, setMsgs] = useState(null);
    const [text, setText] = useState("");
    const [file, setFile] = useState(null);
    const [sending, setSending] = useState(false);
    const scrollRef = useState(null)[0];
    const fileInputRef = useRef(null);

    const load = () => clientApi.get("/chat/messaggi").then((r) => setMsgs(r.data)).catch(() => setMsgs([]));
    useEffect(() => {
        load();
        const t = setInterval(load, 8000);
        return () => clearInterval(t);
    }, []);

    const invia = async (e) => {
        e?.preventDefault();
        if ((!text.trim() && !file) || sending) return;
        setSending(true);
        try {
            if (file) {
                const fd = new FormData();
                fd.append("testo", text);
                fd.append("file", file);
                await clientApi.post("/chat/messaggi", fd, {
                    headers: { "Content-Type": "multipart/form-data" },
                });
            } else {
                await clientApi.post("/chat/messaggi", { testo: text });
            }
            setText(""); setFile(null);
            if (fileInputRef.current) fileInputRef.current.value = "";
            load();
        } catch (err) {
            toast.error(err.response?.data?.detail || "Errore invio");
        } finally { setSending(false); }
    };

    const downloadAllegato = async (allegatoId, nomeFile) => {
        try {
            const r = await clientApi.get(`/chat/allegato/${allegatoId}`, { responseType: "blob" });
            const url = URL.createObjectURL(r.data);
            const a = document.createElement("a");
            a.href = url; a.download = nomeFile || "allegato";
            document.body.appendChild(a); a.click(); a.remove();
            URL.revokeObjectURL(url);
        } catch { toast.error("Errore download"); }
    };

    return (
        <div>
            <SectionHeader icon={MessageSquare} title="Chat con l'agenzia"
                subtitle="Scrivi in qualsiasi momento — ti risponderemo il prima possibile"
                gradient={SEZIONI_COLORS.chat} />
            <div className="bg-white rounded-2xl shadow-sm border border-slate-100 flex flex-col overflow-hidden" style={{ height: "60vh", minHeight: 420 }}>
                <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-2 bg-slate-50 rounded-t-xl">
                    {msgs === null ? (
                        <div className="text-center text-slate-400 py-8">Caricamento…</div>
                    ) : msgs.length === 0 ? (
                        <div className="text-center text-slate-400 py-8">
                            <MessageSquare size={28} className="mx-auto mb-2 opacity-50" />
                            Nessun messaggio. Scrivi alla tua agenzia!
                        </div>
                    ) : msgs.map((m) => {
                        const mine = m.direzione === "in"; // dal cliente
                        return (
                            <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`} data-testid={`chat-msg-${m.id}`}>
                                <div className={`max-w-[80%] px-3 py-2 rounded-lg text-sm ${mine
                                    ? "bg-sky-600 text-white"
                                    : "bg-white border border-slate-200 text-slate-800"}`}>
                                    {m.testo && <div className="whitespace-pre-wrap break-words">{m.testo}</div>}
                                    {m.allegato_id && (
                                        <button onClick={() => downloadAllegato(m.allegato_id, m.allegato_nome)}
                                                className={`mt-1 inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded ${mine
                                                    ? "bg-sky-700 hover:bg-sky-800 text-white"
                                                    : "bg-slate-100 hover:bg-slate-200 text-slate-700"}`}
                                                data-testid={`chat-alleg-${m.allegato_id}`}>
                                            <Download size={12} /> {m.allegato_nome || "Allegato"}
                                        </button>
                                    )}
                                    <div className={`text-[10px] mt-1 ${mine ? "text-sky-100" : "text-slate-400"}`}>
                                        {!mine && m.mittente_admin_nome && (<span>{m.mittente_admin_nome} · </span>)}
                                        {m.created_at ? new Date(m.created_at).toLocaleString("it-IT",
                                            { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : ""}
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
                {file && (
                    <div className="border-t border-slate-200 bg-sky-50 px-3 py-2 flex items-center justify-between text-xs">
                        <span className="text-sky-800 truncate">📎 {file.name} ({(file.size / 1024).toFixed(0)} KB)</span>
                        <button onClick={() => { setFile(null); if (fileInputRef.current) fileInputRef.current.value = ""; }}
                                className="text-slate-500 hover:text-rose-600">
                            <X size={14} />
                        </button>
                    </div>
                )}
                <form onSubmit={invia} className="border-t border-slate-200 p-3 flex gap-2 bg-white rounded-b-xl">
                    <input ref={fileInputRef} type="file" hidden accept="image/*,.pdf,.doc,.docx,.xls,.xlsx"
                           onChange={(e) => setFile(e.target.files?.[0] || null)}
                           data-testid="portale-chat-file" />
                    <button type="button" onClick={() => fileInputRef.current?.click()}
                            className="px-3 rounded-lg border border-slate-300 hover:bg-slate-50 text-slate-600"
                            data-testid="portale-chat-attach"
                            title="Allega file">
                        <Paperclip size={16} />
                    </button>
                    <input type="text" value={text} onChange={(e) => setText(e.target.value)}
                           placeholder="Scrivi un messaggio…"
                           className="flex-1 px-3 py-2.5 border border-slate-300 rounded-lg text-sm focus:border-sky-500 focus:ring-2 focus:ring-sky-200 outline-none"
                           data-testid="portale-chat-input" />
                    <button type="submit" disabled={sending || (!text.trim() && !file)}
                            className="px-4 rounded-lg bg-sky-600 hover:bg-sky-700 text-white disabled:opacity-40"
                            data-testid="portale-chat-send">
                        <Send size={16} />
                    </button>
                </form>
            </div>
            <div className="text-[11px] text-slate-400 text-center">
                Ti risponderemo il prima possibile durante gli orari di apertura dell&apos;agenzia.
            </div>
        </div>
    );
}
