import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Zap, CheckCircle2, Loader2 } from "lucide-react";

const BASE_LABEL = {
    fatturato: "Fatturato", mercedi: "Monte mercedi (retribuzioni)", addetti: "Numero addetti",
    retribuzioni: "Retribuzioni", ricavi: "Ricavi", altro: "Dato consuntivo",
};

export default function RegolazionePublic() {
    const { token } = useParams();
    const [data, setData] = useState(undefined);
    const [valore, setValore] = useState("");
    const [note, setNote] = useState("");
    const [sending, setSending] = useState(false);
    const [done, setDone] = useState(false);

    useEffect(() => {
        api.get(`/public/regolazione/${token}`)
            .then((r) => { setData(r.data); setDone(!!r.data.gia_compilato); })
            .catch(() => setData(null));
    }, [token]);

    const submit = async () => {
        if (valore === "" || isNaN(parseFloat(valore))) return;
        setSending(true);
        try {
            await api.post(`/public/regolazione/${token}`, { base_dichiarata: parseFloat(valore), note: note || null });
            setDone(true);
        } catch { /* noop */ }
        finally { setSending(false); }
    };

    if (data === undefined) {
        return <div className="min-h-screen flex items-center justify-center text-slate-400"><Loader2 className="animate-spin mr-2" /> Caricamento…</div>;
    }
    if (data === null) {
        return <div className="min-h-screen flex items-center justify-center p-6 text-center text-slate-500">Link non valido o non più disponibile.</div>;
    }

    const isAddetti = data.base_tipo === "addetti";
    const baseLbl = BASE_LABEL[data.base_tipo] || "Dato consuntivo";

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-900 to-violet-950 flex items-center justify-center p-4">
            <div className="w-full max-w-lg bg-white rounded-2xl shadow-2xl overflow-hidden" data-testid="regolazione-public">
                <div className="bg-violet-700 text-white px-6 py-5">
                    <div className="flex items-center gap-2 text-sm opacity-90"><Zap size={16} /> {data.agenzia}</div>
                    <h1 className="text-xl font-semibold mt-1">Comunicazione dato di regolazione premio</h1>
                </div>
                <div className="p-6 space-y-4">
                    <div className="text-sm text-slate-600">
                        Gentile <b>{data.contraente_nome}</b>, con riferimento alla polizza
                        <b> {data.numero_polizza}</b> ({data.ramo}{data.prodotto ? ` · ${data.prodotto}` : ""}),
                        soggetta a regolazione del premio, La preghiamo di comunicarci il dato consuntivo del periodo.
                    </div>
                    <div className="grid grid-cols-2 gap-3 bg-slate-50 border border-slate-200 rounded-lg p-3 text-sm">
                        <div><div className="text-[11px] text-slate-400 uppercase">Periodo</div>{data.effetto} → {data.scadenza}</div>
                        <div><div className="text-[11px] text-slate-400 uppercase">Base preventivo</div>{isAddetti ? (data.base_preventivo || 0) : `€ ${(data.base_preventivo || 0).toLocaleString("it-IT")}`}</div>
                    </div>

                    {done ? (
                        <div className="flex flex-col items-center text-center py-6" data-testid="regolazione-public-done">
                            <CheckCircle2 size={48} className="text-emerald-500 mb-3" />
                            <div className="text-lg font-medium text-slate-800">Grazie!</div>
                            <div className="text-sm text-slate-500">Il dato è stato inviato all'agenzia. Verrà elaborato a breve.</div>
                        </div>
                    ) : (
                        <>
                            <div>
                                <Label className="text-sm">{baseLbl} effettivo del periodo {isAddetti ? "(n. addetti)" : "(€)"} *</Label>
                                <Input type="number" step={isAddetti ? "1" : "0.01"} value={valore}
                                    onChange={(e) => setValore(e.target.value)} placeholder={isAddetti ? "Es. 12" : "Es. 120000"}
                                    className="text-lg" data-testid="regolazione-public-valore" />
                            </div>
                            <div>
                                <Label className="text-sm">Note (facoltative)</Label>
                                <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} data-testid="regolazione-public-note" />
                            </div>
                            <Button onClick={submit} disabled={sending || valore === ""} className="w-full bg-violet-700 hover:bg-violet-800 h-11" data-testid="regolazione-public-submit">
                                {sending ? <Loader2 className="animate-spin mr-2" size={16} /> : null} Invia il dato all'agenzia
                            </Button>
                            <p className="text-[11px] text-slate-400 text-center">I dati sono trasmessi in modo sicuro e utilizzati esclusivamente per la regolazione del premio.</p>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}
