from flask import Flask,render_template,request,url_for,redirect,jsonify,session
import mysql.connector
from dotenv import load_dotenv
import os
from groq import Groq
from typing import Any
from utils.parser import parse_resume
from utils.rag import create_vector_store, build_context, is_ready
import re

# load .env file
load_dotenv()

app=Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY")

# get api key from .env
client = Groq(
    api_key=os.getenv("API")
)

db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="admin123",
    database="ai_interview_bott"
)

cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100),
    email VARCHAR(100) UNIQUE,
    password VARCHAR(100)
)
""")

app.config["UPLOAD_FOLDER"]="uploads"

cursor.execute("""
CREATE TABLE IF NOT EXISTS resumes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(100),
    filename VARCHAR(255),
    role VARCHAR(100),
    resume_text LONGTEXT
)
""")

db.commit()

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        cursor.execute(
            "SELECT * FROM users WHERE email=%s AND password=%s",
            (email, password)
        )

        user = cursor.fetchone()

        if user:

            # save logged in user
            session["email"] = email

            return redirect(url_for("dashboard"))

        return render_template(
            "login.html",
            error="Invalid Email or Password"
        )

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# FORGOT PASSWORD ROUTE
@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():

    if request.method == "POST":

        email = request.form["email"]

        # check user exists
        cursor.execute(
            "SELECT * FROM users WHERE email=%s",
            (email,)
        )

        user = cursor.fetchone()

        if not user:
            return render_template(
                "forgot_password.html",
                error="Email not found."
            )

        # send to reset page
        return redirect(
            url_for(
                "reset_password",
                email=email
            )
        )

    return render_template("forgot_password.html")

# RESET PASSWORD ROUTE
@app.route("/reset-password/<email>", methods=["GET", "POST"])
def reset_password(email):

    if request.method == "POST":

        new_password = request.form["password"]
        confirm_password = request.form["confirm"]

        # passwords match check
        if new_password != confirm_password:

            return render_template(
                "reset_password.html",
                email=email,
                error="Passwords do not match."
            )

        # update password
        cursor.execute(
            """
            UPDATE users
            SET password=%s
            WHERE email=%s
            """,
            (new_password, email)
        )

        db.commit()

        return redirect(url_for("login"))

    return render_template(
        "reset_password.html",
        email=email
    )

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
       

        cursor.execute(
            "SELECT * FROM users WHERE email = %s",
            (email,)
        )

        user = cursor.fetchone()

        if user:
            return render_template(
                "register.html",
                error="Email already registered"
            )

        cursor.execute(
            "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
            (name, email, password)
        )

        db.commit()

        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/upload", methods=["GET", "POST"])
def upload():

    # user must be logged in
    email = session.get("email")

    if not email:
        return redirect(url_for("login"))

    if request.method == "POST":

        # get file + role
        file = request.files["resume"]
        role = request.form["role"]

        # filename
        filename = file.filename

        # no file selected
        if not filename:
            return render_template(
                "upload.html",
                error="Please select a PDF file"
            )

        # allow only pdf
        if not filename.lower().endswith(".pdf"):
            return render_template(
                "upload.html",
                error="Only PDF files are allowed"
            )

        # create filepath
        filepath = os.path.join(
            app.config["UPLOAD_FOLDER"],
            filename
        )

        # save file
        file.save(filepath)

        # parse resume
        clean_text, chunks = parse_resume(filepath)

        # create vector store
        create_vector_store(chunks)

        # save WITH current user email
        cursor.execute(
            """
            INSERT INTO resumes
            (email, filename, role, resume_text)
            VALUES (%s, %s, %s, %s)
            """,
            (email, filename, role, clean_text)
        )

        db.commit()

        return redirect(url_for("questions"))

    return render_template("upload.html")


@app.route("/questions", methods=["GET", "POST"])
def questions():

    # current logged in user
    email = session.get("email")

    if not email:
        return redirect(url_for("login"))

    # get THIS user's latest resume
    cursor.execute(
        """
        SELECT resume_text, role
        FROM resumes
        WHERE email=%s
        ORDER BY id DESC
        LIMIT 1
        """,
        (email,)
    )

    data = cursor.fetchone()

    if not data:
        return render_template(
            "questions.html",
            questions=[],
            error="No resume uploaded yet."
        )

    values: list[Any] = list(data)

    resume_text = str(values[0])
    role = str(values[1])

    prompt = f"""
    You are an interview expert.

    Based on this resume and target role,
    generate 10 personalized interview questions.

    Role:
    {role}

    Resume:
    {resume_text}

    Return only numbered questions.
    """

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.7
    )

    message = response.choices[0].message.content

    if message is None:
        output = ""
    else:
        output = str(message)

    questions_list = output.split("\n")

    return render_template(
        "questions.html",
        questions=questions_list
    )


@app.route("/dashboard")
def dashboard():

    email = session.get("email")

    if not email:
        return redirect(url_for("login"))

    # total uploads by current user
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM resumes
        WHERE email=%s
        """,
        (email,)
    )

    row1 = cursor.fetchone()

    total = 0

    if row1:
        values: list[Any] = list(row1)
        total = int(values[0])

    # latest role by current user
    cursor.execute(
        """
        SELECT role
        FROM resumes
        WHERE email=%s
        ORDER BY id DESC
        LIMIT 1
        """,
        (email,)
    )

    row2 = cursor.fetchone()

    role = "None"

    if row2:
        values2: list[Any] = list(row2)          #converts tuple → list.
        role = str(values2[0])

    best = 82
    avg = 76

    return render_template(
        "dashboard.html",
        total=total,
        best=best,
        avg=avg,
        role=role
    )

@app.route("/chat")
def chat():

    email = session.get("email")

    if not email:
        return redirect(url_for("login"))

    return render_template("chat.html")


@app.route("/ask", methods=["POST"])
def ask():

    data = request.get_json()

    if not data:
        return jsonify(
            {
                "reply": "No message received."
            }
        )

    message = str(data["message"])


    # RAG CHECK
    if not is_ready():

        return jsonify(
            {
                "reply": "Please upload your resume first."
            }
        )

    # RETRIEVE RELEVANT CONTEXT
    context = build_context(message)

    # PROMPT
    prompt = f"""
You are an AI Career Coach.

Use the resume context to answer.

Resume Context:
{context}

User Question:
{message}

IMPORTANT FORMAT RULES:
- Keep answers clean and professional
- Use short paragraphs
- Use bullet points when needed
- Use headings like:
📌 Key Points
💡 Tips
🚀 Next Steps
- Maximum 200 words
- Do NOT write huge paragraphs

Answer now.
"""

    # GROQ CALL
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.7
    )

    reply = response.choices[0].message.content

    if reply is None:
        final_reply = "Sorry, I could not generate a response."
    else:
        final_reply = str(reply)

    return jsonify(
        {
            "reply": final_reply
        }
    )


@app.route("/jd-match", methods=["GET", "POST"])
def jd_match():

    if request.method == "POST":

        jd = request.form["jd"].strip()

        # empty JD
        if not jd:
            return render_template(
                "jd_match.html",
                result="Please enter a Job Description."
            )

        # Resume uploaded or not
        if not is_ready():
            return redirect(url_for("upload"))

        # RAG Resume Context
        context = build_context(jd)

        # Strong Prompt
        prompt = f"""
You are a professional ATS Resume Matching Engine.

STRICT RULES:
- Do NOT ask interview questions
- Do NOT generate mock questions
- Do NOT act as interviewer
- Only compare resume with job description

Candidate Resume:
{context}

Job Description:
{jd}

Return ONLY in this format:

Match Score: XX%

Matching Skills:
- skill 1
- skill 2
- skill 3

Missing Skills:
- skill 1
- skill 2
- skill 3

Strengths:
- point 1
- point 2

Suggestions:
- point 1
- point 2
"""

        # AI Call
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.2
        )

        output = response.choices[0].message.content

        if output is None:
            final_result = "Could not analyze resume."
        else:
            final_result = str(output)

        return render_template(
            "jd_match.html",
            result=final_result
        )

    return render_template("jd_match.html")


# MOCK START ROUTE
@app.route("/mock")
def mock():

    email = session.get("email")

    if not email:
        return redirect(url_for("login"))

    cursor.execute(
        """
        SELECT role, resume_text
        FROM resumes
        WHERE email=%s
        ORDER BY id DESC
        LIMIT 1
        """,
        (email,)
    )

    data = cursor.fetchone()

    if not data:
        return redirect(url_for("upload"))

    row = list(data)

    role = str(row[0])
    resume_text = str(row[1])

    prompt = f"""
You are a senior technical interviewer.

Candidate Target Role:
{role}

Candidate Resume:
{resume_text}

TASK:
Generate ONE realistic interview question.

STRICT RULES:
- Question MUST match the target role.
- Use resume skills/projects if possible.
- Avoid generic "tell me about yourself".
- Ask technical, project-based, scenario-based, or behavioral questions relevant to the role.

Examples:

If role is Python Developer:
Ask about Flask, APIs, MySQL, debugging, projects.

If role is Data Analyst:
Ask about SQL, Excel, Python, dashboards.

If role is AI/ML Engineer:
Ask about models, embeddings, RAG, vector databases.

Return ONLY the question.
"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.4
    )

    question = response.choices[0].message.content or "Tell me about your latest project."

    session["answers"] = []
    session["questions"] = [question]
    session["mock_count"] = 1

    return render_template(
        "mock.html",
        question=question
    )

# NEXT QUESTION ROUTE
@app.route("/mock-next", methods=["POST"])
def mock_next():

    # check logged in user
    email = session.get("email")

    if not email:
        return jsonify(
            {
                "finished": True,
                "question": "Please login first."
            }
        )

    # get latest role of current user
    cursor.execute(
        """
        SELECT role
        FROM resumes
        WHERE email=%s
        ORDER BY id DESC
        LIMIT 1
        """,
        (email,)
    )

    role_data = cursor.fetchone()

    # if no resume uploaded
    if not role_data:
        return jsonify(
            {
                "finished": True,
                "question": "Please upload your resume first."
            }
        )

    row = list(role_data)
    role = str(row[0])

    # get frontend data
    data = request.get_json()

    answer = str(data["answer"])
    count = int(data["count"])

    # session history
    answers = session.get("answers", [])
    questions = session.get("questions", [])

    # save answer
    answers.append(answer)
    session["answers"] = answers

    # finish after 5 questions
    if count >= 5:
        return jsonify(
            {
                "finished": True
            }
        )

    previous_question = questions[-1]

    prompt = f"""
You are a senior technical interviewer.

Candidate Role:
{role}

Previous Question:
{previous_question}

Candidate Answer:
{answer}

TASK:
Ask the next interview question.

STRICT RULES:
- Keep questions relevant to the role
- Increase difficulty gradually
- Ask project-based or technical follow-up questions
- Do not repeat previous questions
- Do not ask generic HR questions unless relevant
- Ask only ONE question

Return ONLY the question.
"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.4
    )

    next_question = response.choices[0].message.content

    if next_question is None:
        next_question = "Explain one project you have built."

    # save question
    questions.append(next_question)

    session["questions"] = questions
    session["mock_count"] = count + 1

    return jsonify(
        {
            "finished": False,
            "question": next_question
        }
    )

# RESULTS ROUTE
@app.route("/results")
def results():

    answers = session.get("answers", [])
    questions = session.get("questions", [])

    if not answers:
        return redirect(url_for("mock"))

    combined = ""

    for i in range(len(answers)):
        combined += f"""
Question:
{questions[i]}

Answer:
{answers[i]}

"""

    prompt = f"""
You are a strict senior interviewer from top product companies.

Evaluate the candidate honestly.

RULES:
- Do not be nice just to encourage.
- Weak answers = low score.
- Missing technical explanation = reduce score.
- Generic answers = reduce score.
- Confidence issues = reduce score.
- Communication issues = reduce score.

Interview Transcript:

{combined}

Return ONLY in this format:

Score: <number between 0-100>
Technical: <number between 0-10>
Confidence: <number between 0-10>
Communication: <number between 0-10>
Hiring: <Low or Medium or High>
Feedback: <honest detailed feedback>
"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.1
    )

    output = response.choices[0].message.content or ""

    score = 0
    technical = 0
    confidence = 0
    communication = 0
    hiring = "Low"
    feedback = "Could not generate feedback."

    score_match = re.search(r"Score:\s*(\d+)", output)
    technical_match = re.search(r"Technical:\s*(\d+)", output)
    confidence_match = re.search(r"Confidence:\s*(\d+)", output)
    communication_match = re.search(r"Communication:\s*(\d+)", output)
    hiring_match = re.search(r"Hiring:\s*(.*)", output)
    feedback_match = re.search(r"Feedback:\s*(.*)", output)

    if score_match:
        score = int(score_match.group(1))

    if technical_match:
        technical = int(technical_match.group(1))

    if confidence_match:
        confidence = int(confidence_match.group(1))

    if communication_match:
        communication = int(communication_match.group(1))

    if hiring_match:
        hiring = hiring_match.group(1).strip()

    if feedback_match:
        feedback = feedback_match.group(1).strip()

    return render_template(
        "results.html",
        score=score,
        technical=technical,
        confidence=confidence,
        communication=communication,
        hiring=hiring,
        feedback=feedback
    )

if __name__ == "__main__":
    app.run(debug=True)
