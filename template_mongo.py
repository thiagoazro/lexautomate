from pymongo import MongoClient


# CONFIGURAÇÃO DO MONGO
mongo_uri = "mongodb+srv://thiagoazro:FqBdZcF7vtiZXOwl@cluster0.8fmcx.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)

db = client["lexautomate"]
collection = db["modelos_pecas"]

collection.update_many(
    {"$or": [{"prompt_template": {"$exists": False}}, {"prompt_template": ""}]},
    {"$set": {"prompt_template": "Em construção"}}
)
