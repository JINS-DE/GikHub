from flask import Flask, jsonify, render_template, request
from flask.json.provider import JSONProvider
from bson import ObjectId
from pymongo import MongoClient
import socketio

import json
from datetime import datetime, timezone


app = Flask(__name__)
sio = socketio.Server()

app.wsgi_app = socketio.WSGIApp(sio, app.wsgi_app)

client = MongoClient('localhost', 27017)
db = client.gikhub

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        if isinstance(o, datetime):
            return o.isoformat()
        return json.JSONEncoder.default(self, o)


class CustomJSONProvider(JSONProvider):
    def dumps(self, obj, **kwargs):
        return json.dumps(obj, **kwargs, cls=CustomJSONEncoder)

    def loads(self, s, **kwargs):
        return json.loads(s, **kwargs)

app.json = CustomJSONProvider(app)


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/api/memos', methods=['GET'])
def list_memos():
    try:
        items = list(db.memos.find(
            {'deletedAt': None}, {'title': 1, 'content': 1, 'likes': 1}).sort({'likes': -1}))
        return jsonify(items)
    except Exception as e:
        data = {
            "type": "error",
            "error_message": str(e),
        }
        return jsonify({'message': 'Server Error'}), 500


@app.route('/api/memos/<item_id>', methods=['GET'])
def get_memo(item_id):
    try:
        if not ObjectId.is_valid(item_id):
            return jsonify({'message': 'Invalid item ID'}), 400

        item = db.memos.find_one(
            {'_id': ObjectId(item_id), 'deletedAt': None}, {'title': 1, 'content': 1, 'likes': 1})

        if item is None:
            return jsonify({'message': 'Item not found'}), 404

        return jsonify(item)
    except Exception as e:
        data = {
            "type": "error",
            "error_message": str(e),
        }
        return jsonify({'message': 'Server Error'}), 500


@app.route('/api/memos', methods=['POST'])
def create_memo():
    try:
        data = request.json

        if not data:
            return jsonify({"message": "No data provided"}), 400

        title = data.get('title')
        content = data.get('content')

        if not title:
            return jsonify({"message": "Missing 'title' in request"}), 400

        if not content:
            return jsonify({"message": "Missing 'content' in request"}), 400

        now = datetime.now(timezone.utc)

        result = db.memos.insert_one(
            {
                'title': data['title'],
                'content': data['content'],
                'likes': 0,
                'createdAt': now,
                'updatedAt': now,
                'deletedAt': None,
                'origin': request.headers.get('Origin', 'unknown'),
                'ipAddress': request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip(),
                'userAgent': request.user_agent.string
            }
        )

        return jsonify({"_id": result.inserted_id}), 201
    except Exception as e:
        data = {
            "type": "error",
            "error_message": str(e),
        }
        return jsonify({'message': 'Server Error'}), 500


@app.route('/api/memos/<item_id>', methods=['PUT'])
def update_memo(item_id):
    try:
        if not ObjectId.is_valid(item_id):
            return jsonify({'message': 'Invalid item ID'}), 400

        data = request.json

        if not data:
            return jsonify({"message": "No data provided"}), 400

        title = data.get('title')
        content = data.get('content')

        if not title:
            return jsonify({"message": "Missing 'title' in request"}), 400

        if not content:
            return jsonify({"message": "Missing 'content' in request"}), 400

        now = datetime.now(timezone.utc)

        result = db.memos.update_one({'_id': ObjectId(item_id), 'deletedAt': None}, {
            '$set': {
                'title': data["title"],
                'content': data["content"],
                'updatedAt': now,
            }
        })

        if result.matched_count == 0:
            return jsonify({"message": "Item not found"}), 404
        elif result.modified_count == 0:
            return jsonify({"message": "No changes made to the item"}), 200
        else:
            return jsonify({"message": "Item updated successfully"})
    except Exception as e:
        data = {
            "type": "error",
            "error_message": str(e),
        }
        return jsonify({'message': 'Server Error'}), 500


@app.route('/api/memos/<item_id>', methods=['DELETE'])
def delete_memo(item_id):
    try:
        if not ObjectId.is_valid(item_id):
            return jsonify({'message': 'Invalid item ID'}), 400

        now = datetime.now(timezone.utc)

        result = db.memos.update_one({'_id': ObjectId(item_id), 'deletedAt': None}, {
            '$set': {
                'deletedAt': now,
            }
        })

        if result.matched_count == 0:
            return jsonify({"message": "Item not found"}), 404
        elif result.modified_count == 0:
            return jsonify({"message": "No changes made to the item"}), 200
        else:
            return jsonify({"message": "Item deleted successfully"})
    except Exception as e:
        data = {
            "type": "error",
            "error_message": str(e),
        }
        return jsonify({'message': 'Server Error'}), 500


@app.route('/api/memos/likes/<item_id>', methods=['PATCH'])
def like_memo(item_id):
    try:
        if not ObjectId.is_valid(item_id):
            return jsonify({'message': 'Invalid item ID'}), 400

        now = datetime.now(timezone.utc)

        result = db.memos.update_one(
            {'_id': ObjectId(item_id), 'deletedAt': None}, {
                '$set': {
                    'updatedAt': now
                },
                '$inc': {
                    'likes': 1
                }
            })

        if result.matched_count == 0:
            return jsonify({"message": "Item not found"}), 404
        elif result.modified_count == 0:
            return jsonify({"message": "No changes made to the item"}), 200
        else:
            return jsonify({"message": "Item updated successfully"})
    except Exception as e:
        data = {
            "type": "error",
            "error_message": str(e),
        }
        return jsonify({'message': 'Server Error'}), 500

@sio.event
def connect(sid, environ):
    print('connect ', sid)

@sio.event
def disconnect(sid):
    print('disconnect ', sid)


if __name__ == '__main__':
    app.run('0.0.0.0', port=5000)
