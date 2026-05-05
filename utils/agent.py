def route_query(user_message):

    message = user_message.lower().strip()

    # --------------------------
    # JD Match Tool
    # --------------------------
    if (
        "job description" in message
        or "jd" in message
        or "match my resume" in message
        or "ats" in message
        or "compare resume" in message
    ):
        return "jd_match"

    # --------------------------
    # Mock Interview Tool
    # --------------------------
    elif (
        "mock interview" in message
        or "interview me" in message
        or "practice interview" in message
        or "take interview" in message
    ):
        return "mock"

    # --------------------------
    # Question Generator Tool
    # --------------------------
    elif (
        "questions" in message
        or "interview questions" in message
        or "ask questions" in message
        or "generate questions" in message
    ):
        return "questions"

    # --------------------------
    # Dashboard / Progress Tool
    # --------------------------
    elif (
        "dashboard" in message
        or "progress" in message
        or "score" in message
        or "stats" in message
    ):
        return "dashboard"

    # --------------------------
    # Resume Analysis Tool
    # --------------------------
    elif (
        "analyze resume" in message
        or "resume feedback" in message
        or "improve resume" in message
        or "resume tips" in message
    ):
        return "resume_review"

    # --------------------------
    # Default = Chat RAG Tool
    # --------------------------
    else:
        return "chat"
    

# SIMPLE TOOL ROUTER AGENT
# Decides which feature to use