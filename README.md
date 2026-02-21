uv add requirements.txt
set nvidia key
uv run python main.py
that's it!

MATCH (n)
DETACH DELETE n

MATCH (n)-[r:DEPENDS_ON]->(m)
RETURN n, r, m

