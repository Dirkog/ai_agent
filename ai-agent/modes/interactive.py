"""Interactive mode - asks user for clarification like Cursor"""
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

@dataclass
class Question:
    id: str
    text: str
    options: Optional[List[str]] = None
    context: str = ""  # What was the agent doing when it asked

class InteractiveMode:
    def __init__(self):
        self.pending_questions: List[Question] = []
        self.answers: Dict[str, str] = {}
        self.conversation_history: List[Dict[str, str]] = []

    def should_ask_question(self, agent_response: str) -> Optional[Question]:
        """Parse agent response to detect if it wants to ask a question"""
        # Look for question markers in the response
        question_markers = [
            "?",
            "need clarification",
            "should i",
            "would you like",
            "do you want",
            "please specify",
            "unclear",
            "ambiguous"
        ]

        response_lower = agent_response.lower()

        # Check if response contains a question
        if any(marker in response_lower for marker in question_markers):
            # Extract the question
            lines = agent_response.split("\n")
            for line in lines:
                if "?" in line or any(m in line.lower() for m in question_markers[1:]):
                    q = Question(
                        id=f"q_{len(self.pending_questions)}",
                        text=line.strip(),
                        context=agent_response[:500]
                    )
                    return q

        # Check for explicit tool call to ask_user
        if "ASK_USER:" in agent_response:
            parts = agent_response.split("ASK_USER:")
            if len(parts) > 1:
                q_text = parts[1].split("\n")[0].strip()
                q = Question(
                    id=f"q_{len(self.pending_questions)}",
                    text=q_text,
                    context=agent_response[:500]
                )
                return q

        return None

    def ask_user(self, question: Question) -> str:
        """Display question and get user input"""
        print(f"\n{'='*60}")
        print(f"🤔 AGENT NEEDS CLARIFICATION")
        print(f"{'='*60}")
        print(f"Context: {question.context[:200]}...")
        print(f"\n❓ Question: {question.text}")

        if question.options:
            print("Options:")
            for i, opt in enumerate(question.options, 1):
                print(f"  {i}. {opt}")

        print(f"{'='*60}")

        if question.options:
            answer = input("Your choice (number or text): ").strip()
            # Try to parse as number
            try:
                idx = int(answer) - 1
                if 0 <= idx < len(question.options):
                    answer = question.options[idx]
            except ValueError:
                pass
        else:
            answer = input("Your answer: ").strip()

        self.answers[question.id] = answer
        self.pending_questions.append(question)

        return answer

    def format_answer_for_agent(self, question: Question, answer: str) -> str:
        """Format user answer to inject back into agent context"""
        return f"""
[USER CLARIFICATION]
Question: {question.text}
User Answer: {answer}
[END CLARIFICATION]
Please continue with the task based on this clarification.
"""

    def is_interactive_stop(self, response: str) -> bool:
        """Check if agent wants to stop for user input"""
        stop_markers = [
            "<ask_user>",
            "[ASK USER]",
            "WAITING_FOR_USER",
            "NEED_CLARIFICATION"
        ]
        return any(marker in response for marker in stop_markers)
