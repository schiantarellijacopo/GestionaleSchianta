import { useEffect, useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Megaphone, Mail, Send, Tag, Sparkles, Users, ArrowRight } from "lucide-react";
import { toast } from "sonner";

export default function Marketing() {
    return (
        <div data-testid="marketing-page">
            <PageHeader
                title="Marketing"
                subtitle="Newsletter, campagne e segmentazione clienti"
                icon={<Megaphone size={20} className="text-sky-700" />}
            />
            <Tabs defaultValue="newsletter">
                <TabsList className="bg-slate-100">
                    <TabsTrigger value="newsletter" data-testid="mkt-tab-newsletter">
                        <Mail size={13} className="mr-1.5" /> Newsletter
                    </TabsTrigger>
                    <TabsTrigger value="campagne" data-testid="mkt-tab-campagne">
                        <Megaphone size={13} className="mr-1.5" /> Campagne (Pipeline)
                    </TabsTrigger>
                    <TabsTrigger value="tag" data-testid="mkt-tab-tag">
                        <Tag size={13} className="mr-1.5" /> Tag clienti
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="newsletter" className="mt-4"><NewsletterTab /></TabsContent>
                <TabsContent value="campagne" className="mt-4"><CampagneTab /></TabsContent>
                <TabsContent value="tag" className="mt-4"><TagTab /></TabsContent>
            </Tabs>
        </div>
    );
}

// ============== NEWSLETTER ==============
function NewsletterTab() {
    const [anag, setAnag] = useState([]);
    const [tagDisponibili, setTagDisponibili] = useState([]);
    const [tagSelezionati, setTagSelezionati] = useState([]);
    const [oggetto, setOggetto] = useState("");
    const [corpo, setCorpo] = useState("");
    const [sending, setSending] = useState(false);

    useEffect(() => {
        api.get("/anagrafiche?limit=2000").then((r) => {
            setAnag(r.data);
            const all = new Set();
            r.data.forEach((a) => (a.tags || []).forEach((t) => all.add(t)));
            setTagDisponibili(Array.from(all).sort());
        });
    }, []);

    const destinatari = useMemo(() => {
        if (tagSelezionati.length === 0) return [];
        return anag.filter((a) =>
            a.email && (a.tags || []).some((t) => tagSelezionati.includes(t))
            && a.consenso_privacy !== false,
        );
    }, [anag, tagSelezionati]);

    const toggleTag = (t) => {
        setTagSelezionati((prev) => prev.includes(t)
            ? prev.filter((x) => x !== t) : [...prev, t]);
    };

    const invia = async () => {
        if (!oggetto || !corpo) { toast.error("Oggetto e corpo richiesti"); return; }
        if (destinatari.length === 0) { toast.error("Nessun destinatario selezionato"); return; }
        setSending(true);
        try {
            const r = await api.post("/newsletter/invia", {
                tags: tagSelezionati, oggetto, corpo,
            });
            toast.success(`${r.data.email_create} email accodate per l'invio`);
            setOggetto(""); setCorpo(""); setTagSelezionati([]);
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        finally { setSending(false); }
    };

    return (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card className="md:col-span-2 p-5 border-slate-200 space-y-4">
                <div className="text-sm font-semibold text-slate-800 flex items-center gap-2">
                    <Mail size={16} className="text-sky-700" /> Crea newsletter
                </div>
                <div>
                    <Label>Oggetto *</Label>
                    <Input value={oggetto} onChange={(e) => setOggetto(e.target.value)}
                           placeholder="Es: Promozione estate 2026" data-testid="nl-oggetto" />
                </div>
                <div>
                    <Label>Messaggio *</Label>
                    <Textarea rows={8} value={corpo} onChange={(e) => setCorpo(e.target.value)}
                              placeholder="Testo dell'email — puoi usare HTML semplice"
                              data-testid="nl-corpo" />
                    <div className="text-[10px] text-slate-500 mt-1">
                        Variabili supportate: <code>{"{{nome}}"}</code> · <code>{"{{ragione_sociale}}"}</code>
                    </div>
                </div>
                <div className="flex justify-end">
                    <Button onClick={invia} disabled={sending || destinatari.length === 0}
                            className="bg-sky-700 hover:bg-sky-800" data-testid="nl-invia">
                        <Send size={13} className="mr-1.5" />
                        {sending ? "Invio in corso..." : `Invia a ${destinatari.length} destinatari`}
                    </Button>
                </div>
            </Card>

            <Card className="p-5 border-slate-200 space-y-3">
                <div className="text-sm font-semibold text-slate-800 flex items-center gap-2">
                    <Tag size={16} className="text-emerald-700" /> Segmenti / Tag
                </div>
                <div className="text-xs text-slate-500">Clicca per selezionare uno o più tag</div>
                <div className="flex flex-wrap gap-1.5">
                    {tagDisponibili.length === 0 ? (
                        <div className="text-xs text-slate-400">
                            Nessun tag. Vai in <em>Marketing → Tag clienti</em> per generarli automaticamente.
                        </div>
                    ) : tagDisponibili.map((t) => (
                        <button
                            key={t}
                            onClick={() => toggleTag(t)}
                            className={`text-[11px] uppercase tracking-wide px-2 py-1 rounded-full border ${
                                tagSelezionati.includes(t)
                                    ? "bg-sky-700 text-white border-sky-700"
                                    : "bg-white text-slate-600 border-slate-300 hover:bg-slate-50"
                            }`}
                            data-testid={`nl-tag-${t}`}
                        >
                            {t}
                        </button>
                    ))}
                </div>

                <div className="pt-3 border-t border-slate-100">
                    <div className="text-xs uppercase tracking-widest text-slate-500 mb-2">Anteprima destinatari</div>
                    <div className="text-2xl font-semibold num">{destinatari.length}</div>
                    <div className="text-xs text-slate-500">contatti con email + consenso privacy</div>
                    {destinatari.length > 0 && (
                        <div className="mt-2 space-y-0.5 max-h-40 overflow-y-auto text-xs">
                            {destinatari.slice(0, 10).map((d) => (
                                <div key={d.id} className="truncate text-slate-600">
                                    • {d.ragione_sociale} <span className="text-slate-400">{d.email}</span>
                                </div>
                            ))}
                            {destinatari.length > 10 && (
                                <div className="text-[10px] text-slate-400">+ {destinatari.length - 10} altri</div>
                            )}
                        </div>
                    )}
                </div>
            </Card>
        </div>
    );
}

// ============== CAMPAGNE (Pipeline marketing) ==============
function CampagneTab() {
    const [campagne, setCampagne] = useState(null);

    useEffect(() => {
        api.get("/pipelines").then((r) => {
            setCampagne(r.data.filter((p) => p.tipo === "marketing"));
        });
    }, []);

    if (campagne === null) return <Loading />;

    return (
        <div>
            <div className="flex items-center justify-between mb-4">
                <div className="text-sm text-slate-600">
                    Le tue campagne di marketing attive ({campagne.length})
                </div>
                <Link to="/pipeline">
                    <Button variant="outline" size="sm" data-testid="mkt-vai-pipeline">
                        Crea / gestisci pipeline <ArrowRight size={12} className="ml-1" />
                    </Button>
                </Link>
            </div>

            {campagne.length === 0 ? (
                <Card className="p-8 border-dashed border-slate-300 text-center">
                    <Megaphone size={32} className="mx-auto text-slate-300 mb-3" />
                    <div className="font-medium text-slate-700">Nessuna campagna marketing attiva</div>
                    <div className="text-sm text-slate-500 mt-1">
                        Crea una nuova pipeline di tipo &quot;Marketing&quot; per iniziare a tracciare i lead.
                    </div>
                    <Link to="/pipeline">
                        <Button className="mt-4 bg-sky-700 hover:bg-sky-800" data-testid="mkt-prima-campagna">
                            Crea prima campagna
                        </Button>
                    </Link>
                </Card>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {campagne.map((c) => (
                        <Link key={c.id} to="/pipeline" className="block" data-testid={`mkt-camp-${c.id}`}>
                            <Card className="p-5 border-slate-200 hover:border-sky-400 hover:shadow-md transition-all">
                                <div className="flex items-center gap-2 mb-2">
                                    <Megaphone size={16} className="text-sky-700" />
                                    <div className="font-semibold text-slate-800">{c.nome}</div>
                                </div>
                                {c.descrizione && (
                                    <div className="text-xs text-slate-500 mb-3 line-clamp-2">{c.descrizione}</div>
                                )}
                                <div className="flex items-center justify-between text-xs text-slate-500 border-t border-slate-100 pt-2">
                                    <span>{c.colonne?.length || 0} fasi</span>
                                    <span className="font-semibold text-sky-700 num">{c.cards_count || 0} lead</span>
                                </div>
                            </Card>
                        </Link>
                    ))}
                </div>
            )}
        </div>
    );
}

// ============== TAG CLIENTI (auto-genera) ==============
function TagTab() {
    const [busy, setBusy] = useState(false);
    const [stat, setStat] = useState(null);

    useEffect(() => {
        api.get("/anagrafiche?limit=2000").then((r) => {
            const tagCount = {};
            r.data.forEach((a) => (a.tags || []).forEach((t) => {
                tagCount[t] = (tagCount[t] || 0) + 1;
            }));
            setStat({ totale: r.data.length, tag: tagCount });
        });
    }, []);

    const autogenera = async () => {
        setBusy(true);
        try {
            const r = await api.post("/anagrafiche/tags/auto-genera", {});
            toast.success(`Aggiornate ${r.data.aggiornate || 0} anagrafiche`);
            const r2 = await api.get("/anagrafiche?limit=2000");
            const tagCount = {};
            r2.data.forEach((a) => (a.tags || []).forEach((t) => {
                tagCount[t] = (tagCount[t] || 0) + 1;
            }));
            setStat({ totale: r2.data.length, tag: tagCount });
        } catch (e) { toast.error("Errore"); }
        finally { setBusy(false); }
    };

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card className="p-5 border-slate-200 space-y-3">
                <div className="text-sm font-semibold flex items-center gap-2">
                    <Sparkles size={16} className="text-amber-600" /> Auto-genera tag
                </div>
                <div className="text-xs text-slate-600">
                    Analizza tutte le anagrafiche e applica automaticamente tag utili per le campagne:
                </div>
                <ul className="text-xs text-slate-600 list-disc pl-5 space-y-0.5">
                    <li><strong>minorenne</strong> · <strong>maggiorenne</strong> · <strong>senior_65+</strong></li>
                    <li><strong>generazione_z</strong> · <strong>millennials</strong> · <strong>gen_x</strong> · <strong>boomers</strong></li>
                    <li><strong>condominio</strong> · <strong>azienda</strong> · <strong>privato</strong></li>
                    <li><strong>con_polizze</strong> · <strong>senza_polizze</strong></li>
                </ul>
                <Button onClick={autogenera} disabled={busy} className="bg-amber-600 hover:bg-amber-700" data-testid="mkt-autotag">
                    <Sparkles size={13} className="mr-1.5" /> {busy ? "Elaborazione..." : "Auto-genera tag su tutti i clienti"}
                </Button>
            </Card>

            <Card className="p-5 border-slate-200">
                <div className="text-sm font-semibold flex items-center gap-2 mb-3">
                    <Users size={16} className="text-sky-700" /> Statistiche tag
                </div>
                {!stat ? <Loading /> : (
                    <div className="space-y-1.5 max-h-72 overflow-y-auto">
                        {Object.entries(stat.tag).sort((a, b) => b[1] - a[1]).map(([t, n]) => (
                            <div key={t} className="flex items-center justify-between text-xs border-b border-slate-100 pb-1">
                                <span className="badge badge-neutral">{t}</span>
                                <span className="num font-semibold text-slate-700">{n}</span>
                            </div>
                        ))}
                        {Object.keys(stat.tag).length === 0 && <Empty />}
                    </div>
                )}
            </Card>
        </div>
    );
}
