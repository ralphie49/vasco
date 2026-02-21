import os
import json
import re
from neo4j import GraphDatabase
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=os.getenv("NVIDIA_API_KEY")
)

class RepoManualEngine:
    def __init__(self):
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.output_dir = "./generated_docs"
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def close(self):
        self.driver.close()

    def ask_ai(self, prompt, system_persona="architect", json_mode=False):
        personas = {
            "architect": "You are a Senior Lead Systems Architect. Use assertive, technical, and declarative language. Focus on design patterns and structural integrity. No basic explanations.",
            "writer": "You are a lead technical specification author. Provide high-density technical specifications. Avoid introductory filler."
        }
        
        try:
            response_format = {"type": "json_object"} if json_mode else None
            completion = client.chat.completions.create(
                model="meta/llama-3.1-405b-instruct",
                messages=[
                    {"role": "system", "content": personas.get(system_persona, personas["architect"])},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5, 
                response_format=response_format
            )
            return completion.choices[0].message.content.strip()
        except Exception as e:
            print(f"AI Error: {e}")
            return None

    def get_graph_context(self, repo_name):
        """Extracts metadata using modern Neo4j syntax."""
        with self.driver.session() as session:
            query = """
            MATCH (f:File {repo: $repo_name})
            OPTIONAL MATCH (f)-[:DEFINES]->(item)
            OPTIONAL MATCH (f)-[:DEPENDS_ON]->(dep)
            RETURN f.name AS path, 
                   f.extension AS ext, 
                   collect(DISTINCT item.name) AS symbols,
                   collect(DISTINCT dep.name) AS dependencies,
                   COUNT { (f)-[:DEPENDS_ON]->() } as out_degree,
                   COUNT { (f)<-[:DEPENDS_ON]-() } as in_degree
            """
            return session.run(query, repo_name=repo_name).data()

    def clean_json_response(self, text):
        if not text: return []
        try:
            match = re.search(r'(\[.*\]|\{.*\})', text, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                return data["chapters"] if isinstance(data, dict) and "chapters" in data else data
            return json.loads(text)
        except:
            return []

    def generate_documentation(self, repo_name):
        print(f"📡 Analyzing Graph Topology for {repo_name}...")
        all_metadata = self.get_graph_context(repo_name)
        
        if not all_metadata:
            print(f"❌ No graph data for: {repo_name}")
            return

        sorted_metadata = sorted(all_metadata, key=lambda x: x['in_degree'] + x['out_degree'], reverse=True)
        context_summary = "\n".join([
            f"File: {m['path']} | Connects: {m['in_degree'] + m['out_degree']} | Symbols: {m['symbols'][:5]}"
            for m in sorted_metadata
        ])

        toc_prompt = f"""
        Repository: {repo_name}
        Context: {context_summary}

        TASK:
        Create a 3-chapter Engineering Manual structure.
        - Chapter 1 MUST be 'Architectural Blueprint'.
        - Group remaining files by logical domain.
        
        RETURN ONLY a JSON object:
        {{ "chapters": [ {{ "chapter_num": 1, "title": "Architectural Blueprint", "objective": "Global topology", "focus_files": ["..."] }}, ... ] }}
        """
        
        toc_response = self.ask_ai(toc_prompt, json_mode=True)
        chapters = self.clean_json_response(toc_response)

        full_path = os.path.join(self.output_dir, f"{repo_name.upper()}_TECHNICAL_SPEC.md")
        
        with open(full_path, "w", encoding="utf-8") as doc:
            # 1. BULLEPROOF CSS INJECTION
            doc.write("""<style>
                .page-break { page-break-before: always; }
                .cover-page {
                    text-align: center;
                    padding-top: 250px;
                    padding-bottom: 250px;
                    font-family: sans-serif;
                }
                .repo-title {
                    font-size: 80px;
                    font-weight: 900;
                    margin: 0;
                    color: #1a1a1a;
                    text-transform: uppercase;
                    line-height: 1;
                }
                .repo-subtitle {
                    font-size: 24px;
                    color: #666;
                    margin-top: 10px;
                    letter-spacing: 2px;
                }
                .repo-meta {
                    margin-top: 50px;
                    font-size: 16px;
                    color: #888;
                }
            </style>\n\n""")
            
            # 2. HERO COVER PAGE
            doc.write(f"<div class='cover-page'>\n\n")
            doc.write(f"<h1 class='repo-title'>{repo_name.upper()}</h1>\n")
            doc.write(f"<p class='repo-subtitle'>Engineering Specification & Architectural Manual</p>\n")
            doc.write(f"<div class='repo-meta'>\n")
            doc.write(f"<p>CONFIDENTIAL | INTERNAL ENGINEERING USE ONLY</p>\n")
            doc.write(f"<p>Generated: 2026-02-21</p>\n")
            doc.write(f"</div>\n")
            doc.write(f"</div>\n")

            # 3. CHAPTER LOGIC WITH FORCED PAGE BREAKS
            for chapter in chapters:
                if not isinstance(chapter, dict): continue
                c_num = chapter.get('chapter_num')
                
                # Force every chapter to start on a new page
                doc.write('\n<div class="page-break"></div>\n\n')

                c_title = chapter.get('title')
                c_files = chapter.get('focus_files', [])
                
                print(f"✍️ Compiling Chapter {c_num}: {c_title}...")
                specific_metadata = [m for m in all_metadata if m['path'] in c_files]
                
                if c_num == 1:
                    write_prompt = f"Write Chapter 1: '{c_title}'. Focus on Topology and Orchestration for {repo_name}. Data: {json.dumps(specific_metadata)}"
                else:
                    write_prompt = f"Write Chapter {c_num}: {c_title}. Detailed technical breakdown for {repo_name}. Data: {json.dumps(specific_metadata)}"
                
                chapter_body = self.ask_ai(write_prompt, "architect" if c_num == 1 else "writer")
                doc.write(f"## {c_num}. {c_title}\n\n")
                doc.write(f"{chapter_body}\n\n")

            # 4. APPENDIX & MERMAID GRAPH
            doc.write('\n<div class="page-break"></div>\n\n')
            doc.write("## Appendix: Module Dependency Graph\n\n")
            doc.write("```mermaid\ngraph TD\n")
            for m in all_metadata:
                if m['dependencies']:
                    origin = m['path'].replace(".", "_").replace("/", "_").replace("-","_")
                    for d in m['dependencies'][:2]:
                        target = d.replace(".", "_").replace("/", "_").replace("-","_")
                        doc.write(f"  {origin} --> {target}\n")
            doc.write("```\n")

        print(f"✅ Success: Manual generated at {full_path}")

    def generate_book(self, repo_name):
        return self.generate_documentation(repo_name)

if __name__ == "__main__":
    engine = RepoManualEngine()
    repo = input("Enter repo name: ").strip()
    engine.generate_documentation(repo)
    engine.close()