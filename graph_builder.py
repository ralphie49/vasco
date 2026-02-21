import ast
import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

class CodeGraphBuilder:
    def __init__(self, repo_name):
        """Initializes connection to Neo4j."""
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")
        
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.repo_name = repo_name

    def close(self):
        if self.driver:
            self.driver.close()

    def clear_database(self):
        """Wipes all nodes and relationships for a fresh start."""
        print("🧨 Wiping Neo4j database for a fresh start...")
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        print("✅ Database cleared.")

    def build_from_directory(self, directory):
        """Walks directory, creates nodes for all files, and links dependencies."""
        print(f"🕸️ Building isolated graph for: {self.repo_name}")
        
        for root, _, files in os.walk(directory):
            if ".git" in root or "__pycache__" in root:
                continue
                
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, directory).replace("\\", "/")
                
                # 1. Create a node for EVERY file found
                with self.driver.session() as session:
                    session.run("""
                        MERGE (f:File {name: $name, repo: $repo})
                        SET f.extension = $ext
                    """, name=rel_path, repo=self.repo_name, ext=file.split('.')[-1])

                # 2. If it's Python, extract deep logic
                if file.endswith(".py"):
                    self.parse_python_logic(full_path, rel_path)
        
        # 3. Link Python dependencies
        self.link_dependencies(directory)

    def parse_python_logic(self, full_path, rel_path):
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read())
            
            with self.driver.session() as session:
                # Python files also get the 'Module' label
                session.run("MATCH (f:File {name: $name, repo: $repo}) SET f:Module", 
                            name=rel_path, repo=self.repo_name)
                session.execute_write(self._create_sub_elements, rel_path, tree, self.repo_name)
        except Exception as e:
            print(f"⚠️ Skipping deep parse for {rel_path}: {e}")

    def link_dependencies(self, directory):
        """Analyzes import statements."""
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    src_module = os.path.relpath(full_path, directory).replace("\\", "/")
                    
                    with open(full_path, "r", encoding="utf-8") as f:
                        try:
                            tree = ast.parse(f.read())
                            for node in ast.walk(tree):
                                target = None
                                if isinstance(node, ast.Import):
                                    target = node.names[0].name
                                elif isinstance(node, ast.ImportFrom) and node.module:
                                    target = node.module
                                
                                if target:
                                    target_search = target.replace(".", "/")
                                    with self.driver.session() as session:
                                        session.run("""
                                            MATCH (a:File {name: $src, repo: $repo})
                                            MATCH (b:File {repo: $repo})
                                            WHERE b.name CONTAINS $target
                                            MERGE (a)-[:DEPENDS_ON]->(b)
                                        """, src=src_module, target=target_search, repo=self.repo_name)
                        except:
                            continue

    @staticmethod
    def _create_sub_elements(tx, file_name, tree, repo_name):
        for item in tree.body:
            if isinstance(item, (ast.ClassDef, ast.FunctionDef)):
                label = "Class" if isinstance(item, ast.ClassDef) else "Function"
                doc = ast.get_docstring(item) or "No description provided."
                tx.run(f"""
                    MATCH (m:File {{name: $file, repo: $repo}})
                    MERGE (c:{label} {{name: $name, repo: $repo, module: $file}})
                    SET c.description = $doc
                    MERGE (m)-[:DEFINES]->(c)
                """, file=file_name, name=item.name, repo=repo_name, doc=doc)
if __name__ == "__main__":
    builder = CodeGraphBuilder(repo_name="manual_test")
    builder.close()