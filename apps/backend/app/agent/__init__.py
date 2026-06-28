"""The intent agent: a LangGraph state machine over the retrieval primitive.

Classifies a natural-language query (intent + language), decides the next best action, and
returns products, a clarifying question, or a partner hand-off. See docs/decisions/0006.
"""
