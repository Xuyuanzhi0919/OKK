"""
认证相关API
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db

router = APIRouter()


@router.post("/login")
async def login(db: Session = Depends(get_db)):
    """用户登录"""
    # TODO: 实现登录逻辑
    return {"message": "登录接口（待实现）"}


@router.post("/register")
async def register(db: Session = Depends(get_db)):
    """用户注册"""
    # TODO: 实现注册逻辑
    return {"message": "注册接口（待实现）"}


@router.get("/me")
async def get_current_user(db: Session = Depends(get_db)):
    """获取当前用户信息"""
    # TODO: 实现获取用户信息逻辑
    return {"message": "获取用户信息接口（待实现）"}
