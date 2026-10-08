# Hugging Face Spaces (Docker SDK) / any container host.  Local test:
#   docker build -t fleet-ai . && docker run -p 8501:8501 fleet-ai
FROM python:3.12-slim

# HF Spaces run the container as user 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

# code + the generated data/model so the dashboard starts without running the pipeline
COPY --chown=user . .

EXPOSE 8501
CMD ["streamlit", "run", "app/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
