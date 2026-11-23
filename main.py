import asyncio
import os
import json
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, LabeledPrice, PreCheckoutQuery
from contextlib import asynccontextmanager

# ================= НАСТРОЙКИ =================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
APP_URL = "https://tg-game-bot-4.onrender.com"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
rooms = {}

async def run_bot():
    await dp.start_polling(bot)

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(run_bot())
    yield

app = FastAPI(lifespan=lifespan)

# --- 1. КОМАНДЫ БОТА ---
@dp.message(Command("start"))
async def cmd_start(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Играть онлайн", web_app=WebAppInfo(url=APP_URL))],
        [InlineKeyboardButton(text="⭐ Поддержать автора", callback_data="support")]
    ])
    await message.answer("Привет! Нажми кнопку ниже, чтобы сыграть в 'Угадай кто' с другом.", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data == "support")
async def process_support(call):
    await bot.send_invoice(
        chat_id=call.message.chat.id,
        title="Поддержка автора",
        description="Спасибо за поддержку проекта!",
        payload="donate_support",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Поддержка", amount=5)],
        start_parameter="donate"
    )
    await call.answer()

@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout_q: PreCheckoutQuery):
    await pre_checkout_q.answer(ok=True)

@dp.message(lambda message: message.successful_payment is not None)
async def process_successful_payment(message: Message):
    await message.answer(f"Огромное спасибо за поддержку! Ты оплатил {message.successful_payment.total_amount} звезд. ❤️")

# --- 2. ЛОГИКА ОНЛАЙНА (WEBSOCKETS) ---
@app.websocket("/ws/{room_id}/{role}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, role: str):
    await websocket.accept()
    
    if room_id not in rooms:
        rooms[room_id] = {
            "p1": None, "p2": None, 
            "p1_target": None, "p2_target": None,
            "turn": "p1", "started": False
        }
    
    if role == "p1": rooms[room_id]["p1"] = websocket
    elif role == "p2": rooms[room_id]["p2"] = websocket

    # Если оба подключились
    if rooms[room_id]["p1"] and rooms[room_id]["p2"]:
        await rooms[room_id]["p1"].send_text(json.dumps({"type": "connected"}))
        await rooms[room_id]["p2"].send_text(json.dumps({"type": "connected"}))

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            other_role = "p2" if role == "p1" else "p1"
            
            # Выбор секретного персонажа
            if msg["type"] == "set_target":
                rooms[room_id][f"{role}_target"] = msg["target"]
                if rooms[room_id]["p1_target"] and rooms[room_id]["p2_target"]:
                    rooms[room_id]["started"] = True
                    # Сообщаем обоим, что игра началась
                    for r in ["p1", "p2"]:
                        if rooms[room_id][r]:
                            await rooms[room_id][r].send_text(json.dumps({"type": "start", "turn": rooms[room_id]["turn"]}))

            # Чат
            elif msg["type"] == "chat":
                if rooms[room_id][other_role]:
                    await rooms[room_id][other_role].send_text(json.dumps({"type": "chat", "text": msg["text"], "sender": role}))

            # Передача хода
            elif msg["type"] == "end_turn":
                rooms[room_id]["turn"] = other_role
                for r in ["p1", "p2"]:
                    if rooms[room_id][r]:
                        await rooms[room_id][r].send_text(json.dumps({"type": "turn_change", "turn": rooms[room_id]["turn"]}))

            # Попытка угадать (конец игры)
            elif msg["type"] == "guess":
                target = rooms[room_id][f"{other_role}_target"]
                is_win = msg["player"] == target
                
                result_msg = {
                    "type": "result", 
                    "win": is_win, 
                    "guessed": msg["player"], 
                    "target": target,
                    "guesser": role
                }
                for r in ["p1", "p2"]:
                    if rooms[room_id][r]:
                        await rooms[room_id][r].send_text(json.dumps(result_msg))

    except WebSocketDisconnect:
        if rooms[room_id]["p1"] == websocket: rooms[room_id]["p1"] = None
        if rooms[room_id]["p2"] == websocket: rooms[room_id]["p2"] = None
        if not rooms[room_id]["p1"] and not rooms[room_id]["p2"]:
            del rooms[room_id]

# --- 3. HTML ИНТЕРФЕЙС ---
HTML_CONTENT = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@500;700&display=swap');
        body { 
            background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%); color: #fff; 
            padding: 10px; font-family: 'Montserrat', sans-serif; margin: 0; overflow-x: hidden;
        }
        .bg-icon { position: fixed; opacity: 0.05; font-size: 40px; z-index: -1; animation: float 15s infinite linear; }
        @keyframes float { 0% { transform: translateY(0); } 50% { transform: translateY(-30px); } 100% { transform: translateY(0); } }
        .hidden { display: none !important; }
        .container { background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(10px); border-radius: 20px; padding: 15px; border: 1px solid rgba(255,255,255,0.1); box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
        h2 { text-align: center; background: -webkit-linear-gradient(45deg, #60a5fa, #c084fc); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 22px; margin-top: 0; }
        .grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
        .card { 
            background: linear-gradient(135deg, #1e3a8a, #3b82f6); border-radius: 12px; text-align: center; 
            padding: 8px 4px; cursor: pointer; font-size: 11px; font-weight: 700; transition: all 0.2s;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3); border: 1px solid #60a5fa;
            display: flex; flex-direction: column; align-items: center; justify-content: center; height: 80px;
        }
        .card:active { transform: scale(0.95); }
        .card-emoji { font-size: 24px; margin-bottom: 5px; }
        .card.eliminated { opacity: 0.15; filter: grayscale(100%); transform: scale(0.9); }
        .card.my-secret { border-color: #eab308 !important; box-shadow: 0 0 15px #eab308; }
        #chat { height: 120px; overflow-y: auto; border: 1px solid rgba(255,255,255,0.2); border-radius: 12px; margin-top: 15px; padding: 10px; background: rgba(0,0,0,0.3); font-size: 13px; }
        .btn { background: linear-gradient(45deg, #8b5cf6, #3b82f6); color: white; padding: 12px; border: none; border-radius: 12px; cursor: pointer; margin-top: 10px; width: 100%; font-size: 15px; font-weight: bold; transition: 0.2s;}
        .btn:active { transform: scale(0.98); }
        .btn-orange { background: linear-gradient(45deg, #f59e0b, #ef4444); }
        .btn-green { background: linear-gradient(45deg, #10b981, #059669); }
        input { width: 100%; padding: 12px; margin-top: 10px; box-sizing: border-box; border-radius: 12px; border: none; background: rgba(255,255,255,0.1); color: #fff; font-family: inherit;}
        .cat-btn { background: rgba(255,255,255,0.1); border: 1px solid #60a5fa; padding: 8px; margin: 3px; border-radius: 10px; display: inline-block; cursor: pointer; font-size: 12px;}
        #hint { font-size: 15px; text-align: center; margin-bottom: 15px; font-weight: 500; color: #fbbf24; }
        .turn-indicator { text-align: center; font-size: 13px; margin-bottom: 10px; color: #a78bfa; font-weight: bold;}
    </style>
</head>
<body>
    <div class="bg-icon" style="top: 10%; left: 5%;">🎮</div>
    <div class="bg-icon" style="top: 20%; right: 10%; animation-delay: 2s;">👾</div>
    <div class="bg-icon" style="bottom: 15%; left: 15%; animation-delay: 4s;">🎲</div>

    <div id="lobby" class="container">
        <h2>🕵️‍♂️ Угадай Кто?</h2>
        <div style="text-align:center; margin-bottom: 15px;">
            <div class="cat-btn" onclick="selectCat('cs')">🔫 Ксеры</div>
            <div class="cat-btn" onclick="selectCat('dota')">⚔️ Дотера</div>
            <div class="cat-btn" onclick="selectCat('memes')">😂 Мемы</div>
            <div class="cat-btn" onclick="selectCat('rappers')">🎤 Реперы</div>
            <div class="cat-btn" onclick="selectCat('football')">⚽ Футбол</div>
            <div class="cat-btn" onclick="selectCat('gifts')">🎁 Подарки</div>
        </div>
        <button class="btn" onclick="createGame()">Создать игру</button>
        <div style="margin-top: 15px; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 15px;">
            <input type="text" id="joinId" placeholder="Код комнаты">
            <button class="btn btn-green" onclick="joinGame()">Присоединиться</button>
        </div>
        <button class="btn btn-orange" onclick="supportAuthor()">⭐ Поддержать автора</button>
    </div>

    <div id="game" class="container hidden">
        <div id="turn-indicator" class="turn-indicator"></div>
        <div id="hint">Ожидание подключения...</div>
        
        <div id="board" class="grid"></div>
        
        <div id="chat"></div>
        
        <div id="controls" class="hidden">
            <input type="text" id="msg" placeholder="Задай вопрос (да/нет)...">
            <div style="display:flex; gap:10px;">
                <button class="btn" onclick="sendMsg()" style="padding: 10px; font-size:14px; margin-top:5px;">Спросить</button>
                <button class="btn btn-green" onclick="endTurn()" style="padding: 10px; font-size:14px; margin-top:5px;">Передать ход</button>
            </div>
            <button class="btn btn-orange" onclick="activateGuess()" id="guess-btn" style="margin-top:10px;">Я УГАДАЛ! (Кликни сюда, затем на карту)</button>
        </div>
    </div>

    <script>
        const tg = window.Telegram.WebApp;
        tg.ready(); tg.expand();

        let ws, myRole, roomId, currentCategory = 'cs';
        let myTarget = null, isMyTurn = false, isGuessing = false;

        const catEmojis = { "cs": "🎯", "dota": "⚔️", "memes": "😂", "rappers": "🎤", "football": "⚽", "gifts": "🎁" };
        const itemsData = {
            "cs": ["s1mple", "ZywOo", "NiKo", "donk", "m0NESY", "Magisk", "Snax", "hades"],
            "dota": ["Yatoro", "Miracle", "Dendi", "Puppey", "Topson", "Ame", "Somnus", "Kuroky"],
            "memes": ["Doge", "Pepe", "Trollface", "Stonks", "Crying Cat", "Doge 2", "Cheems", "Cat Vibing"],
            "rappers": ["Eminem", "Drake", "Kanye", "Travis Scott", "Morgenshtern", "Oxxxymiron", "Big Baby Tape", "Kizaru"],
            "football": ["Messi", "Ronaldo", "Mbappe", "Neymar", "Haaland", "Benzema", "Modric", "Kane"],
            "gifts": ["Медведь", "Сердце", "Ракета", "Торт", "Корона", "Пицца", "Плюшевый", "Кубок"]
        };

        function selectCat(cat) { currentCategory = cat; document.querySelectorAll('.cat-btn').forEach(b => b.style.background = 'rgba(255,255,255,0.1)'); event.target.style.background = '#3b82f6'; }
        function supportAuthor() { tg.showAlert("Для поддержки вернись в чат с ботом и нажми кнопку под сообщением!"); }
        function createGame() { roomId = Math.floor(1000 + Math.random() * 9000).toString(); connectWS('p1'); }
        function joinGame() { roomId = document.getElementById('joinId').value; if (!roomId) return alert("Введите код"); connectWS('p2'); }

        function renderBoard(category) {
            const items = itemsData[category || 'cs'];
            const board = document.getElementById('board');
            board.innerHTML = '';
            items.forEach((name, index) => {
                let card = document.createElement('div');
                card.className = 'card';
                const hue = (index * 45) % 360;
                card.style.background = `linear-gradient(135deg, hsl(${hue}, 70%, 30%), hsl(${hue}, 70%, 50%))`;
                card.innerHTML = `<div class="card-emoji">${catEmojis[category || 'cs']}</div><div>${name}</div>`;
                
                card.onclick = () => {
                    if (!myTarget) {
                        // Выбор секретного персонажа
                        myTarget = name;
                        card.classList.add('my-secret');
                        ws.send(JSON.stringify({type: "set_target", target: name}));
                        document.getElementById('hint').innerText = "✅ Ты загадал: " + name + ". Ждем друга...";
                    } else if (isGuessing) {
                        // Попытка угадать персонажа врага
                        ws.send(JSON.stringify({type: "guess", player: name}));
                        isGuessing = false;
                        document.getElementById('guess-btn').innerText = "Я УГАДАЛ!";
                    } else if (myTarget) {
                        // Просто вычеркиваем карточку
                        card.classList.toggle('eliminated');
                    }
                };
                board.appendChild(card);
            });
        }

        function connectWS(role) {
            myRole = role;
            document.getElementById('lobby').classList.add('hidden');
            document.getElementById('game').classList.remove('hidden');
            document.getElementById('hint').innerText = `Код: ${roomId}. Ожидание друга...`;
            renderBoard(currentCategory);

            ws = new WebSocket(`wss://${window.location.host}/ws/${roomId}/${role}`);
            
            ws.onopen = () => {
                if (myRole === 'p1') ws.send(JSON.stringify({type: "set_category", category: currentCategory}));
            };

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                
                if (data.type === 'connected') {
                    document.getElementById('hint').innerText = "👇 Нажми на карточку, чтобы загадать персонажа!";
                }
                
                if (data.type === 'start') {
                    isMyTurn = (data.turn === myRole);
                    document.getElementById('controls').classList.remove('hidden');
                    updateTurnUI();
                }
                
                if (data.type === 'chat') {
                    const chat = document.getElementById('chat');
                    let name = data.sender === myRole ? "Вы" : "Друг";
                    chat.innerHTML += `<div style="margin-bottom:5px;"><b style="color:#a78bfa;">${name}:</b> ${data.text}</div>`;
                    chat.scrollTop = chat.scrollHeight;
                }

                if (data.type === 'turn_change') {
                    isMyTurn = (data.turn === myRole);
                    updateTurnUI();
                }

                if (data.type === 'result') {
                    if (data.win) {
                        document.getElementById('hint').innerText = `🎉 ${data.guesser === myRole ? 'ВЫ ПОБЕДИЛИ' : 'ДРУГ ПОБЕДИЛ'}! Это был ${data.target}`;
                    } else {
                        document.getElementById('hint').innerText = `💀 ${data.guesser === myRole ? 'ВЫ ПРОИГРАЛИ' : 'ДРУГ ПРОИГРАЛ'}! Он загадал ${data.target}`;
                    }
                    document.getElementById('controls').classList.add('hidden');
                }
            };
        }

        function updateTurnUI() {
            if (isMyTurn) {
                document.getElementById('turn-indicator').innerText = "🟢 ТВОЙ ХОД";
                document.getElementById('turn-indicator').style.color = "#10b981";
            } else {
                document.getElementById('turn-indicator').innerText = "🔴 ХОД ДРУГА";
                document.getElementById('turn-indicator').style.color = "#ef4444";
            }
        }

        function activateGuess() {
            isGuessing = true;
            document.getElementById('guess-btn').innerText = "ВЫБЕРИ КАРТУ ВРАГА!";
            tg.HapticFeedback.notificationOccurred('warning');
        }

        function sendMsg() {
            const text = document.getElementById('msg').value;
            if (!text) return;
            ws.send(JSON.stringify({type: "chat", text: text}));
            document.getElementById('msg').value = '';
        }

        function endTurn() {
            if (!isMyTurn) return alert("Сейчас не твой ход!");
            ws.send(JSON.stringify({type: "end_turn"}));
        }
    </script>
</body>
</html>
"""

@app.get("/")
async def get():
    return HTMLResponse(content=HTML_CONTENT, status_code=200)

@app.get("/{path:path}")
async def catch_all(path: str):
    return HTMLResponse(content=HTML_CONTENT, status_code=200)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)