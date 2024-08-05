from datetime import datetime, timezone
from pymongo import MongoClient

# uri = "mongodb://mongoadmin:secret@localhost:27017"
# client = MongoClient(uri)
client = MongoClient('localhost', 27017)
db = client.dbjungle

now = datetime.now(timezone.utc)

data = []

# {
#     'title': data['title'],
#     'content': data['content'],
#     'likes': 0,
#     'createdAt': now,
#     'updatedAt': now,
#     'deletedAt': None,
#     'origin': request.headers.get('Origin', 'unknown'),
#     'ipAddress': request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip(),
#     'userAgent': request.user_agent.string
# }

for i in range(2000):
    tmp = {
        'title': f'seed_title_{i}',
        'content': f'seed_content_{i}',
        'likes': 0,
        'createdAt': now,
        'updatedAt': now,
        'deletedAt': None,
        'origin': None,
        'ipAddress': None,
        'userAgent': None
    }
    data.append(tmp)

db.memos.insert_many(data)
