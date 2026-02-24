1. pip install unicorn
uv add -r requirements.txt
uv add fastapi
-----------------------------------
2. Install neo4j for desktop, create instance and connect it to this project.
3. Set nvidia key in .env file
4. Set neo4j password in .env file

# Neo4j Connection Details
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=

NVIDIA_API_KEY=
-----------------------
5. uv add fastapi
6. uv run python bridge.py (to run project on browser)
7. If you want to check dependency graph of a repo after ingestion run this in neo4j query

MATCH (n)-[r]->(m)
RETURN n, r, m

