#!/usr/bin/env python3
"""Antrekan video ke Buffer (YouTube Shorts dan TikTok) sesuai schedule/schedule.json.

Dijalankan oleh GitHub Actions tiap hari. Aman dijalankan berulang: video yang sudah
masuk antrean Buffer tidak dibuat dua kali.
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEDULE = os.path.join(ROOT, "schedule", "schedule.json")
STATE = os.path.join(ROOT, "schedule", "state.json")
API = os.environ.get("BUFFER_API_URL", "https://api.buffer.com")
KEY = os.environ.get("BUFFER_API_KEY", "")
DRY = os.environ.get("DRY_RUN") == "1"
WAIT_BUDGET = int(os.environ.get("URL_WAIT_SECONDS", "300"))
WAIT_STEP = int(os.environ.get("URL_WAIT_STEP", "30"))
LOG = []


def say(msg):
    print(msg, flush=True)
    LOG.append(msg)


def base_url():
    if os.environ.get("PAGES_BASE_URL"):
        return os.environ["PAGES_BASE_URL"].rstrip("/")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" not in repo:
        sys.exit("PAGES_BASE_URL atau GITHUB_REPOSITORY harus diisi.")
    owner, name = repo.split("/", 1)
    return f"https://{owner.lower()}.github.io/{name}"


def gql(query, variables=None):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(API, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {KEY}",
        "User-Agent": "capyboy-queue/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            out = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read()[:300]!r}")
    if out.get("errors"):
        raise RuntimeError(json.dumps(out["errors"])[:400])
    return out["data"]


def parse_time(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def reachable(url):
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "capyboy-queue/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status == 200
    except Exception:
        return False


def wait_for(url):
    global WAIT_BUDGET
    while True:
        if reachable(url):
            return True
        if WAIT_BUDGET < WAIT_STEP:
            return False
        say(f"  menunggu video muncul di GitHub Pages: {url}")
        time.sleep(WAIT_STEP)
        WAIT_BUDGET -= WAIT_STEP


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_state(state):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)


def existing_scheduled(org):
    seen, after = [], None
    q = """query S($input: PostsInput!, $after: String) {
      posts(first: 100, after: $after, input: $input) {
        edges { node { id dueAt channelId status } }
        pageInfo { hasNextPage endCursor } } }"""
    while True:
        d = gql(q, {"input": {"organizationId": org, "filter": {"status": ["scheduled", "sending"]}}, "after": after})["posts"]
        seen += [e["node"] for e in d["edges"] or []]
        if not d["pageInfo"]["hasNextPage"]:
            return seen
        after = d["pageInfo"]["endCursor"]


def scheduled_limit(org):
    d = gql("query { account { organizations { id limits { scheduledPosts } } } }")
    for o in d["account"]["organizations"]:
        if o["id"] == org:
            return o["limits"]["scheduledPosts"]
    raise RuntimeError("organisasi Buffer tidak ditemukan")


MUT = """mutation C($input: CreatePostInput!) {
  createPost(input: $input) { __typename
    ... on PostActionSuccess { post { id status dueAt } }
    ... on MutationError { message } } }"""


def create(channel, due, text, url, metadata):
    inp = {"channelId": channel, "schedulingType": "automatic", "mode": "customScheduled", "dueAt": due,
           "text": text, "assets": [{"video": {"url": url}}], "metadata": metadata}
    if DRY:
        return "dry-run", None
    r = gql(MUT, {"input": inp})["createPost"]
    if r["__typename"] == "PostActionSuccess":
        return r["post"]["id"], None
    return None, (r["__typename"], r.get("message", ""))


def main():
    if not KEY and not DRY:
        sys.exit("BUFFER_API_KEY belum diisi di GitHub Secrets.")
    cfg = load_json(SCHEDULE, None) or sys.exit("schedule/schedule.json tidak ditemukan.")
    state = load_json(STATE, {"queued": {}})
    state.setdefault("queued", {})
    org, chans = cfg["organization_id"], cfg["channels"]
    start = dt.date.fromisoformat(cfg["start_date"])
    hh, mm = cfg["waktu_tayang"].split(":")
    tz = cfg["zona_waktu_offset"]
    now = dt.datetime.now(dt.timezone.utc)
    horizon = now + dt.timedelta(days=cfg.get("lookahead_hari", 7))
    base = base_url()

    if DRY and not KEY:
        existing, capacity = [], 10
    else:
        existing = existing_scheduled(org)
        capacity = scheduled_limit(org) - len(existing)
    taken = {(p["channelId"], parse_time(p["dueAt"]).timestamp()) for p in existing if p.get("dueAt")}
    say(f"Antrean Buffer saat ini: {len(existing)} terjadwal, sisa kapasitas {capacity}.")

    made = 0
    for p in sorted(cfg["posts"], key=lambda x: x["hari_ke"]):
        day = start + dt.timedelta(days=p["hari_ke"])
        due = f"{day.isoformat()}T{hh}:{mm}:00{tz}"
        t = parse_time(due)
        if t > horizon:
            continue
        if t < now + dt.timedelta(minutes=15):
            if not any(k.startswith(p["id"] + ":") for k in state["queued"]):
                say(f"[{p['id']}] terlewat ({due}). Geser start_date di schedule.json kalau mau tayang ulang.")
            continue
        url = f"{base}/{p['file']}"
        todo = [s for s in ("youtube", "tiktok") if f"{p['id']}:{s}" not in state["queued"]
                and (chans[s], t.timestamp()) not in taken]
        for s in ("youtube", "tiktok"):
            if f"{p['id']}:{s}" not in state["queued"] and s not in todo:
                state["queued"][f"{p['id']}:{s}"] = "sudah-ada-di-buffer"
        if not todo:
            continue
        if capacity < len(todo):
            say(f"[{p['id']}] kapasitas antrean penuh, dicoba lagi besok.")
            break
        if not wait_for(url):
            say(f"[{p['id']}] video belum bisa diunduh: {url}")
            continue
        for s in todo:
            if s == "youtube":
                y = p["youtube"]
                text = y["description"]
                meta = {"youtube": {"title": y["title"], "categoryId": y["categoryId"], "madeForKids": y["madeForKids"],
                                    "privacy": "public", "notifySubscribers": True, "isAiGenerated": False}}
            else:
                text = p["tiktok"]["caption"]
                meta = {"tiktok": {"isAiGenerated": False}}
            post_id, err = create(chans[s], due, text, url, meta)
            if err:
                say(f"[{p['id']}] {s} GAGAL: {err[0]} {err[1]}")
                if err[0] == "LimitReachedError":
                    capacity = 0
                continue
            state["queued"][f"{p['id']}:{s}"] = post_id
            capacity -= 1
            made += 1
            say(f"[{p['id']}] {s} dijadwalkan {due} (id {post_id})")
            save_state(state)
        if capacity <= 0:
            break
    save_state(state)
    say(f"Selesai. {made} postingan baru dijadwalkan.")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("### Antrean Buffer\n\n" + "\n".join(f"- {l}" for l in LOG) + "\n")


if __name__ == "__main__":
    main()
