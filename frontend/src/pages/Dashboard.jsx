import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtEur, fmtNum } from "@/lib/api";
import { PageHeader } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { useAuth } from "@/contexts/AuthContext";
import {
    ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
    PieChart, Pie, Cell, Legend,
} from "recharts";
import { TrendingUp, FileText, AlertTriangle, Users, CalendarClock, Wallet, Link2, Plus, Pencil, Trash2, ExternalLink } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";

const COLORS = ["#0369A1", "#10B981", "#F59E0B", "#7C3AED", "#EF4444", "#0EA5E9", "#84CC16", "#F472B6"];

function Stat({ label, value, icon, hint, testid, to }) {
    const content = (
        <Card
            className={`p-5 border-slate-200 transition-shadow ${to ? "hover:shadow-md hover:border-sky-300 cursor-pointer" : "hover:shadow-md"}`}
            data-testid={testid}
        >
            <div className="flex items-start justify-between">
                <div className="stat-label">{label}</div>
                <div className="text-slate-400">{icon}</div>
            </div>
            <div className="stat-value mt-2">{value}</div>
            {hint && <div className="text-xs text-slate-500 mt-1">{hint}</div>}
        </Card>
    );
    if (to) return <Link to={to} className="block">{content}</Link>;
    return content;
}

function ChartCard({ to, className = "", testid, children }) {
    const wrapper = (
        <Card className={`p-6 border-slate-200 ${to ? "hover:shadow-md hover:border-sky-300 cursor-pointer transition-shadow" : ""} ${className}`} data-testid={testid}>
            {children}
        </Card>
    );
    if (to) return <Link to={to} className={`block ${className}`}>{wrapper}</Link>;
    return wrapper;
}

export default function Dashboard() {
    const { user } = useAuth();
    const [data, setData] = useState(null);
    const [admin, setAdmin] = useState(null);
    const [err, setErr] = useState("");

    useEffect(() => {
        api.get("/stats/dashboard").then((r) => setData(r.data)).catch((e) => setErr(e.message));
        if (user?.role === "admin") {
            api.get("/stats/dashboard-admin").then((r) => setAdmin(r.data)).catch(() => {});
        }
    }, [user]);

    if (err) return <div className="text-rose-600">{err}</div>;
    if (!data) return <div className="text-slate-400">Caricamento dashboard...</div>;

    const isClient = user?.role === "cliente";

    return (
        <div data-testid="dashboard-page">
            <PageHeader
                title="Dashboard"
                subtitle="Panoramica generale del portafoglio assicurativo"
            />
            <LinkUtiliCard />

            <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4 mb-8">
                <Stat label="Anagrafiche" value={fmtNum(data.anagrafiche)} icon={<Users size={18} />} testid="stat-anagrafiche" to="/anagrafiche" />
                <Stat label="Polizze attive" value={fmtNum(data.polizze_attive)} icon={<FileText size={18} />}
                      hint={`Totali: ${data.polizze_totali}`} testid="stat-polizze" to="/polizze" />
                <Stat label="In scadenza (60gg)" value={fmtNum(data.polizze_in_scadenza)} icon={<CalendarClock size={18} />} testid="stat-scadenze" to="/avvisi" />
                <Stat label="Sinistri aperti" value={fmtNum(data.sinistri_aperti)} icon={<AlertTriangle size={18} />} testid="stat-sinistri" to="/sinistri" />
                <Stat label="Premi anno" value={fmtEur(data.premi_anno_corrente)} icon={<Wallet size={18} />} testid="stat-premi" to="/contabilita" />
                {!isClient && (
                    <Stat label="Crescita" value="+12%" hint="vs anno scorso" icon={<TrendingUp size={18} />} testid="stat-crescita" to="/contabilita" />
                )}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <ChartCard to="/contabilita" className="lg:col-span-2" testid="dash-chart-incassi">
                    <div className="flex items-center justify-between mb-4">
                        <h3 className="text-lg font-medium text-slate-900">Incassi ultimi 6 mesi</h3>
                        <span className="text-xs text-slate-500">in Euro</span>
                    </div>
                    <ResponsiveContainer width="100%" height={280}>
                        <BarChart data={data.incassi_mensili}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                            <XAxis dataKey="mese" tick={{ fontSize: 11, fill: "#475569" }} />
                            <YAxis tick={{ fontSize: 11, fill: "#475569" }} />
                            <Tooltip
                                formatter={(v) => fmtEur(v)}
                                contentStyle={{ fontSize: 12, borderRadius: 6, border: "1px solid #e2e8f0" }}
                            />
                            <Bar dataKey="totale" fill="#0369A1" radius={[4, 4, 0, 0]} />
                        </BarChart>
                    </ResponsiveContainer>
                </ChartCard>

                <ChartCard to="/polizze" testid="dash-chart-polizze-ramo">
                    <h3 className="text-lg font-medium text-slate-900 mb-4">Polizze per ramo</h3>
                    <ResponsiveContainer width="100%" height={280}>
                        <PieChart>
                            <Pie
                                data={data.polizze_per_ramo}
                                dataKey="count"
                                nameKey="ramo"
                                cx="50%" cy="50%"
                                outerRadius={90}
                                innerRadius={45}
                                paddingAngle={2}
                            >
                                {data.polizze_per_ramo.map((_, i) => (
                                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                                ))}
                            </Pie>
                            <Tooltip contentStyle={{ fontSize: 12 }} />
                            <Legend
                                wrapperStyle={{ fontSize: 11 }}
                                layout="horizontal"
                                verticalAlign="bottom"
                            />
                        </PieChart>
                    </ResponsiveContainer>
                </ChartCard>
            </div>

            {admin && user?.role === "admin" && (
                <div className="mt-8" data-testid="dashboard-admin-section">
                    <h2 className="text-lg font-bold text-slate-900 mb-3">📊 KPI Amministratore</h2>
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                        <Stat label="Provvigioni anno" value={fmtEur(admin.provvigioni_anno)} icon={<Wallet size={18} />} testid="kpi-provv" to="/provvigioni" />
                        <Stat label="Premi incassati anno" value={fmtEur(admin.premi_anno)} icon={<TrendingUp size={18} />} testid="kpi-premi-anno" to="/contabilita" />
                        <Stat label="N. titoli anno" value={fmtNum(admin.n_titoli_anno)} icon={<FileText size={18} />} testid="kpi-titoli" to="/titoli" />
                        <Stat label="Sinistri liquidati" value={fmtNum(admin.sinistri_per_stato?.liquidato?.n || 0)}
                              hint={fmtEur(admin.sinistri_per_stato?.liquidato?.totale || 0)} icon={<AlertTriangle size={18} />} testid="kpi-sin-liq" to="/sinistri" />
                    </div>
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
                        <Link to="/anagrafiche" className="block">
                            <Card className="p-5 border-slate-200 hover:shadow-md hover:border-sky-300 cursor-pointer transition-shadow h-full" data-testid="dash-clienti-cat">
                                <h3 className="font-semibold mb-3">Clienti per categoria</h3>
                                <div className="grid grid-cols-2 gap-2">
                                    {Object.entries(admin.clienti_per_categoria || {}).map(([k, v]) => (
                                        <div key={k} className="flex justify-between bg-slate-50 rounded p-2 text-sm">
                                            <span>{k}</span>
                                            <span className="font-bold text-sky-700">{v}</span>
                                        </div>
                                    ))}
                                </div>
                            </Card>
                        </Link>
                        <Link to="/avvisi" className="block">
                            <Card className="p-5 border-slate-200 hover:shadow-md hover:border-sky-300 cursor-pointer transition-shadow h-full" data-testid="dash-polizze-scadenze">
                                <h3 className="font-semibold mb-3">Polizze in scadenza</h3>
                                <div className="grid grid-cols-5 gap-1">
                                    {Object.entries(admin.scadenze || {}).map(([k, v]) => (
                                        <div key={k} className={`text-center rounded p-2 ${v > 0 ? "bg-amber-100" : "bg-slate-50"}`}>
                                            <div className="text-xs text-slate-500">{k}</div>
                                            <div className={`font-bold text-lg ${v > 0 ? "text-amber-700" : "text-slate-400"}`}>{v}</div>
                                        </div>
                                    ))}
                                </div>
                            </Card>
                        </Link>
                    </div>
                    <Link to="/polizze" className="block">
                        <Card className="p-5 border-slate-200 hover:shadow-md hover:border-sky-300 cursor-pointer transition-shadow" data-testid="dash-produzione-ramo">
                            <h3 className="font-semibold mb-3">Nuova produzione per ramo (anno corrente)</h3>
                            <table className="w-full text-sm">
                                <thead><tr className="text-xs text-slate-500 border-b">
                                    <th className="text-left py-1">Ramo</th><th className="text-right">N. polizze</th><th className="text-right">Premio totale</th>
                                </tr></thead>
                                <tbody>
                                    {(admin.produzione_per_ramo || []).map((p) => (
                                        <tr key={p.ramo} className="border-b border-slate-100">
                                            <td className="py-1.5">{p.ramo}</td>
                                            <td className="text-right">{p.n}</td>
                                            <td className="text-right font-semibold text-emerald-700">{fmtEur(p.premio)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </Card>
                    </Link>
                </div>
            )}
        </div>
    );
}


function LinkUtiliCard() {
    const [links, setLinks] = useState(null);
    const [open, setOpen] = useState(false);
    const [editing, setEditing] = useState(null);

    const load = () => api.get("/dashboard/links").then((r) => setLinks(r.data || []));
    useEffect(() => { load(); }, []);

    const apriNuovo = () => { setEditing(null); setOpen(true); };
    const apriEdit = (l, e) => { e.stopPropagation(); e.preventDefault(); setEditing(l); setOpen(true); };
    const elimina = async (l, e) => {
        e.stopPropagation(); e.preventDefault();
        if (!window.confirm(`Eliminare il link "${l.label}"?`)) return;
        try {
            await api.delete(`/dashboard/links/${l.id}`);
            toast.success("Link eliminato");
            load();
        } catch (err) { toast.error(err.response?.data?.detail || "Errore"); }
    };

    return (
        <Card className="p-4 border-slate-200 mb-4" data-testid="dash-links">
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                    <Link2 size={16} className="text-sky-600" />
                    <h3 className="font-semibold text-slate-900">Link utili</h3>
                    {links && links.length > 0 && (
                        <span className="text-xs text-slate-400">({links.length})</span>
                    )}
                </div>
                <Button
                    size="sm" variant="outline" onClick={apriNuovo}
                    data-testid="dash-link-new"
                >
                    <Plus size={13} className="mr-1" /> Aggiungi
                </Button>
            </div>
            {links === null ? (
                <div className="text-xs text-slate-400 py-3">Caricamento…</div>
            ) : links.length === 0 ? (
                <div className="text-xs text-slate-400 py-3 italic">
                    Nessun link salvato. Aggiungi i tuoi collegamenti rapidi (es. Linktr.ee, portali compagnie...).
                </div>
            ) : (
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
                    {links.map((l) => (
                        <a
                            key={l.id}
                            href={l.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="group relative flex flex-col items-start gap-1 p-3 border border-slate-200 rounded-lg hover:border-sky-400 hover:shadow-sm bg-white transition"
                            style={l.color ? { borderLeftWidth: 4, borderLeftColor: l.color } : undefined}
                            data-testid={`dash-link-${l.id}`}
                            title={l.url}
                        >
                            <div className="flex items-center gap-1.5 w-full">
                                <ExternalLink size={12} className="text-slate-400 group-hover:text-sky-600 shrink-0" />
                                <span className="font-medium text-sm truncate text-slate-800">{l.label}</span>
                            </div>
                            <span className="text-[10px] text-slate-400 truncate w-full">
                                {l.url.replace(/^https?:\/\//, "").slice(0, 32)}
                            </span>
                            <div className="absolute top-1 right-1 hidden group-hover:flex gap-0.5 bg-white rounded shadow-sm border border-slate-200">
                                <button
                                    onClick={(e) => apriEdit(l, e)}
                                    className="h-5 w-5 flex items-center justify-center hover:bg-slate-100 rounded"
                                    title="Modifica"
                                    data-testid={`dash-link-edit-${l.id}`}
                                >
                                    <Pencil size={10} className="text-slate-600" />
                                </button>
                                <button
                                    onClick={(e) => elimina(l, e)}
                                    className="h-5 w-5 flex items-center justify-center hover:bg-rose-50 rounded text-rose-600"
                                    title="Elimina"
                                    data-testid={`dash-link-del-${l.id}`}
                                >
                                    <Trash2 size={10} />
                                </button>
                            </div>
                        </a>
                    ))}
                </div>
            )}
            {open && (
                <LinkDialog
                    link={editing}
                    onClose={(refresh) => { setOpen(false); setEditing(null); if (refresh) load(); }}
                />
            )}
        </Card>
    );
}

function LinkDialog({ link, onClose }) {
    const [f, setF] = useState(() => link ? {
        label: link.label, url: link.url,
        color: link.color || "", ordine: link.ordine || 0,
    } : { label: "", url: "", color: "", ordine: 0 });
    const [saving, setSaving] = useState(false);

    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const save = async () => {
        if (!f.label || !f.url) { toast.error("Nome e URL obbligatori"); return; }
        setSaving(true);
        try {
            const body = { label: f.label, url: f.url, color: f.color || null, ordine: parseInt(f.ordine, 10) || 0 };
            if (link) {
                await api.put(`/dashboard/links/${link.id}`, body);
                toast.success("Link aggiornato");
            } else {
                await api.post("/dashboard/links", body);
                toast.success("Link aggiunto");
            }
            onClose(true);
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        finally { setSaving(false); }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose(false)}>
            <DialogContent className="max-w-md" data-testid="dash-link-dialog">
                <DialogHeader>
                    <DialogTitle>{link ? "Modifica link" : "Nuovo link utile"}</DialogTitle>
                </DialogHeader>
                <div className="space-y-3 py-2">
                    <div>
                        <Label>Nome *</Label>
                        <Input
                            placeholder="es. Linktree, Generali Agenzia..."
                            value={f.label}
                            onChange={(e) => set("label", e.target.value)}
                            data-testid="dash-link-label"
                        />
                    </div>
                    <div>
                        <Label>URL *</Label>
                        <Input
                            placeholder="https://linktr.ee/SCHIANTARELLILINK"
                            value={f.url}
                            onChange={(e) => set("url", e.target.value)}
                            data-testid="dash-link-url"
                        />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <Label>Colore (opzionale)</Label>
                            <Input
                                type="color"
                                value={f.color || "#0369A1"}
                                onChange={(e) => set("color", e.target.value)}
                                data-testid="dash-link-color"
                            />
                        </div>
                        <div>
                            <Label>Ordine</Label>
                            <Input
                                type="number"
                                value={f.ordine}
                                onChange={(e) => set("ordine", e.target.value)}
                            />
                        </div>
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={() => onClose(false)}>Annulla</Button>
                    <Button
                        onClick={save} disabled={saving}
                        className="bg-sky-700 hover:bg-sky-800"
                        data-testid="dash-link-save"
                    >
                        {saving ? "Salvataggio…" : (link ? "Aggiorna" : "Aggiungi")}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
