from twilio.rest import Client
from app.config.settings import settings

twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

class TwilioService:
    @staticmethod
    def initiate_call(to_number: str, url: str):
        """
        Initiates an outbound call using Twilio.
        The url should point to the /call/voice webhook which provides initial TwiML.
        """
        call = twilio_client.calls.create(
            to=to_number,
            from_=settings.TWILIO_PHONE_NUMBER,
            url=url,
            record=True,
            status_callback=f"{settings.BASE_URL}/api/calls/status",
            status_callback_event=["initiated", "ringing", "answered", "completed"]
        )
        return call.sid
