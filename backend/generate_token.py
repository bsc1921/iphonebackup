"""Generate a random API token for backend/config.json."""

from config import generate_api_token, save_config


def main() -> None:
    token = generate_api_token()
    save_config({"api_token": token})
    print("Saved api_token to backend/config.json")
    print(token)


if __name__ == "__main__":
    main()
