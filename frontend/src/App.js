import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "@/contexts/AuthContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import Layout from "@/components/Layout";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Anagrafiche from "@/pages/Anagrafiche";
import AnagraficaDetail from "@/pages/AnagraficaDetail";
import Polizze from "@/pages/Polizze";
import PolizzaDetail from "@/pages/PolizzaDetail";
import Titoli from "@/pages/Titoli";
import TitoliStorici from "@/pages/TitoliStorici";
import Alert from "@/pages/Alert";
import Sinistri from "@/pages/Sinistri";
import SinistroDetail from "@/pages/SinistroDetail";
import Statistiche from "@/pages/Statistiche";
import Cervello from "@/pages/Cervello";
import LibroMatricolaPage from "@/pages/LibroMatricolaPage";
import CorsiIvass from "@/pages/CorsiIvass";
import AssistentePersonale from "@/pages/AssistentePersonale";
import Ritenute from "@/pages/Ritenute";
import Trattative from "@/pages/Trattative";
import Newsletter from "@/pages/Newsletter";
import Voucher from "@/pages/Voucher";
import Contabilita from "@/pages/Contabilita";
import Compagnie from "@/pages/Compagnie";
import Importazione from "@/pages/Importazione";
import Pensioni from "@/pages/Pensioni";
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
import TitoliSospesi from "@/pages/TitoliSospesi";
import Marketing from "@/pages/Marketing";
import Avvisi from "@/pages/Avvisi";
import RubricaCompagnie from "@/pages/RubricaCompagnie";
import Rappel from "@/pages/Rappel";
import Agenzie from "@/pages/Agenzie";
import RitenuteCompagnia from "@/pages/RitenuteCompagnia";
import FattureAgenziaPartner from "@/pages/FattureAgenziaPartner";
import LeadListe from "@/pages/LeadListe";
import RitenuteHub from "@/pages/RitenuteHub";
import SetupIniziale from "@/pages/SetupIniziale";
import ScambioDati from "@/pages/ScambioDati";
import DocumentiInbox from "@/pages/DocumentiInbox";
import { Toaster } from "@/components/ui/sonner";

function App() {
    return (
        <div className="App">
            <AuthProvider>
                <BrowserRouter>
                    <Routes>
                        <Route path="/login" element={<Login />} />
                        <Route
                            element={
                                <ProtectedRoute>
                                    <Layout />
                                </ProtectedRoute>
                            }
                        >
                            <Route path="/" element={<Dashboard />} />
                            <Route path="/anagrafiche" element={<Anagrafiche />} />
                            <Route path="/anagrafiche/:id" element={<AnagraficaDetail />} />
                            <Route path="/polizze" element={<Polizze />} />
                            <Route path="/polizze/:id" element={<PolizzaDetail />} />
                            <Route path="/titoli" element={<Titoli />} />
                            <Route path="/titoli-storici" element={<TitoliStorici />} />
                            <Route path="/alert" element={<Alert />} />
                            <Route path="/sinistri" element={<Sinistri />} />
                            <Route path="/sinistri/:id" element={<SinistroDetail />} />
                            <Route path="/statistiche" element={<Statistiche />} />
                            <Route path="/cervello" element={<Cervello />} />
                            <Route path="/libro-matricola" element={<LibroMatricolaPage />} />
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
                            <Route path="*" element={<Navigate to="/" replace />} />
                        </Route>
                    </Routes>
                </BrowserRouter>
                <Toaster position="top-right" richColors />
            </AuthProvider>
        </div>
    );
}

export default App;
