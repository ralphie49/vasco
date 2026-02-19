import os
import re
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

class RepoBookGenerator:
    def __init__(self):
        """Initializes the Neo4j driver using environment variables."""
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def clean_docs(self, text):
        """Transforms raw Sphinx/reST docstrings into clean Markdown and truncates length."""
        if not text or text == "No description provided.":
            return "_No description available._"
        
        # 1. Clean up Sphinx/reST tags
        text = re.sub(r':[a-z]+ [^:]+:', '', text)
        text = re.sub(r':[a-z]+:`~?\.?([^`<>]+)(?: <[^>]+>)?`', r'**\1**', text)
        text = text.replace('::', ':')

        # 2. Flatten line breaks and clean whitespace
        lines = [line.strip() for line in text.split('\n')]
        text = ' '.join(lines)
        text = re.sub(r'\s+', ' ', text).strip()
        
        # 3. Truncate for the "Executive Summary" feel (approx 300 chars)
        if len(text) > 300:
            text = text[:300] + "..."
            
        return text

    def get_repo_stats(self, repo_name):
        """Fetches total counts for the specific repository, excluding tests."""
        with self.driver.session() as session:
            query = """
            MATCH (n {repo: $repo_name})
            WHERE NOT n.name CONTAINS 'test'
            RETURN 
                count(DISTINCT CASE WHEN n:Module THEN n END) as modules,
                count(DISTINCT CASE WHEN n:Class THEN n END) as classes,
                count(DISTINCT CASE WHEN n:Function THEN n END) as functions
            """
            return session.run(query, repo_name=repo_name).single()

    def generate(self, repo_name):
        """Generates the Markdown book for a specific repository."""
        stats = self.get_repo_stats(repo_name)
        
        with self.driver.session() as session:
            # Query targets specific repo and categorizes modules into chapters
            query = """
            MATCH (m:Module {repo: $repo_name})
            WHERE NOT m.name CONTAINS 'test'
            
            OPTIONAL MATCH (m)-[:DEFINES]->(item)
            WITH m, item, labels(item)[0] AS type
            WITH m, collect({name: item.name, type: type, desc: item.description}) AS components
            
            RETURN m.name AS file, 
                   components,
                   CASE 
                     WHEN m.name CONTAINS 'api' OR m.name CONTAINS 'sessions' THEN 'Ch 1: The Gateway (API & Core)'
                     WHEN m.name CONTAINS 'models' OR m.name CONTAINS 'structures' THEN 'Ch 2: The Skeleton (Data Models)'
                     WHEN m.name CONTAINS 'util' OR m.name CONTAINS 'helper' THEN 'Ch 3: The Toolbelt (Utilities)'
                     ELSE 'Ch 4: Supporting Infrastructure'
                   END AS chapter,
                   COUNT { (m)<-[:IMPORTS]-() } AS importance 
            ORDER BY chapter ASC, importance DESC
            """
            data = session.run(query, repo_name=repo_name).data()

        if not data:
            print(f"⚠️ Repo '{repo_name}' not found in Neo4j. Check case sensitivity.")
            return

        filename = f"{repo_name.upper()}_THE_BOOK.md"
        book = {}
        for rec in data:
            book.setdefault(rec['chapter'], []).append(rec)

        with open(filename, "w", encoding="utf-8") as f:
            # --- COVER PAGE ---
            f.write(f"# 📖 {repo_name.upper()}: Technical Reference\n\n")
            f.write(f"## 📊 Project at a Glance\n")
            f.write(f"- **Core Modules:** {stats['modules']}\n")
            f.write(f"- **Documented Classes:** {stats['classes']}\n")
            f.write(f"- **Key Functions:** {stats['functions']}\n\n")
            f.write('<div style="page-break-after: always;"></div>\n\n')

            # --- TABLE OF CONTENTS ---
            f.write("## 📑 Table of Contents\n")
            for ch in sorted(book.keys()):
                anchor = ch.lower().replace(" ", "-").replace(":", "").replace("(", "").replace(")", "")
                f.write(f"- [{ch}](#{anchor})\n")
            f.write('\n<div style="page-break-after: always;"></div>\n\n')

            # --- CHAPTERS ---
            chapters = sorted(book.items())
            for i, (ch_title, modules) in enumerate(chapters):
                f.write(f"## {ch_title}\n")
                
                # Mermaid Diagram for Chapter
                f.write("### 📉 Chapter Architecture\n")
                f.write("```mermaid\ngraph LR\n")
                for mod in modules[:5]: 
                    # Clean filename for Mermaid syntax compatibility
                    clean_id = re.sub(r'[^a-zA-Z0-9]', '_', mod['file'].split('/')[-1].replace('.py',''))
                    f.write(f"    {clean_id} --> Imp_{mod['importance']}[Impact Score: {mod['importance']}]\n")
                f.write("```\n\n")

                for mod in modules:
                    f.write(f"### 📄 Module: `{mod['file']}`\n")
                    
                    classes = [c for c in mod['components'] if str(c['type']).lower() == 'class']
                    funcs = [c for c in mod['components'] if str(c['type']).lower() == 'function']

                    if classes:
                        f.write("#### 🏛️ Classes\n")
                        for c in classes[:5]:
                            clean_desc = self.clean_docs(c.get('desc'))
                            f.write(f"- **`{c['name']}`**: {clean_desc}\n")
                        f.write("\n")

                    if funcs:
                        f.write("#### ⚙️ Logic\n")
                        for fn in funcs[:3]:
                            clean_desc = self.clean_docs(fn.get('desc'))
                            f.write(f"- **`{fn['name']}`**: {clean_desc}\n")
                        if len(funcs) > 3:
                            others = ", ".join([f"`{fn['name']}`" for fn in funcs[3:12]])
                            f.write(f"\n*Includes:* {others}...\n")
                    
                    f.write("\n---\n")

                if i < len(chapters) - 1:
                    f.write('\n<div style="page-break-after: always;"></div>\n\n')

        print(f"✅ Book successfully generated: {filename}")

if __name__ == "__main__":
    gen = RepoBookGenerator()
    target = input("Which repo would you like to bind into a book? ").strip()
    try:
        gen.generate(target)
    finally:
        gen.close()