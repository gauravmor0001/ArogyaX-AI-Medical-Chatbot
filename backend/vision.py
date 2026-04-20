import io
import fitz  # PyMuPDF
import torch
import torch.nn as nn
from PIL import Image
from torchvision import models, transforms
from dotenv import load_dotenv

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_chroma import Chroma
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import HumanMessage, AIMessage
from langchain_text_splitters import RecursiveCharacterTextSplitter

from fastapi import APIRouter, UploadFile, File, Form
from pydantic import BaseModel
from typing import List, Optional

load_dotenv()
router = APIRouter()

print("⏳ Waking up Computer Vision Models for Report Mode...")

# ─────────────────────────────────────────────
# 1. SETUP COMPUTER VISION MODELS
# ─────────────────────────────────────────────
# X-Ray Model
xray_model = models.densenet121(weights=models.DenseNet121_Weights.DEFAULT)
xray_model.classifier = nn.Linear(xray_model.classifier.in_features, 14)
xray_model.eval()

# MRI / Kidney Model
mri_model = models.resnet50(weights=models.ResNet50_Weights.DEFAULT)
mri_model.fc = nn.Linear(mri_model.fc.in_features, 4)
mri_model.eval()

xray_labels = [
    "Atelectasis", "Cardiomegaly", "Effusion", "Infiltration", "Mass",
    "Nodule", "Pneumonia", "Pneumothorax", "Consolidation", "Edema",
    "Emphysema", "Fibrosis", "Pleural Thickening", "Hernia"
]
mri_labels = ["Glioma", "Meningioma", "Pituitary Tumor", "No Tumor"]
kidney_labels = ["Normal", "Stone", "Cyst", "Tumor"]

img_transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
])

# ─────────────────────────────────────────────
# 2. HYBRID KNOWLEDGE SETUP (FAISS + CHROMA)
# ─────────────────────────────────────────────
embedding_model = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    encode_kwargs={"normalize_embeddings": True},
)

# We load a read-only instance of the textbook database to combine with the report
books_vectorstore = Chroma(
    persist_directory="./chroma_db",
    collection_name="medical_books_15",
    embedding_function=embedding_model,
)
books_retriever = books_vectorstore.as_retriever(search_kwargs={"k": 4})

llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.2)

# Hybrid Prompt (Combines Patient Report + Textbook Knowledge)
report_prompt = ChatPromptTemplate.from_messages([
    ("system", 
     "You are Arogya, a medical AI analyzing a patient's report. "
     "Use BOTH the patient's report and the medical textbooks to answer.\n\n"
     "--- Patient Report Findings ---\n{report_context}\n\n"
     "--- Medical Textbook Knowledge ---\n{books_context}\n\n"
     "Rule 1: Focus on the patient's specific findings.\n"
     "Rule 2: Add a disclaimer that you are an AI, not a doctor."
    ),
    MessagesPlaceholder("chat_history"),
    ("human", "{input}"),
])
report_chain = report_prompt | llm | StrOutputParser()

# ─────────────────────────────────────────────
# 3. SESSION MEMORY MANAGEMENT
# ─────────────────────────────────────────────
sessions: dict = {}

def get_session(session_id: str) -> dict:
    if session_id not in sessions:
        sessions[session_id] = {
            "report_db": None, 
            "chat_history": []
        }
    return sessions[session_id]

# ─────────────────────────────────────────────
# 4. IMAGE & TEXT EXTRACTION LOGIC
# ─────────────────────────────────────────────
def analyze_image(filename: str, img: Image.Image) -> str:
    name = filename.lower()
    tensor = img_transform(img).unsqueeze(0)
    
    with torch.no_grad():
        if "mri" in name or "kidney" in name:
            probs = torch.softmax(mri_model(tensor), dim=1)[0]
            pred = torch.argmax(probs).item()
            return f"Scan Result: {mri_labels[pred] if 'mri' in name else kidney_labels[pred]}"
        else:
            probs = torch.sigmoid(xray_model(tensor))[0]
            findings = [xray_labels[i] for i, p in enumerate(probs) if p > 0.5]
            return "X-ray Findings: " + (", ".join(findings) if findings else "No major abnormality detected")

def extract_pdf(file_bytes: bytes) -> str:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    return "".join([page.get_text() for page in doc])

# ─────────────────────────────────────────────
# 5. API ENDPOINTS
# ─────────────────────────────────────────────
@router.post("/report/upload")
async def upload_report(session_id: str = Form(...), pdf_file: Optional[UploadFile] = File(None), image_files: Optional[List[UploadFile]] = File(None)):
    session = get_session(session_id)
    all_texts, findings = [], []

    if pdf_file:
        pdf_text = extract_pdf(await pdf_file.read())
        all_texts.extend(RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50).split_text(pdf_text))
        
    if image_files:
        for img_file in image_files:
            img = Image.open(io.BytesIO(await img_file.read())).convert("RGB")
            result = analyze_image(img_file.filename, img)
            findings.append(result)
            all_texts.append(result)

    if not all_texts:
        return {"message": "No content extracted."}

    session["report_db"] = FAISS.from_texts(all_texts, embedding_model)
    session["chat_history"] = [] # Reset memory for new report
    return {"message": "Report processed.", "findings": findings}

class ReportChatRequest(BaseModel):
    session_id: str
    message: str

@router.post("/report/chat")
async def report_chat(req: ReportChatRequest):
    session = get_session(req.session_id)
    if not session["report_db"]:
        return {"reply": "Please upload a report first.", "sources": []}

    # Pull from BOTH databases
    report_docs = session["report_db"].similarity_search(req.message, k=4)
    book_docs = books_retriever.invoke(req.message)

    report_context = "\n".join(d.page_content for d in report_docs)
    books_context = "\n".join(d.page_content for d in book_docs)

    answer = report_chain.invoke({
        "input": req.message,
        "chat_history": session["chat_history"],
        "report_context": report_context,
        "books_context": books_context
    })

    # Update temporary memory
    session["chat_history"].extend([HumanMessage(content=req.message), AIMessage(content=answer)])
    
    return {"reply": answer, "sources": ["Uploaded Patient Report"] + [f"{d.metadata.get('book_title')} (Pg {d.metadata.get('page')})" for d in book_docs]}

@router.delete("/report/session/{session_id}")
async def clear_session(session_id: str):
    if session_id in sessions:
        del sessions[session_id]
    return {"message": "Memory wiped."}