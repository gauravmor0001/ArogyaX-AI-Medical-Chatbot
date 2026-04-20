import os
from dotenv import load_dotenv
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_groq import ChatGroq
from langchain_classic.chains import create_retrieval_chain #takes user input → fetches relevant docs → passes both to LLM
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
# create_stuff_documents_chain: "stuffs" all retrieved document chunks
# into the prompt as a single context block for the LLM to read
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder # ChatPromptTemplate: builds structured prompts with system + human message roles
from langchain_core.output_parsers import StrOutputParser
# StrOutputParser: extracts plain string text from the LLM's response object
# LLM returns an AIMessage object, this converts it to a simple string
from langchain_core.messages import HumanMessage, AIMessage

load_dotenv()
print("Waking up the medical assistant...")
embedding_model = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    encode_kwargs={'normalize_embeddings': True},
)
# import chromadb
# client = chromadb.PersistentClient(path="./chroma_db")
# print("🔍 Collections found in database:")
# for collection in client.list_collections():
#     print(f" - {collection.name}")

vectorstore = Chroma(
    persist_directory="./chroma_db",
    collection_name="medical_books_15",
    embedding_function=embedding_model,
)
print(f"📦 Total chunks in DB: {vectorstore._collection.count()}")
retriever = vectorstore.as_retriever(
    search_type="mmr",
    # mmr = Maximum Marginal Relevance
    # instead of returning the 5 most similar chunks (which can be repetitive),
    # MMR balances relevance AND diversity — avoids returning near-duplicate chunks
    # example: without MMR you might get 5 chunks all saying the same thing about fever
    
    search_kwargs={
        'k': 5,
        'fetch_k': 20
        # fetch_k: ChromaDB first fetches 20 candidates by similarity,
        # then MMR picks the best 5 from those 20 (diverse + relevant)
    }
)

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0.2,
    max_tokens=1024,
)
chat_history = []

rewrite_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a strict search query generator for a medical database. "
     "If the user asks a medical question, rewrite it into a short, concise search string. "
     "CRITICAL RULE: If the user is just saying hello, greeting you, or making casual small talk "
     "(like 'hi', 'hello', 'thanks'), you MUST output EXACTLY this word and nothing else: ROUTE_TO_CHAT\n"
     "Example 1: 'what are the symptoms of diabetes?' -> 'symptoms of diabetes'\n"
     "Example 2: 'hello there' -> 'ROUTE_TO_CHAT'\n"
     "Example 3: 'thanks!' -> 'ROUTE_TO_CHAT'"
    ),
    MessagesPlaceholder("chat_history"),
    ("human", "{input}"),
])
rewriter = rewrite_prompt | llm | StrOutputParser()
# this is a LangChain LCEL pipeline (|  = pipe operator, like Linux)
# step 1: rewrite_prompt formats the user input into the prompt template
# step 2: llm generates the rewritten query
# step 3: StrOutputParser strips it to a plain string

casual_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a friendly medical AI assistant. "
     "The user is making casual conversation — respond warmly and naturally. "
     "You can remind them you're here for medical questions, but don't be pushy."
    ),
    MessagesPlaceholder("chat_history"),
    ("human", "{input}"),
])
casual_chain = casual_prompt | llm | StrOutputParser()


system_prompt = (
    "You are a professional, empathetic medical AI assistant speaking directly to a user. "
    "You are equipped with a highly accurate medical database. Use ONLY the provided excerpts to answer. "
    "CRITICAL RULES: "
    "1. Never say 'According to the context' or 'The text states'. State facts directly. "
    "2. If the question is not medical, say: please ask questions related to healthcare. "
    "3. If the answer is not in the excerpts, say: I cannot answer this based on my medical database. "
    "4. Do not guess or provide outside medical advice.\n\n"
    "Textbook Excerpts:\n{context}"
)


prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    ("human", "{input}"),
])

question_answer_chain = create_stuff_documents_chain(llm, prompt)
# combines the LLM + prompt into one unit
# when called, it stuffs all retrieved chunks into {context} and runs the prompt

rag_chain = create_retrieval_chain(retriever, question_answer_chain)

print("System Ready! Type 'exit' or 'quit' to stop.\n")
print("-" * 50)

while True:
    user_input = input("\nYOU: ")
    
    if user_input.lower() in ['exit', 'quit']:
        print("Goodbye! Stay healthy.")
        break
        
    if not user_input.strip():
        continue
        
    print("Bot is thinking...")
    
    better_query = rewriter.invoke({"input": user_input, "chat_history": chat_history})
    if better_query.strip() == "ROUTE_TO_CHAT":
        # ── CASUAL PATH: no vector search, no sources ─────────────────
        print("💬 Routing to casual chat...")
        answer = casual_chain.invoke({
            "input": user_input,
            "chat_history": chat_history
        })
        print(f"\n BOT: {answer}")
        # no sources block here — nothing was retrieved

    else:
        # ── MEDICAL PATH: vector search + RAG ─────────────────────────
        print(f"🔍 Searching for: {better_query}")
        response = rag_chain.invoke({
            "input": better_query,
            "chat_history": chat_history
        })
        answer = response["answer"]
        print(f"\n BOT: {answer}")

        # sources only shown on medical path
        print("\n📚 Sources used:")
        unique_sources = set()
        for doc in response["context"]:
            book_title = doc.metadata.get('book_title', 'Unknown Source')
            page = doc.metadata.get('page', '?')
            unique_sources.add(f"  - {book_title} (Page {page})")
        for source in unique_sources:
            print(source)

    # STEP 3: Update memory regardless of which path was taken
    chat_history.append(HumanMessage(content=user_input))
    chat_history.append(AIMessage(content=answer))

    if len(chat_history) > 20:
        chat_history = chat_history[-20:]

    print("-" * 50)
    print("\n DISCLAIMER: I am an AI, not a doctor. This is for educational purposes only.")