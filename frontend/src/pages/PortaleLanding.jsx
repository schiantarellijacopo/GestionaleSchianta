/**
 * Landing pubblica personalizzata del Portale Cliente: /c/{slug}
 * URL formato: https://{sottodominio-agenzia}.{dominio}/c/{nome-cliente}
 */
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import axios from "axios";
import { ShieldCheck, ArrowRight, Loader2 } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function PortaleLanding() {
    const { slug } = useParams();
    const navigate = useNavigate();
    const [info, setInfo] = useState(null);
    const [errore, setErrore] = useState(false);

    useEffect(() => {
        axios.get(`${API}/public/portale-info/${slug}`)
            .then((r) => setInfo(r.data))
            .catch(() => setErrore(true));
    }, [slug]);

    const accedi = () => {
        if (info?.email) sessionStorage.setItem("portale_prefill_email", info.email);
        if (slug) sessionStorage.setItem("portale_slug", slug);
        navigate("/portale");
    };

    return (
        <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4"
             data-testid="portale-landing">
            <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-8 text-center">
                {errore ? (
                    <>
                        <div className="text-4xl mb-3">🔒</div>
                        <div className="font-bold text-slate-800 mb-1">Link non valido</div>
                        <div className="text-sm text-slate-500 mb-4">
                            Questo link personalizzato non esiste o è stato disattivato.
                        </div>
                        <button onClick={() => navigate("/portale")}
                                className="text-sm text-sky-700 hover:underline">
                            Vai al Portale Cliente
                        </button>
                    </>
                ) : !info ? (
                    <Loader2 className="animate-spin text-slate-400 mx-auto my-8" size={28} />
                ) : (
                    <>
                        <div className="w-14 h-14 rounded-2xl bg-sky-600 text-white flex items-center justify-center mx-auto mb-4">
                            <ShieldCheck size={26} />
                        </div>
                        <div className="text-[11px] uppercase tracking-widest text-slate-400 font-semibold mb-1"
                             data-testid="landing-agenzia">
                            {info.agenzia_nome}
                        </div>
                        <h1 className="text-xl font-bold text-slate-900 mb-2" data-testid="landing-cliente">
                            Benvenuto, {info.cliente_nome}
                        </h1>
                        <p className="text-sm text-slate-500 mb-6">
                            Questo è il tuo accesso personale al Portale Cliente: polizze,
                            quietanze, documenti, sinistri e la tua Piramide di protezione.
                        </p>
                        <button onClick={accedi}
                                className="w-full bg-sky-600 hover:bg-sky-700 text-white font-semibold rounded-lg py-3 flex items-center justify-center gap-2 transition-colors"
                                data-testid="landing-accedi-btn">
                            Accedi al tuo Portale <ArrowRight size={16} />
                        </button>
                        {info.email && (
                            <div className="text-[11px] text-slate-400 mt-3">
                                Username: <span className="font-mono">{info.email}</span>
                            </div>
                        )}
                    </>
                )}
            </div>
        </div>
    );
}
