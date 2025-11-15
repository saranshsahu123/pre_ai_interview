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


# ============================================
#  TEXT EXTRACTION
# ============================================
def extract_text_from_pdf(pdf_path):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        print("PDF error:", e)
    return text


def extract_text_from_docx(docx_path):
    try:
        doc = docx.Document(docx_path)
        return "\n".join([p.text for p in doc.paragraphs])
    except Exception as e:
        print("DOCX error:", e)
        return ""


# ============================================
#  IMAGE EXTRACTION
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
                filename = f"profile_{random.randint(1111,9999)}.{ext}"
                save_path = os.path.join(settings.MEDIA_ROOT, filename)

                with open(save_path, "wb") as f:
                    f.write(data)

                return settings.MEDIA_URL + filename
    except Exception as e:
        print("Image error:", e)
    return None


# ============================================
#  COMPANY MATCHING (AI Recommendation)
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
        match = set(skills) & set(req)
        if match:
            suggestions.append({
                "company": company,
                "matched_skills": list(match),
                "match_score": len(match)
            })

    return sorted(suggestions, key=lambda x: x["match_score"], reverse=True)


# ============================================
#  RESUME DATA EXTRACTION
# ============================================
def extract_resume_data(file_path):
    text = extract_text_from_pdf(file_path) if file_path.endswith(".pdf") else extract_text_from_docx(file_path)

    lines = [l.strip() for l in text.split("\n") if l.strip()]

    raw_name = lines[0] if lines else "Unknown"
    name = re.sub(r"[^A-Za-z\s]", "", raw_name).strip()

    job_role = lines[1] if len(lines) > 1 else "Not found"

    email = re.search(r"[\w\.-]+@[\w\.-]+", text)
    phone = re.search(r"\+?\d[\d\-\s]{7,20}", text)

    skill_keywords = ["python", "java", "sql", "html", "css", "react", "django", "aws", "linux"]
    skills = [s for s in skill_keywords if re.search(rf"\b{s}\b", text, re.I)]

    has_experience = any(x in text.lower() for x in ["experience", "internship", "worked"])
    has_project = "project" in text.lower()

    degree_map = {"b.tech": 3, "m.tech": 4, "phd": 5}
    degree = next((d.upper() for d in degree_map if d in text.lower()), "Unknown")
    degree_score = degree_map.get(degree.lower(), 0)

    total_score = degree_score + len(skills) + (2 if has_project else 0) + (1 if has_experience else 0)
    rank_score = round((total_score / 20) * 10, 2)

    companies = ai_chatbot_response(skills)
    profile_img = extract_image_from_pdf(file_path) if file_path.endswith(".pdf") else None

    return {
        "name": name,
        "job_role": job_role,
        "email": email.group(0) if email else "Not Found",
        "phone": phone.group(0) if phone else "Not Found",
        "skills": skills,
        "degree": degree,
        "has_experience": has_experience,
        "has_project": has_project,
        "rank_score": rank_score,
        "companies": companies,
        "profile_img": profile_img,
    }


# ============================================
#  INTERVIEW GENERATION (AI)
# ============================================
def generate_ai_interview(data):
    role = data.get("job_role", "")
    skills = data.get("skills", [])
    project = "your project"

    return [
        f"What challenges did you face in {project}?",
        f"How do you use {skills[0] if skills else 'your skills'} in development?",
        "Describe your debugging approach.",
        f"Why do you want to work as a {role}?",
        "What are your strengths and weaknesses?",
        "Explain a complex technical concept in simple language."
    ]


# ============================================
#  AI INTERVIEW PERFORMANCE EVALUATION
# ============================================
def evaluate_interview_performance(answers):
    total = len(answers)
    answered = len([a for a in answers if a.strip()])
    completion_rate = round((answered / total) * 100, 2)

    avg_length = round(sum(len(a.split()) for a in answers if a.strip()) / max(answered, 1), 2)

    overall_score = min(100, int((avg_length * 3) + completion_rate / 2))

    strengths = []
    improvements = []

    if avg_length > 20:
        strengths.append("You explain answers clearly and in detail.")
    else:
        improvements.append("Try elaborating more with real examples.")

    if completion_rate < 80:
        improvements.append("Complete all interview questions.")

    feedback = "Excellent communication!" if overall_score >= 80 else "Keep improving and practice more."

    return {
        "overall_score": overall_score,
        "completion_rate": completion_rate,
        "avg_answer_length": avg_length,
        "feedback": feedback,
        "strengths": strengths,
        "improvements": improvements,
        "suggestions": [
            "Improve explanation depth.",
            "Use STAR format in answers.",
            "Mention real use cases from projects."
        ] if improvements else []
    }


# ============================================
#  MAIN VIEWS
# ============================================
def upload_resume(request):
    if request.method == "POST":
        form = ResumeUploadForm(request.POST, request.FILES)
        if form.is_valid():
            f = request.FILES["resume"]
            path = os.path.join(settings.MEDIA_ROOT, f.name)
            with open(path, "wb+") as dest:
                for chunk in f.chunks():
                    dest.write(chunk)

            data = extract_resume_data(path)
            request.session["resume_data"] = data

            return render(request, "result.html", {"data": data})

    return render(request, "upload.html", {"form": ResumeUploadForm()})


def start_interview(request):
    data = request.session.get("resume_data")
    if not data:
        messages.error(request, "Upload your resume first.")
        return redirect("upload_resume")

    questions = generate_ai_interview(data)

    request.session["questions"] = questions
    request.session["answers"] = []
    request.session["q_index"] = 0

    return render(request, "interview.html", {
        "question": questions[0],
        "index": 1,
        "total": len(questions),
        "data": data
    })


def submit_answer(request):
    if request.method == "POST":
        ans = request.POST.get("answer", "")
        answers = request.session.get("answers", [])
        answers.append(ans)
        request.session["answers"] = answers

        q_index = request.session.get("q_index", 0) + 1
        request.session["q_index"] = q_index

        questions = request.session.get("questions", [])

        if q_index >= len(questions):
            return redirect("interview_feedback")

        data = request.session.get("resume_data")
        return render(request, "interview.html", {
            "question": questions[q_index],
            "index": q_index + 1,
            "total": len(questions),
            "data": data,
        })

    return redirect("start_interview")


def interview_feedback(request):
    answers = request.session.get('answers', [])
    data = request.session.get('resume_data', {})

    if not answers:
        messages.error(request, "No answers found.")
        return redirect('start_interview')

    # --------------------------
    # 1️⃣ Calculate Score (0–10)
    # --------------------------
    total_words = sum(len(a.split()) for a in answers)
    avg_len = total_words / len(answers)

    # Score based on answer depth
    depth_score = min(avg_len / 20, 5)  # deeper answers = higher score

    # Score based on completion
    completion_score = 5 if len(answers) == 5 else (len(answers) / 5) * 5

    score = depth_score + completion_score
    score = round(max(0, min(score, 10)), 1)  # final clamp 0–10

    # --------------------------
    # 2️⃣ Strengths Detection
    # --------------------------
    strengths = []
    if avg_len > 25:
        strengths.append("You provide detailed and structured explanations.")
    if any("experience" in a.lower() for a in answers):
        strengths.append("You present your past experiences confidently.")
    if any(len(a.split()) > 40 for a in answers):
        strengths.append("Your answers show strong clarity and elaboration.")
    if any(skill.lower() in " ".join(answers).lower() for skill in data.get("skills", [])):
        strengths.append("Good use of your technical skills in explanations.")

    if not strengths:
        strengths.append("Good communication. Keep practicing for more depth.")

    # ------------------------------
    # 3️⃣ Weakness / Improvement Area
    # ------------------------------
    improvements = []
    if avg_len < 20:
        improvements.append("Your answers are short. Try to add examples or explanations.")
    if not any("project" in a.lower() for a in answers):
        improvements.append("You didn't mention project details — include concrete achievements.")
    if any(len(a.split()) < 10 for a in answers):
        improvements.append("Some answers were too brief. Add clarity and structure.")
    if "error" in " ".join(answers).lower():
        improvements.append("Revise debugging techniques; rely on systematic approaches.")

    # If still empty:
    if not improvements:
        improvements.append("No major weaknesses detected — keep polishing your skills.")

    # ------------------------------------
    # 4️⃣ Recommend Skills to Improve Resume
    # ------------------------------------
    job_role = data.get("job_role", "").lower()
    resume_skills = set([s.lower() for s in data.get("skills", [])])

    job_skill_map = {
        "full stack developer": ["python", "django", "html", "css", "javascript", "react", "node"],
        "software engineer": ["java", "python", "c++", "algorithms", "dsa"],
        "data scientist": ["python", "machine learning", "pandas", "numpy", "sql", "deep learning"],
        "cloud engineer": ["aws", "azure", "gcp", "linux", "terraform"],
        "data analyst": ["sql", "excel", "power bi", "python", "tableau"]
    }

    matched_role = None
    recommended_skills = []

    for role, required in job_skill_map.items():
        if role.lower() in job_role:
            matched_role = role
            recommended_skills = [s for s in required if s not in resume_skills]
            break

    # If job role not recognized → generic suggestions
    if not recommended_skills:
        recommended_skills = ["communication", "problem solving", "team collaboration"]

    # -----------------------------------------
    # 5️⃣ Suggest Other Roles Based on Skills
    # -----------------------------------------
    skill_based_roles = []
    if {"python", "sql"} <= resume_skills:
        skill_based_roles.append("Data Analyst")
    if {"python", "pandas"} <= resume_skills:
        skill_based_roles.append("Business Analyst")
    if {"java"} <= resume_skills:
        skill_based_roles.append("Backend Developer")

    evaluation = {
        "score": score,
        "strengths": strengths,
        "improvements": improvements,
        "recommended_skills": recommended_skills,
        "alternate_roles": skill_based_roles,
        "avg_words": round(avg_len, 1)
    }

    return render(request, 'feedback.html', {
        'evaluation': evaluation,
        'data': data
    })


# ============================================
#  AUTHENTICATION
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
            messages.error(request, "Email already registered")
        else:
            Candidate.objects.create(email=email, password=make_password(pwd))
            messages.success(request, "Account created!")
            return redirect("login_candidate")

    return render(request, "signin.html")
