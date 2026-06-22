import { useEffect, useState } from "react";
import { api, fmtDate } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Activity } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const AZIONE_LABEL = {
    login: "Accesso", logout: "Disconnessione",
    create: "Creazione", update: "Modifica", delete: "Cancellazione",
    incasso: "Incasso", invio: "Invio", import: "Import dati",
    calc_pensione: "Calcolo pensione", genera_avvisi: "Genera avvisi",
};

export default function Attivita() {
    const [list, setList] = useState(null);
    const [entita, setEntita] = useState("all");

    const load = () => {
        const params = {};
        if (entita !== "all") params.entita = entita;
        api.get("/attivita", { params }).then((r) => setList(r.data));
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [entita]);

    return (
        <div data-testid="attivita-page">
            <PageHeader
                title="Log attività"
                subtitle="Tutte le azioni effettuate sul sistema"
            />

            <div className="flex items-center gap-3 mb-4">
                <Select value={entita} onValueChange={setEntita}>
                    <SelectTrigger className="w-48"><SelectValue /></SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">Tutte le entità</SelectItem>
                        <SelectItem value="anagrafica">Anagrafiche</SelectItem>
                        <SelectItem value="polizza">Polizze</SelectItem>
                        <SelectItem value="titolo">Titoli</SelectItem>
                        <SelectItem value="sinistro">Sinistri</SelectItem>
                        <SelectItem value="movimento">Movimenti contabili</SelectItem>
                        <SelectItem value="email">Email</SelectItem>
                        <SelectItem value="ania">Import ANIA</SelectItem>
                        <SelectItem value="auth">Auth</SelectItem>
                    </SelectContent>
                </Select>
                <span className="text-sm text-slate-500 num ml-auto">{list ? `${list.length} eventi` : ""}</span>
            </div>

            <div className="bg-white border border-slate-200 rounded-md">
                {list === null ? <Loading /> : list.length === 0 ? <Empty /> : (
                    <ul className="divide-y divide-slate-100">
                        {list.map((a) => (
                            <li key={a.id} className="px-4 py-3 flex items-start gap-3 hover:bg-slate-50" data-testid={`activity-${a.id}`}>
                                <div className="w-8 h-8 rounded-full bg-sky-50 text-sky-700 flex items-center justify-center shrink-0">
                                    <Activity size={14} />
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="text-sm text-slate-900">
                                        <span className="font-medium">{a.utente_email || "Sistema"}</span>
                                        {" — "}
                                        <span className="text-slate-600">{AZIONE_LABEL[a.azione] || a.azione}</span>
                                        {" su "}
                                        <span className="badge badge-neutral">{a.entita}</span>
                                    </div>
                                    {a.descrizione && <div className="text-xs text-slate-500 mt-0.5">{a.descrizione}</div>}
                                </div>
                                <div className="text-xs text-slate-400 num shrink-0">
                                    {fmtDate(a.created_at)} {new Date(a.created_at).toLocaleTimeString("it-IT")}
                                </div>
                            </li>
                        ))}
                    </ul>
                )}
            </div>
        </div>
    );
}
