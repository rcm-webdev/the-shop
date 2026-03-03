from pymongo import MongoClient

client = MongoClient()
db = client["diecast_inventory"]
collection = db["variants"]

cursor = collection.find({ "Toy #": "N4011" })

for i, doc in enumerate(cursor, 1):
    print(f"\nVariant {i}")
    for k, v in doc.items():
        print(f"{k}: {v}")