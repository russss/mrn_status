FROM ghcr.io/russss/polybot:latest
WORKDIR /app
COPY . /app
ENTRYPOINT ["python", "./tweet_mrn.py"]
