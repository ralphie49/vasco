import os
import time
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
        self.output_dir = "./output_docs"
        if not os.path.exists(self.output_dir): 
            os.makedirs(self.output_dir)

    def close(self):
        self.driver.close()

    def ask_ai(self, prompt, style="architect"):
        """Queries the AI using a persona that avoids hesitant language."""
        styles = {
            "architect": "You are a Senior Software Architect. Write in a confident, declarative, and technical tone. Avoid phrases like 'based on the provided info', 'maybe', or 'it seems'. Speak in the present tense.",
            "manual": "You are a technical writer for high-end engineering manuals. Use structured, authoritative language. Do not use first-person ('I') or hedge words."
        }
        
        try:
            completion = client.chat.completions.create(
                model="meta/llama-3.1-405b-instruct",
                messages=[
                    {"role": "system", "content": styles.get(style, styles["architect"])},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8 # Lower temperature for higher confidence/consistency
            )
            return completion.choices[0].message.content.strip()
        except Exception:
            return "Reference data unavailable."

    def generate_book(self, repo_name):
        print(f"📚 Publishing Authoritative Manual: {repo_name}")
        
        with self.driver.session() as session:
            query = """
            MATCH (f:File {repo: $repo_name})
            WHERE NOT f.name CONTAINS 'node_modules'
            OPTIONAL MATCH (f)-[:DEFINES]->(item)
            WITH f, collect({name: item.name, type: labels(item)[0], desc: item.description}) AS items
            OPTIONAL MATCH (f)-[:DEPENDS_ON]->(dep)
            RETURN f.name AS file, f.extension AS ext, items, collect(dep.name) AS deps
            ORDER BY size(deps) DESC, file ASC
            """
            results = session.run(query, repo_name=repo_name).data()

        if not results:
            print("❌ No data found.")
            return

        # DYNAMIC ENTRY POINT DETECTION
        all_files = [r['file'] for r in results]
        identity_prompt = f"Analyze this file list: {all_files[:20]}. Identify the primary ENTRY file and the primary CORE logic file. Format: ENTRY:filename, CORE:filename"
        identity = self.ask_ai(identity_prompt)
        
        try:
            entry_file = identity.split("ENTRY:")[1].split(",")[0].strip()
            core_file = identity.split("CORE:")[1].strip()
        except:
            entry_file = results[0]['file']
            core_file = results[1]['file'] if len(results) > 1 else entry_file

        full_path = os.path.join(self.output_dir, f"{repo_name.upper()}_TECHNICAL_MANUAL.md")
        
        with open(full_path, "w", encoding="utf-8") as book:
            # CHAPTER 1: DESIGN PHILOSOPHY
            book.write(f"# 📖 {repo_name.upper()} | Engineering Specification\n\n")
            book.write("## 01. Architectural Design\n")
            summary_prompt = f"Explain the purpose and architectural pattern of a project containing these files: {all_files[:12]}. Start directly with the definition."
            book.write(f"{self.ask_ai(summary_prompt, 'manual')}\n\n")

            # CHAPTER 2: EXECUTION FLOW
            book.write("## 02. System Workflow\n")
            book.write("The following diagram outlines the high-level call sequence and module dependencies.\n\n")
            book.write("```mermaid\nsequenceDiagram\n  autonumber\n")
            book.write(f"  Note over {entry_file.replace('.','_')}, {core_file.replace('.','_')}: Critical Path\n")
            
            for res in results[:12]:
                fid = res['file'].replace('.','_').replace('/','_')
                for d in res['deps']:
                    did = d.replace('.','_').replace('/','_')
                    book.write(f"  {fid}->>{did}: invokes\n")
            book.write("```\n\n---\n")

            # CHAPTER 3: MODULE SPECIFICATIONS
            book.write("## 03. Module Deep-Dive\n")
            for i, res in enumerate(results, 1):
                book.write(f"### 3.{i} `{res['file']}`\n")
                
                # Logic Analysis - No guessing allowed
                if res['ext'] in ['py', 'js', 'java', 'ts', 'cpp']:
                    logic_prompt = f"Define the execution logic for the module `{res['file']}`. It contains these symbols: {res['items']}. Focus on how it processes data."
                else:
                    logic_prompt = f"Define the role of `{res['file']}` within the project infrastructure."
                
                book.write(f"{self.ask_ai(logic_prompt, 'architect')}\n\n")

                # Table with Dynamic Fallback (Live Terminal-style Querying)
                if res['items'] and any(item['name'] for item in res['items']):
                    book.write("| Component | Type | Responsibility |\n| :--- | :--- | :--- |\n")
                    for item in res['items']:
                        if not item['name']: continue
                        
                        desc = item['desc']
                        # If description is missing ("No description thing"), query the AI just like the terminal!
                        if not desc or desc == "None" or "No description" in desc:
                            desc = self.ask_ai(f"Define the specific responsibility of the {item['type']} `{item['name']}` in the {repo_name} system.")
                        
                        book.write(f"| `{item['name']}` | {item['type']} | {desc} |\n")
                book.write("\n---\n")

        print(f"✅ Authoritative Book Generated: {full_path}")

if __name__ == "__main__":
    engine = RepoManualEngine()
    repo = input("Enter repo name: ").strip()
    engine.generate_book(repo)
    engine.close()