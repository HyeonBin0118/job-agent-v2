import streamlit as st
import httpx
from bs4 import BeautifulSoup
from openai import OpenAI
import fitz
import json
import os
from dotenv import load_dotenv

load_dotenv()


api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    try:
        api_key = st.secrets["OPENAI_API_KEY"]
    except Exception:
        pass
client = OpenAI(api_key=api_key)

def crawl_job_posting(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    response = httpx.get(url, headers=headers, follow_redirects=True, timeout=10)
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    lines = [line.strip() for line in soup.get_text(separator="\n").splitlines() if line.strip()]
    return "\n".join(lines)


def extract_job_info(content: str) -> dict:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": f"""
아래 채용공고 텍스트에서 다음 항목을 JSON으로 추출해줘.
- company, position, required_skills, preferred_skills, experience, summary
텍스트: {content}
JSON만 반환해.
"""}],
        temperature=0
    )
    result = response.choices[0].message.content.replace("```json", "").replace("```", "").strip()
    return json.loads(result)


def parse_resume(file) -> str:
    doc = fitz.open(stream=file.read(), filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text.strip()


def match_resume_to_job(resume_text: str, job_info: dict) -> dict:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": f"""
이력서와 채용공고를 비교해서 JSON으로 반환해줘.
- matched_skills, missing_skills, score(0~100), summary
채용공고: {json.dumps(job_info, ensure_ascii=False)}
이력서: {resume_text[:3000]}
JSON만 반환해.
"""}],
        temperature=0
    )
    result = response.choices[0].message.content.replace("```json", "").replace("```", "").strip()
    return json.loads(result)


def generate_cover_letter(resume_text: str, job_info: dict, match_result: dict) -> dict:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": f"""
이력서, 채용공고, 매칭 결과를 바탕으로 자소서 초안을 작성해줘.
항목: motivation(지원동기), experience(직무경험), goal(입사후포부)
각 항목 200자 내외로 작성해줘.
채용공고: {json.dumps(job_info, ensure_ascii=False)}
매칭결과: {json.dumps(match_result, ensure_ascii=False)}
이력서: {resume_text[:3000]}
JSON만 반환해.
"""}],
        temperature=0.7
    )
    result = response.choices[0].message.content.replace("```json", "").replace("```", "").strip()
    return json.loads(result)


st.set_page_config(page_title="Job Agent", layout="wide")
st.title("🤖 Job Agent")
st.caption("채용공고 분석 · 이력서 매칭 · 자소서 생성 자동화")

tab1, tab2, tab3 = st.tabs(["📋 공고 분석", "📊 이력서 매칭", "✍️ 자소서 생성"])

with tab1:
    st.subheader("채용공고 분석")
    job_url = st.text_input("채용공고 URL을 입력하세요")
    if st.button("분석 시작"):
        if not job_url:
            st.warning("URL을 입력해주세요")
        else:
            with st.spinner("분석 중..."):
                try:
                    job_content = crawl_job_posting(job_url)
                    job_info = extract_job_info(job_content)
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("회사", job_info.get("company", "-"))
                        st.metric("직무", job_info.get("position", "-"))
                        st.metric("경력", job_info.get("experience", "-"))
                    with col2:
                        st.write("**필수 스킬**")
                        for skill in job_info.get("required_skills", []):
                            st.badge(skill)
                        st.write("**우대 스킬**")
                        for skill in job_info.get("preferred_skills", []):
                            st.badge(skill)
                    st.info(job_info.get("summary", ""))
                except Exception as e:
                    st.error(f"분석 실패: {e}")

with tab2:
    st.subheader("이력서 매칭 분석")
    job_url2 = st.text_input("채용공고 URL", key="url2")
    resume_file2 = st.file_uploader("이력서 PDF 업로드", type=["pdf"], key="resume2")
    if st.button("매칭 분석"):
        if not job_url2 or not resume_file2:
            st.warning("URL과 이력서를 모두 입력해주세요")
        else:
            with st.spinner("분석 중..."):
                try:
                    job_content = crawl_job_posting(job_url2)
                    job_info = extract_job_info(job_content)
                    resume_text = parse_resume(resume_file2)
                    match_result = match_resume_to_job(resume_text, job_info)
                    st.metric("매칭 점수", f"{match_result.get('score', 0)} / 100")
                    st.info(match_result.get("summary", ""))
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**✅ 보유 스킬**")
                        for skill in match_result.get("matched_skills", []):
                            st.badge(skill)
                    with col2:
                        st.write("**❌ 부족한 스킬**")
                        for skill in match_result.get("missing_skills", []):
                            st.badge(skill)
                except Exception as e:
                    st.error(f"분석 실패: {e}")

with tab3:
    st.subheader("자소서 초안 생성")
    job_url3 = st.text_input("채용공고 URL", key="url3")
    resume_file3 = st.file_uploader("이력서 PDF 업로드", type=["pdf"], key="resume3")
    if st.button("자소서 생성"):
        if not job_url3 or not resume_file3:
            st.warning("URL과 이력서를 모두 입력해주세요")
        else:
            with st.spinner("생성 중... (30초 정도 걸려요)"):
                try:
                    job_content = crawl_job_posting(job_url3)
                    job_info = extract_job_info(job_content)
                    resume_text = parse_resume(resume_file3)
                    match_result = match_resume_to_job(resume_text, job_info)
                    cover_letter = generate_cover_letter(resume_text, job_info, match_result)
                    st.subheader("지원동기")
                    st.write(cover_letter.get("motivation", ""))
                    st.subheader("직무 관련 경험")
                    st.write(cover_letter.get("experience", ""))
                    st.subheader("입사 후 포부")
                    st.write(cover_letter.get("goal", ""))
                except Exception as e:
                    st.error(f"생성 실패: {e}")