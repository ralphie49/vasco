import os
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

def check_neo():
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    pw = os.getenv("NEO4J_PASSWORD")
    
    try:
        driver = GraphDatabase.driver(uri, auth=(user, pw))
        driver.verify_connectivity()
        print("🔗 VS Code -> Neo4j: CONNECTION SUCCESSFUL")
    except Exception as e:
        print(f"❌ CONNECTION FAILED: {e}")

if __name__ == "__main__":
    check_neo()