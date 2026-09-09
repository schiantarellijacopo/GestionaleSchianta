import { useEffect, useState } from "react";
import { Circle, ListTodo } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

const fmt = (d) => (d ? String(d).slice(0, 10).split("-").reverse().join("/") : null);

export const TaskCollegati = ({ entitaTipo, entitaId }) => {
    const [tasks, setTasks] = useState([]);

    const load = () => api.get("/tasks/collegati", { params: { entita_tipo: entitaTipo, entita_id: entitaId } })
        .then((r) => setTasks(r.data || [])).catch(() => setTasks([]));
    useEffect(() => { if (entitaId) load(); /* eslint-disable-next-line */ }, [entitaTipo, entitaId]);

    const completa = async (t) => {
        try { await api.post(`/tasks/${t.id}/toggle`); toast.success("Attività completata"); load(); }
        catch { toast.error("Errore"); }
    };

    if (!tasks.length) return null;
    return (
        <div className="border border-violet-200 bg-violet-50/60 rounded-lg p-3 mb-4" data-testid="task-collegati-panel">
            <div className="flex items-center gap-2 text-sm font-semibold text-violet-800 mb-2">
                <ListTodo size={15} /> Attività aperte collegate ({tasks.length})
            </div>
            <div className="space-y-1.5">
                {tasks.map((t) => (
                    <div key={t.id} className="flex items-center gap-2 bg-white rounded-md border border-violet-100 px-2 py-1.5" data-testid={`task-collegato-${t.id}`}>
                        <button onClick={() => completa(t)} title="Segna come completata" className="text-slate-400 hover:text-emerald-600" data-testid={`task-collegato-done-${t.id}`}>
                            <Circle size={16} />
                        </button>
                        <div className="flex-1 min-w-0">
                            <div className="text-sm text-slate-800 truncate">{t.titolo}</div>
                            {t.note && <div className="text-[11px] text-slate-500 truncate">{t.note}</div>}
                        </div>
                        {t.priorita === "alta" && <span className="text-[10px] text-rose-600 font-semibold">ALTA</span>}
                        {t.data_scadenza && <span className="text-[11px] text-slate-500">scad. {fmt(t.data_scadenza)}</span>}
                    </div>
                ))}
            </div>
        </div>
    );
};

export default TaskCollegati;
