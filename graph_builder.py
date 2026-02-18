import ast
import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

# 1. Load your .env file credentials automatically
load_dotenv()

class CodeGraphBuilder:
    def __init__(self):
        # Use os.getenv to keep your password out of the code
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")
        
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def parse_file_to_graph(self, file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read())
        except Exception as e:
            print(f"❌ Could not read {file_path}: {e}")
            return

        file_name = os.path.basename(file_path)
        
        # 2. Use execute_write to ensure the database SAVES (commits) the data
        with self.driver.session(database="neo4j") as session:
            session.execute_write(self._create_elements, file_name, tree)

    @staticmethod
    def _create_elements(tx, file_name, tree):
        # Create the File Node
        tx.run("MERGE (m:Module {name: $name})", name=file_name)

        for item in tree.body:
            if isinstance(item, ast.ClassDef):
                tx.run("""
                    MATCH (m:Module {name: $file})
                    MERGE (c:Class {name: $name})
                    MERGE (m)-[:DEFINES]->(c)
                """, file=file_name, name=item.name)
            elif isinstance(item, ast.FunctionDef):
                tx.run("""
                    MATCH (m:Module {name: $file})
                    MERGE (f:Function {name: $name})
                    MERGE (m)-[:DEFINES]->(f)
                """, file=file_name, name=item.name)

    def build_from_directory(self, directory):
        # 3. Validation: Check if folder actually exists
        if not os.path.exists(directory):
            print(f"⚠️ Error: The directory '{directory}' does not exist!")
            return

        file_count = 0
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    print(f"🌲 Parsing AST for {file}...")
                    self.parse_file_to_graph(full_path)
                    file_count += 1
        
        if file_count == 0:
            print("⚠️ Warning: No .py files were found in that directory.")

if __name__ == "__main__":
    builder = CodeGraphBuilder()
    
    # Updated to match the "repos" folder we created in main.py
    # Change 'PWAI' to whatever repo you just cloned
    repo_folder = "./repos/PWAI" 
    
    builder.build_from_directory(repo_folder)
    builder.close()
    print("✅ Graph database build complete!")