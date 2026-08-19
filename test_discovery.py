import asyncio
from app.services.discovery import suggest_iso_standards
from app.core.models import IsoSuggestionRequest

async def main():
    try:
        req = IsoSuggestionRequest(category="security")
        res = await suggest_iso_standards(req)
        print(res.json(indent=2))
    except Exception as e:
        print("ERROR:", e)

if __name__ == "__main__":
    asyncio.run(main())
