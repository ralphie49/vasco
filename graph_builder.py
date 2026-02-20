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

    def build_from_directory(self, directory):
        """Walks directory, parses code, and then links dependencies."""
        print(f"🕸️ Building isolated graph for: {self.repo_name}")
        
        # Step 1: Create all nodes
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, directory).replace("\\", "/")
                    self.parse_file_to_graph(full_path, rel_path)
        
        # Step 2: Create relationships between nodes (Imports)
        self.link_dependencies(directory)

    def parse_file_to_graph(self, full_path, rel_path):
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read())
            
            with self.driver.session() as session:
                session.execute_write(self._create_elements, rel_path, tree, self.repo_name)
        except Exception as e:
            print(f"❌ Error parsing {rel_path}: {str(e)}")

    def link_dependencies(self, directory):
        """Analyzes import statements to create DEPENDS_ON relationships."""
        print("🔗 Analyzing module dependencies...")
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
                                    # Logic to match 'requests.models' to 'requests/models.py'
                                    target_search = target.replace(".", "/")
                                    with self.driver.session() as session:
                                        session.run("""
                                            MATCH (a:Module {name: $src, repo: $repo})
                                            MATCH (b:Module {repo: $repo})
                                            WHERE b.name CONTAINS $target
                                            MERGE (a)-[:DEPENDS_ON]->(b)
                                        """, src=src_module, target=target_search, repo=self.repo_name)
                        except:
                            continue

    @staticmethod
    def _create_elements(tx, file_name, tree, repo_name):
        # Create Module
        tx.run("MERGE (m:Module {name: $file, repo: $repo})", file=file_name, repo=repo_name)

        for item in tree.body:
            if isinstance(item, (ast.ClassDef, ast.FunctionDef)):
                label = "Class" if isinstance(item, ast.ClassDef) else "Function"
                doc = ast.get_docstring(item) or "No description provided."
                tx.run(f"""
                    MATCH (m:Module {{name: $file, repo: $repo}})
                    MERGE (c:{label} {{name: $name, repo: $repo, module: $file}})
                    SET c.description = $doc
                    MERGE (m)-[:DEFINES]->(c)
                """, file=file_name, name=item.name, repo=repo_name, doc=doc)

if __name__ == "__main__":
    builder = CodeGraphBuilder(repo_name="manual_test")
    # builder.build_from_directory("./your_code")
    builder.close()