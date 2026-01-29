import requests

def reverse_geocode_nominatim(lat: float, lng: float) -> str | None:
    url = "https://nominatim.openstreetmap.org/reverse"
    params = {
        "format": "jsonv2",
        "lat": lat,
        "lon": lng,
        "zoom": 18,
        "addressdetails": 1,
    }
    headers = {
        "User-Agent": "DenunciasSalcedo/1.0 (contacto: tukackerfav9@gmail.com)"
    }
    r = requests.get(url, params=params, headers=headers, timeout=6)
    if r.status_code != 200:
        return None
    data = r.json()
    return data.get("display_name")
