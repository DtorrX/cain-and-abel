import json

import networkx as nx

from wikinet.family_chart import build_family_chart, export_family_chart


def test_build_family_chart_groups_partnerships_and_children(tmp_path):
    graph = nx.MultiDiGraph()
    graph.add_node("P1", label="Patriarch", family_hierarchy_level=0)
    graph.add_node("P2", label="Matriarch", family_hierarchy_level=0)
    graph.add_node("C1", label="Child One", family_hierarchy_level=1)
    graph.add_node("C2", label="Child Two", family_hierarchy_level=1)

    graph.add_edge("P1", "P2", relation="spouse")
    graph.add_edge("P1", "C1", relation="child")
    graph.add_edge("P2", "C1", relation="child")
    graph.add_edge("P1", "C2", relation="child")

    chart = build_family_chart(graph)

    assert chart["summary"]["people"] == 4
    assert chart["summary"]["families"] == 1
    assert any(edge["type"] == "union_child" for edge in chart["relationships"])

    union = chart["unions"][0]
    assert set(union["partners"]) == {"P1", "P2"}
    assert "C1" in union["children"]
    assert "C2" not in union["children"], "C2 has only one recorded parent"

    # Layout should reflect hierarchy levels
    assert chart["layout"]["P1"]["y"] == 0
    assert chart["layout"]["C1"]["y"] == 1

    # Export writes a JSON file that round-trips cleanly
    path = export_family_chart(graph, tmp_path)
    with open(path, "r", encoding="utf-8") as fh:
        exported = json.load(fh)
    assert exported["summary"]["families"] == 1
