from duckduckgo_search import DDGS


def search_web(query):
    """
    Perform a live web search using DuckDuckGo.
    Returns a list of relevant text snippets.
    Falls back gracefully if the search fails.
    """
    try:
        results = []

        with DDGS() as ddgs:

            search_results = ddgs.text(query, max_results=5)

            for r in search_results:

                results.append(r["body"])

        return results

    except Exception as e:
        print(f"[WEB SEARCH ERROR] {e}")
        return []