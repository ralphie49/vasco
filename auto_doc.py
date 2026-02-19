import os
import re
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

class RepoBookGenerator:
    def __init__(self):
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def clean_docs(self, text):
        """Transforms raw Sphinx/reST docstrings into clean Markdown."""
        if not text or text == "No description provided.":
            return "_No description available._"
        
        # 1. Clean up Sphinx tags like :param name:, :type:, :rtype:
        text = re.sub(r':[a-z]+ [^:]+:', '', text)
        
        # 2. Clean up class/meth links: :class:`~requests.models.Response` -> **Response**
        text = re.sub(r':[a-z]+:`~?\.?([^`<>]+)(?: <[^>]+>)?`', r'**\1**', text)
        
        # 3. Handle double-colon code blocks (::) often used in requests docs
        text = text.replace('::', ':')

        # 4. Remove excessive hard line breaks that make the PDF look choppy
        lines = [line.strip() for line in text.split('\n')]
        text = ' '.join(lines)
        
        # 5. Final polish on whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text

    def get_repo_stats(self, repo_name):
        with self.driver.session() as session:
            query = """
            MATCH (n {repo: $repo_name})
            RETURN 
                count(DISTINCT CASE WHEN n:Module THEN n END) as modules,
                count(DISTINCT CASE WHEN n:Class THEN n END) as classes,
                count(DISTINCT CASE WHEN n:Function THEN n END) as functions
            """
            return session.run(query, repo_name=repo_name).single()

    def generate(self, repo_name):
        stats = self.get_repo_stats(repo_name)
        
        with self.driver.session() as session:
            query = """
            MATCH (m:Module {repo: $repo_name})
            WHERE m.name CONTAINS "/" OR m.name CONTAINS $repo_name
            
            OPTIONAL MATCH (m)-[:DEFINES]->(item)
            WITH m, item, labels(item)[0] AS type
            WITH m, collect({name: item.name, type: type, desc: item.description}) AS components
            
            RETURN m.name AS file, 
                   components,
                   CASE 
                     WHEN m.name CONTAINS 'api' OR m.name CONTAINS 'sessions' THEN 'Ch 1: The Gateway (API & Sessions)'
                     WHEN m.name CONTAINS 'models' OR m.name CONTAINS 'structures' THEN 'Ch 2: The Skeleton (Data Models)'
                     WHEN m.name CONTAINS 'adapter' OR m.name CONTAINS 'hooks' OR m.name CONTAINS 'auth' THEN 'Ch 3: The Pulse (Transport & Auth)'
                     WHEN m.name CONTAINS 'util' OR m.name CONTAINS 'compat' OR m.name CONTAINS 'help' THEN 'Ch 4: The Toolbelt (Utilities)'
                     WHEN m.name CONTAINS 'test' THEN 'Ch 5: The Shield (Testing Suite)'
                     ELSE 'Ch 6: Supporting Infrastructure'
                   END AS chapter,
                   COUNT { (m)<-[:IMPORTS]-() } AS importance 
            ORDER BY chapter ASC, importance DESC
            """
            data = session.run(query, repo_name=repo_name).data()

        if not data:
            print(f"⚠️ Repo '{repo_name}' not found in Neo4j.")
            return

        filename = f"{repo_name.upper()}_THE_BOOK.md"
        book = {}
        for rec in data:
            book.setdefault(rec['chapter'], []).append(rec)

        with open(filename, "w", encoding="utf-8") as f:
            # --- COVER PAGE ---
            f.write(f"# 📖 {repo_name.upper()}: The Complete Reference\n\n")
            f.write(f"## 📊 Project at a Glance\n")
            f.write(f"- **Total Modules:** {stats['modules']}\n")
            f.write(f"- **Total Classes:** {stats['classes']}\n")
            f.write(f"- **Total Functions:** {stats['functions']}\n\n")
            # Force TOC to a new page
            f.write('<div style="page-break-after: always;"></div>\n\n')

            # --- TABLE OF CONTENTS ---
            f.write("## 📑 Table of Contents\n")
            for ch in sorted(book.keys()):
                anchor = ch.lower().replace(" ", "-").replace(":", "").replace("(", "").replace(")", "")
                f.write(f"- [{ch}](#{anchor})\n")
            # Force Chapter 1 to a new page
            f.write('\n<div style="page-break-after: always;"></div>\n\n')

            # --- CHAPTERS ---
            chapters = sorted(book.items())
            for i, (ch_title, modules) in enumerate(chapters):
                f.write(f"## {ch_title}\n")
                
                f.write("### 📉 Chapter Dependency Map\n")
                f.write("```mermaid\ngraph LR\n")
                for mod in modules[:5]: 
                    short_name = mod['file'].split('/')[-1].replace('.py','')
                    f.write(f"    {short_name} --> Imp_{mod['importance']}[Impact: {mod['importance']}]\n")
                f.write("```\n\n")

                for mod in modules:
                    f.write(f"### 📄 Module: `{mod['file']}`\n")
                    f.write(f"> Architecture Role: {ch_title.split(': ')[1]}\n\n")
                    
                    classes = [c for c in mod['components'] if str(c['type']).lower() == 'class']
                    funcs = [c for c in mod['components'] if str(c['type']).lower() == 'function']

                    if classes:
                        f.write("#### 🏛️ Classes\n")
                        for c in classes:
                            clean_desc = self.clean_docs(c.get('desc'))
                            f.write(f"- **`{c['name']}`**: {clean_desc}\n")
                        f.write("\n")

                    if funcs:
                        f.write("#### ⚙️ Logic & Functions\n")
                        for fn in funcs[:5]:
                            clean_desc = self.clean_docs(fn.get('desc'))
                            f.write(f"- **`{fn['name']}`**: {clean_desc}\n")
                        if len(funcs) > 5:
                            remaining = ", ".join([f"`{fn['name']}`" for fn in funcs[5:20]])
                            f.write(f"\n*Additional Logic:* {remaining}...\n")
                    
                    f.write("\n---\n")

                # ADD PAGE BREAK AFTER EACH CHAPTER
                if i < len(chapters) - 1:
                    f.write('\n<div style="page-break-after: always;"></div>\n\n')

        print(f"✅ Your project book is ready: {filename}")

    def close(self):
        self.driver.close()

if __name__ == "__main__":
    gen = RepoBookGenerator()
    target = input("Which repo would you like to bind into a book? ").strip()
    try:
        gen.generate(target)
    finally:
        gen.close()