from flask import Flask, jsonify, render_template, request,redirect, flash, url_for
from flask.json.provider import JSONProvider
from bson import ObjectId
from pymongo import MongoClient
import socketio
from enum import Enum
import certifi
from flask_socketio import SocketIO, join_room, leave_room, send, emit
import os
from dotenv import load_dotenv
import json
from datetime import datetime, timezone
# JWT
from flask_jwt_extended import JWTManager, create_access_token
# 해쉬
from flask_bcrypt import Bcrypt

app = Flask(__name__)
socketio = SocketIO(app)

# JWT 설정 (JWT 비밀 키 설정)
app.config['JWT_SECRET_KEY'] = 'gikhub'
# secret_key를 선언하여 html (front end)와 flask 사이flash 메세지 전달을 암호화
app.secret_key = 'gikhub'
# JWTManager 및 Bcrypt 인스턴스 초기화
jwt = JWTManager(app)
bcrypt = Bcrypt(app)

room_user_counts = {}
user_rooms = {}
ca = certifi.where()
environment = os.getenv('ENVIRONMENT', 'production')

if environment == 'production':
    ca = certifi.where()
    client = MongoClient(os.getenv('MONGODB_URI_PRODUCTION'))
else:
    client = MongoClient(os.getenv('MONGODB_URI'), tlsCAFile=ca)


socketio = SocketIO(app)

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
            {'deletedAt': None}, {'title': 1, 'status':1}).sort([('createdAt',-1)]).skip(skip).limit(per_page))

        for item in items:
            # todo 토큰 변경 필요
            item['user_id']="임시 닉네임"

        total_items = db.items.count_documents({'deletedAt': None})
        total_pages = (total_items + per_page - 1) // per_page  # 총 페이지 수
        return render_template('index.html',items=items,page=page, total_pages=total_pages)


    except Exception as e:
        data = {
            "type": "error",
            "error_message": str(e),
        }
        print(str(e))
        return jsonify({'message': 'Server Error'}), 500

@app.route('/login')
def login():
    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'GET':
        return render_template('signup.html')
    else:
        name = request.form["name"]
        ho = request.form["ho"]
        nick = request.form["nick"]
        user_id = request.form['user_id']
        user_pw = request.form['password']
        confirm_pw = request.form['re_password']


        # 비밀번호와 비밀번호 확인이 일치하는지 확인
        if user_pw != confirm_pw:
            flash("비밀번호가 일치하지 않습니다.", "error")
            return redirect(url_for('signup', user_id=user_id))

        # 비밀번호 길이 확인
        if len(user_pw) < 8:
            flash("패스워드 8자 이상 입력해주세요.", "error")
            return redirect(url_for('signup', user_id=user_id))

        # 사용자 이름 중복 확인
        if db.users.find_one({'user_id': user_id}):
            flash("이미 존재하는 아이디입니다.", "error")
            return redirect(url_for('signup', user_id=user_id))

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



@app.route('/chatting')
def chat_room():
    return render_template('chatting.html')


@app.route('/board', methods=['GET'])
def render_create_board():
    return render_template('create_board.html')


@app.route('/api/boards/<item_id>', methods=['GET'])
def detail_board(item_id):
    try:
        if not ObjectId.is_valid(item_id):
            return jsonify({'message': 'Invalid item ID'}), 400

        item = db.items.find_one(
            {'_id': ObjectId(item_id), 'deletedAt': None})

        if item is None:
            return jsonify({'message': 'Item not found'}), 404

        # userId=db.users.find_one({'_id': item['user_id']}, {'id':1,'_id':0})

        return render_template('board_detail.html',item=item, userId="userId['id']")
    except Exception as e:
        data = {
            "type": "error",
            "error_message": str(e),
        }
        return jsonify({'message': 'Server Error'}), 500


@app.route('/api/boards', methods=['POST'])
def create_board():
    try:
        data = request.json

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
        temporaryId="userId"

        result = db.items.insert_one(
            {
                'title': data['title'],
                'content': data['content'],
                'price': data['price'],
                # todo userId 토큰에서 얻은값을 ObjectId로 변경하여 저장
                'userId':temporaryId,
                'status': status,
                'createdAt': now,
                'updatedAt': now,
                'deletedAt': None,
            }
        )

        return jsonify({"item_id": result.inserted_id}), 201
    except Exception as e:
        print(str(e))
        data = {
            "type": "error",
            "error_message": str(e),
        }
        return jsonify({'message': 'Server Error'}), 500

@app.route('/api/boards/status/<item_id>', methods=['PATCH'])
def update_status(item_id):
    try:
        print(item_id)
        if not ObjectId.is_valid(item_id):
            return jsonify({'message': 'Invalid item ID'}), 400
        print(item_id)
        data = request.json
        if not data:
            return jsonify({"message": "No data provided"}), 400
        now = datetime.now(timezone.utc)
        print(data.get('status'))
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


@app.route('/api/chats', methods=['GET'])
def list_chats():
    try:
        data = request.json

        userId = data.get("userId")

        if not userId:
            return jsonify({"message": "Missing 'userId' in request"}), 400

        items = list(
            db.chat_rooms.find(
                {
                    'deletedAt': None,
                    'participants': {
                        '$elemMatch': {'userId': userId}
                    }
                },
                {'itemId': 1, 'participants': 1, 'messages': 1, 'updatedAt': 1}
            ).sort([('updatedAt', -1)])
        )
        return jsonify(items)
    except Exception as e:
        print(str(e))
        return jsonify({'message': 'Server Error'}), 500


@app.route('/api/chats', methods=['POST'])
def create_chat():
    try:
        data = request.json

        if not data:
            return jsonify({'message': 'No data provided'}), 400

        itemId = data.get('itemId')
        senderId = data.get('senderId')
        receiverId = data.get('receiverId')

        if not itemId:
            return jsonify({"message": "Missing 'itemId' in request"}), 400

        if not senderId:
            return jsonify({"message": "Missing 'senderId' in request"}), 400

        if not receiverId:
            return jsonify({"message": "Missing 'receiverId' in request"}), 400

        now = datetime.now(timezone.utc)

        result = db.chat_rooms.insert_one(
            {
                'itemId': itemId,
                'participants': [
                    {"userId": senderId, "unreadCount": 0},
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
        print(str(e))
        return jsonify({'message': 'Server Error'}), 500


@app.route('/api/chat/messages', methods=['POST'])
def create_chat_message():
    try:
        data = request.json

        if not data:
            return jsonify({'message': 'No data provided'}), 400

        chatId = data.get('chatId')
        userId = data.get('userId')
        message = data.get('message')

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
        print(str(e))
        return jsonify({'message': 'Server Error'}), 500


@socketio.on('connect')
def handle_connect():
    client_id = request.sid
    print(f'Client connected: {client_id}')


@socketio.on('disconnect')
def handle_disconnect():
    client_id = request.sid
    room = user_rooms.get(client_id)  # 연결이 끊긴 유저의 방 정보 가져오기
    if room:
        leave_room(room)
        room_user_counts[room] = room_user_counts.get(room, 1) - 1
        emit('room_user_count', {'room': room, 'count': room_user_counts[room]}, broadcast=True)
        del user_rooms[client_id]
    print(f'Client disconnected: {client_id}')


@socketio.on('error')
def handle_error(e):
    client_id = request.sid
    print(f'An error has occurred on {client_id}: {str(e)}')


@socketio.on('join_room')
def on_join(data):
    room = data['room']
    if room_user_counts.get(room, 0) < 2:  # 방의 최대 인원은 2명
        join_room(room)
        room_user_counts[room] = room_user_counts.get(room, 0) + 1
        user_rooms[request.sid] = room
        emit('room_user_count', {'room': room, 'count': room_user_counts[room]}, broadcast=True)
    else:
        emit('join_error', {'message': 'This room is full.'})  # 방이 가득 찼을 때 클라이언트에게 에러 메시지 전송


@socketio.on('leave_room')
def on_leave(data):
    room = data['room']
    leave_room(room)
    room_user_counts[room] = room_user_counts.get(room, 1) - 1
    emit('room_user_count', {'room': room, 'count': room_user_counts[room]}, broadcast=True)
    del user_rooms[request.sid]
    print(f'User left room: {room}')


@socketio.on('send_message')
def handle_send_message(data):
    client_id = request.sid
    room = user_rooms.get('room')
    if room:
        emit('reply', {"sid": client_id, "message": data["message"]}, room=room)
        print(f'Received message: {data["message"]} from {client_id} in room {room}')
    else:
        emit('error', {'message': 'No room specified'}, to=client_id)
        print(f'Error: No room specified for message: {data["message"]} from {client_id}')


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)
