import os
from dotenv import load_dotenv
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_groq import ChatGroq
from langchain_classic.chains import create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import HumanMessage, AIMessage
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

load_dotenv()
router = APIRouter()

print("Waking up the medical assistant...")

embedding_model = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    encode_kwargs={'normalize_embeddings': True},
)

vectorstore = Chroma(
    persist_directory="../chroma_db",
    collection_name="medical_books_15",
    embedding_function=embedding_model,
)
print(f"📦 Total chunks in DB: {vectorstore._collection.count()}")

retriever = vectorstore.as_retriever(
    search_type="mmr",
    search_kwargs={'k': 5, 'fetch_k': 20}
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
    "4. Do not guess or provide outside medical advice."
   "5. Format your response using clean Markdown. Use bullet points for lists, bold text for key terms, and clear paragraph breaks. Never output a single giant wall of text.\n\n"
    "Textbook Excerpts:\n{context}"
)

prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    ("human", "{input}"),
])

question_answer_chain = create_stuff_documents_chain(llm, prompt)
rag_chain = create_retrieval_chain(retriever, question_answer_chain)


class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    reply: str
    sources: List[str]  # empty list for casual, filled for medical



@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    global chat_history

    user_input = req.message

    if not user_input.strip():
        return ChatResponse(reply="Please enter a message.", sources=[])

    print(f"\nReceived: {user_input}")
    print("Bot is thinking...")

    better_query = rewriter.invoke({
        "input": user_input,
        "chat_history": chat_history
    })

    sources = []  # default empty — only populated on medical path

    if better_query.strip() == "ROUTE_TO_CHAT":
        print("💬 Routing to casual chat...")
        answer = casual_chain.invoke({
            "input": user_input,
            "chat_history": chat_history
        })
        # sources stays empty []

    else:
        print(f"🔍 Searching for: {better_query}")
        response = rag_chain.invoke({
            "input": better_query,
            "chat_history": chat_history
        })
        answer = response["answer"]

        # build deduplicated sources list
        unique_sources = set()
        for doc in response["context"]:
            book_title = doc.metadata.get('book_title', 'Unknown Source')
            page = doc.metadata.get('page', '?')
            unique_sources.add(f"{book_title} (Page {page})")
        sources = list(unique_sources)

    # update memory
    chat_history.append(HumanMessage(content=user_input))
    chat_history.append(AIMessage(content=answer))

    if len(chat_history) > 20:
        chat_history = chat_history[-20:]

    print(f"\nBOT: {answer}")
    print(f"Sources: {sources}")
    print("-" * 50)

    return ChatResponse(reply=answer, sources=sources)