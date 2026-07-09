def main():
    print("LinkedIn Post Generator API")
    print("Run these commands from the backend directory.")
    print("Run DynamoDB Local first:")
    print("docker compose -f docker-compose.dynamodb.yml up -d")
    print("Run the FastAPI app with:")
    print("uv run uvicorn app.api.main:app --reload --host 127.0.0.1 --port 7860")
    print("Open API docs at:")
    print("http://localhost:7860/docs")


if __name__ == "__main__":
    main()
