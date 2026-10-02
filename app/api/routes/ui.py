from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import get_genui
from app.genui.service import GenUIService
from app.schemas.api import UIActionRequest, UIActionResponse

router = APIRouter(prefix="/api/v1")


@router.post("/ui/action", response_model=UIActionResponse)
async def ui_action(
    body: UIActionRequest, genui: Annotated[GenUIService, Depends(get_genui)]
) -> UIActionResponse:
    """Handle an A2UI userAction and return the A2UI messages that update the interface."""
    action = body.userAction
    tool_name, messages = await genui.handle_action(
        body.session_id, action.name, action.surfaceId, action.context
    )
    return UIActionResponse(tool_name=tool_name, messages=messages)
