import os
import re
import random
import spacy
import pdfplumber
import docx
import fitz  # PyMuPDF

from django.conf import settings
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password

from .forms import ResumeUploadForm
from .models import Candidate

nlp = spacy.load("en_core_web_sm")

# Use BASE_DIR from settings
BASE_DIR = settings.BASE_DIR
TEMP_UPLOAD_DIR = BASE_DIR / "temp_uploads"

# Ensure temp folder exists
os.makedirs(TEMP_UPLOAD_DIR, exist_ok=True)


# ============================================
# TEXT EXTRACTION
# ============================================
def extract_text_from_pdf(pdf_path):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                if page.extract_text():
                    text += page.extract_text() + "\n"
    except Exception as e:
        print("PDF extract error:", e)
    return text


def extract_text_from_docx(path):
    try:
        doc = docx.Document(path)
        return "\n".join([p.text for p in doc.paragraphs])
    except:
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

                filename = f"profile_{random.randint(1000,9999)}.{ext}"
                save_path = os.path.join(settings.MEDIA_ROOT, filename)

                with open(save_path, "wb") as f:
                    f.write(data)

                return settings.MEDIA_URL + filename
    except Exception as e:
        print("Image extraction error:", e)
    return None


# ============================================
# COMPANY MATCHING
# ============================================
def ai_chatbot_response(skills):
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
# RESUME DATA EXTRACTION
# ============================================
def extract_resume_data(file_path):
    text = extract_text_from_pdf(file_path) if file_path.endswith(".pdf") else extract_text_from_docx(file_path)

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    raw_name = lines[0] if lines else "Unknown"
    name = re.sub(r"[^A-Za-z\s]", "", raw_name).strip()

    job_role = lines[1] if len(lines) > 1 else "Not found"

    email = re.search(r"[\w\.-]+@[\w\.-]+", text)
    phone = re.search(r"\+?\d[\d\- ]{7,20}", text)

    skill_keywords = ["python", "java", "sql", "html", "css", "react", "django", "aws", "linux"]
    skills = [s for s in skill_keywords if re.search(rf"\b{s}\b", text, re.I)]

    experience = any(x in text.lower() for x in ["experience", "internship", "worked"])
    project = "project" in text.lower()

    degree_map = {"b.tech": 3, "m.tech": 4, "phd": 5}
    degree = next((d.upper() for d in degree_map if d in text.lower()), "Unknown")

    score = degree_map.get(degree.lower(), 0) + len(skills) + (2 if project else 0) + (1 if experience else 0)
    rank_score = round((score / 20) * 10, 2)

    companies = ai_chatbot_response(skills)

    img = extract_image_from_pdf(file_path) if file_path.endswith(".pdf") else None

    return {
        "name": name,
        "job_role": job_role,
        "email": email.group(0) if email else "Not Found",
        "phone": phone.group(0) if phone else "Not Found",
        "skills": skills,
        "degree": degree,
        "has_experience": experience,
        "has_project": project,
        "rank_score": rank_score,
        "companies": companies,
        "profile_img": img,
    }


# ============================================
# UPLOAD RESUME — FIXED (NO SAVING)
# ============================================
def upload_resume(request):
    if request.method == "POST":
        form = ResumeUploadForm(request.POST, request.FILES)
        if form.is_valid():

            f = request.FILES["resume"]

            # save temporarily inside /temp_uploads
            temp_path = TEMP_UPLOAD_DIR / f"{random.randint(1000,9999)}_{f.name}"

            with open(temp_path, "wb+") as dest:
                for chunk in f.chunks():
                    dest.write(chunk)

            # extract data
            data = extract_resume_data(str(temp_path))

            # store in session
            request.session["resume_data"] = data

            # delete file after reading
            try:
                os.remove(temp_path)
            except:
                pass

            return render(request, "result.html", {"data": data})

    return render(request, "upload.html", {"form": ResumeUploadForm()})


# ============================================
# INTERVIEW FLOW
# ============================================
def generate_ai_interview(data):
    skills = data.get("skills", [])
    return [
        f"What challenges did you face in your main project?",
        f"How do you use {skills[0] if skills else 'your skills'} in development?",
        "Explain your debugging approach.",
        f"Why do you want this job role?",
        "What are your strengths & weaknesses?",
        "Explain a complex technology in simple terms."
    ]


def start_interview(request):
    data = request.session.get("resume_data")
    if not data:
        messages.error(request, "Upload resume first.")
        return redirect("upload_resume")

    questions = generate_ai_interview(data)

    request.session["questions"] = questions
    request.session["answers"] = []
    request.session["index"] = 0

    return render(request, "interview.html", {
        "data": data,
        "question": questions[0],
        "index": 1,
        "total": len(questions),
    })


def submit_answer(request):
    if request.method == "POST":
        ans = request.POST.get("answer", "")

        answers = request.session.get("answers", [])
        answers.append(ans)
        request.session["answers"] = answers

        index = request.session.get("index", 0) + 1
        request.session["index"] = index

        questions = request.session.get("questions", [])

        if index >= len(questions):
            return redirect("interview_feedback")

        data = request.session.get("resume_data")

        return render(request, "interview.html", {
            "data": data,
            "question": questions[index],
            "index": index + 1,
            "total": len(questions),
        })

    return redirect("start_interview")


# ============================================
# FEEDBACK PAGE
# ============================================
def interview_feedback(request):
    answers = request.session.get("answers", [])
    data = request.session.get("resume_data", {})

    if not answers:
        return redirect("start_interview")

    total_words = sum(len(a.split()) for a in answers)
    avg_words = total_words / len(answers)

    depth_score = min(avg_words / 20, 5)
    completion_score = min(len(answers), 5)
    final_score = round(depth_score + completion_score, 1)

    strengths = []
    improvements = []

    if avg_words > 25:
        strengths.append("You give detailed explanations.")
    else:
        improvements.append("Try explaining with more clarity and examples.")

    if not any("project" in a.lower() for a in answers):
        improvements.append("Mention your project details more clearly.")

    if not strengths:
        strengths.append("Good speaking ability. Continue improving.")

    job_role = data.get("job_role", "").lower()
    resume_skills = set(s.lower() for s in data.get("skills", []))

    job_skill_map = {
        "full stack": ["javascript", "react", "node", "django"],
        "software engineer": ["dsa", "algorithms", "oops"],
        "data scientist": ["numpy", "pandas", "ml", "deep learning"],
        "cloud": ["aws", "azure", "terraform"],
    }

    recommended_skills = []
    for role, req in job_skill_map.items():
        if role in job_role:
            recommended_skills = [s for s in req if s not in resume_skills]

    if not recommended_skills:
        recommended_skills = ["communication", "problem solving"]

    return render(request, "feedback.html", {
        "evaluation": {
            "score": final_score,
            "strengths": strengths,
            "improvements": improvements,
            "recommended_skills": recommended_skills,
        },
        "data": data
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
