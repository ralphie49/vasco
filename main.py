import os
import stat
import shutil
from dotenv import load_dotenv
from git import Repo

# AI and Vector Search Imports
from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings, ChatNVIDIA
from langchain_community.document_loaders import GitLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter, Language
from langchain_community.vectorstores import FAISS
from langchain_classic.chains import RetrievalQA

# Local Module Imports
from graph_builder import CodeGraphBuilder
from auto_doc import RepoManualEngine

load_dotenv()

def remove_readonly(func, path, excinfo):
    """Helper to handle git's read-only file permissions during deletion."""
    os.chmod(path, stat.S_IWRITE)
    func(path)

class AdaptiveFaissAssistant:
    def __init__(self, storage_dir="./faiss_index_storage", repos_dir="./repos"):
        self.storage_dir = storage_dir
        self.repos_dir = repos_dir
        
        # Ensure base directories exist
        for d in [self.storage_dir, self.repos_dir]:
            if not os.path.exists(d): 
                os.makedirs(d)
            
        self.embeddings = NVIDIAEmbeddings(model="nvidia/nv-embedcode-7b-v1")
        self.llm = ChatNVIDIA(model="meta/llama-3.3-70b-instruct")
        self.vector_db = None
        self.current_repo = None

    def load_repo(self, repo_name):
        """Loads an existing FAISS index from disk for a specific repo."""
        save_path = os.path.join(self.storage_dir, repo_name)
        if os.path.exists(save_path):
            print(f"🔄 Loading vector index for: {repo_name}...")
            self.vector_db = FAISS.load_local(
                save_path, 
                self.embeddings, 
                allow_dangerous_deserialization=True
            )
            self.current_repo = repo_name
            return True
        return False

    def ingest_repository(self, repo_url):
        """Clones a repo, builds a FAISS index, and populates Neo4j."""
        repo_name = repo_url.split("/")[-1].replace(".git", "")
        repo_path = os.path.join(self.repos_dir, repo_name)
        save_path = os.path.join(self.storage_dir, repo_name)

        # 1. Clean previous clone if it exists
        if os.path.exists(repo_path):
            print(f"🧹 Cleaning up old files for {repo_name}...")
            shutil.rmtree(repo_path, onerror=remove_readonly)
        
        # 2. Clone Repository
        print(f"📥 Cloning {repo_url}...")
        repo = Repo.clone_from(repo_url, repo_path)
        
        # 3. Load and Split Code
        loader = GitLoader(
            repo_path=repo_path, 
            branch=repo.active_branch.name, 
            file_filter=lambda fp: fp.endswith((".py", ".md"))
        )
        documents = loader.load()

        splitter = RecursiveCharacterTextSplitter.from_language(
            language=Language.PYTHON, 
            chunk_size=1000, 
            chunk_overlap=150
        )
        chunks = splitter.split_documents(documents)

        # 4. Create and Save FAISS Index
        print(f"🧬 Indexing {len(chunks)} chunks for {repo_name}...")
        self.vector_db = FAISS.from_documents(chunks, self.embeddings)
        self.vector_db.save_local(save_path)
        self.current_repo = repo_name

        # 5. Build Neo4j Graph
        print(f"🌲 Building Neo4j Graph for {repo_name}...")
        try:
            builder = CodeGraphBuilder(repo_name=repo_name)
            # Add this print to verify the path exists
            print(f"DEBUG: Looking for files in {repo_path}") 
            builder.build_from_directory(repo_path)
            builder.close()
            print("✅ Graph Builder finished its job.")
        except Exception as e:
            print(f"❌ CRITICAL NEO4J ERROR: {e}")
        
        
        print(f"✅ Ingestion of {repo_name} complete.")

    def query(self, user_question):
        """Runs a RAG query against the currently loaded vector database."""
        if not self.vector_db:
            return "⚠️ No repository loaded. Please ingest or switch to a repo first."
        
        qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm, 
            chain_type="stuff", 
            retriever=self.vector_db.as_retriever()
        )
        response = qa_chain.invoke(user_question)
        return response["result"]

if __name__ == "__main__":
    assistant = AdaptiveFaissAssistant()
    book_gen = RepoManualEngine()
    
    while True:
        status = f" [Active: {assistant.current_repo}]" if assistant.current_repo else " [No Repo Loaded]"
        print(f"\n--- 🛠️ MULTI-REPO MANAGER{status} ---")
        print("1. Ingest New Repository (GitHub URL)")
        print("2. Switch/Load Existing Repository (Name)")
        print("3. Generate Technical Reference Book (.md)")
        print("4. Chat with Repository (Q&A)")
        print("5. Exit")
        
        choice = input("\nSelect an option (1-5): ").strip()

        if choice == '1':
            url = input("🔗 Enter GitHub URL: ").strip()
            if url:
                assistant.ingest_repository(url)
        
        elif choice == '2':
            name = input("📂 Enter Repo Name to Load: ").strip()
            if not assistant.load_repo(name):
                print(f"❌ No index found for '{name}'. Please ingest it first.")
        
        elif choice == '3':
            name = input("📖 Enter Repo Name to generate book for: ").strip()
            # This uses Neo4j to build the book
            book_gen.generate(name)
            
        elif choice == '4':
            if not assistant.current_repo:
                print("⚠️ Please load a repository (Option 2) before chatting.")
                continue
            question = input(f"❓ [{assistant.current_repo}] Question: ")
            print(f"\n🔍 Searching context...\n\n🤖 AI:\n{assistant.query(question)}")

        elif choice == '5':
            print("👋 Goodbye!")
            book_gen.close()
            break
        else:
            print("Invalid choice, please try again.")