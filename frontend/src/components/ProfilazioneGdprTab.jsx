/**
 * ProfilazioneGdprTab — dati sensibili (art.9 GDPR) e consensi marketing distinti.
 *
 * Sezioni:
 *  • Stile di vita (persona fisica): sport, fumo, salute, animali, viaggi.
 *  • Corporate profile (persona giuridica): fatturato, dipendenti, valori.
 *  • Consensi GDPR: marketing WhatsApp / SMS / Email + generici.
 */
import { useState } from "react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { ShieldCheck, Heart, Building2, MailCheck } from "lucide-react";

export default function ProfilazioneGdprTab({ ana, canEdit, onReload }) {
    const [sv, setSv] = useState(ana.stile_vita || {});
    const [cp, setCp] = useState(ana.corporate_profile || {});
    const [consensi, setConsensi] = useState({
        consenso_privacy: !!ana.consenso_privacy,
        consenso_dati_particolari: !!ana.consenso_dati_particolari,
        consenso_commerciale: !!ana.consenso_commerciale,
        consenso_marketing_whatsapp: !!ana.consenso_marketing_whatsapp,
        consenso_marketing_sms: !!ana.consenso_marketing_sms,
        consenso_marketing_email: !!ana.consenso_marketing_email,
    });

    const salva = async () => {
        try {
            await api.put(`/anagrafiche/${ana.id}`, {
                stile_vita: sv,
                corporate_profile: cp,
                ...consensi,
            });
            toast.success("Profilazione & consensi salvati");
            onReload?.();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const isPG = ana.tipo === "persona_giuridica";

    return (
        <div className="space-y-4 mt-4" data-testid="profilazione-gdpr-tab">
            {!isPG && <StileVitaSection sv={sv} setSv={setSv} canEdit={canEdit} />}
            {isPG && <CorporateProfileSection cp={cp} setCp={setCp} canEdit={canEdit} />}
            <GdprConsensiSection c={consensi} setC={setConsensi} canEdit={canEdit} />

            {canEdit && (
                <div className="flex justify-end">
                    <Button onClick={salva} className="bg-sky-700 hover:bg-sky-800" data-testid="prof-gdpr-save">
                        Salva profilazione e consensi
                    </Button>
                </div>
            )}
        </div>
    );
}

function StileVitaSection({ sv, setSv, canEdit }) {
    const set = (k, v) => setSv({ ...sv, [k]: v });
    return (
        <Card className="p-6 border-slate-200">
            <div className="flex items-center gap-2 mb-1">
                <Heart size={18} className="text-rose-600" />
                <h3 className="font-medium">Stile di vita</h3>
            </div>
            <div className="text-xs text-slate-500 mb-4 bg-amber-50 border border-amber-200 rounded px-3 py-2">
                Sezione con dati sensibili art. 9 GDPR: richiede consenso esplicito &quot;dati particolari&quot;.
            </div>

            {/* Sport */}
            <div className="mb-4">
                <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-2">Sport & hobby</div>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                    <Chk label="Pratica sport pericolosi" checked={sv.sport_pericolosi} onChange={(v) => set("sport_pericolosi", v)} disabled={!canEdit} testid="sv-sport-pericolosi" />
                    <div className="col-span-2">
                        <Label>Sport praticati (separati da virgola)</Label>
                        <Input value={(sv.sport_praticati || []).join(", ")} onChange={(e) => set("sport_praticati", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} disabled={!canEdit} data-testid="sv-sport-praticati" />
                    </div>
                    <div className="col-span-3">
                        <Label>Hobby (separati da virgola)</Label>
                        <Input value={(sv.hobby || []).join(", ")} onChange={(e) => set("hobby", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} disabled={!canEdit} data-testid="sv-hobby" />
                    </div>
                </div>
            </div>

            {/* Fumo & alcol */}
            <div className="mb-4">
                <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-2">Fumo & consumo alcol</div>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                    <Chk label="Fumatore" checked={sv.fumatore} onChange={(v) => set("fumatore", v)} disabled={!canEdit} testid="sv-fumatore" />
                    <div>
                        <Label>Sigarette/giorno</Label>
                        <Input type="number" value={sv.sigarette_giorno || ""} onChange={(e) => set("sigarette_giorno", parseInt(e.target.value) || null)} disabled={!canEdit} data-testid="sv-sigarette" />
                    </div>
                    <div>
                        <Label>Consumo alcol</Label>
                        <Input placeholder="nullo / moderato / regolare" value={sv.consumo_alcol || ""} onChange={(e) => set("consumo_alcol", e.target.value)} disabled={!canEdit} data-testid="sv-alcol" />
                    </div>
                </div>
            </div>

            {/* Salute */}
            <div className="mb-4">
                <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-2">Salute</div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div>
                        <Label>Patologie note</Label>
                        <Textarea rows={2} value={sv.patologie || ""} onChange={(e) => set("patologie", e.target.value)} disabled={!canEdit} data-testid="sv-patologie" />
                    </div>
                    <div>
                        <Label>Interventi chirurgici</Label>
                        <Textarea rows={2} value={sv.interventi || ""} onChange={(e) => set("interventi", e.target.value)} disabled={!canEdit} data-testid="sv-interventi" />
                    </div>
                </div>
            </div>

            {/* Animali */}
            <div className="mb-4">
                <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-2">Animali domestici</div>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                    <Chk label="Possiede cane" checked={sv.possiede_cane} onChange={(v) => set("possiede_cane", v)} disabled={!canEdit} testid="sv-possiede-cane" />
                    <div>
                        <Label>Razza cane</Label>
                        <Input value={sv.cane_razza || ""} onChange={(e) => set("cane_razza", e.target.value)} disabled={!canEdit || !sv.possiede_cane} data-testid="sv-cane-razza" />
                    </div>
                    <div>
                        <Label>Taglia cane</Label>
                        <Input placeholder="piccola / media / grande" value={sv.cane_taglia || ""} onChange={(e) => set("cane_taglia", e.target.value)} disabled={!canEdit || !sv.possiede_cane} data-testid="sv-cane-taglia" />
                    </div>
                </div>
            </div>

            {/* Viaggi */}
            <div>
                <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-2">Viaggi</div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <Chk label="Viaggia spesso all'estero" checked={sv.viaggi_estero_frequenti} onChange={(v) => set("viaggi_estero_frequenti", v)} disabled={!canEdit} testid="sv-viaggi-estero" />
                    <div>
                        <Label>Destinazioni frequenti</Label>
                        <Input value={(sv.viaggi_destinazioni || []).join(", ")} onChange={(e) => set("viaggi_destinazioni", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} disabled={!canEdit} data-testid="sv-viaggi-destinazioni" />
                    </div>
                </div>
            </div>
        </Card>
    );
}

function CorporateProfileSection({ cp, setCp, canEdit }) {
    const set = (k, v) => setCp({ ...cp, [k]: v });
    return (
        <Card className="p-6 border-slate-200">
            <div className="flex items-center gap-2 mb-4">
                <Building2 size={18} className="text-sky-700" />
                <h3 className="font-medium">Profilo aziendale</h3>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <div>
                    <Label>Fatturato annuo €</Label>
                    <Input type="number" step="0.01" value={cp.fatturato_annuo || ""} onChange={(e) => set("fatturato_annuo", parseFloat(e.target.value) || null)} disabled={!canEdit} data-testid="cp-fatturato" />
                </div>
                <div>
                    <Label>Monte salari €</Label>
                    <Input type="number" step="0.01" value={cp.monte_salari || ""} onChange={(e) => set("monte_salari", parseFloat(e.target.value) || null)} disabled={!canEdit} data-testid="cp-monte-salari" />
                </div>
                <div>
                    <Label>N. dipendenti</Label>
                    <Input type="number" value={cp.numero_dipendenti || ""} onChange={(e) => set("numero_dipendenti", parseInt(e.target.value) || null)} disabled={!canEdit} data-testid="cp-dipendenti" />
                </div>
                <div>
                    <Label>Valore fabbricato €</Label>
                    <Input type="number" step="0.01" value={cp.valore_fabbricato || ""} onChange={(e) => set("valore_fabbricato", parseFloat(e.target.value) || null)} disabled={!canEdit} data-testid="cp-valore-fabbricato" />
                </div>
                <div>
                    <Label>Valore macchinari €</Label>
                    <Input type="number" step="0.01" value={cp.valore_macchinari || ""} onChange={(e) => set("valore_macchinari", parseFloat(e.target.value) || null)} disabled={!canEdit} data-testid="cp-valore-macchinari" />
                </div>
                <div>
                    <Label>Valore merci €</Label>
                    <Input type="number" step="0.01" value={cp.valore_merci || ""} onChange={(e) => set("valore_merci", parseFloat(e.target.value) || null)} disabled={!canEdit} data-testid="cp-valore-merci" />
                </div>
                <div>
                    <Label>ATECO</Label>
                    <Input value={cp.ateco || ""} onChange={(e) => set("ateco", e.target.value)} disabled={!canEdit} data-testid="cp-ateco" />
                </div>
                <div>
                    <Label>PEC</Label>
                    <Input value={cp.pec || ""} onChange={(e) => set("pec", e.target.value)} disabled={!canEdit} data-testid="cp-pec" />
                </div>
                <div>
                    <Label>Capitale sociale €</Label>
                    <Input type="number" step="0.01" value={cp.capitale_sociale || ""} onChange={(e) => set("capitale_sociale", parseFloat(e.target.value) || null)} disabled={!canEdit} data-testid="cp-capitale" />
                </div>
                <div className="col-span-2">
                    <Label>Legale rappresentante</Label>
                    <Input value={cp.legale_rappresentante || ""} onChange={(e) => set("legale_rappresentante", e.target.value)} disabled={!canEdit} data-testid="cp-lr" />
                </div>
                <div className="col-span-3">
                    <label className="flex items-center gap-2 text-sm cursor-pointer">
                        <input
                            type="checkbox" checked={!!cp.export_usa_extra_ue}
                            onChange={(e) => set("export_usa_extra_ue", e.target.checked)}
                            disabled={!canEdit} data-testid="cp-export-usa"
                        />
                        Esporta verso USA / extra-UE (impatta polizze responsabilità prodotto)
                    </label>
                </div>
            </div>
        </Card>
    );
}

function GdprConsensiSection({ c, setC, canEdit }) {
    const set = (k, v) => setC({ ...c, [k]: v });
    return (
        <Card className="p-6 border-slate-200">
            <div className="flex items-center gap-2 mb-4">
                <ShieldCheck size={18} className="text-emerald-700" />
                <h3 className="font-medium">Consensi GDPR distinti</h3>
            </div>
            <div className="space-y-4">
                <div>
                    <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-2">Consensi obbligatori/generici</div>
                    <div className="space-y-2">
                        <Chk label="Consenso Privacy (informativa art.13)" checked={c.consenso_privacy} onChange={(v) => set("consenso_privacy", v)} disabled={!canEdit} testid="gdpr-privacy" />
                        <Chk label="Consenso al trattamento dati particolari (art.9 GDPR)" checked={c.consenso_dati_particolari} onChange={(v) => set("consenso_dati_particolari", v)} disabled={!canEdit} testid="gdpr-dati-particolari" />
                        <Chk label="Consenso comunicazioni commerciali (generico)" checked={c.consenso_commerciale} onChange={(v) => set("consenso_commerciale", v)} disabled={!canEdit} testid="gdpr-commerciale" />
                    </div>
                </div>

                <div className="pt-4 border-t border-slate-100">
                    <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-2 flex items-center gap-1">
                        <MailCheck size={12} /> Marketing su canali distinti (necessario consenso separato per ciascuno)
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                        <Chk label="Marketing via WhatsApp" checked={c.consenso_marketing_whatsapp} onChange={(v) => set("consenso_marketing_whatsapp", v)} disabled={!canEdit} testid="gdpr-mkt-whatsapp" />
                        <Chk label="Marketing via SMS" checked={c.consenso_marketing_sms} onChange={(v) => set("consenso_marketing_sms", v)} disabled={!canEdit} testid="gdpr-mkt-sms" />
                        <Chk label="Marketing via Email" checked={c.consenso_marketing_email} onChange={(v) => set("consenso_marketing_email", v)} disabled={!canEdit} testid="gdpr-mkt-email" />
                    </div>
                </div>
            </div>
        </Card>
    );
}

function Chk({ label, checked, onChange, disabled, testid }) {
    return (
        <label className={`flex items-center gap-2 text-sm ${disabled ? "opacity-60" : "cursor-pointer"}`}>
            <input type="checkbox" checked={!!checked} onChange={(e) => onChange(e.target.checked)} disabled={disabled} data-testid={testid} />
            {label}
        </label>
    );
}
