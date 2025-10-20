"""Prompt utilities for hybrid_chat_test.

Provides prompt construction, chat call wrapper, basic validation,
sanitization and citation expansion helpers. This is a stable, minimal
implementation used by the CLI.
"""
from typing import List, Dict, Any
import re
from openai import OpenAI
import config

client = OpenAI(api_key=config.OPENAI_API_KEY)


def search_summary(pinecone_matches: List[Dict[str, Any]], graph_facts: List[Dict[str, Any]]) -> str:
    vec_snippets = []
    for m in sorted(pinecone_matches, key=lambda x: x.get('score', 0), reverse=True)[:5]:
        meta = m.get('metadata', {})
        score = m.get('score', 0)
        vec_snippets.append(f"- {meta.get('name','Unknown')}: {meta.get('type','Unknown')} (tags: {', '.join(meta.get('tags', []))}, score: {score:.2f})")

    graph_snippets = [f"- {f.get('target_name','')}: {f.get('target_desc','')[:120]}..." for f in graph_facts[:7]]
    return 'Prioritized Vector matches:\n' + '\n'.join(vec_snippets) + '\n\nPrioritized Graph facts:\n' + '\n'.join(graph_snippets)


def build_prompt(user_query: str, pinecone_matches: List[Dict[str, Any]], graph_facts: List[Dict[str, Any]], preferences: Dict[str, str] = None) -> List[Dict[str, str]]:
    preferences = preferences or {}
    trip_length = 4 if '4' in user_query else 3
    # Simple prompt templates. Use preferences['template'] to select.
    TEMPLATES = {
        "concise": {
            "system": "You are a helpful, concise travel assistant.",
            "suffix": f"Provide exactly {trip_length}-day itineraries with timings and local tips. Be concise and factual."
        },
        "chain_of_thought": {
            "system": "You are a helpful travel assistant who explains reasoning clearly.",
            "suffix": f"Provide exactly {trip_length}-day itineraries with timings and local tips. After the itinerary, include a short 'Reasoning' section that lists the key assumptions and steps used to produce the plan (3-5 bullet points). Keep the reasoning concise and factual."
        }
    }

    template_name = (preferences or {}).get("template") or "concise"
    template = TEMPLATES.get(template_name, TEMPLATES["concise"])

    system = template["system"] + " " + template["suffix"]

    vec_context = []
    for m in pinecone_matches[:10]:
        meta = m.get('metadata', {})
        vec_context.append(f"- id: {m.get('id')}, name: {meta.get('name','')}, type: {meta.get('type','')}, score: {m.get('score')}")

    graph_context = [f"- ({f.get('source')}) -[{f.get('rel')}]-> ({f.get('target_id')}) {f.get('target_name')}: {f.get('target_desc')}" for f in graph_facts[:15]]
    summary = search_summary(pinecone_matches, graph_facts)

    user_content = "User query: " + user_query + "\n\n"
    user_content += "Preferences: " + str(preferences) + "\n\n"
    user_content += "Summary:\n" + summary + "\n\n"
    user_content += "Top semantic matches:\n" + "\n".join(vec_context) + "\n\n"
    user_content += "Graph facts:\n" + "\n".join(graph_context) + "\n\n"
    user_content += "Please produce the requested output."

    prompt = [{"role": "system", "content": system}, {"role": "user", "content": user_content}]
    return prompt


def call_chat(prompt_messages: List[Dict[str, str]], max_tokens: int = 1000) -> str:
    resp = client.chat.completions.create(
        model='gpt-4o-mini',
        messages=prompt_messages,
        max_tokens=max_tokens,
        temperature=0.2,
    )
    return resp.choices[0].message.content


def validate_response(response: str, trip_length: int) -> str:
    if f"Day {trip_length}" not in response:
        return f"Response incomplete: Missing Day {trip_length}."
    return 'Valid'


def sanitize_answer(response: str) -> str:
    response = re.sub(r"score:\s*\d+\.\d+", "", response, flags=re.IGNORECASE)
    response = re.sub(r"\[\s*node_id\s*:\s*[^\]]+\]", "", response, flags=re.IGNORECASE)
    response = re.sub(r"\(\s*node_id\s*:\s*[^\)]+\)", "", response, flags=re.IGNORECASE)
    response = re.sub(r" {2,}", " ", response)
    lines = [ln for ln in response.splitlines() if not re.match(r"^\s*(Note:|Validation:)", ln)]
    return '\n'.join(lines).strip()


def expand_citations(response: str, matches: List[Dict[str, Any]] = None, graph_facts: List[Dict[str, Any]] = None) -> str:
    if not matches:
        matches = []
    if not graph_facts:
        graph_facts = []

    meta_by_id = {m.get('id'): m.get('metadata', {}) for m in matches if m.get('id')}
    facts_by_id = {f.get('target_id'): f for f in graph_facts if f.get('target_id')}

    def repl(match):
        raw = match.group(1).strip()
        m_id = re.search(r"(?:(?:node[_ ]?id|nodeid|id)\s*:\s*)?(?P<id>[A-Za-z0-9_-]+)", raw, flags=re.IGNORECASE)
        nodeid = m_id.group('id') if m_id else raw
        if nodeid in meta_by_id:
            meta = meta_by_id[nodeid]
            typ = meta.get('type') or 'Entity'
            tags = meta.get('tags') or []
            return f"{typ} ({', '.join(tags)})" if tags else typ
        if nodeid in facts_by_id:
            f = facts_by_id[nodeid]
            typ = (f.get('labels') or [None])[0] or 'Entity'
            desc = f.get('target_desc','')
            found = [kw for kw in ('romantic','beach','culture','heritage','food','nature','mountain') if kw in desc.lower()]
            return f"{typ} ({', '.join(found)})" if found else typ
        return match.group(0)

    return re.sub(r"\[\s*([^\]]+)\s*\]", repl, response)