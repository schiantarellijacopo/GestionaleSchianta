# Iter116: direct test of scheduler_alert._tick_copertura (window, idempotency via copertura_auto_state)
import os, sys, asyncio
from datetime import datetime
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from motor.motor_asyncio import AsyncIOMotorClient
import scheduler_alert as sa

PRINC = "tenant-principale-schiantarelli"


async def main():
    raw = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    try:
        from tzlocal import get_localzone
        now = datetime.now(get_localzone())
    except Exception:
        now = datetime.utcnow()
    cfg = await raw.azienda_config.find_one({"agenzia_tenant_id": PRINC}, {"_id": 0})
    orig = {k: cfg.get(k) for k in ("copertura_auto_attivo", "copertura_auto_hour", "copertura_auto_minute")}
    n_before = await raw.comunicazioni_copertura.count_documents({})
    try:
        await raw.copertura_auto_state.delete_many({"tenant_id": PRINC})
        # 1) disabled -> no state
        await raw.azienda_config.update_one({"id": cfg["id"]}, {"$set": {"copertura_auto_attivo": False, "copertura_auto_hour": now.hour, "copertura_auto_minute": now.minute}})
        await sa._tick_copertura(raw)
        st = await raw.copertura_auto_state.find_one({"tenant_id": PRINC})
        print("disabled -> state:", st, "PASS" if st is None else "FAIL")
        # 2) enabled, out of window -> no state
        await raw.azienda_config.update_one({"id": cfg["id"]}, {"$set": {"copertura_auto_attivo": True, "copertura_auto_hour": (now.hour + 2) % 24}})
        await sa._tick_copertura(raw)
        st = await raw.copertura_auto_state.find_one({"tenant_id": PRINC})
        print("out of window -> state:", st, "PASS" if st is None else "FAIL")
        # 3) enabled, in window -> state set
        await raw.azienda_config.update_one({"id": cfg["id"]}, {"$set": {"copertura_auto_hour": now.hour, "copertura_auto_minute": now.minute}})
        await sa._tick_copertura(raw)
        st = await raw.copertura_auto_state.find_one({"tenant_id": PRINC}, {"_id": 0})
        print("in window -> state:", st, "PASS" if st and st["last_run_date"] == now.date().isoformat() else "FAIL")
        # 4) second tick same day -> no change
        await sa._tick_copertura(raw)
        st2 = await raw.copertura_auto_state.find_one({"tenant_id": PRINC}, {"_id": 0})
        print("2nd tick idempotent:", "PASS" if st2["last_run_at"] == st["last_run_at"] else "FAIL")
        n_after = await raw.comunicazioni_copertura.count_documents({})
        print("comunicazioni before/after:", n_before, n_after)
        new = await raw.comunicazioni_copertura.find({}, {"_id": 0, "id": 1, "giorno": 1, "stato": 1, "agenzia_tenant_id": 1, "created_by_name": 1}).to_list(50)
        print("docs:", new)
        jobs = sa.__dict__.get("_scheduler")
        print("scheduler obj:", type(jobs))
    finally:
        await raw.azienda_config.update_one({"id": cfg["id"]}, {"$set": orig})
        await raw.copertura_auto_state.delete_many({"tenant_id": PRINC})
        print("restored", orig)

asyncio.run(main())
