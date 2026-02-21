import os
import stat
import shutil
from dotenv import load_dotenv
from git import Repo

from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings, ChatNVIDIA
from langchain_community.document_loaders import GitLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_classic.chains import create_retrieval_chain

from graph_builder import CodeGraphBuilder
from auto_doc import RepoManualEngine

load_dotenv()

def remove_readonly(func, path, excinfo):
    os.chmod(path, stat.S_IWRITE)
    func(path)

class AdaptiveFaissAssistant:
    def __init__(self, storage_dir="./faiss_index_storage", repos_dir="./repos"):
        self.storage_dir = storage_dir
        self.repos_dir = repos_dir
        for d in [self.storage_dir, self.repos_dir]:
            if not os.path.exists(d): os.makedirs(d)
            
        self.embeddings = NVIDIAEmbeddings(model="nvidia/nv-embedcode-7b-v1")
        self.llm = ChatNVIDIA(model="meta/llama-3.3-70b-instruct")
        self.vector_db = None
        self.current_repo = None

    def ingest_repository(self, repo_url=None, local_path=None):
        """Handles both new clones and switching to existing local repos."""
        if repo_url:
            repo_name = repo_url.split("/")[-1].replace(".git", "")
            repo_path = os.path.join(self.repos_dir, repo_name)
        else:
            repo_name = os.path.basename(local_path)
            repo_path = local_path

        save_path = os.path.join(self.storage_dir, repo_name)

        # 1. Clean up Neo4j for fresh ingestion
        builder = CodeGraphBuilder(repo_name=repo_name)
        builder.clear_database()

        # Only clone if a URL is provided and path doesn't exist
        if repo_url:
            if os.path.exists(repo_path):
                shutil.rmtree(repo_path, onerror=remove_readonly)
            print(f"📥 Cloning {repo_url}...")
            repo_obj = Repo.clone_from(repo_url, repo_path)
            branch_name = repo_obj.active_branch.name
        else:
            print(f"🔄 Switching to existing local repo: {repo_name}...")
            repo_obj = Repo(repo_path)
            branch_name = repo_obj.active_branch.name

        # 2. Vectorize code
        loader = GitLoader(
            repo_path=repo_path, 
            branch=branch_name, 
            file_filter=lambda fp: fp.endswith((".py", ".md", ".html", ".css", ".js"))
        )
        documents = loader.load()
        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
        chunks = splitter.split_documents(documents)

        print(f"🧬 Vectorizing {len(chunks)} chunks...")
        self.vector_db = FAISS.from_documents(chunks, self.embeddings)
        self.vector_db.save_local(save_path)
        self.current_repo = repo_name

        # 3. Build Dependency Graph
        print(f"🌲 Building Graph...")
        builder.build_from_directory(repo_path)
        builder.close()
        print(f"✅ Ingestion of {repo_name} complete.")

    def switch_to_local_repo(self, repo_name):
        """Checks if repo exists in /repos and ingests it."""
        target_path = os.path.join(self.repos_dir, repo_name)
        if os.path.exists(target_path):
            self.ingest_repository(local_path=target_path)
            return True
        else:
            print(f"❌ Repo '{repo_name}' not found in {self.repos_dir}")
            return False

    def query(self, user_question):
        if not self.vector_db: return "⚠️ Load a repo first."
        
        system_prompt = (
            "You are a technical assistant for a software repository. "
            "Use the following pieces of retrieved context to answer the question. "
            "\n\n{context}"
        )
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{input}"),
        ])

        question_answer_chain = create_stuff_documents_chain(self.llm, prompt)
        rag_chain = create_retrieval_chain(self.vector_db.as_retriever(), question_answer_chain)
        
        response = rag_chain.invoke({"input": user_question})
        return response["answer"]

if __name__ == "__main__":
    assistant = AdaptiveFaissAssistant()
    book_gen = RepoManualEngine()
    
    while True:
        status = f" [Active: {assistant.current_repo}]" if assistant.current_repo else " [No Repo Loaded]"
        print(f"\n--- 🛠️ REPO MANAGER{status} ---")
        print("1. Ingest New Repository (Clone from GitHub)")
        print("2. Switch to Existing Local Repository (Wipes & Re-builds Graph)")
        print("3. Generate Technical Manual")
        print("4. Chat with Repo")
        print("5. Exit")
        
        choice = input("\nSelect (1-5): ").strip()
        
        if choice == '1':
            url = input("🔗 GitHub URL: ").strip()
            if url: assistant.ingest_repository(repo_url=url)
            
        elif choice == '2':
            existing = [d for d in os.listdir("./repos") if os.path.isdir(os.path.join("./repos", d))]
            print(f"Available Repos: {existing}")
            name = input("📁 Enter folder name of repo: ").strip()
            assistant.switch_to_local_repo(name)

        elif choice == '3':
            if not assistant.current_repo:
                print("⚠️ Please ingest a repo first.")
            else:
                book_gen.generate_book(assistant.current_repo)
                
        elif choice == '4':
            if not assistant.current_repo:
                print("⚠️ Load a repo first.")
                continue
            question = input(f"❓ Question: ")
            print(f"\n🤖 AI:\n{assistant.query(question)}")
            
        elif choice == '5':
            book_gen.close()
            break