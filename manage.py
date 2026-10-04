#!/usr/bin/env python3
"""
manage.py — user administration from the shell (Render Shell, on the same disk as the app).

  python manage.py add-user <username> --roles agent --brands rozela,velora [--lang he] [--name "Agent One"]
  python manage.py add-user manager --roles admin,user-manager --brands all
  python manage.py reset-password <username>
  python manage.py disable <username> | enable <username>
  python manage.py list
  python manage.py seed-team            # the four first accounts (skips any that exist)

Passwords are never typed or stored in clear: every new account and every reset prints a ONE-TIME
temporary password, and the user must choose their own at first sign-in (must_change).
Every change is written to the same audit log the web user manager uses (actor "cli").
"""

import argparse
import json
import os
import sys

import engine_proxy
import security
from users_store import UserStore, UserStoreError, public_user

# DECISIONS.md 2026-10-05 (team) + the brief: the owner is the owner admin. Brands "all" = every known brand.
SEED_TEAM = [
    ("guy", "Guy", ["admin"], "all", "he"),
    ("manager", "Manager", ["admin", "user-manager"], "all", "he"),
    ("agent-one", "Agent One", ["agent"], "rozela,velora", "he"),
    ("agent-two", "Agent Two", ["agent"], "celesta,apexmen", "he"),
]


def valid_brands():
    engines, _ = engine_proxy.parse_engines(os.environ.get("ENGINES_JSON", ""))
    extra = [b.strip().lower() for b in os.environ.get("EXTRA_BRANDS", "").split(",") if b.strip()]
    return sorted(set(engine_proxy.KNOWN_BRANDS) | set(engines) | set(extra))


def store_from(args):
    path = args.users or os.environ.get("USERS_PATH", "/var/data/users.json")
    audit = os.environ.get("AUDIT_PATH", os.path.join(os.path.dirname(path), "users-audit.jsonl"))
    return UserStore(path, audit)


def parse_brands(s):
    vb = valid_brands()
    if s.strip().lower() == "all":
        return vb
    return [b.strip().lower() for b in s.split(",") if b.strip()]


def add_user(store, username, name, roles, brands, lang):
    temp = security.temp_password()
    store.create("cli", username, security.hash_password(temp),
                 {"display_name": name or username, "roles": roles, "brands": brands, "lang": lang}, valid_brands())
    return temp


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--users", help="path to users.json (default: $USERS_PATH or /var/data/users.json)")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add-user")
    a.add_argument("username")
    a.add_argument("--roles", required=True, help="comma list: agent, admin, user-manager")
    a.add_argument("--brands", required=True, help='comma list, or "all"')
    a.add_argument("--lang", default="he", choices=["he", "en"])
    a.add_argument("--name", default="")
    for c in ("reset-password", "disable", "enable"):
        sub.add_parser(c).add_argument("username")
    sub.add_parser("list")
    sub.add_parser("seed-team")
    args = p.parse_args(argv)
    store = store_from(args)

    try:
        if args.cmd == "add-user":
            roles = [r.strip() for r in args.roles.split(",") if r.strip()]
            temp = add_user(store, args.username.strip().lower(), args.name, roles, parse_brands(args.brands), args.lang)
            print("created %s\none-time temporary password: %s\n(the user must change it at first sign-in)" % (args.username, temp))
        elif args.cmd == "seed-team":
            for uname, name, roles, brands, lang in SEED_TEAM:
                if store.get(uname):
                    print("%-10s exists — skipped" % uname)
                    continue
                temp = add_user(store, uname, name, roles, parse_brands(brands), lang)
                print("%-10s %-22s %-26s temp password: %s" % (uname, ",".join(roles), ",".join(parse_brands(brands)), temp))
            print("Send each password privately. Each user must change it at first sign-in.")
        elif args.cmd == "reset-password":
            temp = security.temp_password()
            h = security.hash_password(temp)

            def m(rec, _all):
                rec["pw"] = h
                rec["must_change"] = True
            store.update("cli", args.username, m, "password_reset", bump_sv=True)
            print("one-time temporary password for %s: %s" % (args.username, temp))
        elif args.cmd in ("disable", "enable"):
            flag = args.cmd == "disable"

            def m(rec, all_users):
                rec["disabled"] = flag
                if not [n for n, r in all_users.items() if "admin" in r.get("roles", []) and not r.get("disabled")]:
                    raise UserStoreError("last_admin")
            store.update("cli", args.username, m, "user_updated", {"disabled": flag}, bump_sv=True)
            print("%s %sd" % (args.username, args.cmd))
        elif args.cmd == "list":
            for u in store.all():
                print(json.dumps(public_user(u), ensure_ascii=False))
    except UserStoreError as e:
        print("error: %s" % e.code, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
