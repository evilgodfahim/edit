#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import feedparser
import os
import sys
from datetime import datetime, timezone, timedelta
import xml.etree.ElementTree as ET
from xml.dom import minidom
import json
import hashlib
import re
import requests
from email.utils import parsedate_to_datetime

# -----------------------------
# CONFIGURATION
# -----------------------------
FEEDS = [
    "https://politepaul.com/fd/pzVBxx3Z2fUI.xml",
    "https://evilgodfahim.github.io/fen/fe_editorial_views.xml",
    "https://evilgodfahim.github.io/laqa/feeds/feed.xml",
    "https://evilgodfahim.github.io/obd/feeds/observer_editorial.xml",
    "https://evilgodfahim.github.io/obd/feeds/observer_opinion.xml",
    "https://politepaul.com/fd/NrEWP2V2AGVT.xml",
    "https://politepaul.com/fd/lZysXjRwAlVQ.xml",
    "https://politepaul.com/fd/ekwvBiJQh6be.xml",
    "https://evilgodfahim.github.io/dt/opinion.xml",
    "https://evilgodfahim.github.io/bd24/feeds/feed.xml",
    "https://evilgodfahim.github.io/dsop/feeds/feed.xml",
    "https://evilgodfahim.github.io/Latest/result.xml",
    "https://politepaul.com/fd/vIzuCnimE1YU.xml",
    "https://politepaul.com/fd/QAIWwDi3wOuZ.xml",
    "https://politepaul.com/fd/LONi4mJ2tfbd.xml",
    "https://evilgodfahim.github.io/rss-combo-NA/feed.xml",
    "https://politepaul.com/fd/2XdgObSDG4FD.xml",
    "https://politepaul.com/fd/xaIRlDYPW0kP.xml",
    "https://politepaul.com/fd/LwUmZUwUaj7i.xml",
    "https://politepaul.com/fd/Uh7pOg6WWCMR.xml",
    "https://politepaul.com/fd/GxmRWljxfGEo.xml",
    "https://politepaul.com/fd/oT0YgLtnGzze.xml",
    "https://politepaul.com/fd/ggpXf4wO5uEz.xml",
    "https://politepaul.com/fd/OAVNbKjejtJQ.xml",
    "https://politepaul.com/fd/CnOMC37mGwul.xml",
    "https://politepaul.com/fd/qVPraFDG1MNh.xml",
    "https://politepaul.com/fd/vF2VjeDKWjUw.xml",
    "https://politepaul.com/fd/v4jixX1PsBB9.xml",
    "https://politepaul.com/fd/NxM7X35BsyKv.xml",
    "https://politepaul.com/fd/qJzBCq1mQyIq.xml",
    "https://politepaul.com/fd/d3vTXXWIpQfi.xml",
    "https://politepaul.com/fd/gXwt22exG6r5.xml",
    "https://politepaul.com/fd/wUSywgW7UoCL.xml",
    "https://politepaul.com/fd/a18TrHXs0awo.xml",
    "https://politepaul.com/fd/nqB5lyvhHzWI.xml",
    "https://evilgodfahim.github.io/ds/opinion.xml",
    "https://evilgodfahim.github.io/ds/editorial.xml",
    "https://politepaul.com/fd/8R6kYL0taEqD.xml",
    "https://evilgodfahim.github.io/fedit/feed.xml",
    "https://politepaul.com/fd/wjvHK2ovRT07.xml",
    "https://politepaul.com/fd/xgP8bvJjusuL.xml",
    "https://politepaul.com/fd/7InJTyJ6DJEW.xml",
    "https://politepaul.com/fd/aHOZhCiCh6Td.xml",
    "https://evilgodfahim.github.io/ds/deep_dive.xml",
    "https://evilgodfahim.github.io/tbs/thoughts.xml",
]

MASTER_FILE         = "feed_master.xml"
DAILY_FILE          = "daily_feed.xml"
SEEN_FILE           = "seen_ids.json"
SOURCES_FILE        = "sources.txt"
EMPTY_FILE          = "empty_feeds.xml"

MAX_ITEMS           = 5000
SEEN_RETENTION_DAYS = 365
FETCH_TIMEOUT       = 15  # seconds per feed

# -----------------------------
# SEEN-IDS HELPERS
# -----------------------------

def load_seen():
    """
    Returns (history_ids: set, history_dict: dict[id -> iso_str]).
    Migrates old list format. Drops entries older than SEEN_RETENTION_DAYS.
    """
    if not os.path.exists(SEEN_FILE):
        return set(), {}
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=SEEN_RETENTION_DAYS)).isoformat()
        raw = data.get("seen_ids", [])
        if isinstance(raw, list):
            now_iso = datetime.now(timezone.utc).isoformat()
            history = {id_: now_iso for id_ in raw}
        else:
            history = {id_: ts for id_, ts in raw.items() if ts >= cutoff}
        return set(history.keys()), history
    except Exception:
        return set(), {}


def save_seen(history: dict):
    """Prune to SEEN_RETENTION_DAYS and persist."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=SEEN_RETENTION_DAYS)).isoformat()
    pruned = {id_: ts for id_, ts in history.items() if ts >= cutoff}
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump({"seen_ids": pruned}, f, indent=2)
    except Exception:
        pass


# -----------------------------
# UTILITIES
# -----------------------------

def clean_html(text):
    if not text:
        return ""
    text = text.replace("≪span class=\"color-red\"≫", "")
    text = text.replace("≪/span≫", "")
    return text


def get_unique_id(entry):
    try:
        eid = entry.get("id") if isinstance(entry, dict) else getattr(entry, "id", None)
    except Exception:
        eid = None
    if eid:
        return str(eid)
    try:
        link = entry.get("link") if isinstance(entry, dict) else getattr(entry, "link", None)
    except Exception:
        link = None
    if link:
        return str(link)
    title     = entry.get("title", "")     if isinstance(entry, dict) else getattr(entry, "title", "")
    published = entry.get("published", "") if isinstance(entry, dict) else getattr(entry, "published", "")
    return hashlib.md5(f"{title}{published}".encode("utf-8")).hexdigest()


def parse_date(entry):
    for field in ("published_parsed", "updated_parsed", "created_parsed"):
        try:
            t = entry.get(field) if isinstance(entry, dict) else getattr(entry, field, None)
        except Exception:
            t = None
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    for key in ("published", "updated", "pubDate", "created"):
        try:
            val = entry.get(key) if isinstance(entry, dict) else getattr(entry, key, None)
        except Exception:
            val = None
        if val:
            try:
                dt = parsedate_to_datetime(val)
                if dt is None:
                    continue
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except Exception:
                continue
    return datetime.now(timezone.utc)


def extract_source(link):
    try:
        if not link:
            return "unknown"
        host = link.split("/")[2].lower().replace("www.", "")
        return host.split(".")[0]
    except Exception:
        return "unknown"


# -----------------------------
# FEED FETCHER
# -----------------------------

def fetch_feed(url, timeout=FETCH_TIMEOUT):
    """
    Fetch via requests (real timeout + real HTTP errors), then parse with feedparser.

    Returns (raw_bytes, feed, warn_str | None).
      raw_bytes: response body — pass to parse_custom_xml to avoid a second HTTP hit.
      feed:      feedparser result, or None on hard failure / total parse failure.
      warn:      human-readable problem description, or None on full success.

    Callers should skip the URL when raw_bytes is None (hard network/HTTP failure).
    When feed is None but raw_bytes is not, try parse_custom_xml(raw_bytes).
    When feed is not None but feed.entries is empty, also try parse_custom_xml(raw_bytes).
    """
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; feedparser/6.0)",
                "Accept": "application/rss+xml, application/atom+xml, text/xml, */*",
            },
            allow_redirects=True,
        )
    except requests.exceptions.Timeout:
        return None, None, f"timeout after {timeout}s"
    except requests.exceptions.ConnectionError as e:
        return None, None, f"connection error: {e}"
    except requests.exceptions.RequestException as e:
        return None, None, f"request error: {e}"

    if resp.status_code >= 400:
        return None, None, f"HTTP {resp.status_code}"

    raw = resp.content

    # Pass bytes — lets feedparser sniff encoding from XML declaration / BOM
    feed = feedparser.parse(raw)

    if feed.bozo:
        exc = getattr(feed, "bozo_exception", "unknown")
        if not feed.entries:
            # Total feedparser failure — raw bytes still usable for custom parser
            return raw, None, f"malformed XML, 0 entries recoverable: {exc}"
        # Partial parse — still worth using
        return raw, feed, f"malformed XML, {len(feed.entries)} entries recovered: {exc}"

    return raw, feed, None


# -----------------------------
# CUSTOM XML PARSER
# Accepts already-fetched bytes OR a URL string (fallback, causes a second fetch).
# Handles two schemas:
#   1. Custom <article><url><snippet><published>
#   2. Standard RSS <item><link><description><pubDate><guid>
# -----------------------------

def parse_custom_xml(url_or_bytes):
    """
    Fallback parser for when feedparser returns no entries.
    Pass raw bytes (from fetch_feed) to avoid a second HTTP round-trip.
    A URL string is also accepted for standalone use (e.g. --empty-only).
    """
    if isinstance(url_or_bytes, bytes):
        raw = url_or_bytes
    else:
        try:
            resp = requests.get(
                url_or_bytes,
                timeout=FETCH_TIMEOUT,
                headers={"User-Agent": "Mozilla/5.0 (compatible; feedparser/6.0)"},
                allow_redirects=True,
            )
            if resp.status_code >= 400:
                return []
            raw = resp.content
        except Exception:
            return []

    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []

    # ── Schema 1: custom <article> format ─────────────────────────────────
    articles = root.findall(".//article")
    if articles:
        items = []
        for article in articles:
            try:
                def text(tag, _el=article):
                    node = _el.find(tag)
                    return (node.text or "").strip() if node is not None else ""

                title    = text("title") or "No Title"
                link     = text("url")
                desc     = text("snippet")
                pub_text = text("published")

                if pub_text:
                    try:
                        dt = parsedate_to_datetime(pub_text)
                        if dt is None:
                            raise ValueError
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        dt = dt.astimezone(timezone.utc)
                    except Exception:
                        dt = datetime.now(timezone.utc)
                else:
                    dt = datetime.now(timezone.utc)

                entry_id = hashlib.md5(
                    f"{title}{link}{desc[:80]}".encode("utf-8")
                ).hexdigest()

                items.append({
                    "title":       title,
                    "link":        link,
                    "description": desc,
                    "pubDate":     dt.replace(microsecond=0),
                    "id":          entry_id,
                })
            except Exception:
                continue
        return items

    # ── Schema 2: standard RSS <item> format ──────────────────────────────
    rss_items = root.findall(".//item")
    if not rss_items:
        return []

    items = []
    for rss_item in rss_items:
        try:
            def text(tag, _el=rss_item):
                node = _el.find(tag)
                return (node.text or "").strip() if node is not None else ""

            title    = text("title") or "No Title"
            link     = text("link")
            desc     = text("description")
            pub_text = text("pubDate")
            guid     = text("guid") or link

            if pub_text:
                try:
                    dt = parsedate_to_datetime(pub_text)
                    if dt is None:
                        raise ValueError
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    dt = dt.astimezone(timezone.utc)
                except Exception:
                    dt = datetime.now(timezone.utc)
            else:
                dt = datetime.now(timezone.utc)

            entry_id = guid or hashlib.md5(
                f"{title}{link}".encode("utf-8")
            ).hexdigest()

            items.append({
                "title":       title,
                "link":        link,
                "description": desc,
                "pubDate":     dt.replace(microsecond=0),
                "id":          entry_id,
            })
        except Exception:
            continue

    return items


# -----------------------------
# XML HELPERS
# -----------------------------

def load_existing(path):
    if not os.path.exists(path):
        return []
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        items = []
        for it in root.findall(".//item"):
            try:
                title_node = it.find("title")
                link_node  = it.find("link")
                desc_node  = it.find("description")
                pub_node   = it.find("pubDate")
                guid_node  = it.find("guid")
                title = title_node.text.strip() if title_node is not None and title_node.text else ""
                link  = link_node.text.strip()  if link_node  is not None and link_node.text  else ""
                desc  = desc_node.text          if desc_node  is not None and desc_node.text  else ""
                guid  = guid_node.text.strip()  if guid_node  is not None and guid_node.text  else link or ""
                pub_text = pub_node.text.strip() if pub_node is not None and pub_node.text else None
                if pub_text:
                    try:
                        dt = parsedate_to_datetime(pub_text)
                        if dt is None:
                            dt = datetime.now(timezone.utc)
                        elif dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        dt = dt.astimezone(timezone.utc)
                    except Exception:
                        try:
                            dt = datetime.strptime(pub_text, "%a, %d %b %Y %H:%M:%S %z")
                        except Exception:
                            dt = datetime.now(timezone.utc)
                else:
                    dt = datetime.now(timezone.utc)
                dt = dt.replace(microsecond=0)
                items.append({
                    "title":       title,
                    "link":        link,
                    "description": desc,
                    "pubDate":     dt,
                    "id":          guid,
                })
            except Exception:
                continue
        return items
    except Exception:
        return []


def write_rss(items, path, title="Feed"):
    rss = ET.Element("rss", version="2.0")
    ch  = ET.SubElement(rss, "channel")
    ET.SubElement(ch, "title").text       = title
    ET.SubElement(ch, "link").text        = "https://evilgodfahim.github.io/"
    ET.SubElement(ch, "description").text = f"{title} generated by script"
    for it in items:
        node = ET.SubElement(ch, "item")
        ET.SubElement(node, "title").text       = it.get("title", "")
        ET.SubElement(node, "link").text        = it.get("link", "")
        ET.SubElement(node, "description").text = it.get("description", "")
        pub_dt = it.get("pubDate")
        if isinstance(pub_dt, datetime):
            try:
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                pub_text = pub_dt.strftime("%a, %d %b %Y %H:%M:%S %z")
            except Exception:
                pub_text = pub_dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
        else:
            pub_text = str(pub_dt)
        ET.SubElement(node, "pubDate").text = pub_text
        guid = ET.SubElement(node, "guid")
        guid.text = it.get("id", it.get("link", ""))
        guid.set("isPermaLink", "false")
    xml_str = minidom.parseString(ET.tostring(rss)).toprettyxml(indent="  ")
    with open(path, "w", encoding="utf-8") as f:
        f.write(xml_str)


# -----------------------------
# HASH DEDUP
# -----------------------------

def adjust_duplicate_timestamps(items):
    from collections import defaultdict
    for item in items:
        dt = item.get("pubDate")
        if not isinstance(dt, datetime):
            try:
                dt = parsedate_to_datetime(str(dt))
                if dt is None:
                    raise ValueError
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dt = dt.astimezone(timezone.utc)
            except Exception:
                dt = datetime.now(timezone.utc)
        else:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                try:
                    dt = dt.astimezone(timezone.utc)
                except Exception:
                    dt = dt.replace(tzinfo=timezone.utc)
        item["pubDate"] = dt.replace(microsecond=0)

    timestamp_groups = defaultdict(list)
    for item in items:
        timestamp_groups[item["pubDate"]].append(item)

    for original_dt, group in timestamp_groups.items():
        if len(group) > 1:
            group.sort(key=lambda x: x.get("link", "") or x.get("id", ""))
            for item in group:
                link_val  = (item.get("link") or item.get("id") or "")
                link_hash = hashlib.md5(link_val.encode("utf-8")).hexdigest()
                offset    = int(link_hash[:8], 16) % 300
                item["_proposed_dt"] = original_dt + timedelta(seconds=offset)
        else:
            group[0]["_proposed_dt"] = original_dt

    used      = set()
    all_items = list(items)
    all_items.sort(key=lambda x: (x.get("_proposed_dt", x["pubDate"]), x.get("link", "") or x.get("id", "")))
    for itm in all_items:
        prop = itm.get("_proposed_dt", itm["pubDate"])
        if prop.tzinfo is None:
            prop = prop.replace(tzinfo=timezone.utc)
        prop = prop.replace(microsecond=0).astimezone(timezone.utc)
        while prop in used:
            prop += timedelta(seconds=1)
        used.add(prop)
        itm["pubDate"] = prop
        itm.pop("_proposed_dt", None)

    return items


# -----------------------------
# LOGIC: MASTER FEED
# -----------------------------

def update_master():
    print("[Updating feed_master.xml]")

    existing = load_existing(MASTER_FILE)
    seen_ids = {x["id"] for x in existing}
    new_items     = []
    empty_reports = []

    ok_count = warn_count = skip_count = 0

    for url in FEEDS:
        raw, feed, warn = fetch_feed(url)

        # Hard network/HTTP failure — nothing to work with
        if raw is None:
            skip_count += 1
            print(f"  [SKIP] {url}")
            print(f"         {warn}")
            empty_reports.append({
                "title":       f"Fetch failed: {url}",
                "link":        url,
                "description": warn or "Unknown error",
                "pubDate":     datetime.now(timezone.utc).replace(microsecond=0),
                "id":          f"fail_{hashlib.md5(url.encode()).hexdigest()}",
            })
            continue

        if warn:
            warn_count += 1
            print(f"  [WARN] {url}")
            print(f"         {warn}")
        else:
            ok_count += 1

        entries = feed.entries if feed is not None else []

        # No feedparser entries — try custom XML using already-fetched bytes
        if not entries:
            custom = parse_custom_xml(raw)
            if custom:
                added = 0
                for item in custom:
                    if item["id"] not in seen_ids:
                        source        = extract_source(item["link"] or url)
                        item["title"] = f"{clean_html(item['title'])}. [ {source} ]"
                        item["description"] = clean_html(item["description"])
                        new_items.append(item)
                        seen_ids.add(item["id"])
                        added += 1
                print(
                    f"  [CUSTOM] {url}\n"
                    f"           entries=0 (feedparser)  custom={len(custom)}  new={added}"
                )
            else:
                print(f"  [EMPTY] {url}\n          entries=0  custom=0")
                empty_reports.append({
                    "title":       f"Empty feed: {url}",
                    "link":        url,
                    "description": "No articles in feedparser or custom XML format.",
                    "pubDate":     datetime.now(timezone.utc).replace(microsecond=0),
                    "id":          f"empty_{hashlib.md5(url.encode()).hexdigest()}",
                })
            continue

        # Normal feedparser path
        added = skipped_dup = 0
        for entry in entries:
            try:
                entry_id = get_unique_id(entry)
                if entry_id in seen_ids:
                    skipped_dup += 1
                    continue
                link      = entry.get("link")    if isinstance(entry, dict) else getattr(entry, "link",    "")
                raw_title = entry.get("title")   if isinstance(entry, dict) else getattr(entry, "title",   "No Title")
                raw_desc  = entry.get("summary") if isinstance(entry, dict) else getattr(entry, "summary", "")
                source    = extract_source(link)
                new_items.append({
                    "title":       f"{clean_html(raw_title)}. [ {source} ]",
                    "link":        link,
                    "description": clean_html(raw_desc),
                    "pubDate":     parse_date(entry),
                    "id":          entry_id,
                })
                seen_ids.add(entry_id)
                added += 1
            except Exception:
                continue

        print(
            f"  [OK]   {url}\n"
            f"         entries={len(entries)}  new={added}  dup={skipped_dup}"
        )

    print(
        f"\n  feeds: {ok_count} ok / {warn_count} warn / {skip_count} skipped"
        f" / {len(FEEDS)} total"
    )

    all_items = existing + new_items
    all_items = adjust_duplicate_timestamps(all_items)
    all_items.sort(key=lambda x: x["pubDate"], reverse=True)
    all_items = all_items[:MAX_ITEMS]

    if not all_items:
        all_items = [{
            "title":       "No articles yet",
            "link":        "https://evilgodfahim.github.io/",
            "description": "Master feed will populate after first successful fetch.",
            "pubDate":     datetime.now(timezone.utc).replace(microsecond=0),
            "id":          "init_1",
        }]

    write_rss(all_items, MASTER_FILE, "Master Feed (Updated every 30 mins)")
    write_rss(empty_reports, EMPTY_FILE, "Empty Feeds Report")
    print(f"✓ feed_master.xml updated with {len(all_items)} items ({len(new_items)} new)")
    print(f"✓ empty_feeds.xml written with {len(empty_reports)} entries")


# -----------------------------
# LOGIC: DAILY
# -----------------------------

def update_daily():
    print("[Updating daily_feed.xml]")

    history_ids, history = load_seen()
    master = load_existing(MASTER_FILE)
    master.sort(key=lambda x: x["pubDate"], reverse=True)

    now_iso     = datetime.now(timezone.utc).isoformat()
    daily_items = []
    for it in master:
        if it["id"] not in history_ids:
            it["title"]       = clean_html(it["title"])
            it["description"] = clean_html(it["description"])
            daily_items.append(it)
            history[it["id"]] = now_iso

    if not daily_items:
        daily_items = [{
            "title":       "No new articles right now",
            "link":        "https://evilgodfahim.github.io/",
            "description": "Check back later.",
            "pubDate":     datetime.now(timezone.utc).replace(microsecond=0),
            "id":          f"msg_{int(datetime.now(timezone.utc).timestamp())}",
        }]

    write_rss(daily_items, DAILY_FILE, "Daily Feed (New Items Only)")
    save_seen(history)

    sources = set()
    for item in daily_items:
        m = re.search(r'\[\s*(.+?)\s*\]', item.get("title", ""))
        if m:
            sources.add(m.group(1).strip())
    with open(SOURCES_FILE, "w", encoding="utf-8") as f:
        for src in sorted(sources):
            f.write(src + "\n")
    print(f"✓ sources.txt written with {len(sources)} unique sources")


# -----------------------------
# EMPTY FEED REPORT
# -----------------------------

def update_empty_feeds():
    print("[Scanning for empty feeds]")

    reports  = []
    ok_count = skip_count = empty_count = 0

    for url in FEEDS:
        raw, feed, warn = fetch_feed(url)

        if raw is None:
            skip_count += 1
            print(f"  [SKIP] {url}  —  {warn}")
            reports.append({
                "title":       f"Fetch failed: {url}",
                "link":        url,
                "description": warn or "Unknown error",
                "pubDate":     datetime.now(timezone.utc).replace(microsecond=0),
                "id":          f"fail_{hashlib.md5(url.encode()).hexdigest()}",
            })
            continue

        entries = feed.entries if feed is not None else []

        if not entries:
            custom = parse_custom_xml(raw)  # reuse fetched bytes — no second request
            if not custom:
                empty_count += 1
                print(f"  [EMPTY] {url}")
                reports.append({
                    "title":       f"Empty feed: {url}",
                    "link":        url,
                    "description": "No articles in feedparser or custom XML format.",
                    "pubDate":     datetime.now(timezone.utc).replace(microsecond=0),
                    "id":          f"empty_{hashlib.md5(url.encode()).hexdigest()}",
                })
            else:
                ok_count += 1
                print(f"  [CUSTOM-OK] {url}  —  {len(custom)} items via custom parser")
        else:
            ok_count += 1

    write_rss(reports, EMPTY_FILE, "Empty Feeds Report")
    print(
        f"\n  scan: {ok_count} ok / {empty_count} empty / {skip_count} unreachable"
        f" / {len(FEEDS)} total"
    )
    print(f"✓ empty_feeds.xml written with {len(reports)} entries")


# -----------------------------
# MAIN
# -----------------------------

if __name__ == "__main__":
    args = sys.argv[1:]
    if "--master-only" in args:
        update_master()
    elif "--daily-only" in args:
        update_daily()
    elif "--empty-only" in args:
        update_empty_feeds()
    else:
        update_master()
        update_daily()
        update_empty_feeds()
