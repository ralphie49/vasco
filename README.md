uv add requirements.txt
set nvidia key

MATCH (n)
DETACH DELETE n

MATCH (n)-[r]->(m)
RETURN n, r, m

uv run python main.py
