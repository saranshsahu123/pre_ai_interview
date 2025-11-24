import os
import re
import random
import json

import spacy
import pdfplumber
import docx
import fitz  # PyMuPDF

from django.conf import settings
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password
import base64


from .forms import ResumeUploadForm
from .models import Candidate

# --- Gemini SDK ---
from google import genai  # pip install google-genai

# Client will pick up GEMINI_API_KEY from environment
gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)

nlp = spacy.load("en_core_web_sm")

BASE_DIR = settings.BASE_DIR
TEMP_UPLOAD_DIR = BASE_DIR / "temp_uploads"
os.makedirs(TEMP_UPLOAD_DIR, exist_ok=True)


# ============================================
# TEXT EXTRACTION
# ============================================
def extract_text_from_pdf(pdf_path):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        print("PDF extract error:", e)
    return text


def extract_text_from_docx(path):
    try:
        doc = docx.Document(path)
        return "\n".join([p.text for p in doc.paragraphs])
    except Exception as e:
        print("DOCX extract error:", e)
        return ""


# ============================================
# IMAGE EXTRACTION (PROFILE IMAGE ONLY)
# ============================================


def extract_image_from_pdf(path):
    try:
        doc = fitz.open(path)
        for page in doc:
            for img in page.get_images():
                xref = img[0]
                base = doc.extract_image(xref)
                ext = base["ext"]
                data = base["image"]

                # Convert binary image → BASE64
                b64 = base64.b64encode(data).decode("utf-8")

                # Return image URI
                return f"data:image/{ext};base64,{b64}"

    except Exception as e:
        print("Image extraction error:", e)
    return None



# ============================================
# COMPANY MATCHING
# ============================================
def ai_chatbot_response(skills):
    skills = [s.lower() for s in skills]
    company_db = {
        "Google": ["python", "tensorflow", "machine learning"],
        "Microsoft": ["azure", "python", "c#"],
        "Amazon": ["aws", "python", "java"],
        "Infosys": ["python", "django", "sql"],
        "Wipro": ["html", "css", "javascript"],
        "Accenture": ["cloud", "react", "sql"],
        "IBM": ["cloud", "java", "data analysis"],
        "TCS": ["java", "spring", "sql"],
    }

    suggestions = []
    for company, req in company_db.items():
        matched = set(skills) & set(req)
        if matched:
            suggestions.append({
                "company": company,
                "matched_skills": list(matched),
                "match_score": len(matched)
            })

    return sorted(suggestions, key=lambda x: x["match_score"], reverse=True)


# ============================================
# EXTRA HELPERS: PROJECT TITLES & SOCIAL LINKS
# ============================================
def extract_project_titles(text: str):
    lines = [l.strip() for l in text.splitlines()]
    titles = []
    in_project_section = False

    for line in lines:
        lower = line.lower()

        if "project" in lower and len(lower) < 40:
            in_project_section = True
            continue

        if in_project_section:
            if not line:
                in_project_section = False
                continue

            if re.match(r"^\d+[\).\-\)]\s+", line) or line.isupper():
                titles.append(line)
            else:
                if not titles:
                    titles.append(line)

    return titles


def extract_social_links(text: str):
    social = {}

    linkedin = re.search(r"https?://(www\.)?linkedin\.com/[^\s]+", text, re.I)
    github = re.search(r"https?://(www\.)?github\.com/[^\s]+", text, re.I)
    portfolio = re.search(
        r"https?://(www\.)?(myportfolio|behance|dribbble|vercel|netlify|portfolio)\.[^\s]+",
        text, re.I
    )

    if linkedin:
        social["LinkedIn"] = linkedin.group(0)
    if github:
        social["GitHub"] = github.group(0)
    if portfolio:
        social["Portfolio"] = portfolio.group(0)

    return social


# ============================================
# RESUME DATA EXTRACTION
# ============================================
def extract_resume_data(file_path):
    is_pdf = file_path.lower().endswith(".pdf")
    text = extract_text_from_pdf(file_path) if is_pdf else extract_text_from_docx(file_path)

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    raw_name = lines[0] if lines else "Unknown"
    name = re.sub(r"[^A-Za-z\s]", "", raw_name).strip() or "Unknown"

    job_role = lines[1] if len(lines) > 1 else "Not found"

    email = re.search(r"[\w\.-]+@[\w\.-]+", text)
    phone = re.search(r"\+?\d[\d\- ]{7,20}", text)

    skill_keywords = ["python", "java", "sql", "html", "css", "react", "django", "aws", "linux"]
    skills = [s for s in skill_keywords if re.search(rf"\b{s}\b", text, re.I)]

    experience = any(x in text.lower() for x in ["experience", "internship", "worked"])
    project_flag = "project" in text.lower()

    degree_map = {"b.tech": 3, "m.tech": 4, "phd": 5}
    found_degree = next((d for d in degree_map if d in text.lower()), None)
    degree = found_degree.upper() if found_degree else "Unknown"

    score = degree_map.get(found_degree, 0) + len(skills) + (2 if project_flag else 0) + (1 if experience else 0)
    rank_score = round((score / 20) * 10, 2)

    companies = ai_chatbot_response(skills)
    img = extract_image_from_pdf(file_path) if is_pdf else None

    project_titles = extract_project_titles(text)
    social_links = extract_social_links(text)

    return {
        "name": name,
        "job_role": job_role,
        "email": email.group(0) if email else "Not Found",
        "phone": phone.group(0) if phone else "Not Found",
        "skills": skills,
        "degree": degree,
        "has_experience": experience,
        "has_project": project_flag,
        "rank_score": rank_score,
        "companies": companies,
        "profile_img": img,
        "project_titles": project_titles,
        "social_links": social_links,
    }


# ============================================
# UPLOAD RESUME — FIXED (NO SAVING)
# ============================================
def upload_resume(request):
    if request.method == "POST":
        form = ResumeUploadForm(request.POST, request.FILES)
        if form.is_valid():
            f = request.FILES["resume"]

            temp_path = TEMP_UPLOAD_DIR / f"{random.randint(1000,9999)}_{f.name}"

            with open(temp_path, "wb+") as dest:
                for chunk in f.chunks():
                    dest.write(chunk)

            data = extract_resume_data(str(temp_path))
            request.session["resume_data"] = data

            try:
                os.remove(temp_path)
            except Exception as e:
                print("Temp file delete error:", e)

            return render(request, "result.html", {"data": data})

    return render(request, "upload.html", {"form": ResumeUploadForm()})


# ============================================
# GEMINI HELPERS (Q generation + evaluation)
# ============================================
def _strip_json(text: str) -> str:
    """
    Remove ```json ... ``` wrappers if model returns fenced code.
    """
    text = text.strip()
    if text.startswith("```"):
        # remove leading ```(json)?
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


def generate_ai_questions(resume_data: dict, difficulty: str):
    """
    Ask Gemini to generate 10 questions with correct answers + keywords.
    """
    job_role = resume_data.get("job_role", "Software Engineer")
    skills = resume_data.get("skills", [])
    skills_str = ", ".join(skills) if skills else "general programming and soft skills"

    prompt = f"""
You are an expert technical + HR interviewer.

Generate exactly 10 interview questions for this candidate:

- Role: {job_role}
- Skills: {skills_str}
- Difficulty level: {difficulty.upper()} (Easy / Medium / Hard)

Mix:
- Technical questions (based on skills / CS fundamentals)
- HR / communication questions

Return ONLY valid JSON in this exact format, no extra text, no explanation:

{{
  "questions": [
    {{
      "question": "string",
      "answer": "short ideal answer in 3-6 sentences",
      "keywords": ["short keyword 1", "short keyword 2", "short keyword 3"]
    }},
    ...
  ]
}}
"""

    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        raw = response.text or ""
        cleaned = _strip_json(raw)
        data = json.loads(cleaned)
        questions = data.get("questions", [])
    except Exception as e:
        print("Gemini question generation error:", e)
        questions = []

    # fallback: if API fails, return some simple backup questions
    if not questions:
        questions = [
            {
                "question": "Tell me about yourself.",
                "answer": "Give a short summary of your education, skills, and projects.",
                "keywords": ["introduction", "profile", "summary"],
            }
        ] * 10

    # make sure there are 10
    return questions[:10]


def evaluate_answer_with_ai(question_obj: dict, user_answer: str):
    """
    Ask Gemini to evaluate the candidate's answer:
    - is_correct (bool)
    - ideal_answer (string)
    - feedback (communication + content)
    - english_score (0-10)
    - communication_score (0-10)
    """
    question_text = question_obj.get("question", "")
    reference_answer = question_obj.get("answer", "")

    prompt = f"""
You are an interview evaluator.

Evaluate the candidate's answer to the question.

Question:
\"\"\"{question_text}\"\"\"

Reference good answer (for your understanding, do NOT just repeat it):
\"\"\"{reference_answer}\"\"\"

Candidate's answer:
\"\"\"{user_answer}\"\"\"

Return ONLY valid JSON, no explanation, in this exact shape:

{{
  "is_correct": true or false,
  "ideal_answer": "a concise, improved ideal answer in 3-6 sentences",
  "feedback": "friendly specific feedback on what was good and what to improve",
  "english_score": 0-10,   // grammar, vocabulary
  "communication_score": 0-10  // structure, clarity, confidence
}}
"""

    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        raw = response.text or ""
        cleaned = _strip_json(raw)
        data = json.loads(cleaned)

        is_correct = bool(data.get("is_correct", False))
        ideal_answer = data.get("ideal_answer", reference_answer)
        feedback_text = data.get("feedback", "")
        english_score = int(data.get("english_score", 0))
        communication_score = int(data.get("communication_score", 0))

    except Exception as e:
        print("Gemini evaluation error:", e)
        # fallback if API fails
        is_correct = False
        ideal_answer = reference_answer or "No ideal answer available."
        feedback_text = "Could not evaluate with AI. Please review the ideal answer and compare."
        english_score = 0
        communication_score = 0

    return {
        "is_correct": is_correct,
        "ideal_answer": ideal_answer,
        "feedback_text": feedback_text,
        "english_score": english_score,
        "communication_score": communication_score,
    }


# ============================================
# INTERVIEW FLOW WITH DIFFICULTY + GEMINI
# ============================================
def start_interview(request):
    """
    Difficulty selection page.
    """
    data = request.session.get("resume_data")
    if not data:
        messages.error(request, "Upload resume first.")
        return redirect("upload_resume")

    if request.method == "POST":
        difficulty = request.POST.get("difficulty", "easy").lower()
        if difficulty not in ["easy", "medium", "hard"]:
            difficulty = "easy"

        # generate 10 AI questions
        questions = generate_ai_questions(data, difficulty)

        request.session["questions"] = questions
        request.session["difficulty"] = difficulty
        request.session["index"] = 0
        request.session["score"] = 0

        # we will also accumulate avg English & communication scores
        request.session["english_scores"] = []
        request.session["communication_scores"] = []

        return redirect("interview_question")

    return render(request, "select_difficulty.html", {"data": data})


def interview_question(request):
    data = request.session.get("resume_data")
    questions = request.session.get("questions")
    if not data or not questions:
        messages.error(request, "Please start interview again.")
        return redirect("start_interview")

    index = request.session.get("index", 0)
    score = request.session.get("score", 0)
    english_scores = request.session.get("english_scores", [])
    communication_scores = request.session.get("communication_scores", [])

    total = len(questions)

    if index >= total:
        return redirect("interview_feedback")

    current_q = questions[index]
    feedback = None

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "submit":
            user_answer = request.POST.get("answer", "").strip()

            evaluation = evaluate_answer_with_ai(current_q, user_answer)

            # update score
            if evaluation["is_correct"]:
                score += 1
                request.session["score"] = score

            english_scores.append(evaluation["english_score"])
            communication_scores.append(evaluation["communication_score"])

            request.session["english_scores"] = english_scores
            request.session["communication_scores"] = communication_scores

            feedback = {
                "is_correct": evaluation["is_correct"],
                "user_answer": user_answer,
                "ideal_answer": evaluation["ideal_answer"],
                "feedback_text": evaluation["feedback_text"],
                "english_score": evaluation["english_score"],
                "communication_score": evaluation["communication_score"],
            }

        elif action == "next":
            index += 1
            request.session["index"] = index
            if index >= total:
                return redirect("interview_feedback")
            current_q = questions[index]

    context = {
        "data": data,
        "question": current_q["question"],
        "index": index + 1,
        "total": total,
        "score": score,
        "feedback": feedback,
        "difficulty": request.session.get("difficulty", "easy"),
    }
    return render(request, "interview.html", context)


def interview_feedback(request):
    data = request.session.get("resume_data", {})
    questions = request.session.get("questions", [])
    score = request.session.get("score", 0)
    english_scores = request.session.get("english_scores", [])
    communication_scores = request.session.get("communication_scores", [])

    total = len(questions) or 10

    # normalize to /10
    if total != 10 and total > 0:
        normalized_score = round((score / total) * 10)
    else:
        normalized_score = score

    avg_english = round(sum(english_scores) / len(english_scores), 1) if english_scores else 0.0
    avg_comm = round(sum(communication_scores) / len(communication_scores), 1) if communication_scores else 0.0

    if normalized_score >= 8:
        readiness = "You are ready for real interviews! 🎉"
    elif normalized_score >= 5:
        readiness = "You are partially ready. Keep practicing and improving."
    else:
        readiness = "You need more practice. Focus on fundamentals and try again."

    return render(request, "feedback.html", {
        "evaluation": {
            "score": normalized_score,
            "out_of": 10,
            "readiness": readiness,
            "avg_english": avg_english,
            "avg_communication": avg_comm,
        },
        "data": data,
        "difficulty": request.session.get("difficulty", "easy"),
    })


# ============================================
# AUTHENTICATION
# ============================================
def login_candidate(request):
    if request.method == "POST":
        email = request.POST.get("email")
        pwd = request.POST.get("password")

        user = Candidate.objects.filter(email=email).first()

        if user and check_password(pwd, user.password):
            request.session["candidate"] = email
            return redirect("upload_resume")

        return render(request, "login.html", {"error": "Invalid credentials"})

    return render(request, "login.html")


def signup_candidate(request):
    if request.method == "POST":
        email = request.POST.get("email")
        pwd = request.POST.get("password")
        confirm = request.POST.get("confirm_password")

        if pwd != confirm:
            messages.error(request, "Passwords do not match")
        elif Candidate.objects.filter(email=email).exists():
            messages.error(request, "Email already exists")
        else:
            Candidate.objects.create(email=email, password=make_password(pwd))
            return redirect("login_candidate")

    return render(request, "signin.html")
