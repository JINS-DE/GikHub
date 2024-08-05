from flask import Flask, jsonify, render_template, request
from flask.json.provider import JSONProvider
from bson import ObjectId
from pymongo import MongoClient

import json
from datetime import datetime, timezone


app = Flask(__name__)

# uri = "mongodb://mongoadmin:secret@localhost:27017"
# client = MongoClient(uri)
# db = client.dbjungle

client = MongoClient('localhost', 27017)
db = client.dbjungle

#####################################################################################
# 이 부분은 코드를 건드리지 말고 그냥 두세요. 코드를 이해하지 못해도 상관없는 부분입니다.
#
# ObjectId 타입으로 되어있는 _id 필드는 Flask 의 jsonify 호출시 문제가 된다.
# 이를 처리하기 위해서 기본 JsonEncoder 가 아닌 custom encoder 를 사용한다.
# Custom encoder 는 다른 부분은 모두 기본 encoder 에 동작을 위임하고 ObjectId 타입만 직접 처리한다.


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


# 위에 정의되 custom encoder 를 사용하게끔 설정한다.
app.json = CustomJSONProvider(app)

# 여기까지 이해 못해도 그냥 넘어갈 코드입니다.
# #####################################################################################

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

        # result = db.memos.delete_one({'_id': ObjectId(item_id)})

        # if result.deleted_count == 0:
        #     return jsonify({'message': 'Item not found'}), 404

        # return jsonify({'message': 'Item deleted successfully'})

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


if __name__ == '__main__':
    app.run('0.0.0.0', port=5000)
