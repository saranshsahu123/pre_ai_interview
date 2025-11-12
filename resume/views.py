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


# ---------------------- TEXT EXTRACTION ------------------------
def extract_text_from_pdf(pdf_path):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        print(f"PDF extraction error: {e}")
    return text


def extract_text_from_docx(docx_path):
    try:
        doc = docx.Document(docx_path)
        return "\n".join([para.text for para in doc.paragraphs])
    except Exception as e:
        print(f"DOCX extraction error: {e}")
        return ""


def extract_image_from_pdf(pdf_path):
    """Extract the first image (profile picture) from a PDF."""
    try:
        doc = fitz.open(pdf_path)
        for page_index in range(len(doc)):
            for img_index, img in enumerate(doc.get_page_images(page_index)):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                filename = f"profile_{random.randint(1000,9999)}.{image_ext}"
                image_path = os.path.join(settings.MEDIA_ROOT, filename)
                with open(image_path, "wb") as f:
                    f.write(image_bytes)
                return os.path.join(settings.MEDIA_URL, filename)
    except Exception as e:
        print(f"Image extraction error: {e}")
    return None


# ---------------------- COMPANY MATCHING ------------------------
def ai_chatbot_response(skills_list):
    """Suggest companies based on candidate's skills."""
    company_db = {
        "Google": ["python", "machine learning", "tensorflow", "sql"],
        "Microsoft": ["azure", "c#", "sql", "python"],
        "Amazon": ["aws", "python", "java", "data analysis"],
        "TCS": ["java", "sql", "spring", "oracle"],
        "Infosys": ["python", "sql", "django", "react"],
        "Wipro": ["html", "css", "javascript", "node"],
        "Capgemini": ["java", "spring", "sql"],
        "Accenture": ["python", "react", "cloud", "sql"],
        "IBM": ["java", "cloud computing", "data analysis", "python"],
        "Cognizant": ["java", "sql", "cloud computing", "python"],
        "HCL": ["java", "c++", "cloud", "linux"],
    }

    suggestions = []
    for company, required_skills in company_db.items():
        matches = set(skills_list) & set(required_skills)
        if matches:
            suggestions.append({
                "company": company,
                "matched_skills": list(matches),
                "match_score": len(matches),
            })

    return sorted(suggestions, key=lambda x: x["match_score"], reverse=True)


# ---------------------- RESUME DATA EXTRACTION ------------------------
def extract_resume_data(file_path):
    if file_path.lower().endswith(".pdf"):
        text = extract_text_from_pdf(file_path)
    elif file_path.lower().endswith(".docx"):
        text = extract_text_from_docx(file_path)
    else:
        raise ValueError("Unsupported file format")

    lines = [line.strip() for line in text.split('\n') if line.strip()]
    name = re.sub(r'[^a-zA-Z\s]', '', lines[0]) if lines else "Unknown Name"

    email_match = re.search(r'[\w\.-]+@[\w\.-]+', text)
    phone_match = re.search(r'(\+?\d{1,3}[-.\s]?)?\(?\d{3,5}\)?[-.\s]?\d{3,5}[-.\s]?\d{3,5}', text)

    skill_keywords = [
        'python', 'java', 'c++', 'sql', 'html', 'css', 'django', 'react',
        'node', 'aws', 'linux', 'git', 'shell scripting'
    ]
    skills = [word for word in skill_keywords if re.search(rf"\b{word}\b", text, re.IGNORECASE)]

    has_experience = any(x in text.lower() for x in ["experience", "internship", "worked at"])
    has_project = "project" in text.lower()

    degree_ranks = {'b.tech': 3, 'm.tech': 4, 'phd': 5, 'b.e': 3, 'm.sc': 4}
    degree = next((deg.upper() for deg in degree_ranks if re.search(rf"\b{deg}\b", text, re.IGNORECASE)), None)
    degree_score = degree_ranks.get(degree.lower(), 0) if degree else 0

    rank_score = round((degree_score + len(skills) + (2 if has_project else 0) + (1 if has_experience else 0)) / 20 * 10, 2)

    companies = ai_chatbot_response(skills)
    profile_img = extract_image_from_pdf(file_path) if file_path.endswith(".pdf") else None

    return {
        "name": name,
        "email": email_match.group(0) if email_match else "Not Found",
        "phone": phone_match.group(0) if phone_match else "Not Found",
        "skills": skills,
        "degree": degree or "Unknown",
        "has_experience": has_experience,
        "has_project": has_project,
        "rank_score": rank_score,
        "companies": companies,
        "profile_img": profile_img,
    }


# ---------------------- MAIN VIEWS ------------------------
def upload_resume(request):
    if request.method == 'POST':
        form = ResumeUploadForm(request.POST, request.FILES)
        if form.is_valid():
            resume = request.FILES['resume']

            if not resume.name.lower().endswith(('.pdf', '.docx')):
                messages.error(request, "Please upload a PDF or DOCX file.")
                return redirect('upload_resume')

            save_path = os.path.join(settings.MEDIA_ROOT, resume.name)
            with open(save_path, 'wb+') as dest:
                for chunk in resume.chunks():
                    dest.write(chunk)

            try:
                data = extract_resume_data(save_path)
                request.session['resume_data'] = data
                messages.success(request, "Resume uploaded and analyzed successfully!")
                return render(request, 'result.html', {'data': data})
            except Exception as e:
                messages.error(request, f"Error processing resume: {e}")
                return redirect('upload_resume')

    else:
        form = ResumeUploadForm()
    return render(request, 'upload.html', {'form': form})


def start_interview(request):
    data = request.session.get('resume_data')
    if not data:
        messages.error(request, "Please upload your resume first.")
        return redirect('upload_resume')

    # Dummy questions for now
    questions = [
        "Tell me about your most challenging project.",
        "What technologies are you most comfortable with?",
        "Describe how you approach debugging a complex problem.",
        "What are your strengths as a developer?",
        "Why are you interested in this position?"
    ]

    request.session['questions'] = questions
    request.session['answers'] = []
    request.session['current_q'] = 0

    return render(request, 'interview.html', {
        'question': questions[0],
        'question_number': 1,
        'total_questions': len(questions),
        'data': data,
    })


def submit_answer(request):
    if request.method == 'POST':
        answer = request.POST.get('answer', '')
        current_q = request.session.get('current_q', 0)
        answers = request.session.get('answers', [])
        questions = request.session.get('questions', [])

        answers.append(answer)
        request.session['answers'] = answers
        current_q += 1
        request.session['current_q'] = current_q

        if current_q >= len(questions):
            return redirect('interview_feedback')

        data = request.session.get('resume_data', {})
        return render(request, 'interview.html', {
            'question': questions[current_q],
            'question_number': current_q + 1,
            'total_questions': len(questions),
            'data': data,
        })
    return redirect('start_interview')


def interview_feedback(request):
    answers = request.session.get('answers', [])
    data = request.session.get('resume_data', {})

    if not answers:
        messages.error(request, "No answers found.")
        return redirect('start_interview')

    score = len([a for a in answers if len(a.strip()) > 30]) * 2
    evaluation = {
        "score": score,
        "feedback": "Excellent communication!" if score > 6 else "You can elaborate more on your answers."
    }

    return render(request, 'feedback.html', {'evaluation': evaluation, 'data': data})


# ---------------------- AUTH ------------------------
def login_candidate(request):
    if request.method == "POST":
        email = request.POST.get('email')
        password = request.POST.get('password')
        candidate = Candidate.objects.filter(email=email).first()

        if candidate and check_password(password, candidate.password):
            request.session['candidate_email'] = email
            return redirect('upload_resume')
        else:
            return render(request, 'login.html', {'error': 'Invalid email or password'})
    return render(request, 'login.html')


def signup_candidate(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm = request.POST.get('confirm_password')

        if not all([email, password, confirm]):
            messages.error(request, "All fields are required.")
        elif password != confirm:
            messages.error(request, "Passwords do not match.")
        elif Candidate.objects.filter(email=email).exists():
            messages.error(request, "Email already registered.")
        else:
            Candidate.objects.create(email=email, password=make_password(password))
            messages.success(request, "Account created successfully.")
            return redirect('login_candidate')
    return render(request, 'signin.html')
