import os
import stat
import shutil
from dotenv import load_dotenv
from git import Repo

from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings, ChatNVIDIA
from langchain_community.document_loaders import GitLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_classic.chains import RetrievalQA

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
            
        # Model Configuration
        self.embeddings = NVIDIAEmbeddings(model="nvidia/nv-embedcode-7b-v1")
        self.llm = ChatNVIDIA(model="meta/llama-3.3-70b-instruct")
        self.vector_db = None
        self.current_repo = None

    def ingest_repository(self, repo_url):
        repo_name = repo_url.split("/")[-1].replace(".git", "")
        repo_path = os.path.join(self.repos_dir, repo_name)
        save_path = os.path.join(self.storage_dir, repo_name)

        # 1. Clean up Neo4j for fresh ingestion
        builder = CodeGraphBuilder(repo_name=repo_name)
        builder.clear_database()

        if os.path.exists(repo_path):
            shutil.rmtree(repo_path, onerror=remove_readonly)
        
        print(f"📥 Cloning {repo_url}...")
        repo = Repo.clone_from(repo_url, repo_path)
        
        # 2. Vectorize code and assets
        loader = GitLoader(
            repo_path=repo_path, 
            branch=repo.active_branch.name, 
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

    def query(self, user_question):
        if not self.vector_db: return "⚠️ Load a repo first."
        
        # Define the system prompt for the modern chain
        system_prompt = (
            "You are a technical assistant for a software repository. "
            "Use the following pieces of retrieved context to answer the question. "
            "If you don't know the answer, say that you don't know. "
            "\n\n"
            "{context}"
        )
        
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("human", "{input}"),
            ]
        )

        # Create the modern RAG pipeline
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
        print("1. Ingest/Re-Ingest Repository (Wipes Graph)")
        print("2. Generate Technical Manual (Saved to /output_docs)")
        print("3. Chat with Repo")
        print("4. Exit")
        
        choice = input("\nSelect (1-4): ").strip()
        
        if choice == '1':
            url = input("🔗 GitHub URL: ").strip()
            if url: assistant.ingest_repository(url)
            
        elif choice == '2':
            if not assistant.current_repo:
                print("⚠️ Please ingest a repo first.")
            else:
                book_gen.generate_book(assistant.current_repo)
                
        elif choice == '3':
            if not assistant.current_repo:
                print("⚠️ Load a repo first.")
                continue
            question = input(f"❓ Question: ")
            print(f"\n🤖 AI:\n{assistant.query(question)}")
            
        elif choice == '4':
            book_gen.close()
            break