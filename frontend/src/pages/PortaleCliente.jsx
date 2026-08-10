/**
 * PortaleCliente — Dashboard self-service del cliente finale.
 *
 * Layout responsive: sidebar su desktop, hamburger menu su mobile.
 * Design fresh consumer-friendly con colori chiari.
 *
 * Sezioni: Profilo · Polizze · Titoli · Documenti · Sinistri · Servizi
 * Le polizze Libro Matricola mostrano inline le applicazioni (targhe/veicoli).
 */
import { useEffect, useState } from "react";
import { toast, Toaster } from "sonner";
import axios from "axios";
import {
    User, FileText, Wallet, FolderOpen, AlertCircle, Phone,
    Menu, X, LogOut, Upload, Download, ChevronRight, Building2, Car, MessageSquare, Send,
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api/portale`;

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
    const [sezione, setSezione] = useState("polizze");
    const [menuOpen, setMenuOpen] = useState(false);

    useEffect(() => {
        if (!token) return;
        clientApi.get("/me").then((r) => setCliente(r.data))
            .catch(() => { localStorage.removeItem("portale_token"); setToken(null); });
    }, [token]);

    const logout = () => {
        localStorage.removeItem("portale_token");
        setToken(null); setCliente(null);
    };

    if (!token) return <LoginScreen onLogin={(t) => { localStorage.setItem("portale_token", t); setToken(t); }} />;
    if (!cliente) return <div className="p-8 text-slate-500 text-center">Caricamento…</div>;

    return (
        <div className="min-h-screen bg-gradient-to-br from-sky-50 via-white to-blue-50">
            <Toaster position="top-center" richColors />
            {/* Header mobile */}
            <header className="lg:hidden sticky top-0 z-40 bg-white border-b border-slate-200 p-3 flex items-center gap-3 shadow-sm">
                <button onClick={() => setMenuOpen(true)} className="p-2 rounded hover:bg-slate-100" aria-label="Menu">
                    <Menu size={22} />
                </button>
                <div className="flex-1 font-bold text-sky-700 text-sm truncate">{cliente.nome}</div>
                <button onClick={logout} className="p-2 rounded hover:bg-slate-100" title="Esci">
                    <LogOut size={18} />
                </button>
            </header>

            <div className="flex">
                {/* Sidebar desktop */}
                <aside className="hidden lg:flex flex-col w-64 min-h-screen bg-white border-r border-slate-200 p-5">
                    <div className="mb-6">
                        <div className="text-[11px] uppercase tracking-wider text-sky-600 font-semibold">Portale Cliente</div>
                        <div className="text-lg font-bold text-slate-800 truncate">{cliente.nome}</div>
                        {cliente.email && <div className="text-[11px] text-slate-400 truncate">{cliente.email}</div>}
                    </div>
                    <NavList sezione={sezione} onSelect={setSezione} />
                    <button onClick={logout} className="mt-auto pt-4 flex items-center gap-2 text-sm text-slate-500 hover:text-rose-600">
                        <LogOut size={16} /> Esci
                    </button>
                </aside>

                {/* Drawer mobile */}
                {menuOpen && (
                    <div className="lg:hidden fixed inset-0 z-50 bg-black/40" onClick={() => setMenuOpen(false)}>
                        <aside className="w-72 h-full bg-white p-5 overflow-y-auto" onClick={(e) => e.stopPropagation()}>
                            <div className="flex items-center justify-between mb-6">
                                <div className="font-bold text-sky-700">{cliente.nome}</div>
                                <button onClick={() => setMenuOpen(false)}><X size={22} /></button>
                            </div>
                            <NavList sezione={sezione} onSelect={(k) => { setSezione(k); setMenuOpen(false); }} />
                        </aside>
                    </div>
                )}

                {/* Content */}
                <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-6xl mx-auto w-full">
                    {sezione === "profilo" && <ProfiloView cliente={cliente} onReload={() => clientApi.get("/me").then((r) => setCliente(r.data))} />}
                    {sezione === "polizze" && <PolizzeView />}
                    {sezione === "titoli" && <TitoliView />}
                    {sezione === "documenti" && <DocumentiView />}
                    {sezione === "sinistri" && <SinistriView />}
                    {sezione === "chat" && <ChatView />}
                    {sezione === "servizi" && <ServiziView />}
                </main>
            </div>
        </div>
    );
}

function NavList({ sezione, onSelect }) {
    return (
        <nav className="space-y-1">
            {SEZIONI.map((s) => {
                const Icon = s.icon;
                const active = sezione === s.key;
                return (
                    <button key={s.key} onClick={() => onSelect(s.key)}
                        className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition
                            ${active ? "bg-sky-100 text-sky-800 font-semibold" : "text-slate-600 hover:bg-slate-100"}`}
                        data-testid={`nav-${s.key}`}>
                        <Icon size={18} />
                        {s.label}
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
    return (
        <div className="space-y-4">
            <h2 className="text-2xl font-bold text-slate-800">Il mio profilo</h2>
            <div className="bg-white rounded-xl p-5 shadow-sm space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <ProfiloField label="Nome / Ragione Sociale" defaultVal={cliente.nome} onChange={onChange("ragione_sociale")} />
                    <ProfiloField label="Codice Fiscale" defaultVal={cliente.codice_fiscale} onChange={onChange("codice_fiscale")} />
                    <ProfiloField label="Partita IVA" defaultVal={cliente.partita_iva} onChange={onChange("partita_iva")} />
                    <ProfiloField label="Email" defaultVal={cliente.email} onChange={onChange("email")} />
                    <ProfiloField label="PEC" defaultVal={cliente.pec} onChange={onChange("pec")} />
                    <ProfiloField label="Cellulare" defaultVal={cliente.cellulare} onChange={onChange("cellulare")} />
                    <ProfiloField label="Indirizzo" defaultVal={cliente.indirizzo} onChange={onChange("indirizzo_residenza")} />
                    <ProfiloField label="Comune" defaultVal={cliente.comune} onChange={onChange("comune_residenza")} />
                    <ProfiloField label="Provincia" defaultVal={cliente.provincia} onChange={onChange("provincia_residenza")} />
                    <ProfiloField label="CAP" defaultVal={cliente.cap} onChange={onChange("cap_residenza")} />
                </div>
                <div className="pt-3 flex justify-end">
                    <button onClick={richiedi}
                        className="px-5 py-2 rounded-lg bg-sky-600 hover:bg-sky-700 text-white text-sm font-semibold"
                        data-testid="richiedi-modifica-btn">
                        Invia richiesta di modifica
                    </button>
                </div>
                <div className="text-[10px] text-slate-400 italic">
                    Le modifiche saranno verificate dall&apos;agenzia prima di essere applicate.
                </div>
            </div>
        </div>
    );
}

// ─── POLIZZE ──────────────────────────────────────────────────────────
function PolizzeView() {
    const [pols, setPols] = useState(null);
    useEffect(() => { clientApi.get("/polizze").then((r) => setPols(r.data)); }, []);
    if (!pols) return <div className="text-slate-400">Caricamento…</div>;
    if (pols.length === 0) return <EmptyState icon={FileText} testo="Nessuna polizza da mostrare" />;
    return (
        <div className="space-y-4">
            <h2 className="text-2xl font-bold text-slate-800">Le mie polizze</h2>
            {pols.map((p) => <PolizzaCard key={p.id} p={p} />)}
        </div>
    );
}

function PolizzaCard({ p }) {
    const [openApps, setOpenApps] = useState(false);
    const oggi = new Date().toISOString().slice(0, 10);
    const scaduta = p.scadenza && p.scadenza < oggi;
    return (
        <div className="bg-white rounded-xl shadow-sm border border-slate-100 p-4 sm:p-5">
            <div className="flex flex-wrap items-start gap-3">
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <span className="font-mono text-lg font-bold text-sky-800">{p.numero_polizza}</span>
                        {p.is_libro_matricola && (
                            <span className="text-[10px] bg-violet-100 text-violet-700 px-2 py-0.5 rounded-full font-semibold">LIBRO MATRICOLA</span>
                        )}
                        {scaduta && <span className="text-[10px] bg-rose-100 text-rose-700 px-2 py-0.5 rounded-full font-semibold">SCADUTA</span>}
                    </div>
                    <div className="text-sm text-slate-600">{p.ramo} · {p.prodotto || "—"}</div>
                    <div className="text-xs text-slate-500 mt-1">Compagnia: {p.compagnia_nome || "—"}</div>
                    <div className="flex flex-wrap gap-4 mt-2 text-xs text-slate-600">
                        <div><b>Effetto:</b> {p.effetto || "—"}</div>
                        <div><b>Scadenza:</b> {p.scadenza || "—"}</div>
                        <div><b>Premio:</b> {p.premio_lordo ? `€ ${Number(p.premio_lordo).toFixed(2)}` : "—"}</div>
                    </div>
                </div>
                <button
                    onClick={() => window.open(`${API}/polizze/${p.id}/pdf?token=${localStorage.getItem("portale_token")}`, "_blank")}
                    className="text-xs px-3 py-1.5 rounded-lg border border-sky-300 text-sky-700 hover:bg-sky-50 inline-flex items-center gap-1">
                    <Download size={12} /> Scarica PDF
                </button>
            </div>
            {p.is_libro_matricola && (p.applicazioni?.length || 0) > 0 && (
                <div className="mt-3 pt-3 border-t border-slate-100">
                    <button onClick={() => setOpenApps(!openApps)}
                        className="text-xs text-sky-700 hover:underline inline-flex items-center gap-1">
                        <Car size={12} /> {openApps ? "Nascondi" : "Mostra"} {p.applicazioni.length} veicoli
                        <ChevronRight size={12} className={`transition ${openApps ? "rotate-90" : ""}`} />
                    </button>
                    {openApps && (
                        <div className="mt-2 space-y-1 max-h-96 overflow-y-auto">
                            {p.applicazioni.filter((a) => (a.stato || "attiva") === "attiva").map((a) => (
                                <div key={a.id} className="text-xs bg-slate-50 rounded p-2 flex flex-wrap gap-2 items-center">
                                    <span className="font-mono font-bold text-sky-700">{a.targa}</span>
                                    <span className="text-slate-600">{[a.marca, a.modello].filter(Boolean).join(" ")}</span>
                                    {a.intestatario && <span className="text-slate-400">· {a.intestatario}</span>}
                                    <span className="ml-auto text-[10px] bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded">ATTIVO</span>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

// ─── TITOLI ───────────────────────────────────────────────────────────
function TitoliView() {
    const [tits, setTits] = useState(null);
    useEffect(() => { clientApi.get("/titoli").then((r) => setTits(r.data)); }, []);
    if (!tits) return <div className="text-slate-400">Caricamento…</div>;
    if (tits.length === 0) return <EmptyState icon={Wallet} testo="Nessun titolo da mostrare" />;
    return (
        <div className="space-y-4">
            <h2 className="text-2xl font-bold text-slate-800">Titoli & Quietanze</h2>
            {tits.map((t) => (
                <div key={t.id} className="bg-white rounded-xl shadow-sm p-4 flex flex-wrap items-center gap-3">
                    <div className="flex-1 min-w-0">
                        <div className="font-semibold text-slate-800">{t.numero_titolo || "Rata"} — €{Number(t.importo_lordo || 0).toFixed(2)}</div>
                        <div className="text-xs text-slate-500">Effetto {t.data_effetto} → Scadenza {t.data_scadenza}</div>
                    </div>
                    <span className={`text-[10px] px-2 py-1 rounded font-semibold ${
                        t.stato === "incassato" ? "bg-emerald-100 text-emerald-700" :
                        t.stato === "pendente" ? "bg-amber-100 text-amber-700" :
                        t.stato === "stornato" ? "bg-slate-200 text-slate-600" :
                        "bg-rose-100 text-rose-700"
                    }`}>{(t.stato || "").toUpperCase()}</span>
                    {t.n_allegati_cliente > 0 && (
                        <span className="text-[10px] bg-sky-100 text-sky-700 px-2 py-1 rounded inline-flex items-center gap-1">
                            📎 {t.n_allegati_cliente} allegat{t.n_allegati_cliente === 1 ? "o" : "i"}
                        </span>
                    )}
                </div>
            ))}
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
        <div className="space-y-4">
            <h2 className="text-2xl font-bold text-slate-800">Documenti & Upload</h2>
            <div className="bg-gradient-to-br from-sky-500 to-blue-600 rounded-xl p-5 text-white shadow-md">
                <div className="flex items-center gap-3 mb-2">
                    <Upload size={22} />
                    <div className="font-bold">Carica un documento</div>
                </div>
                <div className="text-sm text-sky-50 mb-3">Scatta una foto o carica un PDF dal tuo dispositivo</div>
                <label className="inline-block cursor-pointer">
                    <input type="file" accept="application/pdf,image/*" capture="environment"
                        className="hidden" onChange={onFile} disabled={uploading}
                        data-testid="portale-upload-input" />
                    <span className="inline-block px-4 py-2 bg-white text-sky-700 rounded-lg font-semibold text-sm">
                        {uploading ? "Caricamento…" : "Scegli file"}
                    </span>
                </label>
            </div>
            <h3 className="text-sm font-semibold text-slate-600 uppercase tracking-wider mt-6">I miei documenti</h3>
            {!docs ? <div className="text-slate-400">Caricamento…</div>
              : docs.length === 0 ? <EmptyState icon={FolderOpen} testo="Nessun documento pubblicato" />
              : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {docs.map((d) => (
                        <div key={d.id} className="bg-white rounded-xl p-3 shadow-sm flex items-center gap-3">
                            <FolderOpen className="text-sky-600 shrink-0" size={20} />
                            <div className="flex-1 min-w-0">
                                <div className="text-sm font-semibold truncate">{d.nome_file}</div>
                                <div className="text-[10px] text-slate-500 uppercase">{d.categoria}</div>
                            </div>
                            <a href={`${API.replace('/portale','')}/allegati/${d.id}/download?token=${localStorage.getItem("portale_token")}`}
                               target="_blank" rel="noreferrer"
                               className="text-sky-600 hover:text-sky-800">
                                <Download size={18} />
                            </a>
                        </div>
                    ))}
                </div>
              )}
        </div>
    );
}

// ─── SINISTRI ─────────────────────────────────────────────────────────
function SinistriView() {
    const [sin, setSin] = useState(null);
    useEffect(() => { clientApi.get("/sinistri").then((r) => setSin(r.data)); }, []);
    if (!sin) return <div className="text-slate-400">Caricamento…</div>;
    if (sin.length === 0) return <EmptyState icon={AlertCircle} testo="Nessun sinistro da mostrare" />;
    return (
        <div className="space-y-4">
            <h2 className="text-2xl font-bold text-slate-800">I miei sinistri</h2>
            {sin.map((s) => (
                <div key={s.id} className="bg-white rounded-xl shadow-sm p-4">
                    <div className="flex items-center gap-2 mb-2">
                        <span className="font-mono font-bold">{s.numero_sinistro || s.id.slice(0, 8)}</span>
                        <span className={`ml-auto text-[10px] px-2 py-0.5 rounded font-semibold ${
                            s.stato === "aperto" ? "bg-amber-100 text-amber-700" : "bg-emerald-100 text-emerald-700"
                        }`}>{(s.stato || "").toUpperCase()}</span>
                    </div>
                    <div className="text-sm text-slate-600">{s.tipo_sinistro || "—"}</div>
                    <div className="text-xs text-slate-500 mt-1">
                        Data evento: {s.data_evento || "—"} · Denuncia: {s.data_denuncia || "—"}
                    </div>
                    {s.perito_nome && (
                        <div className="text-xs text-slate-500 mt-1">
                            Perito: {s.perito_nome} {s.perito_telefono ? `· ${s.perito_telefono}` : ""}
                        </div>
                    )}
                </div>
            ))}
        </div>
    );
}

// ─── SERVIZI ──────────────────────────────────────────────────────────
function ServiziView() {
    const [srv, setSrv] = useState(null);
    useEffect(() => { clientApi.get("/servizi").then((r) => setSrv(r.data)); }, []);
    if (!srv) return <div className="text-slate-400">Caricamento…</div>;
    return (
        <div className="space-y-4">
            <h2 className="text-2xl font-bold text-slate-800">Servizi & Assistenza</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {srv.map((s, i) => (
                    <a key={i} href={s.url} target="_blank" rel="noreferrer"
                       className="bg-white hover:bg-sky-50 rounded-xl p-4 shadow-sm flex items-center gap-3 transition">
                        <div className="w-11 h-11 rounded-full bg-sky-100 text-sky-700 flex items-center justify-center">
                            <Building2 size={22} />
                        </div>
                        <div className="flex-1 min-w-0">
                            <div className="font-semibold text-slate-800">{s.nome}</div>
                            <div className="text-xs text-slate-500">{s.descrizione}</div>
                        </div>
                        <ChevronRight size={18} className="text-slate-400" />
                    </a>
                ))}
            </div>
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
    const [sending, setSending] = useState(false);
    const scrollRef = useState(null)[0];

    const load = () => clientApi.get("/chat/messaggi").then((r) => setMsgs(r.data)).catch(() => setMsgs([]));
    useEffect(() => {
        load();
        const t = setInterval(load, 8000);
        return () => clearInterval(t);
    }, []);

    const invia = async (e) => {
        e?.preventDefault();
        if (!text.trim() || sending) return;
        setSending(true);
        try {
            await clientApi.post("/chat/messaggi", { testo: text });
            setText("");
            load();
        } catch (err) {
            toast.error("Errore invio");
        } finally { setSending(false); }
    };

    return (
        <div className="space-y-4">
            <h2 className="text-2xl font-bold text-slate-800">Chat con l&apos;agenzia</h2>
            <div className="bg-white rounded-xl shadow-sm flex flex-col" style={{ height: "60vh", minHeight: 420 }}>
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
                                    <div className="whitespace-pre-wrap break-words">{m.testo}</div>
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
                <form onSubmit={invia} className="border-t border-slate-200 p-3 flex gap-2 bg-white rounded-b-xl">
                    <input type="text" value={text} onChange={(e) => setText(e.target.value)}
                           placeholder="Scrivi un messaggio…"
                           className="flex-1 px-3 py-2.5 border border-slate-300 rounded-lg text-sm focus:border-sky-500 focus:ring-2 focus:ring-sky-200 outline-none"
                           data-testid="portale-chat-input" />
                    <button type="submit" disabled={sending || !text.trim()}
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
