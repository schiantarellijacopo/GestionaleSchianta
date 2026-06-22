import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api, fmtDate, fmtEur } from "@/lib/api";
import { PageHeader, Loading, StatusBadge } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { ArrowLeft, GitBranch, UserPlus, ClipboardList } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

export default function AnagraficaDetail() {
    const { id } = useParams();
    const { user } = useAuth();
    const [ana, setAna] = useState(null);
    const [polizze, setPolizze] = useState([]);
    const [interviste, setInterviste] = useState([]);
    const canEdit = ["admin", "collaboratore", "dipendente"].includes(user?.role);

    const load = async () => {
        const [a, p, i] = await Promise.all([
            api.get(`/anagrafiche/${id}`),
            api.get("/polizze", { params: { contraente_id: id } }),
            api.get(`/anagrafiche/${id}/interviste`),
        ]);
        setAna(a.data);
        setPolizze(p.data);
        setInterviste(i.data);
    };

    useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);

    if (!ana) return <Loading />;

    return (
        <div data-testid="anagrafica-detail-page">
            <Link to="/anagrafiche" className="text-sm text-slate-500 hover:text-sky-700 inline-flex items-center gap-1 mb-3">
                <ArrowLeft size={14} /> Torna alle anagrafiche
            </Link>
            <PageHeader
                title={ana.ragione_sociale}
                subtitle={`${ana.tipo === "persona_giuridica" ? "Persona giuridica" : "Persona fisica"} · ${ana.codice_fiscale || ana.partita_iva || "—"}`}
            />

            <Tabs defaultValue="dati" className="w-full">
                <TabsList className="bg-slate-100">
                    <TabsTrigger value="dati" data-testid="tab-dati">Anagrafica</TabsTrigger>
                    <TabsTrigger value="albero" data-testid="tab-albero">Albero genealogico</TabsTrigger>
                    <TabsTrigger value="polizze" data-testid="tab-polizze">Polizze ({polizze.length})</TabsTrigger>
                    <TabsTrigger value="intervista" data-testid="tab-intervista">Intervista</TabsTrigger>
                </TabsList>

                <TabsContent value="dati">
                    <Card className="p-6 border-slate-200 mt-4">
                        <div className="grid grid-cols-2 md:grid-cols-3 gap-x-8 gap-y-4">
                            {[
                                ["Codice fiscale", ana.codice_fiscale],
                                ["Partita IVA", ana.partita_iva],
                                ["Data nascita", fmtDate(ana.data_nascita)],
                                ["Sesso", ana.sesso === "M" ? "Maschio" : ana.sesso === "F" ? "Femmina" : "-"],
                                ["Comune nascita", ana.comune_nascita],
                                ["Email", ana.email],
                                ["Telefono", ana.telefono],
                                ["Cellulare", ana.cellulare],
                                ["IBAN", ana.iban],
                                ["Indirizzo", ana.indirizzo],
                                ["Comune", `${ana.comune || ""} ${ana.provincia ? `(${ana.provincia})` : ""}`],
                                ["CAP", ana.cap],
                                ["Professione", ana.professione],
                                ["Stato civile", ana.stato_civile],
                                ["Fonte", ana.fonte === "import_ania" ? "Import ANIA" : "Manuale"],
                            ].map(([k, v]) => (
                                <div key={k}>
                                    <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-1">{k}</div>
                                    <div className="text-sm text-slate-800 num">{v || "—"}</div>
                                </div>
                            ))}
                        </div>
                    </Card>
                </TabsContent>

                <TabsContent value="albero">
                    <AlberoGenealogico
                        ana={ana}
                        canEdit={canEdit}
                        onReload={load}
                    />
                </TabsContent>

                <TabsContent value="polizze">
                    <Card className="border-slate-200 mt-4 overflow-hidden">
                        {polizze.length === 0 ? (
                            <div className="p-8 text-center text-slate-500 text-sm">Nessuna polizza intestata.</div>
                        ) : (
                            <table className="tbl w-full">
                                <thead>
                                    <tr>
                                        <th>Numero polizza</th>
                                        <th>Compagnia</th>
                                        <th>Ramo</th>
                                        <th>Stato</th>
                                        <th>Effetto</th>
                                        <th>Scadenza</th>
                                        <th className="text-right">Premio</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {polizze.map((p) => (
                                        <tr key={p.id}>
                                            <td><Link to={`/polizze/${p.id}`} className="text-sky-700 hover:underline">{p.numero_polizza}</Link></td>
                                            <td>{p.compagnia_nome}</td>
                                            <td>{p.ramo}</td>
                                            <td><StatusBadge stato={p.stato} /></td>
                                            <td className="num">{fmtDate(p.effetto)}</td>
                                            <td className="num">{fmtDate(p.scadenza)}</td>
                                            <td className="num text-right">{fmtEur(p.premio_lordo)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </Card>
                </TabsContent>

                <TabsContent value="intervista">
                    <Intervista anagrafica_id={id} interviste={interviste} onReload={load} canEdit={canEdit} />
                </TabsContent>
            </Tabs>
        </div>
    );
}

function AlberoGenealogico({ ana, canEdit, onReload }) {
    const [open, setOpen] = useState(false);
    const [target, setTarget] = useState("");
    const [rel, setRel] = useState("figlio");
    const [relInv, setRelInv] = useState("genitore");
    const [options, setOptions] = useState([]);

    useEffect(() => {
        api.get("/anagrafiche").then((r) =>
            setOptions(r.data.filter((a) => a.id !== ana.id))
        );
    }, [ana.id]);

    const aggiungi = async () => {
        if (!target) return;
        try {
            await api.post(`/anagrafiche/${ana.id}/relazioni`, {
                anagrafica_id: target, relazione: rel, relazione_inversa: relInv,
            });
            toast.success("Relazione aggiunta");
            setOpen(false);
            setTarget("");
            onReload();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        }
    };

    const rimuovi = async (tid) => {
        if (!confirm("Rimuovere la relazione?")) return;
        await api.delete(`/anagrafiche/${ana.id}/relazioni/${tid}`);
        toast.success("Relazione rimossa");
        onReload();
    };

    return (
        <Card className="p-6 border-slate-200 mt-4">
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                    <GitBranch size={18} className="text-sky-700" />
                    <h3 className="font-medium text-slate-900">Relazioni familiari</h3>
                </div>
                {canEdit && (
                    <Dialog open={open} onOpenChange={setOpen}>
                        <DialogTrigger asChild>
                            <Button size="sm" variant="outline" data-testid="add-relation-button">
                                <UserPlus size={14} className="mr-1" /> Aggiungi
                            </Button>
                        </DialogTrigger>
                        <DialogContent>
                            <DialogHeader><DialogTitle>Aggiungi relazione</DialogTitle></DialogHeader>
                            <div className="space-y-3 py-2">
                                <div>
                                    <Label>Anagrafica collegata</Label>
                                    <Select value={target} onValueChange={setTarget}>
                                        <SelectTrigger data-testid="rel-target-select"><SelectValue placeholder="Seleziona..." /></SelectTrigger>
                                        <SelectContent>
                                            {options.map((o) => (
                                                <SelectItem key={o.id} value={o.id}>{o.ragione_sociale}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                                <div className="grid grid-cols-2 gap-3">
                                    <div>
                                        <Label>{ana.ragione_sociale} &egrave;</Label>
                                        <Select value={rel} onValueChange={setRel}>
                                            <SelectTrigger><SelectValue /></SelectTrigger>
                                            <SelectContent>
                                                {["genitore", "figlio", "coniuge", "fratello", "nonno", "nipote", "zio", "cugino", "altro"].map((r) => (
                                                    <SelectItem key={r} value={r}>{r}</SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div>
                                        <Label>{"L'altro è"}</Label>
                                        <Select value={relInv} onValueChange={setRelInv}>
                                            <SelectTrigger><SelectValue /></SelectTrigger>
                                            <SelectContent>
                                                {["genitore", "figlio", "coniuge", "fratello", "nonno", "nipote", "zio", "cugino", "altro"].map((r) => (
                                                    <SelectItem key={r} value={r}>{r}</SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>
                            </div>
                            <DialogFooter>
                                <Button data-testid="rel-save-button" onClick={aggiungi} className="bg-sky-700 hover:bg-sky-800">Salva</Button>
                            </DialogFooter>
                        </DialogContent>
                    </Dialog>
                )}
            </div>

            {ana.relazioni_risolte?.length === 0 ? (
                <div className="text-sm text-slate-500 py-6 text-center">Nessuna relazione registrata.</div>
            ) : (
                <div className="relative">
                    <div className="flex justify-center mb-8">
                        <div className="tree-node bg-sky-50 border-sky-200 font-medium">
                            {ana.ragione_sociale}
                        </div>
                    </div>
                    <div className="flex flex-wrap justify-center gap-4 relative">
                        {ana.relazioni_risolte?.map((r) => (
                            <div key={r.id} className="flex flex-col items-center" data-testid={`relation-${r.id}`}>
                                <div className="h-6 w-px bg-slate-300 -mt-8" />
                                <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">{r.relazione}</div>
                                <div className="tree-node">
                                    <Link to={`/anagrafiche/${r.id}`} className="text-sky-700 hover:underline">
                                        {r.ragione_sociale}
                                    </Link>
                                    <div className="text-[11px] text-slate-500 num">{r.codice_fiscale || "-"}</div>
                                    {canEdit && (
                                        <button
                                            onClick={() => rimuovi(r.id)}
                                            className="text-[10px] text-rose-600 hover:underline mt-1"
                                        >
                                            rimuovi
                                        </button>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </Card>
    );
}

function Intervista({ anagrafica_id, interviste, onReload, canEdit }) {
    const [form, setForm] = useState({
        situazione_familiare: { coniugato: "", figli: "", a_carico: "" },
        situazione_lavorativa: { professione: "", reddito_annuo: "", azienda: "" },
        situazione_patrimoniale: { casa_proprieta: "", veicoli: "", investimenti: "" },
        coperture_attuali: { vita: "", malattia: "", infortuni: "", rc_capofamiglia: "" },
        obiettivi: { protezione: "", risparmio: "", previdenza: "" },
        note: "",
    });
    const upd = (sec, k, v) => setForm((f) => ({ ...f, [sec]: { ...f[sec], [k]: v } }));

    const salva = async () => {
        try {
            await api.post(`/anagrafiche/${anagrafica_id}/interviste`, form);
            toast.success("Intervista salvata");
            onReload();
        } catch (e) {
            toast.error("Errore: " + (e.response?.data?.detail || e.message));
        }
    };

    return (
        <div className="space-y-6 mt-4">
            {canEdit && (
                <Card className="p-6 border-slate-200">
                    <div className="flex items-center gap-2 mb-4">
                        <ClipboardList size={18} className="text-sky-700" />
                        <h3 className="font-medium text-slate-900">Nuova intervista cliente</h3>
                    </div>

                    {[
                        { sec: "situazione_familiare", title: "Situazione familiare", fields: [
                            ["coniugato", "Stato civile"], ["figli", "N. figli"], ["a_carico", "Persone a carico"]] },
                        { sec: "situazione_lavorativa", title: "Situazione lavorativa", fields: [
                            ["professione", "Professione"], ["reddito_annuo", "Reddito annuo"], ["azienda", "Azienda"]] },
                        { sec: "situazione_patrimoniale", title: "Situazione patrimoniale", fields: [
                            ["casa_proprieta", "Casa di proprietà"], ["veicoli", "Veicoli"], ["investimenti", "Investimenti"]] },
                        { sec: "coperture_attuali", title: "Coperture attuali", fields: [
                            ["vita", "Vita"], ["malattia", "Malattia"], ["infortuni", "Infortuni"], ["rc_capofamiglia", "RC capofamiglia"]] },
                        { sec: "obiettivi", title: "Obiettivi", fields: [
                            ["protezione", "Protezione"], ["risparmio", "Risparmio"], ["previdenza", "Previdenza"]] },
                    ].map(({ sec, title, fields }) => (
                        <div key={sec} className="mb-5">
                            <div className="text-xs font-semibold uppercase tracking-wider text-slate-600 mb-2">{title}</div>
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                                {fields.map(([k, label]) => (
                                    <div key={k}>
                                        <Label className="text-xs">{label}</Label>
                                        <Input value={form[sec][k]} onChange={(e) => upd(sec, k, e.target.value)} />
                                    </div>
                                ))}
                            </div>
                        </div>
                    ))}

                    <div>
                        <Label className="text-xs">Note</Label>
                        <Textarea value={form.note} onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))} rows={3} />
                    </div>

                    <div className="mt-4 flex justify-end">
                        <Button data-testid="intervista-save-button" onClick={salva} className="bg-sky-700 hover:bg-sky-800">
                            Salva intervista
                        </Button>
                    </div>
                </Card>
            )}

            <Card className="p-6 border-slate-200">
                <h3 className="font-medium text-slate-900 mb-3">Interviste precedenti ({interviste.length})</h3>
                {interviste.length === 0 ? (
                    <div className="text-sm text-slate-500">Nessuna intervista registrata.</div>
                ) : (
                    <ul className="divide-y divide-slate-100">
                        {interviste.map((i) => (
                            <li key={i.id} className="py-3 text-sm">
                                <div className="font-medium text-slate-900 num">{fmtDate(i.data_intervista)}</div>
                                <div className="text-xs text-slate-500 mt-1">
                                    {[i.situazione_familiare?.coniugato, i.situazione_lavorativa?.professione, i.obiettivi?.protezione]
                                        .filter(Boolean).join(" · ")}
                                </div>
                                {i.note && <div className="text-xs text-slate-600 mt-1">{i.note}</div>}
                            </li>
                        ))}
                    </ul>
                )}
            </Card>
        </div>
    );
}
