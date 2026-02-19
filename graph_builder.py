import ast
import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

class CodeGraphBuilder:
    def __init__(self, repo_name):
        """
        Initializes the connection to Neo4j and sets the current repository context.
        """
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")
        
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.repo_name = repo_name

    def close(self):
        """Closes the Neo4j driver connection."""
        if self.driver:
            self.driver.close()

    def build_from_directory(self, directory):
        """
        Walks through the local directory, finds Python files, and parses them.
        """
        print(f"🕸️ Building isolated graph for: {self.repo_name}")
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    # Create a clean relative path for the node name
                    rel_path = os.path.relpath(full_path, directory).replace("\\", "/")
                    self.parse_file_to_graph(full_path, rel_path)

    def parse_file_to_graph(self, full_path, rel_path):
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read())
            
            with self.driver.session() as session:
                # You MUST pass self.repo_name here as the third argument!
                session.execute_write(self._create_elements, rel_path, tree, self.repo_name)
        except Exception as e:
            print(f"❌ Error parsing {rel_path}: {str(e)}")
            
    @staticmethod
    def _create_elements(tx, file_name, tree, repo_name):
        # 1. Create the Module (File) Node
        tx.run("""
            MERGE (m:Module {name: $file, repo: $repo})
        """, file=file_name, repo=repo_name)

        for item in tree.body:
            # 2. Extract Classes
            if isinstance(item, ast.ClassDef):
                doc = ast.get_docstring(item) or "No description provided."
                tx.run("""
                    MATCH (m:Module {name: $file, repo: $repo})
                    MERGE (c:Class {name: $name, repo: $repo, module: $file})
                    SET c.description = $doc
                    MERGE (m)-[:DEFINES]->(c)
                """, file=file_name, name=item.name, repo=repo_name, doc=doc)

            # 3. Extract Standalone Functions
            elif isinstance(item, ast.FunctionDef):
                doc = ast.get_docstring(item) or "No description provided."
                tx.run("""
                    MATCH (m:Module {name: $file, repo: $repo})
                    MERGE (f:Function {name: $name, repo: $repo, module: $file})
                    SET f.description = $doc
                    MERGE (m)-[:DEFINES]->(f)
                """, file=file_name, name=item.name, repo=repo_name, doc=doc)

# Example usage (if run directly):
if __name__ == "__main__":
    # Ensure environment variables are loaded
    test_repo = "test_project"
    builder = CodeGraphBuilder(repo_name=test_repo)
    # builder.build_from_directory("./path_to_code")
    builder.close()