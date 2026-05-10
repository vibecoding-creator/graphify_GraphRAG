# Graphify Audit AI Service (GraphRAG)

지식 그래프(Knowledge Graph)를 기반으로 감사 리포트(3F Report)를 분석하고, AI와 대화하며 인사이트를 얻을 수 있는 지능형 대시보드입니다.

## 🚀 주요 기능
- **GraphRAG 기반 채팅**: 단순 검색을 넘어 지식 그래프의 관계 정보를 활용한 정밀한 AI 답변
- **통합 대시보드**: 여러 리포트를 하나의 그래프로 병합하여 분석
- **현대적인 UI**: ShadCN 스타일의 깔끔한 4:6 분할 인터페이스
- **API 서비스**: 외부 프론트엔드 연동이 가능한 표준 API 제공

## 🛠 시작하기 (uv 사용)

이 프로젝트는 `uv`를 사용하여 의존성을 관리합니다.

### 1. 환경 변수 설정
`.env.example` 파일을 복사하여 `.env` 파일을 만들고, Google Gemini API 키를 입력하세요.
```bash
cp .env.example .env
# .env 파일을 열어 GOOGLE_API_KEY=your_key_here 입력
```

### 2. 서버 실행
아래 명령어를 입력하면 의존성 설치부터 서버 실행까지 한 번에 진행됩니다.
```bash
uv run uvicorn app:app --port 8000 --reload
```

### 3. 접속
브라우저에서 `http://127.0.0.1:8000`에 접속하세요.

## 📂 프로젝트 구조
- `app.py`: FastAPI 기반 메인 API 서버
- `graph_builder.py`: 리포트 분석 및 그래프 생성 엔진
- `templates/`: 프론트엔드 UI (HTML/Tailwind)
- `clean_project/`: 배포용 클린 소스코드
