# cli.py
# Command-line interface for the chat assistant

from typing import List
from vector_search import query_pinecone
from graph import fetch_graph_context
from prompting import build_prompt, call_chat, validate_response, sanitize_answer, expand_citations

def interactive_chat():
    """Run interactive chat loop."""
    print("Hybrid travel assistant. Type 'exit' to quit.")
    # Get user preferences
    budget = input("Enter your budget (e.g., low, medium, high): ").strip().lower() or "medium"
    interests = input("Enter your interests (e.g., romantic, adventure, culture): ").strip().lower() or "romantic"
    preferences = {"budget": budget, "interests": interests}
    
    while True:
        query = input("\nEnter your travel question: ").strip()
        if not query or query.lower() in ("exit", "quit"):
            break

        # Query vector DB
        matches = query_pinecone(query, top_k=10)  # Updated to 10
        match_ids = [m["id"] for m in matches]

        # Fetch graph context with error handling
        try:
            graph_facts = fetch_graph_context(match_ids)
        except Exception as e:
            print(f"Warning: Could not fetch graph context ({e}). Using vector-only response.")
            graph_facts = []

        # Build and call prompt
        prompt = build_prompt(query, matches, graph_facts, preferences)
        # first attempt
        answer = call_chat(prompt, max_tokens=1100)

        # validate and retry once if incomplete (common cause: token truncation)
        validation = validate_response(answer, 4 if '4' in query else 3)
        if validation != "Valid":
            # silently retry once to complete the response (no user-facing message)
            followup = [
                {"role": "user", "content": "The previous response was incomplete. Please complete the missing day(s) and ensure all days are covered."}
            ]
            prompt_extended = prompt + followup
            answer = call_chat(prompt_extended, max_tokens=1200)

        # expand citation placeholders like [city_da_lat] to readable tags, then sanitize
        answer_expanded = expand_citations(answer, matches, graph_facts)
        answer_clean = sanitize_answer(answer_expanded)
        print("\n=== Assistant Answer ===\n")
        print(answer_clean)
        print("\n=== End ===\n")

if __name__ == "__main__":
    interactive_chat()