from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import MCPServerCreate, MCPServerResponse, MCPServerUpdate, MCPTestResult
from app.services import mcp_service

router = APIRouter(prefix="/mcp", tags=["mcp"])


class EnableBody(BaseModel):
    enabled: bool


@router.get("/servers", response_model=list[MCPServerResponse])
def list_servers(db: Session = Depends(get_db)):
    return mcp_service.list_servers(db)


@router.post(
    "/servers", response_model=MCPServerResponse, status_code=status.HTTP_201_CREATED
)
def create_server(payload: MCPServerCreate, db: Session = Depends(get_db)):
    return mcp_service.create_server(db, payload)


@router.put("/servers/{server_id}", response_model=MCPServerResponse)
def update_server(
    server_id: int, payload: MCPServerUpdate, db: Session = Depends(get_db)
):
    server = mcp_service.update_server(db, server_id, payload)
    if server is None:
        raise HTTPException(status_code=404, detail="MCP 服务器不存在")
    return server


@router.delete("/servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_server(server_id: int, db: Session = Depends(get_db)):
    if not mcp_service.delete_server(db, server_id):
        raise HTTPException(status_code=404, detail="MCP 服务器不存在")


@router.post("/servers/{server_id}/enable", response_model=MCPServerResponse)
def enable_server(
    server_id: int, body: EnableBody, db: Session = Depends(get_db)
):
    server = mcp_service.enable_server(db, server_id, enabled=body.enabled)
    if server is None:
        raise HTTPException(status_code=404, detail="MCP 服务器不存在")
    return server


@router.post("/servers/{server_id}/test", response_model=MCPTestResult)
def test_server(server_id: int, db: Session = Depends(get_db)):
    result = mcp_service.test_connection(db, server_id)
    if result is None:
        raise HTTPException(status_code=404, detail="MCP 服务器不存在")
    return result


@router.get("/servers/{server_id}/tools", response_model=MCPTestResult)
def list_tools(server_id: int, db: Session = Depends(get_db)):
    result = mcp_service.server_tools(db, server_id, use_cache=True)
    if result is None:
        raise HTTPException(status_code=404, detail="MCP 服务器不存在")
    return result
