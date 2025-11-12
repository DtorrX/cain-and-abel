# file: wikinet_min.py
import argparse, os, json, time, pathlib, subprocess
from typing import Dict, List, Tuple, Iterable
import requests
import networkx as nx

WDQS = "https://query.wikidata.org/sparql"
WIKI_API = "https://{lang}.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "wikinet/0.1 (research; contact unavailable)"}

FAMILY_PROPS = {
    "P22": "father",
    "P25": "mother",
    "P26": "spouse",
    "P40": "child",
    "P3373": "sibling",
    "P1038": "relative",
    "P451": "partner",
}
POLITICAL_PROPS = {
    "P39": "position_held",
    "P102": "member_of_party",
    "P463": "member_of_org",
    "P108": "employer",
    "P69": "educated_at",
    "P6": "head_of_government",
    "P35": "head_of_state",
    "P488": "chairperson",
    "P2388": "officeholder",
}

def _req_json(url, params=None, method="GET", headers=None, retries=3, sleep=0.5):
    headers = headers or HEADERS
    for i in range(retries):
        r = requests.request(method, url, params=params, headers=headers, timeout=30)
        if r.status_code in (200, 304):
            return r.json()
        if r.status_code in (429, 502, 503, 504):
            time.sleep(sleep * (2 ** i))
            continue
        r.raise_for_status()
    r.raise_for_status()

def resolve_title_to_qid(title: str, lang="en") -> str:
    """Resolve a Wikipedia page title to a Wikidata Q-ID."""
    data = _req_json(
        WIKI_API.format(lang=lang),
        {
            "action": "query",
            "prop": "pageprops",
            "ppprop": "wikibase_item",
            "titles": title,
            "format": "json",
        },
    )
    pages = data.get("query", {}).get("pages", {})
    for _, p in pages.items():
        qid = p.get("pageprops", {}).get("wikibase_item")
        if qid:
            return qid
    raise ValueError(f"Could not resolve Q-ID for '{title}'")

def resolve_category_members(category: str, lang="en", limit=200) -> List[str]:
    """Return page titles under a category."""
    titles = []
    cmtitle = f"Category:{category}"
    cont = None
    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": cmtitle,
            "cmlimit": min(50, limit),
            "format": "json",
            "cmnamespace": 0,
        }
        if cont:
            params.update(cont)
        data = _req_json(WIKI_API.format(lang=lang), params)
        cms = data.get("query", {}).get("categorymembers", [])
        for m in cms:
            titles.append(m["title"])
            if len(titles) >= limit:
                return titles
        cont = data.get("continue")
        if not cont:
            return titles

def wd_sparql(q: str) -> Dict:
    return _req_json(
        WDQS,
        params={"query": q, "format": "json"},
        headers={**HEADERS, "Accept": "application/sparql-results+json"},
    )

def batch_family_political_relations(qids: List[str]) -> List[Dict]:
    """Fetch family & political edges for a batch of Q-IDs."""
    prop_ids = list(FAMILY_PROPS.keys()) + list(POLITICAL_PROPS.keys())
    values = " ".join(f"(wd:{qid})" for qid in qids)
    props = " ".join(f"wdt:{p}" for p in prop_ids)
    query = f"""
    SELECT ?src ?p ?dst ?srcLabel ?dstLabel WHERE {{
      VALUES (?src) {{ {values} }}
      VALUES ?p {{ { ' '.join('wdt:'+p for p in prop_ids) } }}
      OPTIONAL {{ ?src ?p ?dst . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    """
    res = wd_sparql(query)
    rows = res.get("results", {}).get("bindings", [])
    out = []
    for b in rows:
        if "dst" not in b:  # not all props bound
            continue
        src = b["src"]["value"].split("/")[-1]
        dst = b["dst"]["value"].split("/")[-1]
        p_full = b["p"]["value"]
        pid = p_full.split("/")[-1]
        out.append(
            {
                "src": src,
                "dst": dst,
                "pid": pid,
                "relation": FAMILY_PROPS.get(pid, POLITICAL_PROPS.get(pid, pid)),
                "src_label": b.get("srcLabel", {}).get("value"),
                "dst_label": b.get("dstLabel", {}).get("value"),
                "source_system": "wikidata",
            }
        )
    return out

def ensure_labels(qids: Iterable[str]) -> Dict[str, str]:
    values = " ".join(f"(wd:{qid})" for qid in set(qids))
    q = f"""
    SELECT ?q ?qLabel WHERE {{
      VALUES (?q) {{ {values} }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    """
    res = wd_sparql(q)
    labels = {}
    for b in res.get("results", {}).get("bindings", []):
        qid = b["q"]["value"].split("/")[-1]
        labels[qid] = b.get("qLabel", {}).get("value", qid)
    return labels

def build_graph(seeds: List[str], lang="en", max_depth=1, treat_seeds_as_titles=True):
    # Resolve seeds to Q-IDs
    frontier = []
    for s in seeds:
        if s.startswith("Q"):
            frontier.append(s)
        else:
            frontier.append(resolve_title_to_qid(s, lang=lang))
    G = nx.MultiDiGraph()
    seen = set(frontier)
    depth = 0
    while frontier and depth <= max_depth:
        batch = frontier[:50]
        frontier = frontier[50:]
        edges = batch_family_political_relations(batch)
        qids = set()
        for e in edges:
            qids.add(e["src"]); qids.add(e["dst"])
        labels = ensure_labels(qids)
        for q in qids:
            G.add_node(q, label=labels.get(q, q))
        for e in edges:
            G.add_edge(
                e["src"], e["dst"],
                relation=e["relation"], pid=e["pid"], source=e["source_system"]
            )
        # frontier expansion = the dsts we haven't seen yet
        new_qs = [e["dst"] for e in edges if e["dst"] not in seen]
        for q in new_qs:
            seen.add(q); frontier.append(q)
        depth += 1
    return G

def export_all(G: nx.Graph, outdir: str):
    os.makedirs(outdir, exist_ok=True)
    # JSON
    nodes = [{"id": n, **G.nodes[n]} for n in G.nodes]
    edges = [{"u": u, "v": v, **d} for u, v, d in G.edges(data=True)]
    with open(os.path.join(outdir, "nodes.json"), "w") as f:
        json.dump(nodes, f, indent=2)
    with open(os.path.join(outdir, "edges.json"), "w") as f:
        json.dump(edges, f, indent=2)
    # GraphML
    nx.write_graphml(G, os.path.join(outdir, "graph.graphml"))
    # DOT
    try:
        from networkx.drawing.nx_pydot import write_dot
        write_dot(G, os.path.join(outdir, "graph.dot"))
        # Try PNG via Graphviz if installed
        dot = os.path.join(outdir, "graph.dot")
        png = os.path.join(outdir, "graph.png")
        try:
            subprocess.run(["dot", "-Tpng", dot, "-o", png], check=True)
        except Exception:
            pass
    except Exception:
        pass

def main():
    ap = argparse.ArgumentParser(description="Wikidata/Wikipedia network crawler (minimal)")
    ap.add_argument("--seed", action="append", help="Seed page title or Q-ID (repeatable)")
    ap.add_argument("--category", help="Wikipedia Category (without 'Category:')")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--max-depth", type=int, default=1)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    seeds = args.seed or []
    if args.category:
        seeds.extend(resolve_category_members(args.category, lang=args.lang, limit=200))
    if not seeds:
        raise SystemExit("Provide --seed and/or --category")

    G = build_graph(seeds, lang=args.lang, max_depth=args.max_depth)
    export_all(G, args.out)
    print(f"Done. Nodes={G.number_of_nodes()} Edges={G.number_of_edges()} → {args.out}")

if __name__ == "__main__":
    main()
