from flask import Flask, jsonify, render_template, request,redirect, flash, url_for, make_response
from flask.json.provider import JSONProvider
from bson import ObjectId
from pymongo import MongoClient
from enum import Enum
import certifi
from flask_socketio import SocketIO, join_room, leave_room, send, emit, disconnect
import os
from dotenv import load_dotenv
import json
from datetime import datetime, timezone, timedelta
# JWT
import jwt
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity, verify_jwt_in_request,create_refresh_token

# 해쉬
from flask_bcrypt import Bcrypt

app = Flask(__name__)
socketio = SocketIO(app)

# JWT 설정 (JWT 비밀 키 설정, 만료시간)
app.config['JWT_SECRET_KEY'] = 'gikhub'
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1) # 토큰 만료 시간 1시간

# secret_key를 선언하여 html (front end)와 flask 사이flash 메세지 전달을 암호화
app.secret_key = 'gikhub'
# JWTManager 및 Bcrypt 인스턴스 초기화
jwtManager = JWTManager(app)
bcrypt = Bcrypt(app)

user_info = {}
socket_info = {}

ca = certifi.where()
environment = os.getenv('ENVIRONMENT', 'production')
if environment == 'production':
    ca = certifi.where()
    client = MongoClient(os.getenv('MONGODB_URI_PRODUCTION'))

else:
    client = MongoClient(os.getenv('MONGODB_URI'), tlsCAFile=ca)

db = client.gikhub


class RequestStatus(Enum):
    IN_PROGRESS = "진행중"
    COMPLETED = "거래 완료"

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

@app.route('/' , methods=['GET'])
def render_home():
    try:
        page=int(request.args.get('page',1))
        per_page=int(request.args.get('per_page',5))
        skip=(page-1)*per_page
        items = list(db.items.find(
            {'deletedAt': None}, {'title': 1, 'status':1,'userId':1}).sort([('createdAt',-1)]).skip(skip).limit(per_page))

        for item in items:
            user = db.users.find_one({"_id": item['userId']},{'ho':1,'nick':1})
            item['user_id']=user['ho']+"호 "+user['nick']

        total_items = db.items.count_documents({'deletedAt': None})
        total_pages = (total_items + per_page - 1) // per_page  # 총 페이지 수
        return render_template('index.html',items=items,page=page, total_pages=total_pages)


    except Exception as e:
        data = {
            "type": "error",
            "error_message": str(e),
        }
        return jsonify({'message': 'Server Error'}), 500

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    else:
        user_id = request.json.get('user_id')
        user_pw = request.json.get('password')

        user = db.users.find_one({"user_id": user_id})

        if not user or not bcrypt.check_password_hash(user['password'], user_pw):
            return jsonify({"error": "아이디 또는 비밀번호가 잘못되었습니다."}), 401

        # JWT 토큰 생성
        # indenty 속성에 자신이 포장하고 싶은 값을 넣음(보통 식별을 위해 사용자 아이디를 넣어서 토큰을 만든다.)
        access_token = create_access_token(identity=str(user['_id']))

        return jsonify({"access_token": access_token}), 200

@app.route('/protected', methods=['GET'])
def protected():
    token = request.headers.get('Authorization')
    if token:
            token = token.split("Bearer ")[1]
            decoded_token= jwt.decode(token, app.secret_key, algorithms=['HS256'])
            userId=decoded_token.get('sub')
    else:
        userId = None

    return jsonify({"auth": userId}), 200



@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'GET':
        return render_template('signup.html')
    else:
        data = request.json
        name = data.get('name')
        ho = data.get('ho')
        nick = data.get('nick')
        user_id = data.get('user_id')
        user_pw = data.get('password')

        # 비밀번호 해싱
        hashed_password = bcrypt.generate_password_hash(user_pw).decode('utf-8')
        # 사용자 정보 저장
        db.users.insert_one({
            "user_id": user_id,
            "password": hashed_password,
            "name":name,
            "ho":ho,
            "nick":nick
        })

        flash("회원가입이 성공적으로 완료되었습니다.", "success")
        return redirect(url_for('login'))

@app.route('/check-duplicate', methods=['POST'])
def check_duplicate():
    user_id = request.form['user_id']
    user_exists = db.users.find_one({'user_id': user_id}) is not None
    return jsonify({'exists': user_exists})


@app.route('/chatting/<room_id>')
def chat_room(room_id):
    result = list(db.chat_rooms.aggregate([
        {
                "$match": {
                    "_id": ObjectId(room_id)
                }
            },
            {
                "$lookup": {
                    "from": "items",
                    "localField": "itemId",
                    "foreignField": "_id",
                    "as": "itemData"
                }
            },
            {
                "$unwind": "$itemData"
            },
            {
                "$project": {
                    "_id": 1,
                    "itemId": 1,
                    "participants": 1,
                    "messages": 1,
                    "createdAt": 1,
                    "updatedAt": 1,
                    "itemDetails": "$itemData"
                }
            }
    ]))

    return render_template('chatting.html', room_id=room_id, title=result[0]["itemDetails"]["title"])


@app.route('/chatting-list')
def chat_room_list():
    return render_template('chatting_list.html')


@app.route('/board/<item_id>', methods=['GET'])
def render_board_detail():
    return render_template('board_detail.html')


@app.route('/board', methods=['GET'])
def render_create_board():
    # 만약 토큰 에러 발생시 login
    return render_template('create_board.html')


@app.route('/api/boards/<item_id>', methods=['GET'])
def detail_board(item_id):
    try:
        if not ObjectId.is_valid(item_id):
            return jsonify({'message': 'Invalid item ID'}), 400

        item = db.items.find_one(
            {'_id': ObjectId(item_id), 'deletedAt': None})

        user = db.users.find_one({"_id": item['userId']},{'ho':1,'nick':1})
        item['userId']=user['ho']+"호 "+user['nick']

        if item is None:
            return jsonify({'message': 'Item not found'}), 404

        return render_template('board_detail.html',item=item)
    except Exception as e:
        data = {
            "type": "error",
            "error_message": str(e),
        }
        return jsonify({'message': 'Server Error'}), 500

# refreshToken 을 통해 accessToken 재발급 (아직 사용안함)
@app.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    try:
        current_user = get_jwt_identity()
        access_token = create_access_token(identity=current_user)
        return jsonify(access_token=access_token)
    except Exception as e:
        return jsonify({"msg": "Token refresh failed", "error": str(e)}), 401

@app.route('/api/boards', methods=['POST'])
@jwt_required()
def create_board():
    try:
        # JWT 토큰에서 사용자 ID를 가져옵니다.
        current_user_id = get_jwt_identity()

        data = request.json

        userId=get_jwt_identity()

        if not data:
            return jsonify({"message": "No data provided"}), 400

        title = data.get('title')
        content = data.get('content')
        price=data.get('price')

        if not title:
            return jsonify({"message": "Missing 'title' in request"}), 400

        if not content:
            return jsonify({"message": "Missing 'content' in request"}), 400

        if not price:
            return jsonify({"message": "Missing 'price' in request"}), 400

        now = datetime.now(timezone.utc)
        status=RequestStatus.IN_PROGRESS.value
        # todo userId 토큰에서 얻은값으로 변경

        result = db.items.insert_one(
            {
                'title': data['title'],
                'content': data['content'],
                'price': data['price'],
                # todo userId 토큰에서 얻은값을 ObjectId로 변경하여 저장
                'userId':ObjectId(userId),
                'status': status,
                'createdAt': now,
                'updatedAt': now,
                'deletedAt': None,
            }
        )

        return jsonify({"item_id": result.inserted_id}), 201
    except Exception as e:
        data = {
            "type": "error",
            "error_message": str(e),
        }
        return jsonify({'message': 'Server Error'}), 500


@app.route('/api/boards/<itemId>', methods=['DELETE'])
@jwt_required()
def delete_boards(itemId):
     try:
         if not ObjectId.is_valid(itemId):
             return jsonify({'message': 'Invalid item ID'}), 400

         now = datetime.now(timezone.utc)

         userId=get_jwt_identity()

         item = db.items.find_one({'_id': ObjectId(itemId), 'deletedAt': None})

         if item['userId'] != ObjectId(userId):
            return jsonify({'message': 'Unauthorized'}), 403

         result = db.items.update_one({'_id': ObjectId(itemId), 'deletedAt': None}, {
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

@app.route('/api/boards/status/<item_id>', methods=['PATCH'])
@jwt_required()
def update_status(item_id):
    try:
        if not ObjectId.is_valid(item_id):
            return jsonify({'message': 'Invalid item ID'}), 400
        data = request.json
        if not data:
            return jsonify({"message": "No data provided"}), 400
        now = datetime.now(timezone.utc)
        userId=get_jwt_identity()

        item = db.items.find_one({'_id': ObjectId(item_id), 'deletedAt': None})
        if item['userId']!= ObjectId(userId):
            return jsonify({'message': 'Unauthorized'}), 403
        result = db.items.update_one(
            {'_id': ObjectId(item_id), 'deletedAt': None},
            {
                '$set': { 'updatedAt': now,'status': data.get('status')},
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

@app.route('/api/boards/edit/<item_id>', methods=['PATCH'])
def edit_board(item_id):
    try:
        data=request.json
        title = data.get('title')
        content = data.get('content')
        price = data.get('price')
        now = datetime.now(timezone.utc)
        result = db.items.update_one(
             {'_id': ObjectId(item_id), 'deletedAt': None},
             {
                '$set': { 'updatedAt': now,'title': title,'content':content,'price':price},
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


@app.route('/api/chats', methods=['GET'])
@jwt_required()
def list_chats():
    try:
        auth_header = request.headers.get('Authorization', None)

        if auth_header:
            try:
                token = auth_header.split(' ')[1]
            except IndexError:
                return jsonify({'error': 'Bearer token malformed'}), 401
        else:
            return jsonify({'error': 'Authorization header is missing'}), 401

        userId = get_jwt_identity()

        items = list(db.chat_rooms.aggregate([
            {
                "$match": {
                    "participants": {
                        "$elemMatch": {
                            "userId": ObjectId(userId)
                        }
                    }
                }
            },
            {
                "$lookup": {
                    "from": "items",
                    "localField": "itemId",
                    "foreignField": "_id",
                    "as": "itemData"
                }
            },
            {
                "$unwind": "$itemData"
            },
            {
                "$project": {
                    "_id": 1,
                    "itemId": 1,
                    "participants": 1,
                    "messages": 1,
                    "createdAt": 1,
                    "updatedAt": 1,
                    "itemDetails": "$itemData"
                }
            }
        ]))

        return jsonify(items)
    except Exception as e:
        return jsonify({'message': 'Server Error'}), 500


@app.route('/api/chats', methods=['POST'])
@jwt_required()
def create_chat():
    try:
        data = request.json

        if not data:
            return jsonify({'message': 'No data provided'}), 400

        itemId = data.get('itemId')

        item = db.items.find_one(
            {'_id': ObjectId(itemId), 'deletedAt': None})


        senderId = get_jwt_identity()
        receiverId = item.get('userId')

        if not itemId:
            return jsonify({"message": "Missing 'itemId' in request"}), 400

        if not senderId:
            return jsonify({"message": "Missing 'senderId' in request"}), 400

        if not receiverId:
            return jsonify({"message": "Missing 'receiverId' in request"}), 400

        existing_room = db.chat_rooms.find_one({
            'itemId': ObjectId(itemId),
            'participants': {
                '$all': [
                    {'$elemMatch': {'userId': ObjectId(senderId)}},
                    {'$elemMatch': {'userId': receiverId}}
                ]
            }
        })

        if existing_room:
            return jsonify({'message': 'Chat room already exists', '_id': str(existing_room['_id'])}), 200

        now = datetime.now(timezone.utc)

        result = db.chat_rooms.insert_one(
            {
                'itemId': ObjectId(itemId),
                'participants': [
                    {"userId": ObjectId(senderId), "unreadCount": 0},
                    {"userId": receiverId, "unreadCount": 0}
                ],
                'messages': [],
                'createdAt': now,
                'updatedAt': now,
                'deletedAt': None,
            }
        )

        return jsonify({'_id': str(result.inserted_id)}), 201
    except Exception as e:
        return jsonify({'message': 'Server Error'}), 500


@app.route('/api/chat/messages', methods=['GET'])
@jwt_required()
def list_chat_message():
    try:
        roomId = request.args.get('room')
        # result = db.chat_rooms.find_one({'_id': ObjectId(roomId), 'deletedAt': None})
        result = list(db.chat_rooms.aggregate([
            {
                "$match": {
                    "_id": ObjectId(roomId)
                }
            },
            {
                "$unwind": "$participants"
            },
            {
                "$lookup": {
                    "from": "users",
                    "localField": "participants.userId",
                    "foreignField": "_id",
                    "as": "participantDetails"
                }
            },
            {
                "$unwind": "$participantDetails"
            },
            {
                "$group": {
                    "_id": "$_id",
                    "participants": { "$push": "$participantDetails" },
                    "messages": { "$first": "$messages" },
                    "createdAt": { "$first": "$createdAt" },
                    "updatedAt": { "$first": "$updatedAt" },
                    "deletedAt": { "$first": "$deletedAt" }
                }
            }
        ]))

        return jsonify(result[0])
    except Exception as e:
        return jsonify({'message': 'Server Error'}), 500


@app.route('/api/chat/messages', methods=['POST'])
@jwt_required()
def create_chat_message():
    try:
        data = request.json

        if not data:
            return jsonify({'message': 'No data provided'}), 400

        chatId = data.get('chatId')
        userId = data.get('userId')
        message = data.get('message')

        if not chatId:
            return jsonify({"message": "Missing 'chatId' in request"}), 400

        if not userId:
            return jsonify({"message": "Missing 'userId' in request"}), 400

        if not message:
            return jsonify({"message": "Missing 'message' in request"}), 400

        now = datetime.now(timezone.utc)

        result = db.chat_rooms.update_one(
            { '_id': ObjectId(chatId) },
            {
                '$push': {
                    'messages': {
                        'userId': userId,
                        'message': message,
                        'createdAt': now
                    }
                }
            }
        )

        if result.matched_count == 0:
            return jsonify({'message': 'Item not found'}), 404
        elif result.modified_count == 0:
            return jsonify({'message': 'No changes made to the item'}), 200
        else:
            return jsonify({'message': 'Item updated successfully'})
    except Exception as e:
        return jsonify({'message': 'Server Error'}), 500


def authenticated_only(f):
    def wrapped(*args, **kwargs):
        try:
            verify_jwt_in_request()
        except Exception as e:
            disconnect()
            return
        return f(*args, **kwargs)
    return wrapped

@socketio.on('connect')
@authenticated_only
def handle_connect():
    client_id = request.sid
    token = request.headers.get('Authorization')
    token = token.split()[1]
    payload = jwt.decode(token, 'gikhub', algorithms=['HS256'])

    user = db.users.find_one({"_id": ObjectId(payload['sub'])})

    user_info[payload['sub']] = {"sid": client_id}
    socket_info[request.sid] = {"userId": payload['sub'], "nick": user["nick"]}


@socketio.on('disconnect')
def handle_disconnect():
    client_id = request.sid
    del socket_info[request.sid]

    room = socket_info.get(client_id).get("room")
    if room:
        leave_room(room)
        del socket_info[client_id]


@socketio.on('error')
def handle_error(e):
    client_id = request.sid


@socketio.on('join_room')
def on_join(data):
    room = data['room']
    join_room(room)
    socket_info[request.sid]["room"] = room


@socketio.on('leave_room')
def on_leave(data):
    room = data['room']
    leave_room(room)
    del socket_info[request.sid]["room"]


@socketio.on('send_message')
def handle_send_message(data):
    client_id = request.sid
    room = socket_info.get(client_id).get("room")
    userId = socket_info[request.sid]["userId"]
    nick = socket_info.get(client_id).get("nick")
    if room:
        db.chat_rooms.update_one(
            { '_id': ObjectId(room) },
            {
                '$push': {
                    'messages': {
                        'userId': ObjectId(userId),
                        'message': data["message"],
                        'createdAt': datetime.now(timezone.utc)
                    }
                }
            }
        )
        emit('reply', {"sid": client_id, "message": data["message"], "userId": userId, "nick": nick}, room=room)
        print(f'Received message: {data["message"]} from {client_id} in room {room}')
    else:
        emit('error', {'message': 'No room specified'}, to=client_id)
        print(f'Error: No room specified for message: {data["message"]} from {client_id}')


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)
