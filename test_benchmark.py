from app.core.models import BenchmarkRequest

def main():
    try:
        # Test default
        req1 = BenchmarkRequest(document_text="This is a test document to analyze compliance...")
        print("Default target_standard:", req1.target_standard)

        # Test custom target_standard
        req2 = BenchmarkRequest(
            document_text="This is a test document to analyze compliance...",
            target_standard="ISO 27001:2022"
        )
        print("Custom target_standard:", req2.target_standard)
        
    except Exception as e:
        print("ERROR:", e)

if __name__ == "__main__":
    main()
