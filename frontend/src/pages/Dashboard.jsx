import { useEffect, useState } from "react";
import { api, fmtEur, fmtNum } from "@/lib/api";
import { PageHeader } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { useAuth } from "@/contexts/AuthContext";
import {
    ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
    PieChart, Pie, Cell, Legend,
} from "recharts";
import { TrendingUp, FileText, AlertTriangle, Users, CalendarClock, Wallet } from "lucide-react";

const COLORS = ["#0369A1", "#10B981", "#F59E0B", "#7C3AED", "#EF4444", "#0EA5E9", "#84CC16", "#F472B6"];

function Stat({ label, value, icon, hint, testid }) {
    return (
        <Card className="p-5 border-slate-200 hover:shadow-md transition-shadow" data-testid={testid}>
            <div className="flex items-start justify-between">
                <div className="stat-label">{label}</div>
                <div className="text-slate-400">{icon}</div>
            </div>
            <div className="stat-value mt-2">{value}</div>
            {hint && <div className="text-xs text-slate-500 mt-1">{hint}</div>}
        </Card>
    );
}

export default function Dashboard() {
    const { user } = useAuth();
    const [data, setData] = useState(null);
    const [err, setErr] = useState("");

    useEffect(() => {
        api.get("/stats/dashboard").then((r) => setData(r.data)).catch((e) => setErr(e.message));
    }, []);

    if (err) return <div className="text-rose-600">{err}</div>;
    if (!data) return <div className="text-slate-400">Caricamento dashboard...</div>;

    const isClient = user?.role === "cliente";

    return (
        <div data-testid="dashboard-page">
            <PageHeader
                title="Dashboard"
                subtitle="Panoramica generale del portafoglio assicurativo"
            />

            <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4 mb-8">
                <Stat label="Anagrafiche" value={fmtNum(data.anagrafiche)} icon={<Users size={18} />} testid="stat-anagrafiche" />
                <Stat label="Polizze attive" value={fmtNum(data.polizze_attive)} icon={<FileText size={18} />}
                      hint={`Totali: ${data.polizze_totali}`} testid="stat-polizze" />
                <Stat label="In scadenza (60gg)" value={fmtNum(data.polizze_in_scadenza)} icon={<CalendarClock size={18} />} testid="stat-scadenze" />
                <Stat label="Sinistri aperti" value={fmtNum(data.sinistri_aperti)} icon={<AlertTriangle size={18} />} testid="stat-sinistri" />
                <Stat label="Premi anno" value={fmtEur(data.premi_anno_corrente)} icon={<Wallet size={18} />} testid="stat-premi" />
                {!isClient && (
                    <Stat label="Crescita" value="+12%" hint="vs anno scorso" icon={<TrendingUp size={18} />} testid="stat-crescita" />
                )}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <Card className="lg:col-span-2 p-6 border-slate-200">
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
                </Card>

                <Card className="p-6 border-slate-200">
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
                </Card>
            </div>
        </div>
    );
}
