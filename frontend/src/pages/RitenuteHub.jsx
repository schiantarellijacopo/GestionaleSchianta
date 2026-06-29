/**
 * Ritenute (hub) — pagina unificata con 3 tab:
 *  - Ritenute Compagnia (sulle nostre provvigioni)
 *  - Ritenute Collaboratori (versamenti F24)
 *  - Ritenute Agenzie Partner (sulle fatture provvigioni partner)
 */
import { useState } from "react";
import { PageHeader } from "@/components/Shared";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Coins, TrendingDown, Users, Handshake } from "lucide-react";
import RitenuteCompagnia from "./RitenuteCompagnia";
import Ritenute from "./Ritenute";
import FattureAgenziaPartner from "./FattureAgenziaPartner";

export default function RitenuteHub() {
    const [tab, setTab] = useState("compagnia");

    return (
        <div data-testid="ritenute-hub-page" className="space-y-3">
            <PageHeader
                title={<span className="flex items-center gap-2"><Coins className="text-amber-600" /> Ritenute</span>}
                subtitle="Gestione unica delle ritenute: compagnie, collaboratori, agenzie partner"
            />
            <Tabs value={tab} onValueChange={setTab}>
                <TabsList>
                    <TabsTrigger value="compagnia" data-testid="rit-tab-compagnia">
                        <TrendingDown size={14} className="mr-1" /> Ritenute Compagnia
                    </TabsTrigger>
                    <TabsTrigger value="collaboratori" data-testid="rit-tab-collab">
                        <Users size={14} className="mr-1" /> Ritenute Collaboratori
                    </TabsTrigger>
                    <TabsTrigger value="partner" data-testid="rit-tab-partner">
                        <Handshake size={14} className="mr-1" /> Ritenute Agenzia Partner
                    </TabsTrigger>
                </TabsList>
                <TabsContent value="compagnia"><RitenuteCompagnia /></TabsContent>
                <TabsContent value="collaboratori"><Ritenute /></TabsContent>
                <TabsContent value="partner"><FattureAgenziaPartner /></TabsContent>
            </Tabs>
        </div>
    );
}
