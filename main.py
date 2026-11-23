import asyncio
import os
import json
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# ================= НАСТРОЙКИ =================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
APP_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://ваш-сервис.onrender.com")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
app = FastAPI()

rooms = {}

@dp.message(Command("start"))
async def cmd_start(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Играть", web_app=WebAppInfo(url=APP_URL))]
    ])
    await message.answer("Привет! Нажми кнопку ниже, чтобы начать играть в 'Угадай кто' онлайн.", reply_markup=keyboard)

@app.websocket("/ws/{room_id}/{role}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, role: str):
    await websocket.accept()
    
    if room_id not in rooms:
        rooms[room_id] = {"p1": None, "p2": None, "target": None, "secret": None}
    
    if role == "p1":
        rooms[room_id]["p1"] = websocket
    elif role == "p2":
        rooms[room_id]["p2"] = websocket

    if rooms[room_id]["p1"] and rooms[room_id]["p2"]:
        await rooms[room_id]["p1"].send_text(json.dumps({"type": "start", "role": "p1"}))
        await rooms[room_id]["p2"].send_text(json.dumps({"type": "start", "role": "p2"}))

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            
            if msg["type"] == "chat":
                other_role = "p2" if role == "p1" else "p1"
                if rooms[room_id][other_role]:
                    await rooms[room_id][other_role].send_text(data)
            
            if msg["type"] == "set_target":
                rooms[room_id]["target"] = msg["target"]
                if rooms[room_id]["p1"]:
                    await rooms[room_id]["p1"].send_text(json.dumps({"type": "target_set"}))
                    
            if msg["type"] == "guess":
                is_win = msg["player"] == rooms[room_id]["target"]
                if rooms[room_id]["p1"]:
                    await rooms[room_id]["p1"].send_text(json.dumps({"type": "result", "win": is_win, "target": rooms[room_id]["target"]}))
                if rooms[room_id]["p2"]:
                    await rooms[room_id]["p2"].send_text(json.dumps({"type": "result", "win": is_win, "target": rooms[room_id]["target"]}))
                    
    except WebSocketDisconnect:
        if rooms[room_id]["p1"] == websocket: rooms[room_id]["p1"] = None
        if rooms[room_id]["p2"] == websocket: rooms[room_id]["p2"] = None
        if not rooms[room_id]["p1"] and not rooms[room_id]["p2"]:
            del rooms[room_id]

@app.get("/")
async def get():
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            body { background: #0f172a; color: #fff; padding: 10px; font-family: sans-serif; }
            .hidden { display: none; }
            .grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 5px; }
            .card { background: #1e3a8a; border: 2px solid #2563eb; border-radius: 5px; text-align: center; padding: 5px; cursor: pointer; font-size: 10px;}
            .card img { width: 100%; height: 60px; object-fit: cover; background: #000; }
            .correct { border-color: #22c55e !important; background: #15803d; }
            .wrong { border-color: #ef4444 !important; opacity: 0.5; }
            #chat { height: 150px; overflow-y: scroll; border: 1px solid #3b82f6; margin-top: 10px; padding: 5px; }
            .btn { background: #3b82f6; color: white; padding: 10px; border: none; border-radius: 5px; cursor: pointer; margin-top: 10px; width: 100%; font-size: 16px;}
        </style>
    </head>
    <body>
        <div id="lobby">
            <h2>Онлайн Угадай Кто</h2>
            <button class="btn" onclick="createGame()">Создать игру</button>
            <input type="text" id="joinId" placeholder="Введите код комнаты" style="width: 100%; padding: 10px; margin-top: 10px; box-sizing: border-box;">
            <button class="btn" onclick="joinGame()">Присоединиться</button>
        </div>

        <div id="game" class="hidden">
            <div id="hint" style="text-align: center; margin-bottom: 10px;">Ожидание игроков...</div>
            <div id="board" class="grid"></div>
            <div id="chat"></div>
            <div id="controls" class="hidden" style="margin-top: 10px;">
                <input type="text" id="msg" placeholder="Введите вопрос..." style="width: 100%; padding: 8px; box-sizing: border-box;">
                <button class="btn" onclick="sendMsg()">Отправить</button>
            </div>
        </div>

        <script>
            const tg = window.Telegram.WebApp;
            tg.ready(); tg.expand();

            const players = ["s1mple", "ZywOo", "NiKo", "donk", "m0NESY", "Magisk", "Snax", "hades"];
            let ws;
            let myRole;
            let roomId;

            function renderBoard() {
                const board = document.getElementById('board');
                board.innerHTML = '';
                players.forEach(name => {
                    let card = document.createElement('div');
                    card.className = 'card';
                    card.innerHTML = `<img src="https://ui-avatars.com/api/?name=${name}&background=random&color=fff&size=100"><br>${name}`;
                    card.onclick = () => {
                        if (myRole === 'p2') {
                            ws.send(JSON.stringify({type: "set_target", target: name}));
                            document.getElementById('hint').innerText = "Вы загадали: " + name;
                        } else {
                            ws.send(JSON.stringify({type: "guess", player: name}));
                        }
                    };
                    board.appendChild(card);
                });
            }

            function createGame() {
                roomId = Math.floor(1000 + Math.random() * 9000).toString();
                localStorage.setItem('role', 'p1');
                connectWS('p1');
            }

            function joinGame() {
                roomId = document.getElementById('joinId').value;
                if (!roomId) return alert("Введите код");
                localStorage.setItem('role', 'p2');
                connectWS('p2');
            }

            function connectWS(role) {
                myRole = role;
                document.getElementById('lobby').classList.add('hidden');
                document.getElementById('game').classList.remove('hidden');
                document.getElementById('hint').innerText = `Код комнаты: ${roomId}. Ожидание...`;
                renderBoard();

                ws = new WebSocket(`wss://${window.location.host}/ws/${roomId}/${role}`);
                
                ws.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    
                    if (data.type === 'start') {
                        document.getElementById('hint').innerText = "Игра началась!";
                        if (myRole === 'p1') {
                            document.getElementById('controls').classList.remove('hidden');
                            document.getElementById('hint').innerText = "Задавай вопросы в чате и угадывай!";
                        } else {
                            document.getElementById('hint').innerText = "Загадай персонажа (нажми на карточку)!";
                        }
                    }
                    
                    if (data.type === 'chat') {
                        const chat = document.getElementById('chat');
                        chat.innerHTML += `<div><b>${data.sender}:</b> ${data.text}</div>`;
                        chat.scrollTop = chat.scrollHeight;
                    }

                    if (data.type === 'result') {
                        if (data.win) {
                            document.getElementById('hint').innerText = "✅ Победа! Персонаж был: " + data.target;
                        } else {
                            document.getElementById('hint').innerText = "❌ Проигрыш. Персонаж был: " + data.target;
                        }
                    }
                };
            }

            function sendMsg() {
                const text = document.getElementById('msg').value;
                if (!text) return;
                ws.send(JSON.stringify({type: "chat", text: text, sender: myRole === 'p1' ? "Вы" : "Противник"}));
                document.getElementById('chat').innerHTML += `<div><b>Вы:</b> ${text}</div>`;
                document.getElementById('msg').value = '';
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content, status_code=200)

async def run_bot():
    await dp.start_polling(bot)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(run_bot())

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)