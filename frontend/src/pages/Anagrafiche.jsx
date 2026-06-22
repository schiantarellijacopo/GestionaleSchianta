import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtDate } from "@/lib/api";
import { PageHeader, Empty, Loading } from "@/components/Shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, Search } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

export default function Anagrafiche() {
    const { user } = useAuth();
    const [list, setList] = useState(null);
    const [q, setQ] = useState("");
    const [open, setOpen] = useState(false);
    const canCreate = ["admin", "collaboratore", "dipendente"].includes(user?.role);

    const load = () => {
        api.get("/anagrafiche", { params: { q: q || undefined } })
            .then((r) => setList(r.data));
    };

    useEffect(() => { load(); /* eslint-disable-next-line */ }, []);
    useEffect(() => {
        const t = setTimeout(load, 250);
        return () => clearTimeout(t);
        // eslint-disable-next-line
    }, [q]);

    return (
        <div data-testid="anagrafiche-page">
            <PageHeader
                title="Anagrafiche clienti"
                subtitle="Persone fisiche e giuridiche presenti a portafoglio"
                actions={
                    canCreate && (
                        <Dialog open={open} onOpenChange={setOpen}>
                            <DialogTrigger asChild>
                                <Button data-testid="anagrafica-new-button" className="bg-sky-700 hover:bg-sky-800">
                                    <Plus size={16} className="mr-1" /> Nuova anagrafica
                                </Button>
                            </DialogTrigger>
                            <NuovaAnagraficaDialog onClose={() => { setOpen(false); load(); }} />
                        </Dialog>
                    )
                }
            />

            <div className="flex items-center gap-2 mb-4">
                <div className="relative flex-1 max-w-md">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                    <Input
                        data-testid="anagrafiche-search"
                        placeholder="Cerca per nome, codice fiscale, email..."
                        value={q}
                        onChange={(e) => setQ(e.target.value)}
                        className="pl-9"
                    />
                </div>
                <span className="text-sm text-slate-500 num">
                    {list ? `${list.length} risultati` : ""}
                </span>
            </div>

            <div className="bg-white border border-slate-200 rounded-md overflow-hidden">
                {list === null ? <Loading /> : list.length === 0 ? <Empty /> : (
                    <table className="tbl w-full">
                        <thead>
                            <tr>
                                <th>Ragione sociale</th>
                                <th>Codice fiscale / P.IVA</th>
                                <th>Tipo</th>
                                <th>Comune</th>
                                <th>Email</th>
                                <th>Telefono</th>
                                <th>Nascita</th>
                            </tr>
                        </thead>
                        <tbody>
                            {list.map((a) => (
                                <tr key={a.id} data-testid={`anagrafica-row-${a.id}`}>
                                    <td>
                                        <Link to={`/anagrafiche/${a.id}`} className="text-sky-700 hover:underline font-medium">
                                            {a.ragione_sociale}
                                        </Link>
                                    </td>
                                    <td className="num font-mono text-xs">{a.codice_fiscale || a.partita_iva || "-"}</td>
                                    <td>
                                        <span className="badge badge-neutral">
                                            {a.tipo === "persona_giuridica" ? "Giuridica" : "Fisica"}
                                        </span>
                                    </td>
                                    <td>{a.comune || "-"} {a.provincia ? `(${a.provincia})` : ""}</td>
                                    <td>{a.email || "-"}</td>
                                    <td>{a.cellulare || a.telefono || "-"}</td>
                                    <td className="num">{fmtDate(a.data_nascita)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
}

function NuovaAnagraficaDialog({ onClose }) {
    const [form, setForm] = useState({
        tipo: "persona_fisica",
        ragione_sociale: "",
        codice_fiscale: "",
        partita_iva: "",
        data_nascita: "",
        sesso: "",
        email: "",
        cellulare: "",
        comune: "",
        provincia: "",
        cap: "",
        indirizzo: "",
    });
    const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

    const save = async () => {
        if (!form.ragione_sociale) {
            toast.error("Inserisci la ragione sociale");
            return;
        }
        try {
            await api.post("/anagrafiche", form);
            toast.success("Anagrafica creata");
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        }
    };

    return (
        <DialogContent className="max-w-2xl">
            <DialogHeader>
                <DialogTitle>Nuova anagrafica</DialogTitle>
            </DialogHeader>
            <div className="grid grid-cols-2 gap-4 py-2">
                <div>
                    <Label>Tipo</Label>
                    <Select value={form.tipo} onValueChange={(v) => set("tipo", v)}>
                        <SelectTrigger data-testid="anag-tipo-select"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="persona_fisica">Persona fisica</SelectItem>
                            <SelectItem value="persona_giuridica">Persona giuridica</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
                <div>
                    <Label>Ragione sociale *</Label>
                    <Input data-testid="anag-rs-input" value={form.ragione_sociale} onChange={(e) => set("ragione_sociale", e.target.value)} />
                </div>
                <div>
                    <Label>Codice fiscale</Label>
                    <Input data-testid="anag-cf-input" value={form.codice_fiscale} onChange={(e) => set("codice_fiscale", e.target.value.toUpperCase())} />
                </div>
                <div>
                    <Label>Partita IVA</Label>
                    <Input value={form.partita_iva} onChange={(e) => set("partita_iva", e.target.value)} />
                </div>
                <div>
                    <Label>Data nascita</Label>
                    <Input type="date" value={form.data_nascita} onChange={(e) => set("data_nascita", e.target.value)} />
                </div>
                <div>
                    <Label>Sesso</Label>
                    <Select value={form.sesso} onValueChange={(v) => set("sesso", v)}>
                        <SelectTrigger><SelectValue placeholder="-" /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="M">Maschio</SelectItem>
                            <SelectItem value="F">Femmina</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
                <div><Label>Email</Label><Input data-testid="anag-email-input" value={form.email} onChange={(e) => set("email", e.target.value)} /></div>
                <div><Label>Cellulare</Label><Input value={form.cellulare} onChange={(e) => set("cellulare", e.target.value)} /></div>
                <div><Label>Indirizzo</Label><Input value={form.indirizzo} onChange={(e) => set("indirizzo", e.target.value)} /></div>
                <div><Label>Comune</Label><Input value={form.comune} onChange={(e) => set("comune", e.target.value)} /></div>
                <div><Label>Provincia</Label><Input maxLength={2} value={form.provincia} onChange={(e) => set("provincia", e.target.value.toUpperCase())} /></div>
                <div><Label>CAP</Label><Input value={form.cap} onChange={(e) => set("cap", e.target.value)} /></div>
            </div>
            <DialogFooter>
                <Button data-testid="anag-save-button" onClick={save} className="bg-sky-700 hover:bg-sky-800">Salva</Button>
            </DialogFooter>
        </DialogContent>
    );
}
