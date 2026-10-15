from app.crawler.parser import parse_page


def test_parser_does_not_duplicate_paragraphs_inside_list_items():
    _title, content = parse_page(
        "<html><body><ul><li><p>First item</p></li></ul></body></html>"
    )

    assert content.splitlines() == ["First item"]
