import os
import re
import time
import random
from neo4j import GraphDatabase
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# --- AI Configuration (NVIDIA NIM) ---
# This makes the "narrator" explain the code like a peer.
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

    def close(self):
        self.driver.close()

    def get_ai_narrative(self, name, docstring, type_label):
        """Asks NVIDIA AI to explain the logic and 'why' behind the code."""
        if not docstring or docstring == "No description provided.":
            return f"The `{name}` {type_label} serves as a core logic block within this module."

        prompt = f"""
        Explain the purpose of this {type_label}: '{name}'.
        Code Context/Docstring: {docstring}
        
        Instruction: Explain what this does and WHY it exists in the system. 
        Write 2-3 sentences. Do not use 'This is a class'. Speak directly about the logic.
        """

        # Retry logic for NVIDIA 429 Rate Limits
        for attempt in range(5):
            try:
                completion = client.chat.completions.create(
                    model="meta/llama-3.1-405b-instruct",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.4,
                    max_tokens=200
                )
                return completion.choices[0].message.content.strip()
            except Exception as e:
                if "429" in str(e):
                    time.sleep((2 ** attempt) + random.random())
                else:
                    return f"Logic Detail: {docstring[:150]}..."
        return "Explanation timeout."

    def generate_book(self, repo_name):
        print(f"📖 Authoring the Complete Technical Manual for: {repo_name}")
        
        with self.driver.session() as session:
            # Query to get every file, its components, and who it talks to (graphs)
            query = """
            MATCH (m:Module {repo: $repo_name})
            WHERE NOT m.name CONTAINS 'test' AND NOT m.name CONTAINS '__init__'
            
            OPTIONAL MATCH (m)-[:DEFINES]->(item)
            WITH m, item, labels(item)[0] AS type
            WITH m, collect({name: item.name, type: type, desc: item.description}) AS components
            
            OPTIONAL MATCH (m)<-[:DEPENDS_ON]-(other)
            WITH m, components, count(distinct other) as inbound
            OPTIONAL MATCH (m)-[:DEPENDS_ON]->(target)
            WITH m, components, inbound, collect(distinct target.name) as outbound_names
            
            RETURN m.name AS file, components, inbound, outbound_names,
                   CASE 
                     WHEN m.name CONTAINS '/' THEN split(m.name, '/')[0] 
                     ELSE 'Core Operations'
                   END AS folder_group
            ORDER BY folder_group ASC, inbound DESC
            """
            results = session.run(query, repo_name=repo_name).data()

        if not results:
            print("❌ No data found. Ensure you have ingested the repo first.")
            return

        filename = f"{repo_name.upper()}_TECHNICAL_MANUAL.md"
        
        with open(filename, "w", encoding="utf-8") as f:
            # --- 1. THE FRONT MATTER ---
            f.write(f"# 📘 {repo_name.upper()}: Technical Architecture & Logic Reference\n")
            f.write("## An exhaustive guide to every file, connection, and code block.\n\n")
            f.write("---\n")

            # --- 2. THE CHAPTERS (FILES) ---
            for res in results:
                f.write(f"## 📄 File: `{res['file']}`\n")
                
                # --- 3. THE GRAPH SECTION ---
                # We use Mermaid.js to render the graph inside the Markdown book
                f.write("### 📉 Dependency Graph\n")
                f.write("```mermaid\ngraph LR\n")
                this_file = res['file'].split('/')[-1].replace('.py','')
                if res['outbound_names']:
                    for target in res['outbound_names']:
                        target_file = target.split('/')[-1].replace('.py','')
                        f.write(f"    {this_file} --> {target_file}\n")
                else:
                    f.write(f"    {this_file}\n")
                f.write("```\n")
                f.write(f"*This module is a dependency for **{res['inbound']}** other parts of the system.*\n\n")

                # --- 4. THE CODE EXPLANATIONS ---
                f.write("### 🛠️ Code Logic Breakdown\n")
                
                for c in res['components']:
                    label = "Class" if str(c['type']).lower() == 'class' else "Function"
                    f.write(f"#### 🔹 {label}: `{c['name']}`\n")
                    
                    # AI Narrator explains the code
                    explanation = self.get_ai_narrative(c['name'], c['desc'], label)
                    f.write(f"{explanation}\n\n")
                
                f.write("---\n")
                f.write('<div style="page-break-after: always;"></div>\n\n')

        print(f"✅ Manual authored: {filename}")

if __name__ == "__main__":
    engine = RepoManualEngine()
    repo = input("Enter repo name: ").strip()
    engine.generate_book(repo)
    engine.close()