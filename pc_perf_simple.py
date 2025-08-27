#coding:utf-8
import uvicorn
from app.view import app

if __name__ == '__main__':
    print("Starting PC Performance Monitor...")
    uvicorn.run(app, host="0.0.0.0", port=20223, log_level="info", reload=False)
