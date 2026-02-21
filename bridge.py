import os
import traceback
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

try:
    from main import AdaptiveFaissAssistant
    from auto_doc import RepoManualEngine
    print("✅ RETRY Engine: Operational")
except ImportError as e:
    print(f"❌ Dependency Error: {e}")

load_dotenv()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

assistant = AdaptiveFaissAssistant()
book_gen = RepoManualEngine()

class RepoRequest(BaseModel):
    url: str

@app.post("/ingest")
async def ingest_repo(req: RepoRequest):
    try:
        assistant.ingest_repository(req.url)
        repo_name = getattr(assistant, 'current_repo', 'repo_manual')
        return {"status": "success", "repo": repo_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/generate/{repo_name}")
async def get_docs(repo_name: str):
    try:
        book_gen.generate_documentation(repo_name)
        file_path = f"./generated_docs/{repo_name.upper()}_TECHNICAL_SPEC.md"
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            return {"markdown": content}
        return {"error": "File not found"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/graph-data")
async def get_graph_data():
    try:
        with book_gen.driver.session() as session:
            query = "MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 250"
            results = session.run(query)
            elements = []
            nodes_added = set()
            for record in results:
                n, m = record['n'], record['m']
                for node in [n, m]:
                    node_id = str(node.element_id)
                    if node_id not in nodes_added:
                        label_type = list(node.labels)[0] if node.labels else "Default"
                        elements.append({"data": {"id": node_id, "label": node.get('name') or "Node", "type": label_type}})
                        nodes_added.add(node_id)
                elements.append({"data": {"id": f"edge_{record['r'].element_id}", "source": str(n.element_id), "target": str(m.element_id)}})
            return elements
    except Exception:
        return []

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)