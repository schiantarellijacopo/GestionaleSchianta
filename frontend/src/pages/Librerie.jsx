import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import RowActions from "@/components/RowActions";
import { Plus, Landmark, Wallet, Package, Tags, Building2, UserCog, Shield, Building, Percent, Upload, FileText, Trash2, GraduationCap, RotateCw, Pencil } from "lucide-react";
import { toast } from "sonner";

const SECTIONS = [
    { key: "azienda", label: "Azienda", icon: <Building size={14} />, endpoint: "/librerie/azienda" },
    { key: "banche", label: "Banche", icon: <Landmark size={14} />, endpoint: "/librerie/banche" },
    { key: "conti-cassa", label: "Conti deposito", icon: <Wallet size={14} />, endpoint: "/librerie/conti-cassa" },
    { key: "mezzi-pagamento", label: "Modalità pagamento", icon: <Wallet size={14} />, endpoint: "/librerie/mezzi-pagamento" },
    { key: "tipi-pagamento", label: "Tipi pagamento", icon: <Wallet size={14} />, endpoint: "/librerie/tipi-pagamento" },
    { key: "prodotti", label: "Prodotti", icon: <Package size={14} />, endpoint: "/librerie/prodotti" },
    { key: "rami", label: "Rami", icon: <Tags size={14} />, endpoint: "/librerie/rami" },
    { key: "compagnie", label: "Compagnie", icon: <Building2 size={14} />, endpoint: "/compagnie" },
    { key: "utenti", label: "Utenti / Collaboratori", icon: <UserCog size={14} />, endpoint: "/auth/users" },
    { key: "schema-provvigionale", label: "Sistema provvigionale", icon: <Percent size={14} />, endpoint: "/librerie/schema-provvigionale" },
    { key: "voci-ricorsive", label: "Voci ricorsive collab.", icon: <RotateCw size={14} />, endpoint: "/voci-ricorsive-collab", custom: true },
    { key: "mapping-garanzie", label: "Mapping Garanzie ANIA", icon: <Tags size={14} />, endpoint: "/librerie/mapping-garanzie" },
    { key: "mapping-operatori", label: "Mapping Operatori ANIA", icon: <UserCog size={14} />, endpoint: "/librerie/mapping-operatori" },
];

export default function Librerie() {
    return (
        <div data-testid="librerie-page">
            <PageHeader
                title="Librerie / Anagrafiche di sistema"
                subtitle="Banche, conti cassa, prodotti, rami: configurazioni riusate nei moduli"
            />
            <Tabs defaultValue="azienda">
                <TabsList className="bg-slate-100 flex-wrap h-auto">
                    {SECTIONS.map((s) => (
                        <TabsTrigger key={s.key} value={s.key} data-testid={`lib-tab-${s.key}`}>
                            {s.icon}<span className="ml-1.5">{s.label}</span>
                        </TabsTrigger>
                    ))}
                </TabsList>
                {SECTIONS.map((s) => (
                    <TabsContent key={s.key} value={s.key} className="mt-4">
                        {s.key === "azienda" ? <AziendaSezione />
                            : s.key === "voci-ricorsive" ? <VociRicorsiveSezione />
                            : <Sezione section={s} />}
                    </TabsContent>
                ))}
            </Tabs>
        </div>
    );
}

function Sezione({ section }) {
    const [list, setList] = useState(null);
    const [open, setOpen] = useState(false);
    const [editing, setEditing] = useState(null);

    const load = () => api.get(section.endpoint).then((r) => setList(r.data));
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [section.key]);

    const elimina = async (id) => {
        try {
            await api.delete(`${section.endpoint}/${id}`);
            toast.success("Eliminato"); load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const FormDialog = SECTION_FORMS[section.key];

    const applicaMapping = async () => {
        if (!window.confirm("Applicare il mapping a TUTTE le polizze esistenti?")) return;
        try {
            const url = section.key === "mapping-garanzie"
                ? "/librerie/mapping-garanzie/applica-a-polizze"
                : "/librerie/mapping-operatori/applica-a-polizze";
            const r = await api.post(url);
            toast.success(`${r.data.polizze_aggiornate} polizze aggiornate`);
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const showApplica = section.key === "mapping-garanzie" || section.key === "mapping-operatori";

    return (
        <div>
            <div className="flex items-center justify-between mb-3">
                <span className="text-sm text-slate-500 num">{list ? `${list.length} elementi` : ""}</span>
                <div className="flex gap-2">
                    {showApplica && (
                        <Button variant="outline" size="sm" onClick={applicaMapping} data-testid={`lib-apply-${section.key}`}>
                            Applica a polizze esistenti
                        </Button>
                    )}
                    <Dialog open={open || !!editing} onOpenChange={(o) => { if (!o) { setOpen(false); setEditing(null); } }}>
                        <DialogTrigger asChild>
                            <Button data-testid={`lib-new-${section.key}`} onClick={() => setOpen(true)} className="bg-sky-700 hover:bg-sky-800">
                                <Plus size={14} className="mr-1" /> Nuovo
                            </Button>
                        </DialogTrigger>
                        <FormDialog
                            section={section}
                            editing={editing}
                            onClose={() => { setOpen(false); setEditing(null); load(); }}
                        />
                    </Dialog>
                </div>
            </div>

            <Card className="border-slate-200 overflow-hidden">
                {list === null ? <Loading /> : list.length === 0 ? <Empty /> :
                    <ListaSezione section={section} list={list} onEdit={setEditing} onDelete={elimina} />
                }
            </Card>
        </div>
    );
}

function ListaSezione({ section, list, onEdit, onDelete }) {
    if (section.key === "banche") {
        return (
            <table className="tbl w-full">
                <thead><tr><th>Nome</th><th>ABI</th><th>Referente</th><th>Note</th><th></th></tr></thead>
                <tbody>
                    {list.map((b) => (
                        <tr key={b.id}>
                            <td className="font-medium">{b.nome}</td>
                            <td className="num text-xs">{b.codice_abi || "-"}</td>
                            <td>{b.referente || "-"}</td>
                            <td className="text-xs text-slate-500">{b.note || ""}</td>
                            <td className="text-right">
                                <RowActions onEdit={() => onEdit(b)} onDelete={() => onDelete(b.id)} label="banca" />
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        );
    }
    if (section.key === "conti-cassa") {
        return (
            <table className="tbl w-full">
                <thead><tr><th>Nome</th><th>Tipo</th><th>IBAN</th><th className="text-right">Saldo iniz.</th><th>Attivo</th><th title="Non mostrare in Prima Nota">PN</th><th title="Escludi da calcolo liquidità">Liq</th><th></th></tr></thead>
                <tbody>
                    {list.map((c) => (
                        <tr key={c.id}>
                            <td className="font-medium">{c.nome}</td>
                            <td><span className="badge badge-neutral">{c.tipo}</span></td>
                            <td className="num text-xs">{c.iban || "-"}</td>
                            <td className="num text-right">{Number(c.saldo_iniziale || 0).toFixed(2)}</td>
                            <td>{c.attivo ? <span className="badge badge-success">sì</span> : <span className="badge badge-neutral">no</span>}</td>
                            <td>{c.nascondi_prima_nota ? <span className="badge badge-warning">nascosto</span> : <span className="text-slate-400 text-xs">—</span>}</td>
                            <td>{c.escludi_da_liquidita ? <span className="badge badge-warning">escluso</span> : <span className="text-slate-400 text-xs">—</span>}</td>
                            <td className="text-right">
                                <RowActions onEdit={() => onEdit(c)} onDelete={() => onDelete(c.id)} label="conto" />
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        );
    }
    if (section.key === "tipi-pagamento") {
        return (
            <table className="tbl w-full">
                <thead><tr><th>Label</th><th>Modalità</th><th>Conto deposito</th><th className="text-right">Ordine</th><th>Attivo</th><th></th></tr></thead>
                <tbody>
                    {list.map((t) => (
                        <tr key={t.id}>
                            <td className="font-semibold uppercase">{t.label}</td>
                            <td className="text-xs"><span className="badge badge-neutral">{t.modalita_codice}</span></td>
                            <td className="text-xs text-slate-600">{t.conto_id ? <span className="num font-mono text-[10px]">{t.conto_id.slice(0,8)}</span> : <span className="italic text-slate-400">—</span>}</td>
                            <td className="num text-right">{t.ordine}</td>
                            <td>{t.attivo ? <span className="badge badge-success">sì</span> : <span className="badge badge-neutral">no</span>}</td>
                            <td className="text-right">
                                <RowActions onEdit={() => onEdit(t)} onDelete={() => onDelete(t.id)} label="tipo pagamento" />
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        );
    }
    if (section.key === "mezzi-pagamento") {
        return (
            <table className="tbl w-full">
                <thead><tr><th>Codice</th><th>Etichetta</th><th>Tipo conto</th><th className="text-right">Ordine</th><th>Attivo</th><th></th></tr></thead>
                <tbody>
                    {list.map((m) => (
                        <tr key={m.id}>
                            <td className="num font-mono text-xs">{m.codice}</td>
                            <td className="font-medium">{m.label}</td>
                            <td><span className="badge badge-neutral">{m.tipo_conto}</span></td>
                            <td className="num text-right">{m.ordine}</td>
                            <td>{m.attivo ? <span className="badge badge-success">sì</span> : <span className="badge badge-neutral">no</span>}</td>
                            <td className="text-right">
                                <RowActions onEdit={() => onEdit(m)} onDelete={() => onDelete(m.id)} label="mezzo pagamento" />
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        );
    }
    if (section.key === "prodotti") {
        return (
            <table className="tbl w-full">
                <thead><tr><th>Nome</th><th>Ramo</th><th>Compagnia</th><th className="text-right">Mora (gg)</th><th>Descrizione</th><th></th></tr></thead>
                <tbody>
                    {list.map((p) => (
                        <tr key={p.id}>
                            <td className="font-medium">
                                {p.nome}
                                {p.is_libro_matricola && (
                                    <span className="ml-2 inline-block bg-amber-100 text-amber-800 text-[9px] font-bold px-1.5 py-0.5 rounded uppercase">L.M.</span>
                                )}
                            </td>
                            <td><span className="badge badge-neutral">{p.ramo || "-"}</span></td>
                            <td className="text-xs">{p.compagnia_id || "-"}</td>
                            <td className="num text-right font-medium">{p.termini_mora_giorni ?? 15}</td>
                            <td className="text-xs text-slate-500">{p.descrizione || ""}</td>
                            <td className="text-right">
                                <RowActions onEdit={() => onEdit(p)} onDelete={() => onDelete(p.id)} label="prodotto" />
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        );
    }
    // rami
    if (section.key === "rami") {
        return (
            <table className="tbl w-full">
                <thead><tr><th>Codice</th><th>Nome</th><th>Descrizione</th><th></th></tr></thead>
                <tbody>
                    {list.map((r) => (
                        <tr key={r.id}>
                            <td className="num font-medium">{r.codice}</td>
                            <td>{r.nome}</td>
                            <td className="text-xs text-slate-500">{r.descrizione || ""}</td>
                            <td className="text-right">
                                <RowActions onEdit={() => onEdit(r)} onDelete={() => onDelete(r.id)} label="ramo" />
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        );
    }
    if (section.key === "compagnie") {
        return (
            <table className="tbl w-full">
                <thead><tr><th>Codice</th><th>Ragione sociale</th><th>Referente</th><th>Email</th><th>Trattiene Provv.</th><th>Attiva</th><th></th></tr></thead>
                <tbody>
                    {list.map((c) => (
                        <tr key={c.id}>
                            <td className="num text-xs">{c.codice}</td>
                            <td className="font-medium">{c.ragione_sociale}</td>
                            <td>{c.referente || "-"}</td>
                            <td className="text-xs">{c.email || "-"}</td>
                            <td>{c.trattiene_provvigioni !== false ? <span className="badge badge-success">sì</span> : <span className="badge badge-neutral">no</span>}</td>
                            <td>{c.attiva ? <span className="badge badge-success">sì</span> : <span className="badge badge-neutral">no</span>}</td>
                            <td className="text-right">
                                <RowActions onEdit={() => onEdit(c)} onDelete={() => onDelete(c.id)} label="compagnia" />
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        );
    }
    if (section.key === "schema-provvigionale") {
        return (
            <table className="tbl w-full">
                <thead><tr><th>Nome</th><th>Collaboratore</th><th>Compagnia</th><th>Ramo</th><th className="text-right">% Collab</th><th className="text-right">% Premio</th><th>Attivo</th><th></th></tr></thead>
                <tbody>
                    {list.map((s) => (
                        <tr key={s.id}>
                            <td className="font-medium">{s.nome}</td>
                            <td className="text-xs">{s.collaboratore_nome || <span className="text-slate-400">tutti</span>}</td>
                            <td className="text-xs">{s.compagnia_nome || <span className="text-slate-400">tutte</span>}</td>
                            <td><span className="badge badge-neutral">{s.ramo || "tutti"}</span></td>
                            <td className="num text-right font-semibold text-emerald-700">{s.percentuale_collaboratore}%</td>
                            <td className="num text-right text-slate-600">{s.percentuale_su_premio}%</td>
                            <td>{s.attivo ? <span className="badge badge-success">sì</span> : <span className="badge badge-neutral">no</span>}</td>
                            <td className="text-right">
                                <RowActions onEdit={() => onEdit(s)} onDelete={() => onDelete(s.id)} label="schema" />
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        );
    }
    // mapping garanzie ANIA → nome personalizzato
    if (section.key === "mapping-garanzie") {
        return (
            <table className="tbl w-full">
                <thead><tr><th>Codice ANIA</th><th>Descrizione originale (ANIA)</th><th>Nome personalizzato</th><th>Note</th><th></th></tr></thead>
                <tbody>
                    {list.length === 0 && <tr><td colSpan="5" className="text-center text-slate-400 py-6">Nessun mapping. Le voci si creano automaticamente all&apos;import ANIA.</td></tr>}
                    {list.map((m) => (
                        <tr key={m.id}>
                            <td className="num font-medium">{m.codice_ania}</td>
                            <td className="text-xs">{m.descrizione_ania || "-"}</td>
                            <td className="font-medium text-sky-700">{m.nome_personalizzato || <span className="text-slate-400 italic">da mappare</span>}</td>
                            <td className="text-xs text-slate-500">{m.note || ""}</td>
                            <td className="text-right">
                                <RowActions onEdit={() => onEdit(m)} onDelete={() => onDelete(m.id)} label="mapping" />
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        );
    }
    // mapping operatori ANIA → user app
    if (section.key === "mapping-operatori") {
        return (
            <table className="tbl w-full">
                <thead><tr><th>Codice ANIA</th><th>Nome operatore (ANIA)</th><th>Utente collegato</th><th></th></tr></thead>
                <tbody>
                    {list.length === 0 && <tr><td colSpan="4" className="text-center text-slate-400 py-6">Nessun mapping. Le voci si creano automaticamente all&apos;import ANIA.</td></tr>}
                    {list.map((m) => (
                        <tr key={m.id}>
                            <td className="num font-medium">{m.codice_ania}</td>
                            <td className="text-xs">{m.descrizione_ania || m.nome_ania || "-"}</td>
                            <td>
                                {m.user
                                    ? <><span className="font-medium">{m.user.name}</span> <span className="text-[10px] text-slate-500">({m.user.role})</span></>
                                    : <span className="text-slate-400 italic">da mappare</span>}
                            </td>
                            <td className="text-right">
                                <RowActions onEdit={() => onEdit(m)} onDelete={() => onDelete(m.id)} label="mapping" />
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        );
    }
    // utenti
    const ROLE_COLORS = {
        admin: "badge-danger", collaboratore: "badge-info",
        dipendente: "badge-success", cliente: "badge-neutral",
    };
    return (
        <table className="tbl w-full">
            <thead><tr><th>Nome</th><th>Email</th><th>Ruolo</th><th>Anagrafica collegata</th><th></th></tr></thead>
            <tbody>
                {list.map((u) => (
                    <tr key={u.id}>
                        <td className="font-medium flex items-center gap-2">
                            <div className="w-7 h-7 rounded-full bg-slate-200 text-slate-700 flex items-center justify-center text-xs font-semibold">
                                {(u.name || "?").charAt(0).toUpperCase()}
                            </div>
                            {u.name}
                        </td>
                        <td className="text-xs">{u.email}</td>
                        <td><span className={`badge ${ROLE_COLORS[u.role] || "badge-neutral"} inline-flex items-center gap-1`}>
                            <Shield size={10} /> {u.role}
                        </span></td>
                        <td className="text-xs text-slate-500 num">{u.anagrafica_id ? u.anagrafica_id.slice(0, 8) : "-"}</td>
                        <td className="text-right">
                            <RowActions onEdit={() => onEdit(u)} onDelete={() => onDelete(u.id)} label="utente" />
                        </td>
                    </tr>
                ))}
            </tbody>
        </table>
    );
}

const SECTION_FORMS = {
    "banche": BancaForm,
    "conti-cassa": ContoForm,
    "mezzi-pagamento": MezzoPagamentoForm,
    "tipi-pagamento": TipoPagamentoForm,
    "prodotti": ProdottoForm,
    "rami": RamoForm,
    "compagnie": CompagniaForm,
    "utenti": UtenteForm,
    "schema-provvigionale": SchemaProvvForm,
    "mapping-garanzie": MappingGaranziaForm,
    "mapping-operatori": MappingOperatoreForm,
};

function MappingGaranziaForm({ section, editing, onClose }) {
    return <GenericForm section={section} editing={editing} onClose={onClose}
        defaults={{ codice_ania: "", descrizione_ania: "", nome_personalizzato: "", note: "" }}
        fields={(f, set) => (
            <>
                <div><Label>Codice ANIA *</Label><Input value={f.codice_ania || ""} onChange={(e) => set("codice_ania", e.target.value.toUpperCase())} data-testid="mg-codice" /></div>
                <div><Label>Descrizione originale (ANIA)</Label><Input value={f.descrizione_ania || ""} onChange={(e) => set("descrizione_ania", e.target.value)} placeholder="Auto-popolato all'import" /></div>
                <div><Label>Nome personalizzato</Label><Input value={f.nome_personalizzato || ""} onChange={(e) => set("nome_personalizzato", e.target.value)} placeholder="Come vuoi chiamarla nel CRM (es. 'RCA Standard')" data-testid="mg-nome" /></div>
                <div><Label>Note</Label><Input value={f.note || ""} onChange={(e) => set("note", e.target.value)} /></div>
            </>
        )}
    />;
}

function MappingOperatoreForm({ section, editing, onClose }) {
    const [users, setUsers] = useState([]);
    useEffect(() => {
        api.get("/auth/users").then((r) => setUsers(r.data.filter((u) => u.role !== "cliente")));
    }, []);
    return <GenericForm section={section} editing={editing} onClose={onClose}
        defaults={{ codice_ania: "", descrizione_ania: "", user_id: "" }}
        fields={(f, set) => (
            <>
                <div><Label>Codice operatore ANIA *</Label><Input value={f.codice_ania || ""} onChange={(e) => set("codice_ania", e.target.value)} data-testid="mo-codice" /></div>
                <div><Label>Nome operatore (ANIA)</Label><Input value={f.descrizione_ania || ""} onChange={(e) => set("descrizione_ania", e.target.value)} placeholder="Auto-popolato all'import" /></div>
                <div>
                    <Label>Utente del CRM collegato</Label>
                    <Select value={f.user_id || ""} onValueChange={(v) => set("user_id", v)}>
                        <SelectTrigger data-testid="mo-user-select"><SelectValue placeholder="Seleziona utente" /></SelectTrigger>
                        <SelectContent>
                            {users.map((u) => <SelectItem key={u.id} value={u.id}>{u.name} ({u.role})</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
                <div className="text-xs text-slate-500 bg-sky-50 border border-sky-200 rounded p-2">
                    Dopo aver mappato gli operatori puoi cliccare il pulsante <b>&quot;Applica a polizze esistenti&quot;</b> (sotto la tabella) per rinominare/riassegnare in massa.
                </div>
            </>
        )}
    />;
}

function GenericForm({ section, editing, onClose, fields, defaults, dialogClass }) {
    const [f, setF] = useState(editing || defaults);
    const isEdit = !!editing;
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    // FIX: ricarica il form quando cambia editing (es. apertura dialog su voce diversa).
    // Senza questo, lo state resta legato alla PRIMA voce ed Edit mostrerebbe i campi vuoti.
    useEffect(() => {
        if (editing) setF({ ...defaults, ...editing });
        else setF(defaults);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [editing]);

    const save = async () => {
        try {
            if (isEdit) {
                await api.put(`${section.endpoint}/${editing.id}`, f);
                toast.success("Aggiornato");
            } else {
                await api.post(section.endpoint, f);
                toast.success("Creato");
            }
            onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <DialogContent className={dialogClass || "max-w-lg"}>
            <DialogHeader><DialogTitle>{isEdit ? "Modifica" : "Nuovo"} {section.label.toLowerCase()}</DialogTitle></DialogHeader>
            <div className="space-y-3 py-2 max-h-[70vh] overflow-y-auto">
                {fields(f, set)}
            </div>
            <DialogFooter>
                <Button data-testid={`lib-save-${section.key}`} onClick={save} className="bg-sky-700 hover:bg-sky-800">
                    {isEdit ? "Aggiorna" : "Salva"}
                </Button>
            </DialogFooter>
        </DialogContent>
    );
}

function BancaForm({ section, editing, onClose }) {
    return <GenericForm section={section} editing={editing} onClose={onClose}
        defaults={{ nome: "", codice_abi: "", referente: "", note: "", attiva: true }}
        fields={(f, set) => (
            <>
                <div><Label>Nome banca *</Label><Input value={f.nome || ""} onChange={(e) => set("nome", e.target.value)} /></div>
                <div className="grid grid-cols-2 gap-3">
                    <div><Label>Codice ABI</Label><Input value={f.codice_abi || ""} onChange={(e) => set("codice_abi", e.target.value)} /></div>
                    <div><Label>Referente</Label><Input value={f.referente || ""} onChange={(e) => set("referente", e.target.value)} /></div>
                </div>
                <div><Label>Note</Label><Input value={f.note || ""} onChange={(e) => set("note", e.target.value)} /></div>
            </>
        )}
    />;
}

function ContoForm({ section, editing, onClose }) {
    const [banche, setBanche] = useState([]);
    useEffect(() => { api.get("/librerie/banche").then((r) => setBanche(r.data)); }, []);
    return <GenericForm section={section} editing={editing} onClose={onClose}
        defaults={{ nome: "", tipo: "banca", banca_id: "", iban: "", saldo_iniziale: 0, ordine: 0, attivo: true, nascondi_prima_nota: false, escludi_da_liquidita: false }}
        fields={(f, set) => (
            <>
                <div><Label>Nome conto *</Label><Input value={f.nome || ""} onChange={(e) => set("nome", e.target.value)} /></div>
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <Label>Tipo</Label>
                        <Select value={f.tipo || "banca"} onValueChange={(v) => set("tipo", v)}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="cassa">Cassa</SelectItem>
                                <SelectItem value="banca">Banca</SelectItem>
                                <SelectItem value="carta">Carta</SelectItem>
                                <SelectItem value="rid">RID / Direzione</SelectItem>
                                <SelectItem value="online">Online</SelectItem>
                                <SelectItem value="altro">Altro</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <Label>Banca collegata</Label>
                        <Select value={f.banca_id || ""} onValueChange={(v) => set("banca_id", v)}>
                            <SelectTrigger><SelectValue placeholder="-" /></SelectTrigger>
                            <SelectContent>
                                {banche.map((b) => <SelectItem key={b.id} value={b.id}>{b.nome}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                </div>
                <div className="grid grid-cols-3 gap-3">
                    <div><Label>IBAN</Label><Input value={f.iban || ""} onChange={(e) => set("iban", e.target.value)} /></div>
                    <div><Label>Saldo iniziale €</Label><Input type="number" step="0.01" value={f.saldo_iniziale || 0} onChange={(e) => set("saldo_iniziale", parseFloat(e.target.value) || 0)} /></div>
                    <div><Label>Ordine</Label><Input type="number" value={f.ordine || 0} onChange={(e) => set("ordine", parseInt(e.target.value) || 0)} /></div>
                </div>
                <div className="border-t pt-3 mt-2 space-y-2">
                    <div className="text-xs font-medium text-slate-600 uppercase">Opzioni operative</div>
                    <label className="flex items-start gap-2 text-sm cursor-pointer">
                        <input
                            type="checkbox"
                            checked={!!f.nascondi_prima_nota}
                            onChange={(e) => set("nascondi_prima_nota", e.target.checked)}
                            data-testid="conto-flag-nascondi-pn"
                            className="mt-0.5"
                        />
                        <span>
                            <strong>Non mostrare più in Prima Nota</strong>
                            <div className="text-[10px] text-slate-500">Utile per conti dismessi senza eliminarli.</div>
                        </span>
                    </label>
                    <label className="flex items-start gap-2 text-sm cursor-pointer">
                        <input
                            type="checkbox"
                            checked={!!f.escludi_da_liquidita}
                            onChange={(e) => set("escludi_da_liquidita", e.target.checked)}
                            data-testid="conto-flag-escludi-liq"
                            className="mt-0.5"
                        />
                        <span>
                            <strong>Escludi dal calcolo della liquidità (anche postera)</strong>
                            <div className="text-[10px] text-slate-500">Es. conti tecnici, prelievi soci, partite di giro.</div>
                        </span>
                    </label>
                </div>
            </>
        )}
    />;
}

function TipoPagamentoForm({ section, editing, onClose }) {
    const [modalita, setModalita] = useState([]);
    const [conti, setConti] = useState([]);
    useEffect(() => {
        api.get("/librerie/mezzi-pagamento").then((r) => setModalita(r.data || []));
        api.get("/librerie/conti-cassa", { params: { attivi: true } })
            .then((r) => setConti(r.data || []));
    }, []);
    return <GenericForm section={section} editing={editing} onClose={onClose}
        defaults={{
            label: "", modalita_codice: "", conto_id: "",
            ordine: 0, attivo: true, note: "",
        }}
        fields={(f, set) => {
            const autoLabel = () => {
                const mod = modalita.find((m) => m.codice === f.modalita_codice);
                const conto = conti.find((c) => c.id === f.conto_id);
                const lbl = [mod?.label || mod?.codice || "", conto?.nome || ""]
                    .filter(Boolean).join(" ").toUpperCase();
                set("label", lbl);
            };
            return (
                <>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <Label>Modalità *</Label>
                            <select
                                className="w-full border rounded h-9 px-2 text-sm"
                                value={f.modalita_codice || ""}
                                onChange={(e) => set("modalita_codice", e.target.value)}
                                data-testid="tp-modalita"
                            >
                                <option value="">— seleziona —</option>
                                {modalita.map((m) => (
                                    <option key={m.codice} value={m.codice}>{m.label}</option>
                                ))}
                            </select>
                        </div>
                        <div>
                            <Label>Conto deposito</Label>
                            <select
                                className="w-full border rounded h-9 px-2 text-sm"
                                value={f.conto_id || ""}
                                onChange={(e) => set("conto_id", e.target.value)}
                                data-testid="tp-conto"
                            >
                                <option value="">— nessuno —</option>
                                {conti.map((c) => (
                                    <option key={c.id} value={c.id}>{c.nome}</option>
                                ))}
                            </select>
                        </div>
                    </div>
                    <div>
                        <div className="flex items-center justify-between mb-1">
                            <Label>Label visualizzata *</Label>
                            <button
                                type="button" onClick={autoLabel}
                                className="text-[10px] text-sky-700 hover:text-sky-900 underline"
                                data-testid="tp-auto-label"
                            >Auto-componi</button>
                        </div>
                        <Input
                            placeholder="es. BONIFICO BPER SONDRIO"
                            value={f.label || ""}
                            onChange={(e) => set("label", e.target.value)}
                            data-testid="tp-label"
                        />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <Label>Ordine</Label>
                            <Input type="number" value={f.ordine || 0}
                                onChange={(e) => set("ordine", parseInt(e.target.value, 10) || 0)}
                            />
                        </div>
                        <div className="flex items-end">
                            <label className="flex items-center gap-2 text-sm">
                                <input
                                    type="checkbox"
                                    checked={f.attivo !== false}
                                    onChange={(e) => set("attivo", e.target.checked)}
                                />
                                Attivo
                            </label>
                        </div>
                    </div>
                    <div>
                        <Label>Note</Label>
                        <Input value={f.note || ""} onChange={(e) => set("note", e.target.value)} />
                    </div>
                </>
            );
        }}
    />;
}

function MezzoPagamentoForm({ section, editing, onClose }) {
    const [conti, setConti] = useState([]);
    useEffect(() => {
        api.get("/librerie/conti-cassa", { params: { attivi: true } })
            .then((r) => setConti(r.data || []));
    }, []);
    return <GenericForm section={section} editing={editing} onClose={onClose}
        defaults={{
            codice: "", label: "",
            tipo_conto: "altro", conto_default_id: "",
            icona: "", ordine: 0, attivo: true,
        }}
        fields={(f, set) => (
            <>
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <Label>Codice * (univoco, lowercase)</Label>
                        <Input
                            placeholder="es. bonifico, contanti"
                            value={f.codice}
                            onChange={(e) => set("codice", e.target.value)}
                            data-testid="mezzo-codice"
                        />
                    </div>
                    <div>
                        <Label>Etichetta visualizzata *</Label>
                        <Input
                            placeholder="es. Bonifico bancario"
                            value={f.label}
                            onChange={(e) => set("label", e.target.value)}
                            data-testid="mezzo-label"
                        />
                    </div>
                    <div>
                        <Label>Tipo conto associato</Label>
                        <select
                            className="w-full border rounded h-9 px-2 text-sm"
                            value={f.tipo_conto}
                            onChange={(e) => set("tipo_conto", e.target.value)}
                            data-testid="mezzo-tipo"
                        >
                            <option value="cassa">Cassa</option>
                            <option value="banca">Banca</option>
                            <option value="carta">Carta / POS</option>
                            <option value="rid">RID / SDD</option>
                            <option value="online">Online</option>
                            <option value="altro">Altro</option>
                        </select>
                    </div>
                    <div>
                        <Label>Conto default (opzionale)</Label>
                        <select
                            className="w-full border rounded h-9 px-2 text-sm"
                            value={f.conto_default_id || ""}
                            onChange={(e) => set("conto_default_id", e.target.value)}
                            data-testid="mezzo-conto-default"
                        >
                            <option value="">— auto (primo del tipo) —</option>
                            {conti.map((c) => (
                                <option key={c.id} value={c.id}>{c.nome} ({c.tipo})</option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <Label>Ordine</Label>
                        <Input
                            type="number"
                            value={f.ordine}
                            onChange={(e) => set("ordine", e.target.value)}
                        />
                    </div>
                    <div className="flex items-end">
                        <label className="flex items-center gap-2 text-sm">
                            <input
                                type="checkbox"
                                checked={!!f.attivo}
                                onChange={(e) => set("attivo", e.target.checked)}
                            />
                            Attivo
                        </label>
                    </div>
                </div>
            </>
        )}
    />;
}


function ProdottoForm({ section, editing, onClose }) {
    const [compagnie, setCompagnie] = useState([]);
    const [rami, setRami] = useState([]);
    useEffect(() => {
        api.get("/compagnie").then((r) => setCompagnie(r.data));
        api.get("/librerie/rami").then((r) => setRami(r.data));
    }, []);
    // Default mora: 30gg per Vita, 15gg per gli altri
    const defaultMoraFor = (ramo) => {
        if (!ramo) return 15;
        const r = String(ramo).toUpperCase();
        return ["VITA", "VITA_RC", "PREVIDENZA"].includes(r) ? 30 : 15;
    };
    return <GenericForm section={section} editing={editing} onClose={onClose}
        defaults={{ nome: "", ramo: "", compagnia_id: "", descrizione: "", termini_mora_giorni: 15, is_libro_matricola: false, attivo: true }}
        fields={(f, set) => {
            const ramoUpper = String(f.ramo || "").toUpperCase();
            const isRcAuto = ramoUpper.includes("RCA") || ramoUpper.includes("AUTO");
            return (
            <>
                <div><Label>Nome prodotto *</Label><Input value={f.nome || ""} onChange={(e) => set("nome", e.target.value)} /></div>
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <Label>Ramo</Label>
                        <Select value={f.ramo || ""} onValueChange={(v) => {
                            set("ramo", v);
                            if (!editing) set("termini_mora_giorni", defaultMoraFor(v));
                        }}>
                            <SelectTrigger><SelectValue placeholder="-" /></SelectTrigger>
                            <SelectContent>
                                {rami.map((r) => <SelectItem key={r.id} value={r.codice}>{r.nome}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <Label>Compagnia</Label>
                        <Select value={f.compagnia_id || ""} onValueChange={(v) => set("compagnia_id", v)}>
                            <SelectTrigger><SelectValue placeholder="-" /></SelectTrigger>
                            <SelectContent>
                                {compagnie.map((c) => <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <Label>Termini di mora (gg) *</Label>
                        <Input
                            type="number" min="0" max="365"
                            value={f.termini_mora_giorni ?? 15}
                            onChange={(e) => set("termini_mora_giorni", parseInt(e.target.value || 0, 10))}
                            data-testid="prodotto-termini-mora"
                        />
                        <div className="text-[10px] text-slate-500 mt-1">
                            Default: 15 gg · Vita = 30 gg.
                        </div>
                    </div>
                    {isRcAuto && (
                        <div className="bg-amber-50 border border-amber-200 rounded p-2">
                            <label className="flex items-center gap-2 cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={!!f.is_libro_matricola}
                                    onChange={(e) => set("is_libro_matricola", e.target.checked)}
                                    data-testid="prodotto-libro-matricola"
                                />
                                <span className="text-sm font-medium text-amber-900">È Libro Matricola?</span>
                            </label>
                            <div className="text-[10px] text-amber-700 mt-1">
                                Solo per polizze RCA flotta: le polizze con questo prodotto avranno una tab &quot;Libro Matricola&quot; con applicazioni per veicolo.
                            </div>
                        </div>
                    )}
                    <div className="bg-sky-50 border border-sky-200 rounded p-2">
                        <label className="flex items-center gap-2 cursor-pointer">
                            <input
                                type="checkbox"
                                checked={!!f.mostra_sezione_veicolo}
                                onChange={(e) => set("mostra_sezione_veicolo", e.target.checked)}
                                data-testid="prodotto-mostra-veicolo"
                            />
                            <span className="text-sm font-medium text-sky-900">Mostra sezione &quot;Dati veicolo&quot;?</span>
                        </label>
                        <div className="text-[10px] text-sky-700 mt-1">
                            Spunta per prodotti che gestiscono un veicolo (es. RCA, Kasko, ARD, infortuni conducente). Per ramo <b>RCAuto</b> la sezione viene mostrata sempre, anche se non spuntato.
                        </div>
                    </div>
                </div>
                <div><Label>Descrizione</Label><Input value={f.descrizione || ""} onChange={(e) => set("descrizione", e.target.value)} /></div>
            </>
            );
        }}
    />;
}

function RamoForm({ section, editing, onClose }) {
    return <GenericForm section={section} editing={editing} onClose={onClose}
        defaults={{ codice: "", nome: "", descrizione: "", attivo: true }}
        fields={(f, set) => (
            <>
                <div className="grid grid-cols-2 gap-3">
                    <div><Label>Codice *</Label><Input value={f.codice || ""} onChange={(e) => set("codice", e.target.value.toUpperCase())} /></div>
                    <div><Label>Nome *</Label><Input value={f.nome || ""} onChange={(e) => set("nome", e.target.value)} /></div>
                </div>
                <div><Label>Descrizione</Label><Input value={f.descrizione || ""} onChange={(e) => set("descrizione", e.target.value)} /></div>
            </>
        )}
    />;
}

function CompagniaForm({ section, editing, onClose }) {
    return <GenericForm section={section} editing={editing} onClose={onClose}
        defaults={{
            codice: "", ragione_sociale: "", referente: "", email: "", telefono: "",
            sito_web: "", mandato: "", trattiene_provvigioni: true, attiva: true,
        }}
        fields={(f, set) => (
            <>
                <div className="grid grid-cols-2 gap-3">
                    <div><Label>Codice *</Label><Input value={f.codice || ""} onChange={(e) => set("codice", e.target.value.toUpperCase())} /></div>
                    <div><Label>Ragione sociale *</Label><Input value={f.ragione_sociale || ""} onChange={(e) => set("ragione_sociale", e.target.value)} /></div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                    <div><Label>Referente</Label><Input value={f.referente || ""} onChange={(e) => set("referente", e.target.value)} /></div>
                    <div><Label>Mandato</Label><Input value={f.mandato || ""} onChange={(e) => set("mandato", e.target.value)} /></div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                    <div><Label>Email</Label><Input value={f.email || ""} onChange={(e) => set("email", e.target.value)} /></div>
                    <div><Label>Telefono</Label><Input value={f.telefono || ""} onChange={(e) => set("telefono", e.target.value)} /></div>
                </div>
                <div><Label>Sito web</Label><Input value={f.sito_web || ""} onChange={(e) => set("sito_web", e.target.value)} /></div>
                <div className="bg-amber-50 border border-amber-200 rounded-md p-3">
                    <div className="flex items-center gap-2">
                        <input
                            type="checkbox"
                            id="trattiene_provv"
                            checked={f.trattiene_provvigioni !== false}
                            onChange={(e) => set("trattiene_provvigioni", e.target.checked)}
                        />
                        <Label htmlFor="trattiene_provv" className="cursor-pointer font-medium">
                            Trattengo le provvigioni all&apos;incasso
                        </Label>
                    </div>
                    <div className="text-xs text-amber-800 mt-1.5">
                        {f.trattiene_provvigioni !== false
                            ? "Verso alla compagnia il PREMIO meno le provvigioni. Saldo cassa compagnia = -(premio - provvigioni)."
                            : "Verso il premio INTERO alla compagnia. Le provvigioni mi vengono accreditate a parte. Saldo cassa = -premio + provvigioni a credito."}
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <input type="checkbox" id="comp_attiva" checked={f.attiva !== false} onChange={(e) => set("attiva", e.target.checked)} />
                    <Label htmlFor="comp_attiva" className="cursor-pointer">Attiva</Label>
                </div>
            </>
        )}
    />;
}

function UtenteForm({ section, editing, onClose }) {
    const [anagrafiche, setAnagrafiche] = useState([]);
    useEffect(() => { api.get("/anagrafiche").then((r) => setAnagrafiche(r.data)); }, []);
    return <GenericForm section={section} editing={editing} onClose={onClose} dialogClass="max-w-3xl"
        defaults={{
            name: "", email: "", password: "", role: "dipendente", anagrafica_id: null,
            codice_fiscale: "", partita_iva: "", iban: "", indirizzo: "", telefono: "",
            perc_provvigione_default: 0, perc_ritenuta_acconto: 0, perc_inps_inarcassa: 0,
            note_fiscali: "", note_interne: "", attivo: true,
        }}
        fields={(f, set) => (
            <Tabs defaultValue="anagrafica" className="w-full">
                <TabsList className="bg-slate-100">
                    <TabsTrigger value="anagrafica">Anagrafica</TabsTrigger>
                    <TabsTrigger value="fiscale">Dati fiscali / IBAN</TabsTrigger>
                    {editing && f.role !== "cliente" && <TabsTrigger value="documenti">Documenti</TabsTrigger>}
                    {editing && f.role !== "cliente" && <TabsTrigger value="corsi">Corsi</TabsTrigger>}
                </TabsList>

                <TabsContent value="anagrafica" className="space-y-3 mt-4">
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Nome *</Label><Input value={f.name || ""} onChange={(e) => set("name", e.target.value)} /></div>
                        <div><Label>Email *</Label><Input type="email" value={f.email || ""} onChange={(e) => set("email", e.target.value.toLowerCase())} /></div>
                    </div>
                    <div>
                        <Label>{editing ? "Nuova password (lasciare vuoto per non cambiare)" : "Password *"}</Label>
                        <Input
                            type="password"
                            value={f.password || ""}
                            onChange={(e) => set("password", e.target.value)}
                            placeholder={editing ? "•••••••• (invariata)" : ""}
                        />
                    </div>
                    <div>
                        <Label>Ruolo *</Label>
                        <Select value={f.role || "dipendente"} onValueChange={(v) => set("role", v)}>
                            <SelectTrigger data-testid="utente-role"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="admin">Amministratore - vede e modifica tutto</SelectItem>
                                <SelectItem value="collaboratore">Collaboratore - vede tutto, no cancellazioni</SelectItem>
                                <SelectItem value="dipendente">Dipendente - vede tutto, no compagnie/import</SelectItem>
                                <SelectItem value="cliente">Cliente - vede solo i propri dati</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    {f.role === "cliente" && (
                        <div>
                            <Label>Anagrafica cliente collegata *</Label>
                            <Select value={f.anagrafica_id || ""} onValueChange={(v) => set("anagrafica_id", v)}>
                                <SelectTrigger><SelectValue placeholder="Seleziona anagrafica..." /></SelectTrigger>
                                <SelectContent>
                                    {anagrafiche.map((a) => <SelectItem key={a.id} value={a.id}>{a.ragione_sociale}</SelectItem>)}
                                </SelectContent>
                            </Select>
                            <div className="text-xs text-slate-500 mt-1">Il cliente vedrà solo le polizze/sinistri legati a questa anagrafica.</div>
                        </div>
                    )}
                    {f.role !== "cliente" && (
                        <div className="grid grid-cols-2 gap-3">
                            <div><Label>Telefono</Label><Input value={f.telefono || ""} onChange={(e) => set("telefono", e.target.value)} /></div>
                            <div><Label>Indirizzo</Label><Input value={f.indirizzo || ""} onChange={(e) => set("indirizzo", e.target.value.toUpperCase())} /></div>
                        </div>
                    )}
                </TabsContent>

                <TabsContent value="fiscale" className="space-y-3 mt-4">
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Codice fiscale</Label><Input value={f.codice_fiscale || ""} onChange={(e) => set("codice_fiscale", e.target.value.toUpperCase())} /></div>
                        <div><Label>Partita IVA</Label><Input value={f.partita_iva || ""} onChange={(e) => set("partita_iva", e.target.value)} /></div>
                    </div>
                    <div><Label>IBAN</Label><Input value={f.iban || ""} onChange={(e) => set("iban", e.target.value.toUpperCase())} /></div>
                    <div className="grid grid-cols-3 gap-3 bg-amber-50 border border-amber-200 rounded-md p-3">
                        <div>
                            <Label>% Provvigione default</Label>
                            <Input type="number" step="0.01" value={f.perc_provvigione_default || 0} onChange={(e) => set("perc_provvigione_default", parseFloat(e.target.value) || 0)} />
                        </div>
                        <div>
                            <Label>% Ritenuta d&apos;acconto</Label>
                            <Input type="number" step="0.01" value={f.perc_ritenuta_acconto || 0} onChange={(e) => set("perc_ritenuta_acconto", parseFloat(e.target.value) || 0)} />
                        </div>
                        <div>
                            <Label>% INPS / Inarcassa</Label>
                            <Input type="number" step="0.01" value={f.perc_inps_inarcassa || 0} onChange={(e) => set("perc_inps_inarcassa", parseFloat(e.target.value) || 0)} />
                        </div>
                        <div className="col-span-3 text-xs text-amber-800">
                            Valori di default usati nei pagamenti provvigioni. Le regole specifiche per compagnia/ramo si gestiscono in <strong>Sistema provvigionale</strong>.
                        </div>
                    </div>
                    <div><Label>Note fiscali</Label><Input value={f.note_fiscali || ""} onChange={(e) => set("note_fiscali", e.target.value)} /></div>
                    <div><Label>Note interne (visibili solo admin)</Label><Input value={f.note_interne || ""} onChange={(e) => set("note_interne", e.target.value)} /></div>
                </TabsContent>

                {editing && f.role !== "cliente" && (
                    <TabsContent value="documenti" className="space-y-3 mt-4">
                        <DocumentiCollaboratore userId={editing.id} user={f} onChange={(updates) => Object.entries(updates).forEach(([k, v]) => set(k, v))} />
                    </TabsContent>
                )}

                {editing && f.role !== "cliente" && (
                    <TabsContent value="corsi" className="space-y-3 mt-4">
                        <CorsiCollaboratore userId={editing.id} corsi={f.corsi || []} onChange={(nuovi) => set("corsi", nuovi)} />
                    </TabsContent>
                )}

                <div className="bg-slate-50 border border-slate-200 rounded-md p-3 text-xs space-y-1 mt-4">
                    <div className="font-semibold text-slate-700 mb-1">Livelli di visibilità:</div>
                    <div><span className="badge badge-danger">admin</span> Accesso completo, gestione utenti, eliminazioni</div>
                    <div><span className="badge badge-info">collaboratore</span> Vede e gestisce tutto, no eliminazioni critiche</div>
                    <div><span className="badge badge-success">dipendente</span> Operatività su clienti/polizze/sinistri, no librerie</div>
                    <div><span className="badge badge-neutral">cliente</span> Vede solo le proprie polizze e i propri sinistri</div>
                </div>
            </Tabs>
        )}
    />;
}


// =================== AZIENDA (Singleton) ===================
function AziendaSezione() {
    const [f, setF] = useState(null);
    const [logoFile, setLogoFile] = useState(null);
    const [saving, setSaving] = useState(false);
    const load = () => api.get("/librerie/azienda").then((r) => setF(r.data));
    useEffect(() => { load(); }, []);

    if (!f) return <Loading />;
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const salva = async () => {
        setSaving(true);
        try {
            await api.put("/librerie/azienda", f);
            if (logoFile) {
                const fd = new FormData();
                fd.append("file", logoFile);
                const r = await api.post("/librerie/azienda/logo", fd, { headers: { "Content-Type": "multipart/form-data" } });
                set("logo_url", r.data.logo_url);
                setLogoFile(null);
            }
            toast.success("Dati azienda salvati");
            load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        finally { setSaving(false); }
    };

    return (
        <Card className="border-slate-200 p-6">
            <div className="flex items-center justify-between mb-5">
                <div>
                    <div className="text-base font-semibold text-slate-800">Dati Azienda</div>
                    <div className="text-xs text-slate-500">Utilizzati come intestazione su tutte le stampe (PDF, brogliaccio, estratti)</div>
                </div>
                <Button onClick={salva} disabled={saving} className="bg-sky-700 hover:bg-sky-800" data-testid="azienda-save">
                    {saving ? "Salvataggio..." : "Salva"}
                </Button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="md:col-span-1">
                    <Label>Logo agenzia</Label>
                    <div className="mt-2 border border-dashed border-slate-300 rounded-md p-4 text-center bg-slate-50">
                        {(f.logo_url || logoFile) ? (
                            <div>
                                {logoFile ? (
                                    <img alt="logo preview" src={URL.createObjectURL(logoFile)} className="max-h-32 mx-auto mb-2 rounded" />
                                ) : (
                                    <img alt="logo" src={f.logo_url} className="max-h-32 mx-auto mb-2 rounded" />
                                )}
                                <div className="text-xs text-slate-500">{logoFile ? "(non ancora salvato)" : "Logo attuale"}</div>
                            </div>
                        ) : (
                            <div className="text-xs text-slate-500 py-6">Nessun logo caricato</div>
                        )}
                        <input
                            type="file"
                            accept="image/*"
                            id="logo-upload"
                            data-testid="azienda-logo-input"
                            onChange={(e) => setLogoFile(e.target.files?.[0] || null)}
                            className="hidden"
                        />
                        <label htmlFor="logo-upload" className="cursor-pointer mt-3 inline-flex items-center gap-1 text-xs text-sky-700 hover:underline">
                            <Upload size={12} /> Scegli logo (PNG/JPG, max 5MB)
                        </label>
                    </div>
                </div>

                <div className="md:col-span-2 space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Ragione sociale *</Label><Input value={f.ragione_sociale || ""} onChange={(e) => set("ragione_sociale", e.target.value.toUpperCase())} data-testid="azienda-ragione" /></div>
                        <div><Label>Forma giuridica</Label><Input value={f.forma_giuridica || ""} onChange={(e) => set("forma_giuridica", e.target.value.toUpperCase())} placeholder="SRL / SAS / SNC / ditta individuale" /></div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Partita IVA</Label><Input value={f.partita_iva || ""} onChange={(e) => set("partita_iva", e.target.value)} /></div>
                        <div><Label>Codice fiscale</Label><Input value={f.codice_fiscale || ""} onChange={(e) => set("codice_fiscale", e.target.value.toUpperCase())} /></div>
                    </div>
                    <div className="grid grid-cols-3 gap-3">
                        <div><Label>N° iscr. RUI</Label><Input value={f.rui || ""} onChange={(e) => set("rui", e.target.value.toUpperCase())} /></div>
                        <div><Label>Sezione RUI</Label><Input value={f.rui_sezione || ""} onChange={(e) => set("rui_sezione", e.target.value.toUpperCase())} placeholder="A/B/E..." /></div>
                        <div><Label>Data iscr. RUI</Label><Input type="date" value={f.data_iscrizione_rui || ""} onChange={(e) => set("data_iscrizione_rui", e.target.value)} /></div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>REA</Label><Input value={f.rea || ""} onChange={(e) => set("rea", e.target.value.toUpperCase())} /></div>
                        <div><Label>Capitale sociale</Label><Input value={f.capitale_sociale || ""} onChange={(e) => set("capitale_sociale", e.target.value)} /></div>
                    </div>

                    <div className="text-xs uppercase tracking-widest font-semibold text-slate-500 pt-2 border-t border-slate-100">Sede legale</div>
                    <div><Label>Indirizzo</Label><Input value={f.indirizzo || ""} onChange={(e) => set("indirizzo", e.target.value.toUpperCase())} /></div>
                    <div className="grid grid-cols-3 gap-3">
                        <div className="col-span-2"><Label>Comune</Label><Input value={f.comune || ""} onChange={(e) => set("comune", e.target.value.toUpperCase())} /></div>
                        <div><Label>Provincia</Label><Input value={f.provincia || ""} onChange={(e) => set("provincia", e.target.value.toUpperCase())} maxLength={2} /></div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>CAP</Label><Input value={f.cap || ""} onChange={(e) => set("cap", e.target.value)} /></div>
                        <div><Label>Nazione</Label><Input value={f.nazione || ""} onChange={(e) => set("nazione", e.target.value.toUpperCase())} /></div>
                    </div>

                    <div className="text-xs uppercase tracking-widest font-semibold text-slate-500 pt-2 border-t border-slate-100">Contatti</div>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Telefono</Label><Input value={f.telefono || ""} onChange={(e) => set("telefono", e.target.value)} /></div>
                        <div><Label>Fax</Label><Input value={f.fax || ""} onChange={(e) => set("fax", e.target.value)} /></div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Email</Label><Input value={f.email || ""} onChange={(e) => set("email", e.target.value.toLowerCase())} /></div>
                        <div><Label>PEC</Label><Input value={f.pec || ""} onChange={(e) => set("pec", e.target.value.toLowerCase())} /></div>
                    </div>
                    <div><Label>Sito web</Label><Input value={f.sito_web || ""} onChange={(e) => set("sito_web", e.target.value)} /></div>

                    <div className="text-xs uppercase tracking-widest font-semibold text-slate-500 pt-2 border-t border-slate-100">Coordinate bancarie</div>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Banca</Label><Input value={f.banca || ""} onChange={(e) => set("banca", e.target.value.toUpperCase())} /></div>
                        <div><Label>IBAN</Label><Input value={f.iban || ""} onChange={(e) => set("iban", e.target.value.toUpperCase())} /></div>
                    </div>

                    <div><Label>Note in calce alle stampe</Label>
                        <textarea
                            className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm"
                            rows={2}
                            value={f.note_footer_stampe || ""}
                            onChange={(e) => set("note_footer_stampe", e.target.value)}
                            placeholder="Es: Polizza assicurazione professionale, autorizzazione IVASS..."
                        />
                    </div>

                    {/* Sezione Commercialista */}
                    <div className="mt-6 pt-4 border-t border-slate-200">
                        <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wider mb-3">
                            Commercialista (invio Prima Nota chiusa)
                        </h3>
                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <Label>Nome commercialista</Label>
                                <Input
                                    value={f.nome_commercialista || ""}
                                    onChange={(e) => set("nome_commercialista", e.target.value)}
                                    placeholder="Es. Dott. Mario Rossi"
                                    data-testid="azienda-nome-commercialista"
                                />
                            </div>
                            <div>
                                <Label>Email commercialista</Label>
                                <Input
                                    type="email"
                                    value={f.email_commercialista || ""}
                                    onChange={(e) => set("email_commercialista", e.target.value)}
                                    placeholder="commercialista@studio.it"
                                    data-testid="azienda-email-commercialista"
                                />
                            </div>
                            <div className="col-span-2 flex items-center gap-2">
                                <input
                                    type="checkbox"
                                    id="auto-chiusura"
                                    checked={!!f.invio_automatico_chiusura}
                                    onChange={(e) => set("invio_automatico_chiusura", e.target.checked)}
                                    data-testid="azienda-auto-chiusura"
                                />
                                <Label htmlFor="auto-chiusura" className="cursor-pointer text-xs">
                                    Suggerisci l&apos;invio automatico al commercialista alla chiusura di ogni giornata
                                </Label>
                            </div>
                        </div>
                    </div>

                    {/* Sezione SMTP */}
                    <div className="mt-4 pt-4 border-t border-slate-200">
                        <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wider mb-3">
                            SMTP - Invio email (Prima Nota, ecc.)
                        </h3>
                        <div className="text-xs text-slate-500 mb-3">
                            Configurazione del server SMTP per inviare email dall&apos;applicazione (es. brogliaccio al commercialista). Per Gmail: <code>smtp.gmail.com:587</code> con password applicazione.
                        </div>
                        <div className="grid grid-cols-3 gap-3">
                            <div className="col-span-2">
                                <Label>SMTP Host</Label>
                                <Input
                                    value={f.smtp_host || ""}
                                    onChange={(e) => set("smtp_host", e.target.value)}
                                    placeholder="smtp.gmail.com"
                                    data-testid="azienda-smtp-host"
                                />
                            </div>
                            <div>
                                <Label>Porta</Label>
                                <Input
                                    type="number"
                                    value={f.smtp_port || 587}
                                    onChange={(e) => set("smtp_port", parseInt(e.target.value || 0))}
                                    placeholder="587"
                                    data-testid="azienda-smtp-port"
                                />
                            </div>
                            <div>
                                <Label>SMTP User (email)</Label>
                                <Input
                                    value={f.smtp_user || ""}
                                    onChange={(e) => set("smtp_user", e.target.value)}
                                    placeholder="account@gmail.com"
                                    data-testid="azienda-smtp-user"
                                />
                            </div>
                            <div>
                                <Label>SMTP Password</Label>
                                <Input
                                    type="password"
                                    value={f.smtp_password || ""}
                                    onChange={(e) => set("smtp_password", e.target.value)}
                                    placeholder="password app"
                                    data-testid="azienda-smtp-password"
                                />
                            </div>
                            <div>
                                <Label>From (mittente)</Label>
                                <Input
                                    value={f.smtp_from || ""}
                                    onChange={(e) => set("smtp_from", e.target.value)}
                                    placeholder="Assicura <noreply@assicura.it>"
                                />
                            </div>
                            <div className="col-span-3 flex items-center gap-2">
                                <input
                                    type="checkbox"
                                    id="smtp-tls"
                                    checked={f.smtp_use_tls !== false}
                                    onChange={(e) => set("smtp_use_tls", e.target.checked)}
                                />
                                <Label htmlFor="smtp-tls" className="cursor-pointer text-xs">
                                    Usa STARTTLS (consigliato per porta 587). Disabilita per SSL diretto su porta 465.
                                </Label>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </Card>
    );
}

// =================== SCHEMA PROVVIGIONALE ===================
function SchemaProvvForm({ section, editing, onClose }) {
    const [collab, setCollab] = useState([]);
    const [compagnie, setCompagnie] = useState([]);
    const [rami, setRami] = useState([]);
    useEffect(() => {
        api.get("/collaboratori").then((r) => setCollab(r.data));
        api.get("/compagnie").then((r) => setCompagnie(r.data));
        api.get("/librerie/rami").then((r) => setRami(r.data));
    }, []);
    return <GenericForm section={section} editing={editing} onClose={onClose}
        defaults={{ nome: "", collaboratore_id: null, compagnia_id: null, ramo: null,
                    percentuale_collaboratore: 0, percentuale_su_premio: 0,
                    descrizione: "", attivo: true }}
        fields={(f, set) => (
            <>
                <div><Label>Nome regola *</Label><Input value={f.nome || ""} onChange={(e) => set("nome", e.target.value)} placeholder="Es: Mario Rossi - RCA UnipolSai" /></div>
                <div className="grid grid-cols-3 gap-3">
                    <div>
                        <Label>Collaboratore</Label>
                        <Select value={f.collaboratore_id || "__null__"} onValueChange={(v) => set("collaboratore_id", v === "__null__" ? null : v)}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="__null__">— tutti —</SelectItem>
                                {collab.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <Label>Compagnia</Label>
                        <Select value={f.compagnia_id || "__null__"} onValueChange={(v) => set("compagnia_id", v === "__null__" ? null : v)}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="__null__">— tutte —</SelectItem>
                                {compagnie.map((c) => <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <Label>Ramo</Label>
                        <Select value={f.ramo || "__null__"} onValueChange={(v) => set("ramo", v === "__null__" ? null : v)}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="__null__">— tutti —</SelectItem>
                                {rami.map((r) => <SelectItem key={r.id} value={r.codice}>{r.nome}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                </div>
                <div className="grid grid-cols-2 gap-3 bg-emerald-50 border border-emerald-200 rounded-md p-3">
                    <div>
                        <Label>% Provvigione al collaboratore *</Label>
                        <Input type="number" step="0.01" value={f.percentuale_collaboratore || 0}
                               onChange={(e) => set("percentuale_collaboratore", parseFloat(e.target.value) || 0)} />
                        <div className="text-[10px] text-emerald-800 mt-1">Sul totale provvigione incassata dalla polizza</div>
                    </div>
                    <div>
                        <Label>% Provvigione su premio lordo</Label>
                        <Input type="number" step="0.01" value={f.percentuale_su_premio || 0}
                               onChange={(e) => set("percentuale_su_premio", parseFloat(e.target.value) || 0)} />
                        <div className="text-[10px] text-emerald-800 mt-1">Solo se non importata da ANIA</div>
                    </div>
                </div>
                <div><Label>Descrizione / note</Label><Input value={f.descrizione || ""} onChange={(e) => set("descrizione", e.target.value)} /></div>
                <div className="flex items-center gap-2">
                    <input type="checkbox" id="sp_attivo" checked={f.attivo !== false} onChange={(e) => set("attivo", e.target.checked)} />
                    <Label htmlFor="sp_attivo" className="cursor-pointer">Regola attiva</Label>
                </div>
                <div className="bg-slate-50 border border-slate-200 rounded-md p-3 text-xs text-slate-600">
                    <strong>Risoluzione:</strong> la regola più specifica (collaboratore + compagnia + ramo) prevale sulle regole generiche.
                    Lascia &quot;— tutti —&quot; per creare regole di default valide per più collaboratori / compagnie.
                </div>
            </>
        )}
    />;
}

// =================== DOCUMENTI COLLABORATORE ===================
const DOC_TIPI = [
    { key: "firma_digitale", label: "Firma digitale", urlField: "firma_digitale_url" },
    { key: "carta_identita", label: "Carta d'identità", urlField: "carta_identita_url" },
    { key: "casellario", label: "Casellario giudiziale", urlField: "casellario_url" },
    { key: "carichi_pendenti", label: "Carichi pendenti", urlField: "carichi_pendenti_url" },
    { key: "documento_iban", label: "Documento IBAN", urlField: "documento_iban_url" },
];

function DocumentiCollaboratore({ userId, user, onChange }) {
    const upload = async (tipo, file) => {
        if (!file) return;
        const fd = new FormData();
        fd.append("file", file);
        try {
            const r = await api.post(`/auth/users/${userId}/documenti/${tipo}`, fd,
                { headers: { "Content-Type": "multipart/form-data" } });
            onChange(r.data);
            toast.success("Documento caricato");
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };
    const del = async (tipo) => {
        if (!window.confirm("Eliminare il documento?")) return;
        const f = DOC_TIPI.find((d) => d.key === tipo);
        try {
            await api.delete(`/auth/users/${userId}/documenti/${tipo}`);
            onChange({ [f.urlField]: null });
            toast.success("Eliminato");
        } catch (e) { toast.error("Errore"); }
    };
    return (
        <div className="space-y-2">
            {DOC_TIPI.map((d) => {
                const url = user[d.urlField];
                return (
                    <div key={d.key} className="flex items-center justify-between border border-slate-200 rounded-md p-3 bg-slate-50">
                        <div className="flex items-center gap-2">
                            <FileText size={14} className="text-slate-500" />
                            <div>
                                <div className="text-sm font-medium">{d.label}</div>
                                <div className="text-xs text-slate-500">
                                    {url ? <a href={url} target="_blank" rel="noreferrer" className="text-sky-700 hover:underline">Visualizza documento</a> : "Nessun file caricato"}
                                </div>
                            </div>
                        </div>
                        <div className="flex items-center gap-2">
                            <input
                                type="file"
                                id={`doc-${d.key}`}
                                className="hidden"
                                data-testid={`doc-input-${d.key}`}
                                onChange={(e) => upload(d.key, e.target.files?.[0])}
                            />
                            <label htmlFor={`doc-${d.key}`} className="cursor-pointer text-xs px-3 py-1.5 bg-sky-700 hover:bg-sky-800 text-white rounded-md inline-flex items-center gap-1">
                                <Upload size={11} /> {url ? "Sostituisci" : "Carica"}
                            </label>
                            {url && (
                                <button onClick={() => del(d.key)} className="text-red-600 hover:bg-red-50 p-1.5 rounded">
                                    <Trash2 size={13} />
                                </button>
                            )}
                        </div>
                    </div>
                );
            })}
        </div>
    );
}

// =================== CORSI COLLABORATORE ===================
function CorsiCollaboratore({ userId, corsi, onChange }) {
    const [titolo, setTitolo] = useState("");
    const [ente, setEnte] = useState("");
    const [scadenza, setScadenza] = useState("");
    const [file, setFile] = useState(null);

    const aggiungi = async () => {
        if (!titolo && !file) { toast.error("Inserisci almeno titolo o attestato"); return; }
        try {
            let r;
            if (file) {
                const fd = new FormData();
                fd.append("file", file);
                fd.append("titolo", titolo);
                fd.append("ente", ente);
                fd.append("data_scadenza", scadenza);
                r = await api.post(`/auth/users/${userId}/corsi/upload`, fd,
                    { headers: { "Content-Type": "multipart/form-data" } });
            } else {
                r = await api.post(`/auth/users/${userId}/corsi`,
                    { titolo, ente, data_scadenza: scadenza || null });
            }
            onChange([...(corsi || []), r.data]);
            setTitolo(""); setEnte(""); setScadenza(""); setFile(null);
            toast.success("Corso aggiunto");
        } catch (e) { toast.error("Errore"); }
    };
    const rimuovi = async (corsoId) => {
        try {
            await api.delete(`/auth/users/${userId}/corsi/${corsoId}`);
            onChange((corsi || []).filter((c) => c.id !== corsoId));
        } catch (e) { toast.error("Errore"); }
    };

    return (
        <div className="space-y-3">
            <div className="border border-slate-200 rounded-md p-3 bg-slate-50">
                <div className="text-xs font-semibold text-slate-600 mb-2 flex items-center gap-1">
                    <GraduationCap size={13} /> Aggiungi corso / attestato
                </div>
                <div className="grid grid-cols-2 gap-2">
                    <div><Label className="text-xs">Titolo</Label><Input value={titolo} onChange={(e) => setTitolo(e.target.value)} placeholder="Es: IVASS 60h 2024" /></div>
                    <div><Label className="text-xs">Ente</Label><Input value={ente} onChange={(e) => setEnte(e.target.value)} placeholder="Es: IVASS" /></div>
                    <div><Label className="text-xs">Scadenza</Label><Input type="date" value={scadenza} onChange={(e) => setScadenza(e.target.value)} /></div>
                    <div>
                        <Label className="text-xs">Attestato (PDF/IMG, opz.)</Label>
                        <Input type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} accept=".pdf,image/*" />
                    </div>
                </div>
                <Button size="sm" className="mt-2 bg-sky-700 hover:bg-sky-800" onClick={aggiungi}>
                    <Plus size={12} className="mr-1" /> Aggiungi
                </Button>
            </div>

            {(!corsi || corsi.length === 0) ? (
                <div className="text-center text-xs text-slate-400 py-4">Nessun corso registrato</div>
            ) : (
                <table className="tbl w-full">
                    <thead><tr><th>Titolo</th><th>Ente</th><th>Scadenza</th><th>Attestato</th><th></th></tr></thead>
                    <tbody>
                        {corsi.map((c) => (
                            <tr key={c.id}>
                                <td className="font-medium">{c.titolo}</td>
                                <td>{c.ente || "—"}</td>
                                <td className="num">{c.data_scadenza || "—"}</td>
                                <td>{c.url_attestato ? <a className="text-sky-700 hover:underline text-xs" href={c.url_attestato} target="_blank" rel="noreferrer">Apri</a> : "—"}</td>
                                <td className="text-right">
                                    <button onClick={() => rimuovi(c.id)} className="text-red-600 hover:bg-red-50 p-1 rounded"><Trash2 size={12} /></button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </div>
    );
}


function VociRicorsiveSezione() {
    const [items, setItems] = useState(null);
    const [collabs, setCollabs] = useState([]);
    const [open, setOpen] = useState(false);
    const [editing, setEditing] = useState(null);

    const load = () => {
        api.get("/voci-ricorsive-collab").then((r) => setItems(r.data || []));
    };
    useEffect(() => {
        load();
        api.get("/auth/users").then((r) => {
            setCollabs((r.data || []).filter(
                (u) => ["collaboratore", "dipendente"].includes(u.role) && u.attivo !== false,
            ));
        });
    }, []);

    const elimina = async (r) => {
        if (!window.confirm(
            `Eliminare la regola "${r.causale}"?\nVerranno cancellate anche le voci non ancora pagate generate da questa regola.`,
        )) return;
        try {
            await api.delete(`/voci-ricorsive-collab/${r.id}`, { params: { elimina_voci_non_pagate: true } });
            toast.success("Regola eliminata");
            load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };
    const apriEdit = (r) => { setEditing(r); setOpen(true); };
    const apriNuovo = () => { setEditing(null); setOpen(true); };

    return (
        <Card className="p-4 border-slate-200" data-testid="lib-voci-ricorsive">
            <div className="flex items-start justify-between mb-3">
                <div>
                    <h2 className="font-semibold text-slate-900">
                        <RotateCw size={14} className="inline mr-1.5 text-fuchsia-600" />
                        Voci ricorsive collaboratori
                    </h2>
                    <p className="text-xs text-slate-500 mt-1 max-w-2xl">
                        Bonus o trattenute periodiche (mensili/annuali) che vengono generate
                        automaticamente nell'estratto conto del collaboratore alle date previste.
                        L'importo è positivo (bonus) o negativo (trattenuta).
                    </p>
                </div>
                <Button onClick={apriNuovo} className="bg-fuchsia-700 hover:bg-fuchsia-800" data-testid="vr-new">
                    <Plus size={14} className="mr-1" /> Nuova regola
                </Button>
            </div>
            {items === null ? <Loading /> : items.length === 0 ? (
                <Empty message="Nessuna regola ricorsiva. Aggiungine una per automatizzare bonus/trattenute." />
            ) : (
                <table className="tbl w-full">
                    <thead>
                        <tr>
                            <th>Collaboratore</th>
                            <th>Causale</th>
                            <th>Periodicità</th>
                            <th>Quando</th>
                            <th>Da → A</th>
                            <th className="text-right">Importo €</th>
                            <th>Stato</th>
                            <th className="w-24"></th>
                        </tr>
                    </thead>
                    <tbody>
                        {items.map((r) => (
                            <tr key={r.id} data-testid={`vr-row-${r.id}`}>
                                <td className="font-medium">{r.collaboratore_nome}</td>
                                <td>{r.causale}</td>
                                <td className="text-xs">
                                    <span className={`badge ${r.periodicita === "mensile" ? "badge-info" : "badge-warning"}`}>
                                        {r.periodicita}
                                    </span>
                                </td>
                                <td className="text-xs num">
                                    {r.periodicita === "mensile"
                                        ? `giorno ${r.giorno_mese} di ogni mese`
                                        : `${r.giorno_mese}/${r.mese_anno || "?"} di ogni anno`}
                                </td>
                                <td className="text-xs num">
                                    {r.data_inizio} → {r.data_fine || "—"}
                                </td>
                                <td className={`num text-right font-semibold ${r.importo >= 0 ? "text-emerald-700" : "text-rose-700"}`}>
                                    {r.importo >= 0 ? "+" : ""}{r.importo.toFixed(2)}
                                </td>
                                <td>
                                    {r.attiva
                                        ? <span className="badge badge-success">attiva</span>
                                        : <span className="badge badge-warning">disattiva</span>}
                                </td>
                                <td className="text-right">
                                    <button
                                        onClick={() => apriEdit(r)}
                                        className="inline-flex items-center justify-center h-7 w-7 rounded border border-slate-200 hover:bg-slate-100 mr-1"
                                        title="Modifica" data-testid={`vr-edit-${r.id}`}
                                    >
                                        <Pencil size={12} />
                                    </button>
                                    <button
                                        onClick={() => elimina(r)}
                                        className="inline-flex items-center justify-center h-7 w-7 rounded border border-rose-200 hover:bg-rose-50 text-rose-600"
                                        title="Elimina" data-testid={`vr-del-${r.id}`}
                                    >
                                        <Trash2 size={12} />
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
            {open && (
                <VoceRicorsivaDialog
                    voce={editing}
                    collabs={collabs}
                    onClose={(refresh) => {
                        setOpen(false); setEditing(null);
                        if (refresh) load();
                    }}
                />
            )}
        </Card>
    );
}

function VoceRicorsivaDialog({ voce, collabs, onClose }) {
    const today = new Date().toISOString().slice(0, 10);
    const [f, setF] = useState(() => voce ? {
        collaboratore_id: voce.collaboratore_id,
        causale: voce.causale,
        importo: String(voce.importo),
        periodicita: voce.periodicita,
        giorno_mese: voce.giorno_mese || 1,
        mese_anno: voce.mese_anno || 1,
        data_inizio: voce.data_inizio,
        data_fine: voce.data_fine || "",
        note: voce.note || "",
        attiva: voce.attiva !== false,
    } : {
        collaboratore_id: "",
        causale: "",
        importo: "",
        periodicita: "mensile",
        giorno_mese: 1,
        mese_anno: 1,
        data_inizio: today,
        data_fine: "",
        note: "",
        attiva: true,
    });
    const [saving, setSaving] = useState(false);
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const save = async () => {
        if (!f.collaboratore_id) { toast.error("Seleziona il collaboratore (o 'Tutti')"); return; }
        if (!f.causale) { toast.error("Inserisci la causale"); return; }
        const imp = parseFloat(f.importo);
        if (isNaN(imp) || imp === 0) { toast.error("Importo deve essere ≠ 0"); return; }
        setSaving(true);
        try {
            const body = {
                collaboratore_id: f.collaboratore_id,
                causale: f.causale,
                importo: imp,
                periodicita: f.periodicita,
                giorno_mese: parseInt(f.giorno_mese, 10) || 1,
                mese_anno: f.periodicita === "annuale" ? (parseInt(f.mese_anno, 10) || 1) : null,
                data_inizio: f.data_inizio,
                data_fine: f.data_fine || null,
                note: f.note || null,
                attiva: !!f.attiva,
            };
            if (voce) {
                await api.put(`/voci-ricorsive-collab/${voce.id}`, body);
                toast.success("Regola aggiornata");
            } else {
                const r = await api.post("/voci-ricorsive-collab", body);
                toast.success(`Regola creata · ${r.data.voci_generate || 0} voci generate`);
            }
            onClose(true);
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        finally { setSaving(false); }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose(false)}>
            <DialogContent className="max-w-lg" data-testid="vr-dialog">
                <DialogHeader>
                    <DialogTitle>{voce ? "Modifica regola ricorsiva" : "Nuova regola ricorsiva"}</DialogTitle>
                </DialogHeader>
                <div className="space-y-3 py-2">
                    <div>
                        <Label>Collaboratore *</Label>
                        <Select value={f.collaboratore_id} onValueChange={(v) => set("collaboratore_id", v)}>
                            <SelectTrigger data-testid="vr-collab"><SelectValue placeholder="Seleziona" /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="__all__">Tutti i collaboratori (broadcast)</SelectItem>
                                {collabs.map((c) => (
                                    <SelectItem key={c.id} value={c.id}>{c.name || c.email}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div className="col-span-1">
                            <Label>Causale *</Label>
                            <Input
                                placeholder="es. Bonus presenza, Trattenuta auto..."
                                value={f.causale}
                                onChange={(e) => set("causale", e.target.value)}
                                data-testid="vr-causale"
                            />
                        </div>
                        <div className="col-span-1">
                            <Label>Importo € *</Label>
                            <Input
                                type="number" step="0.01"
                                placeholder="+100 bonus / -50 trattenuta"
                                value={f.importo}
                                onChange={(e) => set("importo", e.target.value)}
                                data-testid="vr-importo"
                            />
                        </div>
                    </div>
                    <div className="grid grid-cols-3 gap-3">
                        <div>
                            <Label>Periodicità</Label>
                            <Select value={f.periodicita} onValueChange={(v) => set("periodicita", v)}>
                                <SelectTrigger data-testid="vr-period"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="mensile">Mensile</SelectItem>
                                    <SelectItem value="annuale">Annuale</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <div>
                            <Label>Giorno (1-28)</Label>
                            <Input
                                type="number" min="1" max="28"
                                value={f.giorno_mese}
                                onChange={(e) => set("giorno_mese", e.target.value)}
                                data-testid="vr-giorno"
                            />
                        </div>
                        {f.periodicita === "annuale" && (
                            <div>
                                <Label>Mese (1-12)</Label>
                                <Input
                                    type="number" min="1" max="12"
                                    value={f.mese_anno}
                                    onChange={(e) => set("mese_anno", e.target.value)}
                                    data-testid="vr-mese"
                                />
                            </div>
                        )}
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <Label>Da *</Label>
                            <Input
                                type="date" value={f.data_inizio}
                                onChange={(e) => set("data_inizio", e.target.value)}
                                data-testid="vr-dal"
                            />
                        </div>
                        <div>
                            <Label>A (opzionale)</Label>
                            <Input
                                type="date" value={f.data_fine}
                                onChange={(e) => set("data_fine", e.target.value)}
                                data-testid="vr-al"
                            />
                        </div>
                    </div>
                    <div>
                        <Label>Note (opzionali)</Label>
                        <Input value={f.note} onChange={(e) => set("note", e.target.value)} />
                    </div>
                    <label className="flex items-center gap-2 text-sm">
                        <input
                            type="checkbox" checked={f.attiva}
                            onChange={(e) => set("attiva", e.target.checked)}
                            data-testid="vr-attiva"
                        />
                        Regola attiva (genera voci automaticamente)
                    </label>
                    <div className="text-[11px] text-fuchsia-700 bg-fuchsia-50 border border-fuchsia-200 rounded p-2">
                        Le voci verranno generate automaticamente nell'estratto conto del
                        collaboratore alle date previste, fino ad oggi.
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={() => onClose(false)}>Annulla</Button>
                    <Button
                        onClick={save} disabled={saving}
                        className="bg-fuchsia-700 hover:bg-fuchsia-800"
                        data-testid="vr-save"
                    >
                        {saving ? "Salvataggio…" : (voce ? "Aggiorna" : "Crea regola")}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
