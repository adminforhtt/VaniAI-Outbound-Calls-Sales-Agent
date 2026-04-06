from app.config.settings import settings
import os
print(f"SARVAM_API_KEY from settings: {settings.SARVAM_API_KEY[:5]}...{settings.SARVAM_API_KEY[-5:] if settings.SARVAM_API_KEY else ''}")
print(f"SARVAM_API_KEY from os.environ: {os.environ.get('SARVAM_API_KEY', '')[:5]}...")
