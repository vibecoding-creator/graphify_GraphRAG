import os
import uuid
import json
import glob
import shutil
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, File, UploadFile, HTTPException, Body
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import aiofiles
from graph_builder import build_graph, GLOBAL_GRAPH_DIR

# graphify 내부 모듈
from graphify.build import build_from_json
from graphify.cluster import cluster
import graphify.export as ge

# AI 연동
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

app = FastAPI(
    title="Graphify Audit API",
    description="지식 그래프 기반 감사 리포트 분석 및 AI 채팅 서비스 API",
    version="1.0.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directories
CHATS_DIR = "global_out/chats"
os.makedirs("uploads", exist_ok=True)
os.makedirs(GLOBAL_GRAPH_DIR, exist_ok=True)
os.makedirs(CHATS_DIR, exist_ok=True)
os.makedirs("global_out/graphify-out", exist_ok=True)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class SessionInfo(BaseModel):
    id: str
    title: str

class DocInfo(BaseModel):
    run_id: str
    name: str

@app.get("/", include_in_schema=False)
async def read_root():
    async with aiofiles.open("templates/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=await f.read())

@app.post("/api/upload", tags=["Management"], response_model=dict)
async def upload_file_api(file: UploadFile = File(...)):
    if not file.filename.endswith(".md"):
        raise HTTPException(status_code=400, detail="Only markdown (.md) files are supported.")
    run_id = str(uuid.uuid4())
    upload_dir = os.path.join("uploads", run_id)
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, "input.md")
    async with aiofiles.open(file_path, "wb") as out_file:
        content = await file.read()
        await out_file.write(content)
    try:
        build_graph(file_path, upload_dir, run_id=run_id)
        return {"status": "success", "run_id": run_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/docs", tags=["Management"], response_model=List[DocInfo])
async def list_documents_api():
    json_files = glob.glob(os.path.join(GLOBAL_GRAPH_DIR, "*.json"))
    docs = []
    for jf in json_files:
        run_id = Path(jf).stem
        try:
            with open(jf, "r", encoding="utf-8") as f:
                data = json.load(f)
            doc_name = "Untitled"
            for node in data.get("nodes", []):
                sf = node.get("source_file", "")
                if "__SPLIT__" in sf:
                    doc_name = sf.split("__SPLIT__")[1]
                    break
            docs.append({"run_id": run_id, "name": doc_name})
        except: continue
    return docs

@app.delete("/api/docs/{run_id}", tags=["Management"])
async def delete_document_api(run_id: str):
    target = os.path.join(GLOBAL_GRAPH_DIR, f"{run_id}.json")
    if os.path.exists(target): os.remove(target)
    return {"status": "success"}

@app.get("/api/graph/view/{run_id}", tags=["Visualization"])
async def get_graph_html(run_id: str):
    graph_path = os.path.join("uploads", run_id, "graphify-out", "graph.html")
    if not os.path.exists(graph_path): raise HTTPException(status_code=404)
    return FileResponse(graph_path)

@app.get("/api/chat/sessions", tags=["AI Chat"], response_model=List[SessionInfo])
async def get_chat_sessions_api():
    files = glob.glob(os.path.join(CHATS_DIR, "*.json"))
    sessions = []
    for f in files:
        with open(f, "r", encoding="utf-8") as jf:
            try:
                data = json.load(jf)
                title = data[0]["content"][:40] + "..." if data else "New Chat"
                sessions.append({"id": Path(f).stem, "title": title})
            except: continue
    return sessions

@app.delete("/api/chat/sessions/{session_id}", tags=["AI Chat"])
async def delete_session_api(session_id: str):
    path = os.path.abspath(os.path.join(CHATS_DIR, f"{session_id}.json"))
    if os.path.exists(path):
        os.remove(path)
        return {"status": "success"}
    raise HTTPException(status_code=404)

@app.get("/api/chat/history/{session_id}", tags=["AI Chat"], response_model=List[dict])
async def get_chat_history_api(session_id: str):
    path = os.path.join(CHATS_DIR, f"{session_id}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    return []

@app.post("/api/chat", tags=["AI Chat"])
async def chat_api(request: ChatRequest):
    if not GOOGLE_API_KEY: raise HTTPException(status_code=500)
    user_query = request.message
    session_id = request.session_id or str(uuid.uuid4())
    graph_path = "global_out/graphify-out/graph.json"
    
    if not os.path.exists(graph_path):
        def err(): yield "그래프 데이터가 없습니다."
        return StreamingResponse(err(), media_type="text/plain")

    session_path = os.path.join(CHATS_DIR, f"{session_id}.json")
    history = []
    if os.path.exists(session_path):
        with open(session_path, "r", encoding="utf-8") as f: history = json.load(f)

    # 1. 그래프 데이터 로드 및 강화된 키워드 검색
    with open(graph_path, "r", encoding="utf-8") as f:
        graph = json.load(f)
    
    keywords = [k for k in user_query.split() if len(k) >= 2]
    relevant_ids = set()
    for node in graph.get("nodes", []):
        label = node.get("label", "").lower()
        desc = node.get("description", "").lower()
        if any(k.lower() in label or k.lower() in desc for k in keywords):
            relevant_ids.add(node["id"])

    context_lines = []
    seen_entities = set()
    seen_rels = set()
    
    for node in graph.get("nodes", []):
        if node["id"] in relevant_ids:
            context_lines.append(f"Entity: {node['label']}\n  - 상세내용: {node.get('description','')}")
            seen_entities.add(node["id"])

    for edge in graph.get("links", []):
        if edge["source"] in relevant_ids or edge["target"] in relevant_ids:
            src = next((n for n in graph["nodes"] if n["id"] == edge["source"]), None)
            tgt = next((n for n in graph["nodes"] if n["id"] == edge["target"]), None)
            if src and tgt:
                rel_str = f"Relation: {src['label']} --({edge.get('relation')})--> {tgt['label']}"
                if rel_str not in seen_rels:
                    context_lines.append(rel_str)
                    seen_rels.add(rel_str)

    context = "\n".join(context_lines[:100])
    history_text = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in history[-8:]])
    
    prompt = f"""당신은 전문 감사 분석가입니다. [Graph Context]를 기반으로 질문에 상세히 답하세요.
[Graph Context]
{context if context else "관계 정보 없음"}

[History]
{history_text if history_text else "첫 대화"}

[Question]
{user_query}

지시: 전문적 어조, 한국어 답변, 표(Table) 활용 권장."""

    async def stream_generator():
        full_res = ""
        try:
            model = genai.GenerativeModel("gemini-2.5-flash-lite")
            response = model.generate_content(prompt, stream=True)
            for chunk in response:
                if chunk.text:
                    full_res += chunk.text
                    yield chunk.text
            history.append({"role": "user", "content": user_query})
            history.append({"role": "ai", "content": full_res})
            with open(session_path, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            yield f"\n\n__SESSION_ID__{session_id}"
        except Exception as e:
            yield f"\n\n[AI Error]: {str(e)}"

    return StreamingResponse(stream_generator(), media_type="text/plain")

def _fix_global_html(html_path, doc_count):
    with open(html_path, "r", encoding="utf-8") as f: html = f.read()
    top_bar = f'<div style="position:fixed;top:12px;right:16px;z-index:9999;display:flex;gap:8px;"><span style="color:#aaa;font-size:12px;">{doc_count} docs</span><a href="/" style="background:#374151;color:#fff;padding:6px 12px;border-radius:6px;text-decoration:none;font-size:12px;">← Home</a></div>'
    if "← Home" not in html: html = html.replace("<body>", "<body>" + top_bar)
    with open(html_path, "w", encoding="utf-8") as f: f.write(html)

def _empty_global_page():
    return """<html><body style="background:#fff;display:flex;justify-content:center;align-items:center;height:100vh;"><div>No data. <a href="/">Back</a></div></body></html>"""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
