existing = load_existing(MASTER_FILE)

# Build identity set from existing items
seen = set()
for x in existing:
    lk = x["link"].lower().strip().rstrip("/").split("?")[0]
    tt = (x["title"] or "").strip().lower()
    seen.add((lk, tt))

new = []

for url in FEEDS:
    try:
        feed = feedparser.parse(url)

        for entry in feed.entries:
            raw_link = getattr(entry, "link", "") or getattr(entry, "id", "")
            canonical = raw_link.lower().strip().rstrip("/").split("?")[0]

            raw_title = getattr(entry, "title", "") or ""
            normalized_title = raw_title.strip().lower()

            key = (canonical, normalized_title)

            # FINAL duplicate prevention
            if key in seen:
                continue

            seen.add(key)

            clean_title = clean_html(raw_title)
            clean_desc = clean_html(getattr(entry, "summary", ""))

            source = extract_source(canonical)
            final_title = f"{clean_title}. [ {source} ]"

            new.append({
                "title": final_title,
                "link": canonical,
                "description": clean_desc,
                "pubDate": parse_date(entry)
            })

    except Exception as e:
        print(f"Error parsing {url}: {e}")