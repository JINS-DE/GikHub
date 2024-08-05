from pymongo import MongoClient

# uri = "mongodb://mongoadmin:secret@localhost:27017"
# client = MongoClient(uri)
client = MongoClient('localhost', 27017)
client.drop_database("dbjungle")
