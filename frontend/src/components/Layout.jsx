import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import { Outlet } from "react-router-dom";

export default function Layout() {
    return (
        <div className="flex min-h-screen bg-slate-50">
            <Sidebar />
            <main className="flex-1 min-w-0 flex flex-col">
                <TopBar />
                <div className="max-w-[1400px] mx-auto w-full px-8 py-8 page-fade flex-1">
                    <Outlet />
                </div>
            </main>
        </div>
    );
}
