# load_to_neo4j.py
import json
from tqdm import tqdm
from graph import create_constraints, upsert_node, create_relationship
import config

DATA_FILE = "vietnam_travel_dataset.json"

def main():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        nodes = json.load(f)

    # Create constraints
    create_constraints()

    # Upsert all nodes
    for node in tqdm(nodes, desc="Creating nodes"):
        upsert_node(node)

    # Create relationships
    for node in tqdm(nodes, desc="Creating relationships"):
        conns = node.get("connections", [])
        for rel in conns:
            create_relationship(node["id"], rel)

    print("Done loading into Neo4j.")

if __name__ == "__main__":
    main()
