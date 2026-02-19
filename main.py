import os
import stat
import shutil
from dotenv import load_dotenv
from git import Repo
from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings, ChatNVIDIA
from langchain_community.document_loaders import GitLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter, Language
from langchain_community.vectorstores import FAISS
from langchain_classic.chains import RetrievalQA

load_dotenv()

def remove_readonly(func, path, excinfo):
    os.chmod(path, stat.S_IWRITE)
    func(path)

class AdaptiveFaissAssistant:
    def __init__(self, storage_dir="./faiss_index_storage", repos_dir="./repos"):
        self.storage_dir = storage_dir
        self.repos_dir = repos_dir
        # Create the repos directory if it doesn't exist
        if not os.path.exists(self.repos_dir):
            os.makedirs(self.repos_dir)
            
        self.embeddings = NVIDIAEmbeddings(model="nvidia/nv-embedcode-7b-v1")
        self.llm = ChatNVIDIA(model="meta/llama-3.3-70b-instruct")
        self.vector_db = None
        self.current_k = 5

    def ingest_repository(self, repo_url):
        repo_name = repo_url.split("/")[-1].replace(".git", "")
        save_path = os.path.join(self.storage_dir, repo_name)
        # CHANGED: Repos now live in a dedicated subfolder
        repo_path = os.path.join(self.repos_dir, repo_name)

        # 1. Check if we can skip cloning/indexing
        """if os.path.exists(save_path) and os.path.exists(repo_path):
            print(f"⚡ Loading existing FAISS index and local files for {repo_name}...")
            self.vector_db = FAISS.load_local(
                save_path, self.embeddings, allow_dangerous_deserialization=True
            )
            self.current_k = 10 if self.vector_db.index.ntotal > 500 else 5
            return"""

        # 2. Fresh Processing if files are missing
        if os.path.exists(repo_path):
            shutil.rmtree(repo_path, onerror=remove_readonly)
        
        print(f"📥 Cloning {repo_url} into {repo_path}...")
        repo = Repo.clone_from(repo_url, repo_path)
        
        loader = GitLoader(
            repo_path=repo_path,
            branch=repo.active_branch.name,
            file_filter=lambda fp: fp.endswith((".py", ".js", ".ts", ".md", ".cpp"))
        )
        documents = loader.load()
        num_files = len(documents)

        # --- AUTO-SCALING LOGIC ---
        if num_files > 150:
            c_size, c_overlap, self.current_k = 600, 100, 12
            mode = "Large Scale (Precision)"
        elif num_files > 50:
            c_size, c_overlap, self.current_k = 1000, 150, 8
            mode = "Medium Scale (Balanced)"
        else:
            c_size, c_overlap, self.current_k = 1500, 200, 5
            mode = "Small Scale (Context-Heavy)"
        
        print(f"📊 Mode: {mode} | Files: {num_files} | Chunk Size: {c_size} | k: {self.current_k}")

        splitter = RecursiveCharacterTextSplitter.from_language(
            language=Language.PYTHON, 
            chunk_size=c_size, 
            chunk_overlap=c_overlap
        )
        chunks = splitter.split_documents(documents)

        # 3. FAISS Indexing
        print(f"🧬 Creating FAISS index for {len(chunks)} chunks...")
        self.vector_db = FAISS.from_documents(chunks, self.embeddings)
        self.vector_db.save_local(save_path)
        
        # --- BUILD NEO4J GRAPH ---
        print("🌲 Building AST Graph in Neo4j...")
        # --- BUILD NEO4J GRAPH ---
        repo_name = repo_url.split("/")[-1].replace(".git", "") # Extract name from URL
        try:
            from graph_builder import CodeGraphBuilder
            graph_builder = CodeGraphBuilder(repo_name=repo_name) # Pass the name here
            graph_builder.build_from_directory(repo_path)
            graph_builder.close()
        except Exception as e:
            print(f"❌ Neo4j Error: {e}")

        print("✅ Ingestion complete.")

    def query(self, user_question):
        if not self.vector_db:
            return "Please ingest a repository first."
        qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            chain_type="stuff",
            retriever=self.vector_db.as_retriever(search_kwargs={"k": self.current_k})
        )
        return qa_chain.invoke(user_question)["result"]

if __name__ == "__main__":
    assistant = AdaptiveFaissAssistant()
    
    print("--- 🚀 NVIDIA ADAPTIVE FAISS ASSISTANT ---")
    repo_url = input("🔗 Enter GitHub URL: ").strip()
    assistant.ingest_repository(repo_url)
    
    while True:
        user_input = input("\n❓ Question (or 'exit'): ").strip()
        if user_input.lower() in ['exit', 'quit']:
            break
        
        print("🔍 Searching and generating...")
        print(f"\n🤖 AI:\n{assistant.query(user_input)}")