from curses import meta
import re
import json
from datetime import datetime
from youtube_transcript_api import YouTubeTranscriptApi
from yt_dlp import YoutubeDL
from openai import OpenAI

import json
import os

SEARCH_INDEX_FILE = "search_index.json"


import json
import re

def safe_json_parse(text):

    # Extract JSON block
    match = re.search(r'\{.*\}', text, re.DOTALL)

    if not match:
        raise ValueError("No JSON found in AI response")

    json_text = match.group(0)

    # Try normal parse first
    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        pass

    # 🔥 Attempt auto-fix (very important)
    json_text = json_text.strip()

    # Fix common truncation issues
    json_text = re.sub(r',\s*}', '}', json_text)
    json_text = re.sub(r',\s*]', ']', json_text)

    # Try again
    try:
        return json.loads(json_text)
    except json.JSONDecodeError as e:
        print("\n--- RAW AI RESPONSE (truncated) ---\n")
        print(text[:2000])
        print("\n----------------------------------\n")
        raise e

def load_search_index():
    if os.path.exists(SEARCH_INDEX_FILE):
        with open(SEARCH_INDEX_FILE, "r") as f:
            return json.load(f)
    return []


def save_search_index(index):
    with open(SEARCH_INDEX_FILE, "w") as f:
        json.dump(index, f, indent=2)


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
    
def generate_channel_index(channel):

    index = load_search_index()

    articles = [a for a in index if a["channel"] == channel]

    articles_html = ""

    for a in sorted(articles, key=lambda x: x["date"], reverse=True):
        articles_html += f"""
        <div class="article">
            <a href="../{a['url']}">
                <h3>{a['title']}</h3>
            </a>
            <div class="meta">{a['date']}</div>
            <p>{a['summary']}</p>
        </div>
        """

    html = f"""
<html>
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">

<title>{channel}</title>

<style>
body {{ font-family: Inter, sans-serif; background:#f7f9fc; }}
.container {{ max-width:700px; margin:auto; padding:40px; }}
.article {{ margin-bottom:30px; }}
.article h3 {{ margin:0; color:#2b6cb0; }}
.meta {{ font-size:13px; color:#777; margin-bottom:10px; }}
</style>

</head>

<body>

<div class="container">
<h1>{channel}</h1>
{articles_html}
</div>

</body>
</html>
"""

    folder = clean_filename(channel)
    os.makedirs(folder, exist_ok=True)

    with open(os.path.join(folder, "index.html"), "w") as f:
        f.write(html)
        
        
def generate_tag_pages():

    index = load_search_index()
    tag_map = {}

    # Group by tag
    for article in index:
        for tag in article.get("keywords", []):
            tag_map.setdefault(tag, []).append(article)

    os.makedirs("tags", exist_ok=True)

    for tag, articles in tag_map.items():

        items = ""

        for a in articles:
            items += f"""
            <div class="article">
                <a href="../{a['url']}">
                    <h3>{a['title']}</h3>
                </a>
                <div class="meta">{a['channel']} • {a['date']}</div>
            </div>
            """

        html = f"""
<html>
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">

<title>{tag}</title>

<style>
body {{ font-family: Inter, sans-serif; background:#f7f9fc; }}
.container {{ max-width:700px; margin:auto; padding:40px; }}
.article {{ margin-bottom:25px; }}
.article h3 {{ margin:0; color:#2b6cb0; }}
</style>

</head>

<body>

<div class="container">
<h1>Tag: {tag}</h1>
{items}
</div>

</body>
</html>
"""

        filename = f"tags/{clean_filename(tag)}.html"

        with open(filename, "w") as f:
            f.write(html)
            
            

    

import re

def clean_filename(text, max_len=50):
    # Remove invalid characters
    text = re.sub(r'[\\/*?:"<>|]', "", text)

    # Replace spaces with underscore
    text = re.sub(r"\s+", "_", text)

    # Keep only safe characters
    text = re.sub(r"[^a-zA-Z0-9_]", "", text)

    return text[:max_len]


def extract_title_keywords(title, max_words=5):
    words = re.findall(r'\w+', title.lower())
    keywords = "_".join(words[:max_words])
    return keywords


def format_yyyymmdd(date_str):
    # expects YYYYMMDD or ISO format
    return date_str[:10].replace("-", "")

import os

def generate_filename(meta):

    channel = clean_filename(meta["channel"])
    date = format_yyyymmdd(meta["date"])
    title_keywords = extract_title_keywords(meta["title"])

    filename = f"{channel}_{date}_{title_keywords}.html"

    # Optional: create folder per channel
    folder = channel
    os.makedirs(folder, exist_ok=True)

    return os.path.join(folder, filename)





client = OpenAI()


# -----------------------------
# Extract YouTube Video ID
# -----------------------------
def extract_video_id(url):

    match = re.search(r"v=([a-zA-Z0-9_-]+)", url)

    if match:
        return match.group(1)

    raise ValueError("Invalid YouTube URL")


# -----------------------------
# Get Video Metadata
# -----------------------------
def get_metadata(url):

    with YoutubeDL({"quiet": True}) as ydl:
        info = ydl.extract_info(url, download=False)

    return {
        "title": info.get("title"),
        "channel": info.get("channel"),
        "date": info.get("upload_date"),
        "url": info.get("webpage_url")
    }


# -----------------------------
# Format Date
# -----------------------------
def format_date(date_str):

    if not date_str:
        return ""

    return datetime.strptime(date_str, "%Y%m%d").strftime("%B %d, %Y")


# -----------------------------
# Download Transcript
# -----------------------------
def get_transcript(video_id):

    api = YouTubeTranscriptApi()

    transcript = api.fetch(video_id)

    text = " ".join([t.text for t in transcript])

    return text


# -----------------------------
# Analyze Video Using AI
# -----------------------------
def analyze_video(title, transcript):

    prompt = f"""
You are an expert editor converting a YouTube talk into a clear, engaging article.

Remix this transcript into a magazine-style article.

STRICT RULES:
- Return ONLY valid JSON
- Do NOT include markdown or explanations
- Keep content concise and readable and engaging
- Limit each section to 1–2 short paragraphs
- Do NOT include any explanation or text before or after JSON
- Ensure JSON is complete and properly closed

STYLE:
- Engaging like The Atlantic
- Clear and accessible to a general audience
- Explain jargon simply
- Preserve key insights and memorable ideas

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

    response = client.responses.create(
        model="gpt-5",
        input=prompt,
        max_output_tokens=3000
    )

    text = response.output_text

    try:
#        data = json.loads(text)
        data = safe_json_parse(text)
    except:
        print("AI output was not valid JSON. Printing raw response.")
        print(text)
        raise

    return data


# -----------------------------
# Generate Professional HTML
# -----------------------------

def generate_html(meta, article_data):

    date = format_date(meta["date"])

    # -----------------------------
    # Scripture Cards
    # -----------------------------
    verse_html = ""

    if "verses" in article_data:
        for v in article_data["verses"]:
            verse_html += f"""
            <div class="scripture-card">
                <div class="scripture-ref">{v['reference']}</div>
                <div class="scripture-text">"{v['text']}"</div>
            </div>
            """

    verse_section = ""
    if verse_html:
        verse_section = f"""
        <div class="verse-section">
            <h3 class="verse-title">Scripture Highlights</h3>
            {verse_html}
        </div>
        """

    # -----------------------------
    # Sections
    # -----------------------------
    sections_html = ""

    for s in article_data["sections"]:
        sections_html += f"""
        <section class="section">
            <h2>{s['heading']}</h2>
            <p>{s['content'].replace("\\n","<br><br>")}</p>
        </section>
        """

    # -----------------------------
    # Quotes
    # -----------------------------
    quotes_html = ""

    if "quotes" in article_data:
        for q in article_data["quotes"]:
            quotes_html += f"""
            <blockquote class="quote">
                {q}
            </blockquote>
            """

    # -----------------------------
    # Takeaways
    # -----------------------------
    takeaways_html = ""

    if "takeaways" in article_data:
        for t in article_data["takeaways"]:
            takeaways_html += f"<li>{t}</li>"

    # -----------------------------
    # Keywords
    # -----------------------------
    keywords_html = ""

    if "keywords" in article_data:
        keywords_html = "".join(
            [f'<span class="tag">{k}</span>' for k in article_data["keywords"]]
        )

    # -----------------------------
    # HTML
    # -----------------------------
    html = f"""
<!DOCTYPE html>
<html>

<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{meta['title']}</title>

<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">

<style>

/* -------- Base -------- */

body {{
    margin:0;
    background:#f7f9fc;
    font-family: Inter, system-ui, sans-serif;
    color:#2d3748;
}}

/* -------- Container -------- */

.container {{
    max-width:680px;
    margin:60px auto;
    padding:0 20px;
}}

/* -------- Header -------- */

.header {{
    text-align:center;
    margin-bottom:50px;
}}

.header h1 {{
    font-size:34px;
    line-height:1.3;
    margin-bottom:20px;
}}

.meta {{
    font-size:14px;
    color:#718096;
    line-height:1.8;
}}

/* -------- Intro -------- */

.intro {{
    font-size:20px;
    line-height:1.9;
    margin-bottom:40px;
    color:#4a5568;
}}

/* -------- Divider -------- */

.divider {{
    height:1px;
    background:#e2e8f0;
    margin:50px 0;
}}

/* -------- Scripture -------- */

.verse-title {{
    font-size:18px;
    margin-bottom:10px;
    color:#2b6cb0;
}}

.scripture-card {{
    background:#f9fafb;
    border-left:3px solid #c05621;
    padding:20px 22px;
    margin:20px 0;
    border-radius:8px;
}}

.scripture-ref {{
    font-size:13px;
    font-weight:700;
    letter-spacing:0.5px;
    color:#c05621;
    margin-bottom:10px;
    text-transform:uppercase;
}}

.scripture-text {{
    font-size:18px;
    line-height:1.9;
    font-style:italic;
}}

/* -------- Sections -------- */

.section {{
    margin-bottom:45px;
}}

.section h2 {{
    font-size:22px;
    margin-bottom:15px;
    color:#2b6cb0;
}}

.section p {{
    font-size:18px;
    line-height:2;
}}

/* -------- Quotes -------- */

.quote {{
    border-left:4px solid #ed8936;
    padding-left:20px;
    margin:40px 0;
    font-style:italic;
    color:#4a5568;
    font-size:18px;
    line-height:2;
}}

/* -------- Takeaways -------- */

.takeaways {{
    margin-top:50px;
}}

.takeaways h3 {{
    font-size:20px;
    margin-bottom:20px;
}}

.takeaways ul {{
    padding-left:20px;
}}

.takeaways li {{
    margin-bottom:14px;
    line-height:1.8;
    font-size:17px;
}}

/* -------- Tags -------- */

.tags {{
    margin-top:50px;
}}

.tag {{
    display:inline-block;
    background:#edf2f7;
    padding:6px 12px;
    margin:5px;
    border-radius:16px;
    font-size:13px;
}}

/* -------- Button -------- */

.button {{
    display:block;
    text-align:center;
    margin:50px auto;
    padding:14px 28px;
    background:#ed8936;
    color:white;
    text-decoration:none;
    border-radius:25px;
    width:220px;
    font-weight:600;
}}

/* -------- Footer -------- */

.footer {{
    text-align:center;
    font-size:13px;
    color:#a0aec0;
    margin-top:60px;
}}

@media screen and (max-width: 600px) {

  body {
    font-size: 18px;   /* base font bigger */
  }

  .container {
    padding: 20px 15px;
  }

  h1 {
    font-size: 26px;
  }

  h2 {
    font-size: 22px;
  }

  h3 {
    font-size: 20px;
  }

  .intro {
    font-size: 19px;
    line-height: 1.8;
  }

  .section-card p {
    font-size: 18px;
    line-height: 1.9;
  }

  .quote {
    font-size: 18px;
    line-height: 1.9;
    padding: 20px;
  }

  .takeaways li {
    font-size: 18px;
    line-height: 1.8;
  }

  .meta {
    font-size: 14px;
  }

  .search {
    font-size: 16px;
    padding: 14px;
  }

  /* NAV menu spacing */
  .menu {
    gap: 12px;
  }

  .menu-item {
    font-size: 16px;
  }

}

p {
  line-height: 1.8;
  margin-bottom: 18px;
}

body {
  font-size: clamp(16px, 1.2vw, 18px);
}

.nav-top {
  margin-bottom: 20px;
}

.back-home {
  display:inline-block;
  text-decoration:none;
  font-size:14px;
  color:#2b6cb0;
  background:#edf2f7;
  padding:8px 14px;
  border-radius:20px;
  transition:all 0.2s ease;
}

.back-home:hover {
  background:#e2e8f0;
}

</style>

</head>

<body>
back_button = """
<div class="nav-top">
  <a href="/" class="back-home">← Back to Home</a>
</div>
"""

<div class="container">
{back_button}

<div class="header">
    <h1>{meta['title']}</h1>

    <div class="meta">
        {meta['channel']} &bull;{date}<br>
    </div>
</div>

<div class="intro">
{article_data["intro"]}
</div>

{verse_section}

<div class="divider"></div>

{sections_html}

{quotes_html}

<div class="divider"></div>

<div class="takeaways">
    <h3>Key Takeaways</h3>
    <ul>
        {takeaways_html}
    </ul>
</div>

<div class="tags">
    {keywords_html}
</div>

<a class="button" href="{meta['url']}">Watch Full Video</a>

bottom_nav = """
<div style="text-align:center; margin-top:50px;">
  <a href="/" class="back-home">← Back to Home</a>
</div>
"""

<div class="footer">
    Generated from a YouTube talk • Designed for calm reading
</div>

</div>

</body>
</html>
"""

    return html
# -----------------------------
# Main Program
# -----------------------------
def main():

    url = input("Enter YouTube video URL: ")

    print("Fetching video metadata...")
    meta = get_metadata(url)

    video_id = extract_video_id(url)

    print("Downloading transcript...")
    transcript = get_transcript(video_id)

    print("Analyzing video with AI...")
    article_data = analyze_video(meta["title"], transcript)

    print("Generating HTML article...")
    html = generate_html(meta, article_data)

    filename = generate_filename(meta)

    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)
    
    
    # NEW FEATURES
    update_search_index(meta, article_data, filename)
    generate_channel_index(meta["channel"])
    generate_tag_pages()

    
    
    print(f"\nDone! Open {filename} in your browser.")


if __name__ == "__main__":
    main()