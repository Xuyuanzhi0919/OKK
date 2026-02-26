"""
后端启动脚本 - 确保WebSocket正确加载
"""
import uvicorn
from app.core.config import settings

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 启动 OKK 量化交易系统后端")
    print("=" * 60)
    print(f"📡 HTTP API: http://0.0.0.0:8000")
    print(f"🔌 WebSocket: ws://0.0.0.0:8000/socket.io/")
    print(f"📚 API文档: http://0.0.0.0:8000/docs")
    print(f"🐛 调试模式: {settings.DEBUG}")
    print("=" * 60)
    
    uvicorn.run(
        "app.main:socket_app",  # 使用socket_app而不是app
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info"
    )
