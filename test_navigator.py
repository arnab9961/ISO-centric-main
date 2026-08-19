import asyncio
from app.core.models import NavigatorRequest

def main():
    try:
        # Try passing standard fields
        req1 = NavigatorRequest(
            organization_context="Acme Software Corp is a medium security agency.",
            output_type="Policy Document",
            tone="formal",
            language="English"
        )
        print("Standard instantiation works:")
        print("  org_context:", req1.organization_context)
        print("  output_type:", req1.output_type)
        print("  extra fields:", req1.model_extra)
        
        # Try passing dynamic extra fields
        req2 = NavigatorRequest(
            organization_context="Acme Software Corp is a medium security agency.",
            output_type="Custom Audit Log SOP",
            custom_field_1="value 1",
            additional_context="Very critical compliance project",
            tone="formal",
            language="English"
        )
        print("\nDynamic/extra instantiation works:")
        print("  org_context:", req2.organization_context)
        print("  output_type:", req2.output_type)
        print("  extra fields:", req2.model_extra)

        # Try passing completely arbitrary fields without standard ones (which are now optional)
        req3 = NavigatorRequest(
            company_name="Google LLC",
            document_style="informal",
            any_random_input=42
        )
        print("\nFully dynamic instantiation works:")
        print("  org_context:", req3.organization_context)
        print("  output_type:", req3.output_type)
        print("  extra fields:", req3.model_extra)

    except Exception as e:
        print("ERROR:", e)

if __name__ == "__main__":
    main()
