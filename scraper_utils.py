from bs4 import BeautifulSoup

def extract_variants_from_versions_table(soup: BeautifulSoup):
    results = []
    tables = soup.select("table.wikitable")
    
    for table in tables:
        headers = [th.get_text(strip=True) for th in table.select("tr th")]
        if not headers or len(headers) < 2:
            continue  # skip malformed tables

        rows = table.select("tr")[1:]  # skip header row
        rowspan_map = {}

        for row in rows:
            cells = row.find_all(["td", "th"])
            values = []
            i = 0
            while i < len(headers):
                if i in rowspan_map:
                    values.append(rowspan_map[i]["value"])
                    rowspan_map[i]["rows_left"] -= 1
                    if rowspan_map[i]["rows_left"] == 0:
                        del rowspan_map[i]
                    i += 1
                    continue

                if not cells:
                    values.append("")
                    i += 1
                    continue

                cell = cells.pop(0)
                cell_text = cell.get_text(strip=True)
                rowspan = int(cell.get("rowspan", "1"))

                values.append(cell_text)
                if rowspan > 1:
                    rowspan_map[i] = {"value": cell_text, "rows_left": rowspan - 1}
                i += 1

            result = dict(zip(headers, values))
            results.append(result)

    return results