from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017/")  # ou sua URI real
db = client["lexautomate"]
collection = db["modelos_pecas"]

collection.update_many(
    {"$or": [{"prompt_template": {"$exists": False}}, {"prompt_template": ""}]},
    {"$set": {"prompt_template": "Em construção"}}
)
