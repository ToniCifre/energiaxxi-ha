from custom_components.energiaxxi.api import EnergiaxxiAPI

if __name__ == "__main__":
    api = EnergiaxxiAPI("user@gmail.com", "password123")
    print(api.session.headers)
    consumption_data = api.fetch_consumption()
    print(consumption_data)