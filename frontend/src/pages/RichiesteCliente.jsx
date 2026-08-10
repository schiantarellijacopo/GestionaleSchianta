/**
 * RichiesteCliente — Pagina admin per gestire le richieste inviate dai clienti
 * tramite il Portale (modifica anagrafica + upload documenti).
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CheckCircle2, X, Inbox, User, Upload as UploadIcon, Send } from "lucide-react";
import { Link } from "react-router-dom";

export default function RichiesteCliente() {
    const [items, setItems] = useState(null);
    const [filter, setFilter] = useState("da_verificare");
    const load = () => api.get("/richieste-cliente", { params: { stato: filter } })
        .then((r) => setItems(r.data));
    useEffect(() => { load(); /* eslint-disable-line */ }, [filter]);

    const approva = async (id) => {
        if (!window.confirm("Approvare la richiesta e applicare le modifiche all'anagrafica?")) return;
        try {
            await api.post(`/richieste-cliente/${id}/approva`);
            toast.success("Richiesta approvata");
            load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };
    const rifiuta = async (id) => {
        const motivo = window.prompt("Motivo del rifiuto (facoltativo):", "") || "";
        try {
            await api.post(`/richieste-cliente/${id}/rifiuta`, { motivo });
            toast.success("Richiesta rifiutata");
            load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <div className="p-4 sm:p-6 space-y-4">
            <div className="flex items-center gap-3 flex-wrap">
                <h1 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
                    <Inbox className="text-sky-600" /> Richieste dal Portale Cliente
                </h1>
                <div className="ml-auto flex gap-2">
                    {["da_verificare", "approvata", "rifiutata"].map((s) => (
                        <button key={s} onClick={() => setFilter(s)}
                            className={`text-xs px-3 py-1.5 rounded ${filter === s
                                ? "bg-sky-600 text-white"
                                : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"}`}
                            data-testid={`filter-${s}`}>
                            {s.replace("_", " ").toUpperCase()}
                        </button>
                    ))}
                </div>
            </div>
            {!items ? <div className="text-slate-400">Caricamento…</div>
              : items.length === 0 ? (
                  <div className="text-center py-16 text-slate-400">
                      <Inbox size={48} className="mx-auto mb-3 opacity-50" />
                      Nessuna richiesta {filter.replace("_", " ")}
                  </div>
              ) : (
                  <div className="space-y-3">
                      {items.map((r) => (
                          <Card key={r.id} className="p-4">
                              <div className="flex items-start gap-3 flex-wrap">
                                  <div className={`w-10 h-10 rounded-full flex items-center justify-center ${
                                      r.tipo === "modifica_anagrafica" ? "bg-amber-100 text-amber-700" : "bg-violet-100 text-violet-700"
                                  }`}>
                                      {r.tipo === "modifica_anagrafica" ? <User size={18} /> : <UploadIcon size={18} />}
                                  </div>
                                  <div className="flex-1 min-w-0">
                                      <div className="text-sm font-semibold text-slate-800">
                                          <Link to={`/anagrafiche/${r.cliente_id}`} className="text-sky-700 hover:underline">
                                              {r.cliente_nome}
                                          </Link>
                                          <span className="ml-2 text-[10px] uppercase text-slate-400">{r.tipo?.replace(/_/g, " ")}</span>
                                      </div>
                                      <div className="text-xs text-slate-500 mt-1">
                                          Ricevuta: {r.created_at?.slice(0, 16).replace("T", " ")}
                                      </div>
                                      {r.tipo === "modifica_anagrafica" && r.modifiche_richieste && (
                                          <div className="mt-2 bg-slate-50 rounded p-2 text-xs space-y-0.5">
                                              {Object.entries(r.modifiche_richieste).map(([k, v]) => (
                                                  <div key={k}><b className="text-slate-600">{k}:</b> <span className="text-slate-800">{String(v)}</span></div>
                                              ))}
                                          </div>
                                      )}
                                      {r.tipo === "upload_documento" && r.allegato_id && (
                                          <div className="mt-2 text-xs text-sky-700">
                                              📎 Allegato caricato · <Link to={`/allegati/${r.allegato_id}/download`} className="hover:underline">Apri</Link>
                                          </div>
                                      )}
                                      {r.motivo_rifiuto && (
                                          <div className="text-xs text-rose-600 mt-1 italic">Rifiutata: {r.motivo_rifiuto}</div>
                                      )}
                                  </div>
                                  {r.stato === "da_verificare" && (
                                      <div className="flex gap-2">
                                          <Button size="sm" onClick={() => approva(r.id)}
                                              className="bg-emerald-600 hover:bg-emerald-700 text-white"
                                              data-testid={`approva-${r.id}`}>
                                              <CheckCircle2 size={14} className="mr-1" /> Approva
                                          </Button>
                                          <Button size="sm" variant="outline" onClick={() => rifiuta(r.id)}
                                              className="border-rose-300 text-rose-700 hover:bg-rose-50"
                                              data-testid={`rifiuta-${r.id}`}>
                                              <X size={14} className="mr-1" /> Rifiuta
                                          </Button>
                                      </div>
                                  )}
                                  {r.stato !== "da_verificare" && (
                                      <span className={`text-[10px] uppercase font-semibold px-2 py-1 rounded ${
                                          r.stato === "approvata" ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"
                                      }`}>{r.stato}</span>
                                  )}
                              </div>
                          </Card>
                      ))}
                  </div>
              )}

            <div className="mt-8 bg-sky-50 border border-sky-200 rounded-xl p-4 text-sm">
                <div className="font-semibold text-sky-800 mb-1 flex items-center gap-2">
                    <Send size={16} /> Invia credenziali portale a un cliente
                </div>
                <p className="text-xs text-slate-600 mb-2">
                    Dall&apos;anagrafica del cliente, clicca su &quot;Invia credenziali portale&quot; per generare la comunicazione email + WhatsApp.
                </p>
                <p className="text-[10px] text-slate-500">
                    Endpoint: <code>POST /api/anagrafiche/{"{id}"}/invia-credenziali-portale</code>
                </p>
            </div>
        </div>
    );
}
