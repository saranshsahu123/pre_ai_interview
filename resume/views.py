import os
import re
import json
import random
import base64

import spacy
import pdfplumber
import docx
import fitz  # PyMuPDF

from django.conf import settings
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password

# -----------------------------
# GEMINI SDK (CORRECT USAGE)
# -----------------------------
import google.generativeai as genai
genai.configure(api_key=settings.GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-2.0-flash")

from .forms import ResumeUploadForm
from .models import Candidate

nlp = spacy.load("en_core_web_sm")

BASE_DIR = settings.BASE_DIR
TEMP_DIR = BASE_DIR / "temp_uploads"
os.makedirs(TEMP_DIR, exist_ok=True)


# -----------------------------------------------------
# TEXT EXTRACTION
# -----------------------------------------------------
def extract_text_from_pdf(path):
    text = ""
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text += t + "\n"
    except:
        pass
    return text


def extract_text_from_docx(path):
    try:
        doc = docx.Document(path)
        return "\n".join(p.text for p in doc.paragraphs)
    except:
        return ""


# -----------------------------------------------------
# BASE64 IMAGE ONLY (NO MEDIA SAVE)
# -----------------------------------------------------
def extract_image_from_pdf(path):
    try:
        doc = fitz.open(path)

        for page in doc:
            for img in page.get_images():
                xref = img[0]
                image = doc.extract_image(xref)

                # image bytes
                data = image["image"]
                ext = image["ext"]

                # convert to base64
                b64 = base64.b64encode(data).decode()

                # return inline base64
                return f"data:image/{ext};base64,{b64}"

        doc.close()
    except Exception as e:
        print("PDF image extraction error:", e)

    return None


# -----------------------------------------------------
# SOCIAL LINKS + PROJECT TITLES
# -----------------------------------------------------
def extract_project_titles(text):
    lines = [l.strip() for l in text.splitlines()]
    projects = []
    active = False

    for line in lines:
        if "project" in line.lower() and len(line) < 40:
            active = True
            continue

        if active:
            if not line:
                active = False
                continue
            projects.append(line)

    return projects


def extract_social_links(text):
    social = {}

    linkedin = re.search(r"https?://(www\.)?linkedin\.com/[^\s]+", text)
    github = re.search(r"https?://(www\.)?github\.com/[^\s]+", text)
    portfolio = re.search(r"https?://[^\s]+(portfolio|netlify|vercel|behance|dribbble)[^\s]+", text)

    if linkedin: social["LinkedIn"] = linkedin.group(0)
    if github: social["GitHub"] = github.group(0)
    if portfolio: social["Portfolio"] = portfolio.group(0)

    return social


# -----------------------------------------------------
# COMPANY MATCHING
# -----------------------------------------------------
def ai_chatbot_response(skills):
    skills = [s.lower() for s in skills]
    company_db = {
        "Google": ["python", "machine learning", "tensorflow"],
        "Microsoft": ["azure", "python", "c#"],
        "Amazon": ["aws", "python", "java"],
        "Infosys": ["python", "django"],
        "Wipro": ["html", "css", "javascript"],
    }
    out = []

    for company, req in company_db.items():
        matched = list(set(skills) & set(req))
        if matched:
            out.append({
                "company": company,
                "matched_skills": matched,
                "match_score": len(matched)
            })

    return sorted(out, key=lambda x: x["match_score"], reverse=True)


# -----------------------------------------------------
# RESUME DATA EXTRACTOR
# -----------------------------------------------------
def extract_resume_data(path):
    is_pdf = path.lower().endswith(".pdf")
    text = extract_text_from_pdf(path) if is_pdf else extract_text_from_docx(path)

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    raw_name = re.sub(r"[^A-Za-z\s]", "", lines[0]) if lines else "Unknown"
    job_role = lines[1] if len(lines) > 1 else "Not found"

    email = re.search(r"[\w\.-]+@[\w\.-]+", text)
    phone = re.search(r"\+?\d[\d\s\-]{8,20}", text)

    skill_keywords = ["python", "java", "sql", "react", "django", "aws", "html", "css"]
    skills = [s for s in skill_keywords if s.lower() in text.lower()]

    project_titles = extract_project_titles(text)
    social_links = extract_social_links(text)

    degree_map = {"b.tech": 3, "m.tech": 4, "phd": 5}
    found = next((d for d in degree_map if d in text.lower()), None)
    degree = found.upper() if found else "Unknown"

    score = degree_map.get(found, 0) + len(skills)
    rank = round((score / 12) * 10, 2)

    img = extract_image_from_pdf(path) if is_pdf else None

    return {
        "name": raw_name,
        "job_role": job_role,
        "email": email.group(0) if email else "Not Found",
        "phone": phone.group(0) if phone else "Not Found",
        "skills": skills,
        "degree": degree,
        "rank_score": rank,
        "project_titles": project_titles,
        "social_links": social_links,
        "profile_img": img,
        "companies": ai_chatbot_response(skills),
    }


# -----------------------------------------------------
# UPLOAD RESUME
# -----------------------------------------------------
def upload_resume(request):
    if request.method == "POST":
        form = ResumeUploadForm(request.POST, request.FILES)
        if form.is_valid():

            f = request.FILES["resume"]
            temp_path = TEMP_DIR / f"{random.randint(1000,9999)}_{f.name}"

            with open(temp_path, "wb+") as dest:
                for chunk in f.chunks():
                    dest.write(chunk)

            data = extract_resume_data(str(temp_path))
            request.session["resume_data"] = data

            os.remove(temp_path)
            return render(request, "result.html", {"data": data})

    return render(request, "upload.html", {"form": ResumeUploadForm()})


# -----------------------------------------------------
# JSON CLEANER
# -----------------------------------------------------
def clean_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.replace("```", "")
    return text.strip()


# -----------------------------------------------------
# GEMINI → GENERATE QUESTIONS
# -----------------------------------------------------
def generate_ai_questions(resume, diff):
    skills = ", ".join(resume.get("skills", []))
    projects = ", ".join(resume.get("project_titles", []))
    job_role = resume.get("job_role", "Not specified")

    prompt = f"""
You are an interview system. Generate 10 high-quality interview questions STRICTLY based on:

Job Role: {job_role}
Candidate Skills: {skills}
Candidate Projects: {projects}

Difficulty Level: {diff}

Rules:
1. Ask only resume-based questions.
2. Include technical + project + scenario questions.
3. Return ONLY JSON in this format:

{{
  "questions": [
    {{
      "question": "Write question here...",
      "answer": "Write short ideal answer..."
    }}
  ]
}}
"""

    try:
        response = gemini_model.generate_content(prompt)
        data = json.loads(clean_json(response.text))
        return data["questions"]

    except Exception as e:
        print("Gemini question error:", e)
        return [{
            "question": "Tell me about your skills.",
            "answer": "Explain your skills briefly."
        }] * 10


# -----------------------------------------------------
# GEMINI → EVALUATE ANSWER
# -----------------------------------------------------
def evaluate_answer_ai(question, ideal, user):
    prompt = f"""
Evaluate this answer:

Question: {question}
Ideal Answer: {ideal}
User Answer: {user}

Return ONLY JSON:

{{
  "is_correct": true/false,
  "ideal_answer": "...",
  "feedback": "...",
  "english_score": 0-10,
  "communication_score": 0-10
}}
"""

    try:
        response = gemini_model.generate_content(prompt)
        return json.loads(clean_json(response.text))

    except:
        return {
            "is_correct": False,
            "ideal_answer": ideal,
            "feedback": "Could not evaluate.",
            "english_score": 0,
            "communication_score": 0,
        }


# -----------------------------------------------------
# START INTERVIEW (SELECT DIFFICULTY)
# -----------------------------------------------------
def start_interview(request):
    data = request.session.get("resume_data")
    if not data:
        messages.error(request, "Upload resume first.")
        return redirect("upload_resume")

    if request.method == "POST":
        diff = request.POST.get("difficulty", "easy")

        qs = generate_ai_questions(data, diff)

        request.session["questions"] = qs
        request.session["difficulty"] = diff
        request.session["index"] = 0
        request.session["score"] = 0
        request.session["eng"] = []
        request.session["comm"] = []

        return redirect("interview_question")

    return render(request, "select_difficulty.html", {"data": data})


# -----------------------------------------------------
# SHOW QUESTION + EVALUATE ANSWER
# -----------------------------------------------------
def interview_question(request):
    data = request.session.get("resume_data")
    qs = request.session.get("questions")

    if not data or not qs:
        return redirect("start_interview")

    index = request.session["index"]
    score = request.session["score"]
    eng = request.session["eng"]
    comm = request.session["comm"]

    if index >= len(qs):
        return redirect("interview_feedback")

    q = qs[index]
    feedback = None

    if request.method == "POST":
        if request.POST.get("action") == "submit":
            ans = request.POST.get("answer", "")

            ev = evaluate_answer_ai(q["question"], q["answer"], ans)

            if ev["is_correct"]:
                score += 1
                request.session["score"] = score

            eng.append(ev["english_score"])
            comm.append(ev["communication_score"])

            request.session["eng"] = eng
            request.session["comm"] = comm

            feedback = ev

        else:  # next
            if index + 1 >= len(qs):   # last question reached
                return redirect("interview_feedback")

            request.session["index"] = index + 1
            return redirect("interview_question")

    return render(request, "interview.html", {
        "question": q["question"],
        "index": index + 1,
        "total": len(qs),
        "score": score,
        "feedback": feedback,
        "difficulty": request.session.get("difficulty"),
    })


# -----------------------------------------------------
# FINAL FEEDBACK PAGE
# -----------------------------------------------------
def interview_feedback(request):
    score = request.session.get("score", 0)
    eng = request.session.get("eng", [])
    comm = request.session.get("comm", [])

    avg_eng = round(sum(eng) / len(eng), 1) if eng else 0
    avg_comm = round(sum(comm) / len(comm), 1) if comm else 0

    readiness = (
        "You are ready! 🎉" if score >= 8 else
        "Partially ready." if score >= 5 else
        "Needs improvement."
    )

    return render(request, "feedback.html", {
        "score": score,
        "english": avg_eng,
        "communication": avg_comm,
        "readiness": readiness,
    })


# -----------------------------------------------------
# LOGIN / SIGNUP
# -----------------------------------------------------
def login_candidate(request):
    if request.method == "POST":
        email = request.POST["email"]
        pwd = request.POST["password"]

        u = Candidate.objects.filter(email=email).first()
        if u and check_password(pwd, u.password):
            request.session["candidate"] = email
            return redirect("upload_resume")

        return render(request, "login.html", {"error": "Invalid credentials"})

    return render(request, "login.html")


def signup_candidate(request):
    if request.method == "POST":
        email = request.POST["email"]
        pwd = request.POST["password"]
        c = request.POST["confirm_password"]

        if pwd != c:
            messages.error(request, "Passwords do not match")
        elif Candidate.objects.filter(email=email).exists():
            messages.error(request, "Email already exists")
        else:
            Candidate.objects.create(email=email, password=make_password(pwd))
            return redirect("login_candidate")

    return render(request, "signin.html")
