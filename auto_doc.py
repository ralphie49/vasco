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
            "architect": "You are a Senior Lead Systems Architect. Use assertive, technical, and declarative language. Focus on design patterns. Avoid introductory filler.",
            "writer": "You are a lead technical specification author. Provide high-density technical specifications. Use tables and lists."
        }
        
        try:
            response_format = {"type": "json_object"} if json_mode else None
            completion = client.chat.completions.create(
                model="meta/llama-3.1-405b-instruct",
                messages=[
                    {"role": "system", "content": personas.get(system_persona, personas["architect"])},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7, 
                response_format=response_format
            )
            return completion.choices[0].message.content.strip()
        except Exception as e:
            print(f"AI Error: {e}")
            return None

    def get_graph_context(self, repo_name):
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
                if isinstance(data, dict):
                    for key in ["chapters", "structure", "sections"]:
                        if key in data: return data[key]
                return data
            return json.loads(text)
        except:
            return []

    def generate_documentation(self, repo_name):
        print(f"📡 Analyzing Graph Topology for {repo_name}...")
        all_metadata = self.get_graph_context(repo_name)
        
        if not all_metadata:
            print(f"❌ No graph data found for: {repo_name}")
            return

        sorted_metadata = sorted(all_metadata, key=lambda x: x['in_degree'] + x['out_degree'], reverse=True)
        context_summary = [{"path": m['path'], "connectivity": m['in_degree'] + m['out_degree'], "symbols": m['symbols'][:3]} for m in sorted_metadata]

        # STEP 1: GENERATE TABLE OF CONTENTS (TOC)
        toc_prompt = f"""
        Repository: {repo_name}
        Files: {json.dumps(context_summary)}

        TASK:
        1. Group files into logical domains (Chapters).
        2. Assign a clear title and objective for each.
        3. Identify potential "Logical Connections" between these domains even if no physical imports exist.
        
        RETURN ONLY JSON:
        {{ 
          "chapters": [ {{ "chapter_num": 1, "title": "...", "objective": "...", "focus_files": ["..."] }} ],
          "logical_links": [ {{ "source_chapter": 1, "target_chapter": 2, "reason": "..." }} ]
        }}
        """
        
        toc_response = self.ask_ai(toc_prompt, json_mode=True)
        toc_data = json.loads(toc_response) if toc_response else {}
        chapters = toc_data.get("chapters", [])
        logical_links = toc_data.get("logical_links", [])

        full_path = os.path.join(self.output_dir, f"{repo_name.upper()}_TECHNICAL_SPEC.md")
        
        with open(full_path, "w", encoding="utf-8") as doc:
            # CSS STYLING
            doc.write("""<style>
                body { font-family: 'Inter', sans-serif; color: #1a1a1a; line-height: 1.7; }
                .page-break { page-break-before: always; }
                .cover-page { text-align: center; padding: 250px 0; border: 10px solid #f0f0f0; }
                .repo-title { font-size: 80px; font-weight: 900; margin: 0; }
                h1.chapter-header { font-size: 36px; border-bottom: 3px solid #000; padding-bottom: 10px; text-transform: uppercase; }
                h2 { color: #2c3e50; border-left: 5px solid #3498db; padding-left: 10px; margin-top: 30px; }
                table { width: 100%; border-collapse: collapse; margin: 20px 0; }
                th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
                th { background-color: #f8f9fa; }
            </style>\n\n""")
            
            # COVER PAGE
            doc.write(f"<div class='cover-page'>\n<h1 class='repo-title'>{repo_name.upper()}</h1>\n")
            doc.write(f"<p style='font-size:24px;'>Architectural Manual & Distributed Specification</p>\n")
            doc.write(f"</div>\n")

            # CHAPTERS
            for chapter in chapters:
                c_num = chapter.get('chapter_num')
                c_title = chapter.get('title')
                c_files = chapter.get('focus_files', [])
                
                doc.write('\n<div class="page-break"></div>\n\n')
                doc.write(f"<h1 class='chapter-header'>Chapter {c_num}: {c_title}</h1>\n\n")
                
                specific_metadata = [m for m in all_metadata if m['path'] in c_files]
                
                write_prompt = f"Write technical body for Chapter {c_num}: {c_title}. Context: {json.dumps(specific_metadata)}. RULES: No titles, start with ## Overview, use tables for symbols."
                chapter_body = self.ask_ai(write_prompt, "architect" if c_num == 1 else "writer")
                doc.write(f"{chapter_body}\n\n")

            # APPENDIX: SMART DEPENDENCY GRAPH
            doc.write('\n<div class="page-break"></div>\n\n')
            doc.write("<h1 class='chapter-header'>Appendix: System Topology</h1>\n\n")
            doc.write("```mermaid\ngraph TD\n")
            
            # Try physical links first
            physical_found = False
            for m in all_metadata:
                if m['dependencies']:
                    origin = m['path'].split('/')[-1].replace(".", "_")
                    for d in m['dependencies'][:2]:
                        target = d.split('/')[-1].replace(".", "_")
                        doc.write(f"  {origin} -->|imports| {target}\n")
                        physical_found = True
            
            # If no physical links (like in CHORD), use Logical AI links
            if not physical_found:
                print("⚠️ No physical dependencies found. Generating logical topology...")
                for link in logical_links:
                    src = chapters[link['source_chapter']-1]['title'].replace(" ", "_")
                    tgt = chapters[link['target_chapter']-1]['title'].replace(" ", "_")
                    reason = link.get('reason', 'interacts')
                    doc.write(f"  {src} -- \"{reason}\" --> {tgt}\n")
            
            doc.write("```\n")

        print(f"✅ Success: Manual generated at {full_path}")

if __name__ == "__main__":
    engine = RepoManualEngine()
    repo = input("Enter repo name: ").strip()
    engine.generate_documentation(repo)
    engine.close()