class SupervisorAgent:
    @staticmethod
    def check_response_safety(response: str) -> str:
        """
        Ensures the AI doesn't say inappropriate things or make unintended promises.
        In a production system, this could invoke another LLM call or regex filtering.
        Here we do a simple regex/keyword filter for demonstration.
        """
        forbidden_words = ["guarantee", "100% free", "curse_word"]
        lower_response = response.lower()
        for word in forbidden_words:
            if word in lower_response:
                return "I apologize, but I cannot discuss that currently. Let me provide you with relevant information."
        
        return response
