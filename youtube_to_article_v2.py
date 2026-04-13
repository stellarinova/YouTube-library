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
def generate_html(meta, article):

    return f"""
<!DOCTYPE html>
<html lang="en">

<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<title>{meta['title']}</title>

<link rel="stylesheet" href="../assets/styles.css">

</head>

<body>

<div class="container">

<div class="nav-top">
<a href="../index.html" class="back-home">Back to Home</a>
</div>

<div class="hero">
<h1>{meta['title']}</h1>

<div class="meta">
Channel: {meta['channel']}<br>
Published: {meta['date']}
</div>
</div>

<div class="intro">
{article['intro']}
</div>

{"".join([f'''
<div class="section-card">
<h2>{s["heading"]}</h2>
<p>{s["content"]}</p>
</div>
''' for s in article["sections"]])}

{"".join([f'''
<div class="scripture-box">
<div class="ref">{v["reference"]}</div>
<blockquote>{v["text"]}</blockquote>
</div>
''' for v in article.get("verses", [])])}

{"".join([f'<div class="quote">{q}</div>' for q in article["quotes"]])}

<div class="takeaways">
<h2>Key Takeaways</h2>
<ul>
{"".join([f"<li>{t}</li>" for t in article["takeaways"]])}
</ul>
</div>

<div>
{"".join([f'<span class="tag">{k}</span>' for k in article["keywords"]])}
</div>

<a class="button" href="{meta['url']}">Watch Full Video</a>

</div>

</body>
</html>
"""


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