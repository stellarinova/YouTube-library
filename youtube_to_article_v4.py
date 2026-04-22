import re
import json
import os
import html
from datetime import datetime
from youtube_transcript_api import YouTubeTranscriptApi
from yt_dlp import YoutubeDL
from openai import OpenAI

SEARCH_INDEX_FILE = "search_index.json"
client = OpenAI()

# -----------------------------
# Text cleaning - FIXES � SYMBOLS
# -----------------------------
def normalize_text(s: str) -> str:
    if not isinstance(s, str):
        return s
    replacements = {
        '\u2019': "'", # ’
        '\u2018': "'", # ‘
        '\u201c': '"', # “
        '\u201d': '"', # ”
        '\u2013': '-', # –
        '\u2014': '-', # —
        '\u2026': '...',# …
        '\u00a0': ' ', # nbsp
    }
    for k, v in replacements.items():
        s = s.replace(k, v)
    s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', s)
    return s

def normalize_article(article):
    article['title'] = normalize_text(article.get('title',''))
    article['intro'] = normalize_text(article.get('intro',''))
    for sec in article.get('sections', []):
        sec['heading'] = normalize_text(sec.get('heading',''))
        sec['content'] = normalize_text(sec.get('content',''))
    article['quotes'] = [normalize_text(q) for q in article.get('quotes',[])]
    article['takeaways'] = [normalize_text(t) for t in article.get('takeaways',[])]
    article['keywords'] = [normalize_text(k) for k in article.get('keywords',[])]
    return article

# -----------------------------
# JSON helpers
# -----------------------------
def safe_json_parse(text):
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        raise ValueError("No JSON found")
    json_text = match.group(0).strip()
    json_text = re.sub(r',\s*}', '}', json_text)
    json_text = re.sub(r',\s*]', ']', json_text)
    return json.loads(json_text)

# -----------------------------
# Index helpers
# -----------------------------
def load_search_index():
    if os.path.exists(SEARCH_INDEX_FILE):
        with open(SEARCH_INDEX_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_search_index(index):
    with open(SEARCH_INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

def update_search_index(meta, article_data, filepath):
    index = load_search_index()
    entry = {
        "title": article_data["title"],
        "channel": meta["channel"],
        "date": meta["date"],
        "url": filepath,
        "keywords": article_data.get("keywords", []),
        "summary": article_data.get("intro", "")[:200]
    }
    index.append(entry)
    save_search_index(index)

# -----------------------------
# File helpers
# -----------------------------
def clean_filename(text, max_len=50):
    text = re.sub(r'[\\/*?:"<>|]', "", text)
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[^a-zA-Z0-9_]", "", text)
    return text[:max_len]

def extract_title_keywords(title, max_words=5):
    words = re.findall(r'\w+', title.lower())
    return "_".join(words[:max_words])

def format_yyyymmdd(date_str):
    return date_str[:10].replace("-", "")

def generate_filename(meta):
    channel = clean_filename(meta["channel"])
    date = format_yyyymmdd(meta["date"])
    title_keywords = extract_title_keywords(meta["title"])
    filename = f"{channel}_{date}_{title_keywords}.html"
    folder = channel
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, filename)

# -----------------------------
# YouTube helpers
# -----------------------------
def extract_video_id(url):
    match = re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})", url)
    if match: return match.group(1)
    raise ValueError("Invalid YouTube URL")

def get_metadata(url):
    with YoutubeDL({"quiet": True}) as ydl:
        info = ydl.extract_info(url, download=False)
    return {"title": info.get("title"), "channel": info.get("channel"), "date": info.get("upload_date"), "url": info.get("webpage_url")}

def format_date(date_str):
    return datetime.strptime(date_str, "%Y%m%d").strftime("%B %d, %Y") if date_str else ""

def get_transcript(video_id):
    api = YouTubeTranscriptApi()
    transcript = api.fetch(video_id)
    return " ".join([t.text for t in transcript])

# -----------------------------
# AI analysis - WITH YOUR ORIGINAL RULES RESTORED
# -----------------------------
def analyze_video(title, transcript):
    if len(transcript) > 100000:
        transcript = transcript[:100000] + "\n\n[Transcript truncated due to length]"

    prompt = f"""
You are an expert editor converting a YouTube talk into a clear, engaging article.

Remix this transcript into a magazine-style article.

STRICT RULES:
- Return ONLY valid JSON. Auto Correct if you produce invalid JSON.
- Do NOT include markdown or explanations
- Keep content concise and readable and engaging
- Do NOT include any explanation or text before or after JSON
- Ensure JSON is complete and properly closed

STYLE:
- Engaging like The Atlantic
- Clear and accessible to a general audience
- Explain jargon simply
- Preserve key insights and memorable ideas
- Use 3-5 keywords that capture the essence of the talk
- Each section should have a clear heading and concise content

FORMAT:

{{
"title": "",
"intro": "",

"sections":[
{{
"heading":"",
"content":""
}}
],

"quotes":[
"",
""
],

"takeaways":[
"",
""
],

"keywords":[
"",
"",
""
]
}}

Video title:
{title}

Transcript summary:
{transcript}
"""

    last_text = None
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model="gpt-5",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "You are a JSON API. Output valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                max_completion_tokens=8000
            )
            last_text = response.choices[0].message.content
            return json.loads(last_text)
        except Exception as e:
            print(f"Attempt {attempt+1} failed: {e}")

    if last_text:
        return safe_json_parse(last_text)
    raise RuntimeError("Failed to get response from OpenAI")

# -----------------------------
# HTML generation
# -----------------------------
def generate_html(meta, article):
    channel_slug = clean_filename(meta["channel"])
    nav_html = f"""<div class="nav-top"><a href="../index.html" class="back-home">🏠 Home</a>
<a href="../{channel_slug}/index.html" class="back-home">← Back to Channel</a></div>"""

    sections = "".join([f'<div class="section-card"><h2>{html.escape(s["heading"])}</h2><p>{html.escape(s["content"])}</p></div>' for s in article["sections"]])
    quotes = "".join([f'<div class="quote">{html.escape(q)}</div>' for q in article["quotes"]])
    takeaways = "".join([f"<li>{html.escape(t)}</li>" for t in article["takeaways"]])
    tags = "".join([f'<span class="tag">{html.escape(k)}</span>' for k in article["keywords"]])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(meta['title'])}</title>
<link rel="stylesheet" href="../assets/styles.css">
</head>
<body>
<div class="container">{nav_html}</div>
<div class="hero"><h1>{html.escape(meta['title'])}</h1>
<div class="meta">Channel: {html.escape(meta['channel'])}<br>Published: {format_date(meta['date'])}</div></div>
<div class="intro">{html.escape(article['intro'])}</div>
{sections}
{quotes}
<div class="takeaways"><h2>Key Takeaways</h2><ul>{takeaways}</ul></div>
<div>{tags}</div>
<a class="button" href="{meta['url']}">Watch Full Video</a>
</div>
</body>
</html>"""

def generate_channel_index(channel):
    index = load_search_index()
    articles = [a for a in index if a["channel"] == channel]
    nav_html = '<div class="nav-top"><a href="../index.html" class="back-home">🏠 Back to Home</a></div>'
    articles_html = "".join([f"""<div class="article"><a href="../{a['url']}"><h3>{html.escape(a['title'])}</h3></a><div class="meta">{a['date']}</div><p>{html.escape(a['summary'])}</p></div>""" for a in sorted(articles, key=lambda x: x["date"], reverse=True)])
    html_out = f"""<html><head><meta charset="UTF-8"><title>{html.escape(channel)}</title><style>body{{font-family:Inter,sans-serif;background:#f7f9fc;}}.container{{max-width:700px;margin:auto;padding:40px;}}</style></head><body><div class="container">{nav_html}<h1>{html.escape(channel)}</h1>{articles_html}</div></body></html>"""
    folder = clean_filename(channel)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_out)

def generate_tag_pages():
    index = load_search_index()
    tag_map = {}
    for article in index:
        for tag in article.get("keywords", []):
            tag_map.setdefault(tag, []).append(article)
    os.makedirs("tags", exist_ok=True)
    nav_html = '<div class="nav-top"><a href="../index.html" class="back-home">🏠 Back to Home</a></div>'
    for tag, articles in tag_map.items():
        items = "".join([f"""<div class="article"><a href="../{a['url']}"><h3>{html.escape(a['title'])}</h3></a><div class="meta">{html.escape(a['channel'])} • {a['date']}</div></div>""" for a in articles])
        html_out = f"""<html><head><meta charset="UTF-8"><title>{html.escape(tag)}</title></head><body><div class="container">{nav_html}<h1>Tag: {html.escape(tag)}</h1>{items}</div></body></html>"""
        with open(f"tags/{clean_filename(tag)}.html", "w", encoding="utf-8") as f:
            f.write(html_out)

# -----------------------------
# Main
# -----------------------------
def main():
    url = input("Enter YouTube video URL: ").strip()
    print("Fetching video metadata...")
    meta = get_metadata(url)
    video_id = extract_video_id(url)

    print("Downloading transcript...")
    transcript = get_transcript(video_id)
    print(f"Transcript length: {len(transcript)} chars")

    print("Analyzing video with AI...")
    article_data = analyze_video(meta["title"], transcript)
    article_data = normalize_article(article_data) # clean smart quotes

    print("Generating HTML article...")
    html_out = generate_html(meta, article_data)
    filename = generate_filename(meta)

    with open(filename, "w", encoding="utf-8") as f:
        f.write(html_out)

    update_search_index(meta, article_data, filename)
    generate_channel_index(meta["channel"])
    generate_tag_pages()

    print(f"\nDone! Open {filename} in your browser.")

if __name__ == "__main__":
    main()