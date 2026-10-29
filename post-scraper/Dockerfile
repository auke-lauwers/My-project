# Runs the dashboard on a server (Railway, or anywhere Docker runs). Sign in by
# pasting your li_at cookie: a server has no screen for the sign-in window.
# POSTSCRAPER_PASSWORD is required; without it the server refuses to start.
#
#   docker build -t post-scraper .
#   docker run -d -p 8080:8080 -v post-scraper-data:/data \
#     -e POSTSCRAPER_PASSWORD=change-me --name post-scraper post-scraper

FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app
COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir playwright==1.48.0 -r requirements.txt
COPY postscraper ./postscraper
COPY accounts.txt .

# Everything the app writes (posts, settings, accounts, .env, browser profile) lives
# in /data. Mount a volume there (Railway: add a volume with mount path /data) or
# it is lost on every redeploy. No VOLUME line: Railway rejects it.
WORKDIR /data
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1 PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "[ -f accounts.txt ] || cp /app/accounts.txt .; exec python3 -m postscraper serve --host 0.0.0.0"]
