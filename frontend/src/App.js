import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { useEffect } from "react";
import { AuthProvider } from "@/contexts/AuthContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import Layout from "@/components/Layout";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Anagrafiche from "@/pages/Anagrafiche";
import AnagraficaDetail from "@/pages/AnagraficaDetail";
import Polizze from "@/pages/Polizze";
import PolizzaDetail from "@/pages/PolizzaDetail";
import PortaleCliente from "@/pages/PortaleCliente";
import UploadDocPublic from "@/pages/UploadDocPublic";
import RichiesteCliente from "@/pages/RichiesteCliente";
import Titoli from "@/pages/Titoli";
import TitoliStorici from "@/pages/TitoliStorici";
import Alert from "@/pages/Alert";
import Sinistri from "@/pages/Sinistri";
import SinistroDetail from "@/pages/SinistroDetail";
import Statistiche from "@/pages/Statistiche";
import Cervello from "@/pages/Cervello";
import LibroMatricolaPage from "@/pages/LibroMatricolaPage";
import RegolazionePremio from "@/pages/RegolazionePremio";
import RegolazionePublic from "@/pages/RegolazionePublic";
import CorsiIvass from "@/pages/CorsiIvass";
import AssistentePersonale from "@/pages/AssistentePersonale";
import NotebookAI from "@/pages/NotebookAI";
import NotebookAIDetail from "@/pages/NotebookAIDetail";
import ModelliPiramide from "@/pages/ModelliPiramide";
import PortaleLanding from "@/pages/PortaleLanding";
import ImmaginiAI from "@/pages/ImmaginiAI";
import StudioMarketing from "@/pages/StudioMarketing";
import Ritenute from "@/pages/Ritenute";
import Trattative from "@/pages/Trattative";
import Newsletter from "@/pages/Newsletter";
import Voucher from "@/pages/Voucher";
import Contabilita from "@/pages/Contabilita";
import Compagnie from "@/pages/Compagnie";
import Importazione from "@/pages/Importazione";
import Pensioni from "@/pages/Pensioni";
import BibliotecaPrevidenza from "@/pages/BibliotecaPrevidenza";
import Tasks from "@/pages/Tasks";
import CaricaDocumento from "@/pages/CaricaDocumento";
import AppCliente from "@/pages/AppCliente";
import Email from "@/pages/Email";
import Attivita from "@/pages/Attivita";
import Provvigioni from "@/pages/Provvigioni";
import Pipeline from "@/pages/Pipeline";
import Librerie from "@/pages/Librerie";
import MappaClienti from "@/pages/MappaClienti";
import Chat from "@/pages/Chat";
import Diario from "@/pages/Diario";
import Posta from "@/pages/Posta";
import Corsi from "@/pages/Corsi";
import Calendario from "@/pages/Calendario";
import EstrattoContoCompagnie from "@/pages/EstrattoContoCompagnie";
import EstrattoContoContraente from "@/pages/EstrattoContoContraente";
import TitoliSospesi from "@/pages/TitoliSospesi";
import Marketing from "@/pages/Marketing";
import Avvisi from "@/pages/Avvisi";
import CarichiMensili from "@/pages/CarichiMensili";
import RubricaCompagnie from "@/pages/RubricaCompagnie";
import Rappel from "@/pages/Rappel";
import Agenzie from "@/pages/Agenzie";
import RitenuteCompagnia from "@/pages/RitenuteCompagnia";
import CopilotWidget from "@/components/CopilotWidget";
import FattureAgenziaPartner from "@/pages/FattureAgenziaPartner";
import LeadListe from "@/pages/LeadListe";
import RitenuteHub from "@/pages/RitenuteHub";
import SetupIniziale from "@/pages/SetupIniziale";
import ScambioDati from "@/pages/ScambioDati";
import DocumentiInbox from "@/pages/DocumentiInbox";
import WhatsAppInstances from "@/pages/WhatsAppInstances";
import SuperAdminPanel from "@/pages/SuperAdminPanel";
import AdminLogin from "@/pages/AdminLogin";
import SuperAdminLayout from "@/components/SuperAdminLayout";
import { Toaster } from "@/components/ui/sonner";

function App() {
    return (
        <div className="App">
            <AuthProvider>
                <BrowserRouter>
                    <PortaleSubdomainRedirect />
                    <Routes>
                        <Route path="/login" element={<Login />} />
                        <Route path="/admin-login" element={<AdminLogin />} />
                        <Route path="/portale/*" element={<PortaleCliente />} />
                        <Route path="/c/:slug" element={<PortaleLanding />} />
                        <Route path="/upload-doc" element={<UploadDocPublic />} />
                        <Route path="/carica/:token" element={<CaricaDocumento />} />
                        <Route path="/rp/:token" element={<RegolazionePublic />} />

                        {/* Route dedicate Super Admin (layout separato, no sidebar clienti) */}
                        <Route
                            element={
                                <ProtectedRoute superAdminOnly>
                                    <SuperAdminLayout />
                                </ProtectedRoute>
                            }
                        >
                            <Route path="/super-admin" element={<SuperAdminPanel />} />
                            <Route path="/super-admin/biblioteca" element={<BibliotecaPrevidenza />} />
                        </Route>

                        <Route
                            element={
                                <ProtectedRoute blockSuperAdmin>
                                    <Layout />
                                </ProtectedRoute>
                            }
                        >
                            <Route path="/" element={<Dashboard />} />
                            <Route path="/anagrafiche" element={<Anagrafiche />} />
                            <Route path="/anagrafiche/:id" element={<AnagraficaDetail />} />
                            <Route path="/polizze" element={<Polizze />} />
                            <Route path="/polizze/:id" element={<PolizzaDetail />} />
                            <Route path="/richieste-cliente" element={<RichiesteCliente />} />
                            <Route path="/titoli" element={<Titoli />} />
                            <Route path="/titoli-storici" element={<TitoliStorici />} />
                            <Route path="/alert" element={<Alert />} />
                            <Route path="/sinistri" element={<Sinistri />} />
                            <Route path="/sinistri/:id" element={<SinistroDetail />} />
                            <Route path="/statistiche" element={<Statistiche />} />
                            <Route path="/cervello" element={<Cervello />} />
                            <Route path="/libro-matricola" element={<LibroMatricolaPage />} />
                            <Route path="/regolazione-premio" element={<RegolazionePremio />} />
                            <Route path="/corsi-ivass" element={<CorsiIvass />} />
                            <Route path="/assistente-personale" element={<AssistentePersonale />} />
                            <Route path="/ritenute" element={
                                <ProtectedRoute roles={["admin", "collaboratore"]}><RitenuteHub /></ProtectedRoute>
                            } />
                            <Route path="/ritenute-collaboratori" element={
                                <ProtectedRoute roles={["admin"]}><Ritenute /></ProtectedRoute>
                            } />
                            <Route path="/setup-iniziale" element={
                                <ProtectedRoute roles={["admin"]}><SetupIniziale /></ProtectedRoute>
                            } />
                            <Route path="/scambio-dati" element={
                                <ProtectedRoute roles={["admin"]}><ScambioDati /></ProtectedRoute>
                            } />
                            <Route path="/documenti-inbox" element={
                                <ProtectedRoute roles={["admin", "collaboratore", "dipendente"]}><DocumentiInbox /></ProtectedRoute>
                            } />
                            <Route path="/trattative" element={<Trattative />} />
                            <Route path="/newsletter" element={<Newsletter />} />
                            <Route path="/voucher" element={<Voucher />} />
                            <Route path="/agenzie" element={
                                <ProtectedRoute roles={["admin"]}><Agenzie /></ProtectedRoute>
                            } />
                            <Route path="/ritenute-compagnia" element={
                                <ProtectedRoute roles={["admin", "collaboratore", "dipendente"]}><RitenuteCompagnia /></ProtectedRoute>
                            } />
                            <Route path="/fatture-agenzia-partner" element={
                                <ProtectedRoute roles={["admin", "collaboratore"]}><FattureAgenziaPartner /></ProtectedRoute>
                            } />
                            <Route path="/lead-liste" element={
                                <ProtectedRoute roles={["admin", "collaboratore", "dipendente"]}><LeadListe /></ProtectedRoute>
                            } />
                            <Route
                                path="/avvisi"
                                element={
                                    <ProtectedRoute roles={["admin", "collaboratore", "dipendente"]}>
                                        <Avvisi />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/carichi-mensili"
                                element={
                                    <ProtectedRoute roles={["admin", "collaboratore", "dipendente"]}>
                                        <CarichiMensili />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/rubrica-compagnie"
                                element={
                                    <ProtectedRoute roles={["admin", "collaboratore", "dipendente"]}>
                                        <RubricaCompagnie />
                                    </ProtectedRoute>
                                }
                            />
                            <Route path="/calendario" element={<Calendario />} />
                            <Route
                                path="/sospesi"
                                element={
                                    <ProtectedRoute roles={["admin", "collaboratore", "dipendente"]}>
                                        <TitoliSospesi />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/marketing"
                                element={
                                    <ProtectedRoute roles={["admin", "collaboratore", "dipendente"]}>
                                        <Marketing />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/compagnie-estratto"
                                element={
                                    <ProtectedRoute roles={["admin", "collaboratore", "dipendente"]}>
                                        <EstrattoContoCompagnie />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/contraente-estratto"
                                element={
                                    <ProtectedRoute roles={["admin", "collaboratore", "dipendente"]}>
                                        <EstrattoContoContraente />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/rappel"
                                element={
                                    <ProtectedRoute roles={["admin", "collaboratore", "dipendente"]}>
                                        <Rappel />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/contabilita"
                                element={
                                    <ProtectedRoute roles={["admin", "collaboratore", "dipendente"]}>
                                        <Contabilita />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/compagnie"
                                element={
                                    <ProtectedRoute roles={["admin", "collaboratore"]}>
                                        <Compagnie />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/importazione"
                                element={
                                    <ProtectedRoute roles={["admin", "collaboratore"]}>
                                        <Importazione />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/importazioni"
                                element={
                                    <ProtectedRoute roles={["admin", "collaboratore"]}>
                                        <Importazione />
                                    </ProtectedRoute>
                                }
                            />
                            <Route path="/pensioni" element={<Pensioni />} />
                            <Route path="/biblioteca-previdenza" element={<BibliotecaPrevidenza />} />
                            <Route path="/tasks" element={<Tasks />} />
                            <Route path="/notebook-ai" element={<NotebookAI />} />
                            <Route path="/notebook-ai/:id" element={<NotebookAIDetail />} />
                            <Route path="/modelli-piramide" element={<ModelliPiramide />} />
                            <Route path="/immagini-ai" element={<ImmaginiAI />} />
                            <Route path="/studio-marketing" element={<StudioMarketing />} />
                            <Route path="/app-cliente" element={<AppCliente />} />
                            <Route path="/provvigioni" element={
                                <ProtectedRoute roles={["admin", "collaboratore", "dipendente"]}>
                                    <Provvigioni />
                                </ProtectedRoute>
                            } />
                            <Route path="/pipeline" element={<Pipeline />} />
                            <Route path="/mappa" element={
                                <ProtectedRoute roles={["admin", "collaboratore", "dipendente"]}>
                                    <MappaClienti />
                                </ProtectedRoute>
                            } />
                            <Route path="/chat" element={<Chat />} />
                            <Route path="/diario" element={<Diario />} />
                            <Route path="/posta" element={<Posta />} />
                            <Route path="/corsi" element={<Corsi />} />
                            <Route path="/librerie" element={
                                <ProtectedRoute roles={["admin", "collaboratore"]}>
                                    <Librerie />
                                </ProtectedRoute>
                            } />
                            <Route path="/whatsapp" element={
                                <ProtectedRoute roles={["admin", "collaboratore"]}>
                                    <WhatsAppInstances />
                                </ProtectedRoute>
                            } />
                            <Route
                                path="/email"
                                element={
                                    <ProtectedRoute roles={["admin", "collaboratore", "dipendente"]}>
                                        <Email />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/attivita"
                                element={
                                    <ProtectedRoute roles={["admin", "collaboratore"]}>
                                        <Attivita />
                                    </ProtectedRoute>
                                }
                            />
                            <Route path="/super-admin" element={
                                <ProtectedRoute superAdminOnly>
                                    <Navigate to="/super-admin" replace />
                                </ProtectedRoute>
                            } />
                            <Route path="*" element={<Navigate to="/" replace />} />
                        </Route>
                    </Routes>
                    <CopilotWidget />
                </BrowserRouter>
                <Toaster position="top-right" richColors />
            </AuthProvider>
        </div>
    );
}

export default App;

/**
 * PortaleSubdomainRedirect — Se l'app è servita su un hostname configurato
 * per il portale cliente (es. portale.miaagenzia.it, clienti.miaagenzia.it),
 * reindirizza automaticamente TUTTO il traffico a /portale.
 *
 * Configurazione tramite variabile d'ambiente:
 *   REACT_APP_PORTALE_HOSTS = "portale.dominio.it,clienti.dominio.it"
 * oppure il match automatico: hostname che inizia con "portale." o "clienti."
 */
function PortaleSubdomainRedirect() {
    const location = useLocation();
    useEffect(() => {
        if (typeof window === "undefined") return;
        const host = (window.location.hostname || "").toLowerCase();
        const configured = (process.env.REACT_APP_PORTALE_HOSTS || "")
            .split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);
        const isPortaleHost =
            configured.includes(host) ||
            host.startsWith("portale.") ||
            host.startsWith("clienti.") ||
            host.startsWith("portal.");
        if (!isPortaleHost) return;
        const path = location.pathname || "/";
        // Le route pubbliche che devono restare (upload-doc con token)
        if (path.startsWith("/upload-doc")) return;
        // Se non è già sotto /portale, redirect
        if (!path.startsWith("/portale")) {
            window.location.replace("/portale");
        }
    }, [location]);
    return null;
}
