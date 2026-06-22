import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card } from "@/components/ui/card";

const ENTITA = [
    { key: "polizze", label: "Polizze" },
    { key: "sinistri", label: "Sinistri" },
    { key: "titoli", label: "Titoli" },
    { key: "clienti", label: "Clienti" },
];

const COL_COLORS = {
    in_emissione: "#0EA5E9", attiva: "#10B981", sospesa: "#F59E0B",
    scaduta: "#EF4444", annullata: "#94A3B8",
    aperto: "#0EA5E9", in_istruttoria: "#F59E0B", liquidato: "#10B981",
    chiuso_senza_seguito: "#94A3B8", respinto: "#EF4444",
    da_incassare: "#F59E0B", insoluto: "#EF4444", incassato: "#10B981", stornato: "#94A3B8",
    prospect: "#94A3B8", nuovo: "#0EA5E9", attivo: "#10B981", top: "#7C3AED",
};

export default function Pipeline() {
    return (
        <div data-testid="pipeline-page">
            <PageHeader
                title="Pipeline"
                subtitle="Vista a colonne (kanban) per stato di avanzamento"
            />
            <Tabs defaultValue="polizze">
                <TabsList className="bg-slate-100">
                    {ENTITA.map((e) => (
                        <TabsTrigger key={e.key} value={e.key} data-testid={`pipeline-tab-${e.key}`}>
                            {e.label}
                        </TabsTrigger>
                    ))}
                </TabsList>
                {ENTITA.map((e) => (
                    <TabsContent key={e.key} value={e.key} className="mt-4">
                        <PipelineBoard entita={e.key} />
                    </TabsContent>
                ))}
            </Tabs>
        </div>
    );
}

function PipelineBoard({ entita }) {
    const [data, setData] = useState(null);
    const nav = useNavigate();

    useEffect(() => {
        setData(null);
        api.get(`/pipeline/${entita}`).then((r) => setData(r.data));
    }, [entita]);

    if (!data) return <Loading />;

    return (
        <div className="flex gap-4 overflow-x-auto pb-4" data-testid={`board-${entita}`}>
            {data.colonne.map((col) => (
                <div key={col.key} className="w-72 shrink-0">
                    <div
                        className="rounded-md px-3 py-2 mb-3 flex items-center justify-between"
                        style={{
                            background: `${COL_COLORS[col.key] || "#64748B"}15`,
                            borderLeft: `3px solid ${COL_COLORS[col.key] || "#64748B"}`,
                        }}
                    >
                        <div className="font-medium text-sm text-slate-800">{col.label}</div>
                        <div className="text-xs font-semibold text-slate-600 num bg-white border border-slate-200 rounded-full px-2 py-0.5">
                            {col.count}
                        </div>
                    </div>
                    <div className="space-y-2">
                        {col.cards.length === 0 ? (
                            <div className="text-xs text-slate-400 text-center py-4">Vuoto</div>
                        ) : col.cards.map((c) => (
                            <Card
                                key={c.id}
                                onClick={() => c.link && nav(c.link)}
                                className="p-3 cursor-pointer hover:border-sky-400 hover:shadow-md transition-all border-slate-200"
                                data-testid={`card-${c.id}`}
                            >
                                <div className="font-medium text-sm text-slate-900 truncate">{c.title}</div>
                                {c.subtitle && <div className="text-xs text-slate-600 truncate mt-0.5">{c.subtitle}</div>}
                                {c.footer && <div className="text-xs text-slate-500 truncate mt-1">{c.footer}</div>}
                                <div className="flex items-center justify-between mt-2 pt-2 border-t border-slate-100">
                                    {c.extra && <span className="text-[11px] text-slate-600 num">{c.extra}</span>}
                                    {c.date && <span className="text-[10px] text-slate-400 num">{c.date}</span>}
                                </div>
                            </Card>
                        ))}
                        {col.cards.length === 50 && col.count > 50 && (
                            <div className="text-[10px] text-center text-slate-400">+ {col.count - 50} altri...</div>
                        )}
                    </div>
                </div>
            ))}
            {data.colonne.length === 0 && <Empty />}
        </div>
    );
}
