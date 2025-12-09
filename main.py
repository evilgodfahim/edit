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
from email.utils import parsedate_to_datetime

# -----------------------------
# CONFIGURATION
# -----------------------------
FEEDS = [
    "https://politepol.com/fd/pzVBxx3Z2fUI.xml",
    "https://politepol.com/fd/vIzuCnimE1YU.xml",
    "https://politepol.com/fd/QAIWwDi3wOuZ.xml",
    "https://politepol.com/fd/LONi4mJ2tfbd.xml",
    "https://evilgodfahim.github.io/rss-combo-NA/feed.xml",
    "https://politepol.com/fd/2XdgObSDG4FD.xml",
    "https://politepol.com/fd/xaIRlDYPW0kP.xml",
    "https://politepol.com/fd/LwUmZUwUaj7i.xml",
    "https://politepol.com/fd/Uh7pOg6WWCMR.xml",
    "https://politepol.com/fd/GxmRWljxfGEo.xml",
    "https://politepol.com/fd/oT0YgLtnGzze.xml",
    "https://politepol.com/fd/ggpXf4wO5uEz.xml",
    "https://politepol.com/fd/OAVNbKjejtJQ.xml",
    "https://politepol.com/fd/CnOMC37mGwul.xml",
    "https://politepol.com/fd/qVPraFDG1MNh.xml",
    "https://politepol.com/fd/vF2VjeDKWjUw.xml",
    "https://politepol.com/fd/v4jixX1PsBB9.xml",
    "https://politepol.com/fd/NxM7X35BsyKv.xml",
    "https://politepol.com/fd/qJzBCq1mQyIq.xml",
    "https://politepol.com/fd/d3vTXXWIpQfi.xml",
    "https://politepol.com/fd/gXwt22exG6r5.xml",
    "https://politepol.com/fd/wUSywgW7UoCL.xml",
    "https://politepol.com/fd/a18TrHXs0awo.xml",
    "https://politepol.com/fd/nqB5lyvhHzWI.xml",
    "https://evilgodfahim.github.io/ds/articles.xml",
    "https://politepol.com/fd/8R6kYL0taEqD.xml",
    "https://evilgodfahim.github.io/fedit/feed.xml"
]

MASTER_FILE = "feed_master.xml"
DAILY_FILE = "daily_feed.xml"
SEEN_FILE = "seen_ids.json"

MAX_ITEMS = 500
MAX_SEEN_HISTORY = 2000

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
    # feedparser entries may be dict-like or object-like
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
    title = entry.get("title", "") if isinstance(entry, dict) else getattr(entry, "title", "")
    published = entry.get("published", "") if isinstance(entry, dict) else getattr(entry, "published", "")
    unique_string = f"{title}{published}"
    return hashlib.md5(unique_string.encode('utf-8')).hexdigest()

def parse_date(entry):
    """
    Robust parse: try structured times, RFC dates, then fallback to now (UTC).
    Returns timezone-aware datetime in UTC.
    """
    # 1) structured parsed tuples
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

    # 2) string fields via parsedate_to_datetime
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

    # 3) fallback to now (UTC) — important to avoid epoch dates for missing values
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
# XML OPERATIONS
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
                link_node = it.find("link")
                desc_node = it.find("description")
                pub_node = it.find("pubDate")
                guid_node = it.find("guid")

                title = title_node.text.strip() if title_node is not None and title_node.text else ""
                link = link_node.text.strip() if link_node is not None and link_node.text else ""
                desc = desc_node.text if desc_node is not None and desc_node.text else ""
                guid = guid_node.text.strip() if guid_node is not None and guid_node.text else link or ""

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

                # normalize microseconds away
                dt = dt.replace(microsecond=0)

                items.append({
                    "title": title,
                    "link": link,
                    "description": desc,
                    "pubDate": dt,
                    "id": guid
                })
            except Exception:
                continue
        return items
    except Exception:
        return []

def write_rss(items, path, title="Feed"):
    rss = ET.Element("rss", version="2.0")
    ch = ET.SubElement(rss, "channel")
    ET.SubElement(ch, "title").text = title
    ET.SubElement(ch, "link").text = "https://evilgodfahim.github.io/"
    ET.SubElement(ch, "description").text = f"{title} generated by script"

    for it in items:
        node = ET.SubElement(ch, "item")
        ET.SubElement(node, "title").text = it.get("title", "")
        ET.SubElement(node, "link").text = it.get("link", "")
        ET.SubElement(node, "description").text = it.get("description", "")
        pub_dt = it.get("pubDate")
        if isinstance(pub_dt, datetime):
            # ensure tz-aware
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
# HASH-BASED UNIQUE TIMESTAMPS
# -----------------------------
def adjust_duplicate_timestamps(items):
    """
    Adjusts timestamps using hash-based offsets for deterministic, stable uniqueness.
    Articles with duplicate timestamps get a consistent offset based on their link hash.
    Ensures:
    - timestamps normalized to UTC and seconds precision
    - deterministic offsets per link
    - final global uniqueness (increment by 1 second when hash-collisions occur)
    """
    from collections import defaultdict

    # Normalize all timestamps: ensure timezone-aware UTC and remove microseconds
    for item in items:
        dt = item.get("pubDate")
        if not isinstance(dt, datetime):
            try:
                # attempt to coerce various types, otherwise set now
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

    # Group items by their normalized timestamp
    timestamp_groups = defaultdict(list)
    for item in items:
        timestamp_groups[item["pubDate"]].append(item)

    # First pass: propose offsets for groups with multiple items
    for original_dt, group in timestamp_groups.items():
        if len(group) > 1:
            group.sort(key=lambda x: x.get("link", "") or x.get("id", ""))
            for item in group:
                link_val = (item.get("link") or item.get("id") or "")
                # Deterministic offset from link hash in range 0..299 seconds
                link_hash = hashlib.md5(link_val.encode('utf-8')).hexdigest()
                offset_seconds = int(link_hash[:8], 16) % 300
                item["_proposed_dt"] = original_dt + timedelta(seconds=offset_seconds)
        else:
            group[0]["_proposed_dt"] = original_dt

    # Second pass: ensure global uniqueness by bumping collisions by +1 second as needed
    used = set()
    all_items = list(items)
    all_items.sort(key=lambda x: (x.get("_proposed_dt", x["pubDate"]), x.get("link", "") or x.get("id", "")))

    for itm in all_items:
        prop = itm.get("_proposed_dt", itm["pubDate"])
        if prop.tzinfo is None:
            prop = prop.replace(tzinfo=timezone.utc)
        prop = prop.replace(microsecond=0).astimezone(timezone.utc)

        while prop in used:
            prop = prop + timedelta(seconds=1)
        used.add(prop)
        itm["pubDate"] = prop
        if "_proposed_dt" in itm:
            del itm["_proposed_dt"]

    return items

# -----------------------------
# LOGIC: MASTER FEED
# -----------------------------
def update_master():
    existing = load_existing(MASTER_FILE)
    seen_ids = {x["id"] for x in existing}
    new_items = []

    for url in FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                try:
                    entry_id = get_unique_id(entry)
                    if entry_id not in seen_ids:
                        link = entry.get("link") if isinstance(entry, dict) else getattr(entry, "link", "")
                        raw_title = entry.get("title") if isinstance(entry, dict) else getattr(entry, "title", "No Title")
                        raw_desc = entry.get("summary") if isinstance(entry, dict) else getattr(entry, "summary", "")
                        clean_title = clean_html(raw_title)
                        clean_desc = clean_html(raw_desc)
                        source = extract_source(link)
                        final_title = f"{clean_title}. [ {source} ]"
                        new_items.append({
                            "title": final_title,
                            "link": link,
                            "description": clean_desc,
                            "pubDate": parse_date(entry),
                            "id": entry_id
                        })
                        seen_ids.add(entry_id)
                except Exception:
                    continue
        except Exception:
            continue

    all_items = existing + new_items

    # Apply hash-based timestamp adjustments to ensure uniqueness
    all_items = adjust_duplicate_timestamps(all_items)

    # Sort by timestamp (newest first) AFTER adjustment
    all_items.sort(key=lambda x: x["pubDate"], reverse=True)
    all_items = all_items[:MAX_ITEMS]

    if not all_items:
        all_items = [{
            "title": "No articles yet",
            "link": "https://evilgodfahim.github.io/",
            "description": "Master feed will populate after first successful fetch.",
            "pubDate": datetime.now(timezone.utc).replace(microsecond=0),
            "id": "init_1"
        }]

    write_rss(all_items, MASTER_FILE, "Master Feed (Updated every 30 mins)")

# -----------------------------
# LOGIC: DAILY FEED
# -----------------------------
def update_daily():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                history_ids = set(data.get("seen_ids", []))
        except Exception:
            history_ids = set()
    else:
        history_ids = set()

    master = load_existing(MASTER_FILE)
    master.sort(key=lambda x: x["pubDate"], reverse=True)

    daily_items = []
    for it in master:
        if it["id"] not in history_ids:
            it["title"] = clean_html(it["title"])
            it["description"] = clean_html(it["description"])
            daily_items.append(it)
            history_ids.add(it["id"])

    if not daily_items:
        daily_items = [{
            "title": "No new articles right now",
            "link": "https://evilgodfahim.github.io/",
            "description": "Check back later.",
            "pubDate": datetime.now(timezone.utc).replace(microsecond=0),
            "id": f"msg_{int(datetime.now(timezone.utc).timestamp())}"
        }]

    write_rss(daily_items, DAILY_FILE, "Daily Feed (New Items Only)")

    # Persist only the most recent seen IDs (order not guaranteed due to set -> list)
    updated_history = list(history_ids)[-MAX_SEEN_HISTORY:]
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump({"seen_ids": updated_history}, f)
    except Exception:
        pass

# -----------------------------
# MAIN
# -----------------------------
if __name__ == "__main__":
    args = sys.argv[1:]
    if "--master-only" in args:
        update_master()
    elif "--daily-only" in args:
        update_daily()
    else:
        update_master()
        update_daily()