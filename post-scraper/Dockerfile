# Runs the dashboard on a server. Sign in by pasting your li_at cookie
# (a server has no screen for the sign-in window).
#
#   docker build -t post-scraper .
#   docker run -d -p 8080:8080 -v post-scraper-data:/data \
#     -e POSTSCRAPER_PASSWORD=change-me --name post-scraper post-scraper

FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir playwright==1.48.0 -r requirements.txt
COPY postscraper ./postscraper
COPY accounts.txt .

# Everything the app writes (posts, settings, accounts, .env, browser profile) lives in /data.
WORKDIR /data
VOLUME /data
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1 PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "cp -n /app/accounts.txt /data/accounts.txt; exec python -m postscraper serve --host 0.0.0.0"]
