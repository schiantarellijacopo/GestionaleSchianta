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
import Sinistri from "@/pages/Sinistri";
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
import Corsi from "@/pages/Corsi";
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
                            <Route path="/sinistri" element={<Sinistri />} />
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
