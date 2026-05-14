"""HTML page rendering for the simple demo frontend."""

from html import escape


def render_search_page(version: str, search_path: str, heading: str) -> str:
    """Render a minimal search page."""
    safe_version = escape(version)
    safe_path = escape(search_path)
    safe_heading = escape(heading)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_heading}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 32px; line-height: 1.6; }}
    main {{ max-width: 880px; margin: 0 auto; }}
    input {{ width: min(620px, 70vw); padding: 8px 10px; }}
    button {{ padding: 8px 14px; }}
    article {{ border-top: 1px solid #ddd; padding: 14px 0; }}
    .score {{ color: #666; font-size: 0.9rem; }}
  </style>
</head>
<body>
  <main>
    <h1>{safe_heading}</h1>
    <form id="search-form" action="{safe_path}">
      <input name="q" placeholder="输入 On-Call 问题或关键词" autofocus>
      <button type="submit">搜索</button>
    </form>
    <section id="results"></section>
  </main>
  <script>
    const form = document.querySelector("#search-form");
    const results = document.querySelector("#results");
    form.addEventListener("submit", async (event) => {{
      event.preventDefault();
      const query = new FormData(form).get("q") || "";
      const response = await fetch("{safe_path}?q=" + encodeURIComponent(query));
      const payload = await response.json();
      results.innerHTML = payload.results.map((item) => `
        <article>
          <h2>${{item.title}}</h2>
          <p>${{item.snippet}}</p>
          <p class="score">{safe_version} · ${{item.id}} · score=${{item.score}}</p>
        </article>
      `).join("") || "<p>没有结果</p>";
    }});
  </script>
</body>
</html>"""
