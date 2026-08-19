from app.core.prompts import AUDIT_LENS_STEP_PROMPT

try:
    prompt = AUDIT_LENS_STEP_PROMPT.format(
        step_number=1,
        step_title="Test Title",
        stage="Test Stage",
        scope="Test Scope",
        criteria="Test Criteria",
        objective="Test Objective"
    )
    print("Success")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
