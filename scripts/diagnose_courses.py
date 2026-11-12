"""Read-only diagnostic: inspect the live Supabase `courses` table.

Run:  .\\venv\\Scripts\\python.exe scripts\\diagnose_courses.py

This script performs SELECT / introspection queries ONLY. It never inserts,
updates, or deletes data, and it never prints the service-role key or any
other secret. It checks:

  1. whether public.courses exists and exactly which columns it has,
  2. how many course rows exist (and their active state),
  3. what the application's own list_courses() would return
     (active-only vs all) against this database,
  4. whether public.users.status exists (context for the earlier fix).

If the service-role key is missing/blank, no network call is made.
"""

import os
import socket
import sys

# Fail fast instead of hanging when the machine has no route to Supabase.
socket.setdefaulttimeout(15)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

URL = os.environ.get("SUPABASE_URL", "").strip()
KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def main():
    if not URL or not KEY:
        print("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not set — nothing to inspect.")
        return 1

    from supabase import create_client

    client = create_client(URL, KEY)

    print("== 1) public.courses columns ==")
    try:
        res = (
            client.table("courses")
            .select("id, code, name, duration_years, seats_total, program_type, "
                    "eligibility, tuition_fee, is_active, created_at")
            .limit(1)
            .execute()
        )
        print("SELECT with the app's course columns succeeded; first row:",
              res.data[0] if res.data else "(no rows)")
    except Exception as exc:
        print("SELECT failed:", type(exc).__name__, str(exc)[:300])

    print("\n== 2) row counts ==")
    try:
        res = client.table("courses").select("id", count="exact").execute()
        total = res.count
        print("total courses:", total)
    except Exception as exc:
        print("count failed:", type(exc).__name__, str(exc)[:300])
        total = 0
    try:
        res = client.table("courses").select("id").eq("is_active", True).execute()
        print("active courses:", len(res.data or []))
    except Exception as exc:
        print("active-count failed:", type(exc).__name__, str(exc)[:300])

    print("\n== 3) what the app's service would return (mimics list_courses) ==")
    try:
        all_rows = client.table("courses").select("*").order("name").execute().data or []
        print("list_courses() [all]:", len(all_rows))
        for r in all_rows[:10]:
            print("   -", r.get("code"), "|", r.get("name"), "| active =", r.get("is_active"),
                  "| type =", r.get("program_type"), "| fee =", r.get("tuition_fee"))
    except Exception as exc:
        print("list all failed:", type(exc).__name__, str(exc)[:300])
    try:
        active_rows = (
            client.table("courses").select("*").eq("is_active", True).order("name").execute().data or []
        )
        print("list_courses(active_only=True):", len(active_rows))
    except Exception as exc:
        print("list active failed:", type(exc).__name__, str(exc)[:300])

    print("\n== 4) context: public.users.status ==")
    try:
        res = client.table("users").select("status").limit(1).execute()
        print("users.status column EXISTS (rows:", len(res.data or []), ")")
    except Exception as exc:
        print("users.status missing/failed:", type(exc).__name__, str(exc)[:200])

    return 0


if __name__ == "__main__":
    sys.exit(main())