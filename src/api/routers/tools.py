"""
Tools API Router
Provides endpoints for various tools like paper search, web search, etc.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.logging import get_logger
from src.tools.paper_search_tool import PaperSearchTool

logger = get_logger("ToolsAPI")

router = APIRouter()


class PaperSearchRequest(BaseModel):
    """Request model for paper search"""

    query: str = Field(..., description="Search query (keywords)")
    max_results: int = Field(5, ge=1, le=20, description="Maximum number of results")
    years_limit: int | None = Field(
        3, ge=1, le=20, description="Limit to papers from recent N years"
    )
    sort_by: str = Field("relevance", description="Sort by 'relevance' or 'date'")


class PaperSearchResponse(BaseModel):
    """Response model for paper search"""

    papers: list[dict]
    query: str
    count: int


@router.post("/paper_search", response_model=PaperSearchResponse)
async def search_papers(request: PaperSearchRequest):
    """
    Search for academic papers on ArXiv

    Args:
        request: Paper search request with query and parameters

    Returns:
        List of papers with metadata (title, authors, abstract, url, etc.)
    """
    try:
        logger.info(
            f"Paper search request: query='{request.query}', max_results={request.max_results}"
        )

        tool = PaperSearchTool()
        papers = await tool.search_papers(
            query=request.query,
            max_results=request.max_results,
            years_limit=request.years_limit,
            sort_by=request.sort_by,
        )

        logger.info(f"Paper search completed: found {len(papers)} papers")

        return PaperSearchResponse(papers=papers, query=request.query, count=len(papers))

    except Exception as e:
        logger.error(f"Paper search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Paper search failed: {str(e)}")
