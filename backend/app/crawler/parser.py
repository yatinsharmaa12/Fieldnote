from bs4 import BeautifulSoup


def parse_page(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")

    for element in soup(["script", "style", "nav", "footer", "header"]):
        element.decompose()

    title = soup.title.get_text(strip=True) if soup.title else ""

    content_lines = []

    for element in soup.find_all(
        ["h1", "h2", "h3", "p", "li"]
    ):
        # A list item's text already includes paragraphs nested inside it.
        if element.name == "p" and element.find_parent("li") is not None:
            continue
        text = element.get_text(" ", strip=True)

        if not text:
            continue

        if element.name == "h1":
            text = f"# {text}"
        elif element.name == "h2":
            text = f"## {text}"
        elif element.name == "h3":
            text = f"### {text}"

        content_lines.append(text)

    content = "\n".join(content_lines)
    if not content.strip():
        # Fallback: return plain text stripped from HTML when no structured elements
        content = soup.get_text(strip=True)
    return title, content
