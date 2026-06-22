import Sidebar from "./Sidebar";
import { Outlet } from "react-router-dom";

export default function Layout() {
    return (
        <div className="flex min-h-screen bg-slate-50">
            <Sidebar />
            <main className="flex-1 min-w-0">
                <div className="max-w-[1400px] mx-auto px-8 py-8 page-fade">
                    <Outlet />
                </div>
            </main>
        </div>
    );
}
