from typing import Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from services.ai.nodes import make_generate_node, make_search_node
from services.llm.router import ProviderRouter


class PostState(TypedDict, total=False):
    product_query: str
    search_results: str
    system_prompt: str
    generated_text: str
    error: Optional[str]


def build_graph(
    tavily_api_key: str,
    router: ProviderRouter,
) -> CompiledStateGraph:
    """Build the AI pipeline: search → generate."""
    search_node = make_search_node(tavily_api_key)
    generate_node = make_generate_node(router)

    graph = StateGraph(PostState)
    graph.add_node("search", search_node)
    graph.add_node("generate", generate_node)

    graph.add_edge(START, "search")
    graph.add_edge("search", "generate")
    graph.add_edge("generate", END)

    return graph.compile()
