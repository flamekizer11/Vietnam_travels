# graph.py
"""Simple Neo4j helpers.

Contains functions to fetch neighbors and upsert nodes/relationships.
"""

from typing import List, Dict, Any
from neo4j import GraphDatabase
import config

# sync driver used by the CLI and scripts
driver = GraphDatabase.driver(
    config.NEO4J_URI, auth=(config.NEO4J_USER, config.NEO4J_PASSWORD)
)


def fetch_graph_context(node_ids: List[str]) -> List[Dict[str, Any]]:
    """Return 1- and 2-hop neighbors for the given node ids."""
    facts = []
    with driver.session() as session:
        # Use UNWIND for efficient batch query, include 2-hop
        query = (
            "UNWIND $node_ids AS nid "
            "MATCH (n:Entity {id: nid})-[r]-(m:Entity) "
            "OPTIONAL MATCH (m)-[r2]-(o:Entity) WHERE o <> n "
            "RETURN type(r) AS rel, labels(m) AS labels, m.id AS id, "
            "m.name AS name, m.type AS type, m.description AS description, "
            "type(r2) AS rel2, labels(o) AS labels2, o.id AS id2, "
            "o.name AS name2, o.type AS type2, o.description AS description2 "
            "LIMIT 100"
        )
        recs = session.run(query, node_ids=node_ids)
        for r in recs:
            # 1-hop fact
            facts.append({
                "source": None,
                "rel": r["rel"],
                "target_id": r["id"],
                "target_name": r["name"],
                "target_desc": (r["description"] or "")[:400],
                "labels": r["labels"]
            })
            # 2-hop fact if exists
            if r["rel2"]:
                facts.append({
                    "source": r["id"],  # From the 1-hop node
                    "rel": r["rel2"],
                    "target_id": r["id2"],
                    "target_name": r["name2"],
                    "target_desc": (r["description2"] or "")[:400],
                    "labels": r["labels2"]
                })
    return facts[:50]  # Limit to 50 total

def create_constraints():
    """Create required Neo4j uniqueness constraint."""
    with driver.session() as session:
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE")

def upsert_node(node: Dict[str, Any]):
    """Merge a node into the graph (id is unique)."""
    labels = [node.get("type", "Unknown"), "Entity"]
    label_cypher = ":" + ":".join(labels)
    props = {k: v for k, v in node.items() if k not in ("connections",)}
    with driver.session() as session:
        session.run(
            f"MERGE (n{label_cypher} {{id: $id}}) SET n += $props",
            id=node["id"], props=props
        )

def create_relationship(source_id: str, rel: Dict[str, Any]):
    """Create a relationship from source to target (if target provided)."""
    rel_type = rel.get("relation", "RELATED_TO")
    target_id = rel.get("target")
    if not target_id:
        return
    with driver.session() as session:
        cypher = (
            "MATCH (a:Entity {id: $source_id}), (b:Entity {id: $target_id}) "
            f"MERGE (a)-[r:{rel_type}]->(b) "
            "RETURN r"
        )
        session.run(cypher, source_id=source_id, target_id=target_id)


def fetch_graph_context_async_wrapper(node_ids: List[str]):
    """Run async fetcher from sync code (uses asyncio.run)."""
    import asyncio
    from async_graph import fetch_graph_context_async

    return asyncio.run(fetch_graph_context_async(node_ids))


def fetch_graph_context_via_runner(node_ids: List[str]):
    """Submit the async fetch to the background runner and wait for result."""
    from async_graph import submit_fetch_graph

    return submit_fetch_graph(node_ids)