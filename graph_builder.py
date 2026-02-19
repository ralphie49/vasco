import ast
import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

class CodeGraphBuilder:
    def __init__(self, repo_name):
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.repo_name = repo_name # Track which repo we are in

    def close(self):
        self.driver.close()

    def parse_file_to_graph(self, file_path, base_repo_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read())
        except Exception as e:
            print(f"❌ Could not read {file_path}: {e}")
            return

        file_rel_path = os.path.relpath(file_path, base_repo_path).replace("\\", "/")
        
        with self.driver.session(database="neo4j") as session:
            session.execute_write(self._create_elements, file_rel_path, tree, self.repo_name)

    @staticmethod
    def _create_elements(tx, file_name, tree, repo_name):  # Added 4 spaces here
        # 1. Create Module
        tx.run("MERGE (m:Module {name: $file, repo: $repo_name})", 
               file=file_name, repo_name=repo_name)

        for item in tree.body:
            # --- CLASSES ---
            if isinstance(item, ast.ClassDef):
                doc = ast.get_docstring(item) or "No description provided."
                tx.run("""
                    MATCH (m:Module {name: $file, repo: $repo_name})
                    MERGE (c:Class {name: $name, repo: $repo_name, module: $file})
                    SET c.description = $doc
                    MERGE (m)-[:DEFINES]->(c)
                """, file=file_name, name=item.name, repo_name=repo_name, doc=doc)

            # --- STANDALONE FUNCTIONS ---
            elif isinstance(item, ast.FunctionDef):
                doc = ast.get_docstring(item) or "No description provided."
                tx.run("""
                    MATCH (m:Module {name: $file, repo: $repo_name})
                    MERGE (f:Function {name: $name, repo: $repo_name, module: $file})
                    SET f.description = $doc
                    MERGE (m)-[:DEFINES]->(f)
                """, file=file_name, name=item.name, repo_name=repo_name, doc=doc)

    def build_from_directory(self, directory):
        print(f"🕸️ Building isolated graph for: {self.repo_name}")
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith(".py"):
                    self.parse_file_to_graph(os.path.join(root, file), directory)