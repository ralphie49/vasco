import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

def generate_architectural_docs():
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD")
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    with driver.session() as session:
        # 1. Fetch data with 'Role' logic
        # We look for common patterns to assign roles automatically
        query = """
        MATCH (m:Module)
        OPTIONAL MATCH (m)-[:DEFINES]->(item)
        RETURN m.name AS file, 
               collect({name: item.name, type: labels(item)[0]}) AS components,
               CASE 
                 WHEN m.name CONTAINS 'orchestrator' THEN '🧠 Core Orchestration'
                 WHEN m.name CONTAINS 'api' OR m.name CONTAINS 'app' THEN '🌐 Interface / Entrypoint'
                 WHEN m.name CONTAINS 'adapter' OR m.name CONTAINS 'client' THEN '🔌 External Integration'
                 WHEN m.name CONTAINS 'test' THEN '🧪 Quality Assurance'
                 WHEN m.name CONTAINS 'util' OR m.name CONTAINS 'helpers' THEN '🛠️ Utility Layer'
                 ELSE '📄 Functional Module'
               END AS role
        ORDER BY role DESC, m.name
        """
        data = session.run(query).data()

    with open("PWAI_TECHNICAL_REFERENCE.md", "w", encoding="utf-8") as f:
        f.write("# 💠 PWAI Project Technical Manual\n\n")
        f.write("## 📖 Project Philosophy\n")
        f.write("This document provides a deep-dive into the roles and logic of the PWAI repository. ")
        f.write("The system is designed as a modular AI orchestrator, separating the interface from the core logic.\n\n")

        # Create a Summary Table for Roles
        f.write("## 🏗️ Architectural Overview\n")
        f.write("| Component | Role in Project |\n")
        f.write("| :--- | :--- |\n")
        for record in data:
            f.write(f"| `{record['file']}` | {record['role']} |\n")
        f.write("\n---\n")

        # Deep Dive Sections
        f.write("## 🔍 Detailed Module Breakdown\n")
        current_role = ""
        for record in data:
            if record['role'] != current_role:
                current_role = record['role']
                f.write(f"\n### {current_role}\n")
            
            f.write(f"#### 📦 Module: `{record['file']}`\n")
            f.write(f"- **Primary Responsibility:** {record['role'].split(' ')[1]} tasks and logic.\n")
            
            classes = [c['name'] for c in record['components'] if c['type'] == 'Class' and c['name']]
            funcs = [c['name'] for c in record['components'] if c['type'] == 'Function' and c['name']]

            if classes:
                f.write(f"- **Key Classes:** {', '.join([f'`{c}`' for c in classes])}\n")
            if funcs:
                f.write(f"- **Exposed Logic:** {len(funcs)} functions available for internal calls.\n")
            f.write("\n")

    driver.close()
    print("✅ Comprehensive Manual Generated: PWAI_TECHNICAL_REFERENCE.md")

if __name__ == "__main__":
    generate_architectural_docs()