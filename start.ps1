Write-Host "Activating virtual environment..."
.\.saas-venv\Scripts\Activate.ps1

Write-Host "Initializing Database..."
python init_db.py

Write-Host "Starting FastAPI Backend (Port 8000)..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\.saas-venv\Scripts\Activate.ps1; uvicorn main:app --reload"

Write-Host "Starting Streamlit Frontend (Port 8501)..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\.saas-venv\Scripts\Activate.ps1; streamlit run app.py"

Write-Host "Both backend and frontend have been started in new PowerShell windows."
Write-Host "You can close those windows to stop the servers."
