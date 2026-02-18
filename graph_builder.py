import ast
import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

class CodeGraphBuilder:
    def __init__(self):
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def parse_file_to_graph(self, file_path, base_repo_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read())
        except Exception as e:
            print(f"❌ Could not read {file_path}: {e}")
            return

        # Get relative path to use as a unique ID for the Module
        file_rel_path = os.path.relpath(file_path, base_repo_path).replace("\\", "/")
        
        with self.driver.session(database="neo4j") as session:
            session.execute_write(self._create_elements, file_rel_path, tree)

    @staticmethod
    def _create_elements(tx, file_name, tree):
        # 1. Create/Update the current Module (File)
        tx.run("MERGE (m:Module {name: $name})", name=file_name)

        for item in tree.body:
            # --- DEPENDENCY: Standard Imports (import os) ---
            if isinstance(item, ast.Import):
                for alias in item.names:
                    tx.run("""
                        MATCH (m:Module {name: $file})
                        MERGE (dep:Module {name: $dep_name})
                        MERGE (m)-[:IMPORTS]->(dep)
                    """, file=file_name, dep_name=alias.name)

            # --- DEPENDENCY: From Imports (from x import y) ---
            elif isinstance(item, ast.ImportFrom):
                if item.module:
                    tx.run("""
                        MATCH (m:Module {name: $file})
                        MERGE (dep:Module {name: $dep_name})
                        MERGE (m)-[:IMPORTS]->(dep)
                    """, file=file_name, dep_name=item.module)

            # --- STRUCTURE: Classes ---
            elif isinstance(item, ast.ClassDef):
                tx.run("""
                    MATCH (m:Module {name: $file})
                    MERGE (c:Class {name: $name})
                    MERGE (m)-[:DEFINES]->(c)
                """, file=file_name, name=item.name)

            # --- STRUCTURE: Functions ---
            elif isinstance(item, ast.FunctionDef):
                tx.run("""
                    MATCH (m:Module {name: $file})
                    MERGE (f:Function {name: $name})
                    MERGE (m)-[:DEFINES]->(f)
                """, file=file_name, name=item.name)

    def build_from_directory(self, directory):
        if not os.path.exists(directory):
            print(f"⚠️ Error: {directory} not found!")
            return

        print(f"🕸️ Building dependency graph for: {directory}")
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    self.parse_file_to_graph(full_path, directory)
        print("✅ Graph build complete!")

if __name__ == "__main__":
    builder = CodeGraphBuilder()
    # Ensure this path matches where main.py clones the repo
    repo_to_analyze = "./repos/PWAI" 
    builder.build_from_directory(repo_to_analyze)
    builder.close()