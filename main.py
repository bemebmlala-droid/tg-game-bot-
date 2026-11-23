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
        chat_id=call.message.chat.id, title="Поддержка автора", description="Спасибо за поддержку проекта!",
        payload="donate_support", provider_token="", currency="XTR",
        prices=[LabeledPrice(label="Поддержка", amount=5)], start_parameter="donate"
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
        rooms[room_id] = {"p1": None, "p2": None, "p1_target": None, "p2_target": None, "turn": "p1", "started": False}
    
    if role == "p1": rooms[room_id]["p1"] = websocket
    elif role == "p2": rooms[room_id]["p2"] = websocket

    if rooms[room_id]["p1"] and rooms[room_id]["p2"]:
        await rooms[room_id]["p1"].send_text(json.dumps({"type": "connected"}))
        await rooms[room_id]["p2"].send_text(json.dumps({"type": "connected"}))

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            other_role = "p2" if role == "p1" else "p1"
            
            if msg["type"] == "set_target":
                rooms[room_id][f"{role}_target"] = msg["target"]
                if rooms[room_id]["p1_target"] and rooms[room_id]["p2_target"]:
                    rooms[room_id]["started"] = True
                    for r in ["p1", "p2"]:
                        if rooms[room_id][r]:
                            await rooms[room_id][r].send_text(json.dumps({"type": "start", "turn": rooms[room_id]["turn"]}))

            elif msg["type"] == "chat":
                if rooms[room_id][other_role]:
                    await rooms[room_id][other_role].send_text(json.dumps({"type": "chat", "text": msg["text"], "sender": role}))

            elif msg["type"] == "end_turn":
                rooms[room_id]["turn"] = other_role
                for r in ["p1", "p2"]:
                    if rooms[room_id][r]:
                        await rooms[room_id][r].send_text(json.dumps({"type": "turn_change", "turn": rooms[room_id]["turn"]}))

            elif msg["type"] == "guess":
                target = rooms[room_id][f"{other_role}_target"]
                is_win = msg["player"] == target
                result_msg = {"type": "result", "win": is_win, "guessed": msg["player"], "target": target, "guesser": role}
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
        body { background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%); color: #fff; padding: 10px; font-family: 'Montserrat', sans-serif; margin: 0; overflow-x: hidden; }
        .bg-icon { position: fixed; opacity: 0.05; font-size: 40px; z-index: -1; animation: float 15s infinite linear; }
        @keyframes float { 0% { transform: translateY(0); } 50% { transform: translateY(-30px); } 100% { transform: translateY(0); } }
        .hidden { display: none !important; }
        .container { background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(10px); border-radius: 20px; padding: 15px; border: 1px solid rgba(255,255,255,0.1); box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
        h2 { text-align: center; background: -webkit-linear-gradient(45deg, #60a5fa, #c084fc); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 22px; margin-top: 0; }
        
        .grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; }
        .card { 
            background: #1e293b; border-radius: 10px; text-align: center; cursor: pointer; 
            font-size: 9px; font-weight: 700; transition: all 0.2s; border: 2px solid #3b82f6;
            display: flex; flex-direction: column; align-items: center; overflow: hidden;
            height: 85px; position: relative;
        }
        .card img { width: 100%; height: 65px; object-fit: contain; background: #000; }
        .card-name { padding: 2px; background: rgba(0,0,0,0.7); width: 100%; position: absolute; bottom: 0; box-sizing: border-box; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; }
        
        .card:active { transform: scale(0.95); }
        .card.eliminated { opacity: 0.2; filter: grayscale(100%); transform: scale(0.9); border-color: #ef4444;}
        .card.my-secret { border-color: #eab308 !important; box-shadow: 0 0 10px #eab308; }

        #chat { height: 110px; overflow-y: auto; border: 1px solid rgba(255,255,255,0.2); border-radius: 12px; margin-top: 10px; padding: 8px; background: rgba(0,0,0,0.3); font-size: 12px; }
        .btn { background: linear-gradient(45deg, #8b5cf6, #3b82f6); color: white; padding: 10px; border: none; border-radius: 12px; cursor: pointer; margin-top: 10px; width: 100%; font-size: 14px; font-weight: bold; }
        .btn-orange { background: linear-gradient(45deg, #f59e0b, #ef4444); }
        .btn-green { background: linear-gradient(45deg, #10b981, #059669); }
        input { width: 100%; padding: 10px; margin-top: 8px; box-sizing: border-box; border-radius: 10px; border: none; background: rgba(255,255,255,0.1); color: #fff; font-family: inherit; font-size: 14px;}
        
        .cat-btn { background: rgba(255,255,255,0.1); border: 1px solid #60a5fa; padding: 6px; margin: 2px; border-radius: 8px; display: inline-block; cursor: pointer; font-size: 11px;}
        #hint { font-size: 14px; text-align: center; margin-bottom: 10px; font-weight: 500; color: #fbbf24; }
        .turn-indicator { text-align: center; font-size: 12px; margin-bottom: 8px; color: #a78bfa; font-weight: bold;}
    </style>
</head>
<body>
    <div class="bg-icon" style="top: 10%; left: 5%;">🎮</div>
    <div class="bg-icon" style="top: 20%; right: 10%; animation-delay: 2s;">👾</div>
    <div class="bg-icon" style="bottom: 15%; left: 15%; animation-delay: 4s;">🎲</div>

    <div id="lobby" class="container">
        <h2>🕵️‍♂️ Угадай Кто?</h2>
        <div style="text-align:center; margin-bottom: 10px;">
            <div class="cat-btn" onclick="selectCat('streamers')">🎮 Стримеры</div>
            <div class="cat-btn" onclick="selectCat('bloggers')">📱 Блогеры/Тикток</div>
            <div class="cat-btn" onclick="selectCat('memes')">😂 Мемы 2026</div>
            <div class="cat-btn" onclick="selectCat('cs')">🔫 Ксеры</div>
            <div class="cat-btn" onclick="selectCat('dota')">⚔️ Дотера</div>
            <div class="cat-btn" onclick="selectCat('football')">⚽ Футбол</div>
            <div class="cat-btn" onclick="selectCat('gifts')">🎁 NFT Подарки</div>
        </div>
        <button class="btn" onclick="createGame()">Создать игру</button>
        <div style="margin-top: 10px; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 10px;">
            <input type="text" id="joinId" placeholder="Введите код комнаты">
            <button class="btn btn-green" onclick="joinGame()">Присоединиться</button>
        </div>
        <button class="btn btn-orange" onclick="supportAuthor()">⭐ Поддержать автора</button>
    </div>

    <div id="game" class="container hidden">
        <div id="turn-indicator" class="turn-indicator"></div>
        <div id="hint">Ожидание...</div>
        <div id="board" class="grid"></div>
        <div id="chat"></div>
        
        <div id="controls" class="hidden">
            <input type="text" id="msg" placeholder="Задай вопрос...">
            <div style="display:flex; gap:8px;">
                <button class="btn" onclick="sendMsg()">Спросить</button>
                <button class="btn btn-green" onclick="endTurn()">Передать ход</button>
            </div>
            <button class="btn btn-orange" onclick="activateGuess()" id="guess-btn">Я УГАДАЛ!</button>
        </div>
    </div>

    <script>
        const tg = window.Telegram.WebApp;
        tg.ready(); tg.expand();

        let ws, myRole, roomId, currentCategory = 'streamers';
        let myTarget = null, isMyTurn = false, isGuessing = false;

        const itemsData = {
            "streamers": [
                {name: "Мелстрой", img: "https://ui-avatars.com/api/?name=Mellstroy&background=ff4500&color=fff"},
                {name: "Buster", img: "https://ui-avatars.com/api/?name=Buster&background=1e90ff&color=fff"},
                {name: "Bratishkinoff", img: "https://ui-avatars.com/api/?name=Bratishkinoff&background=dc143c&color=fff"},
                {name: "Kardi", img: "https://ui-avatars.com/api/?name=Kardi&background=32cd32&color=fff"},
                {name: "Stray228", img: "https://ui-avatars.com/api/?name=Stray228&background=00008b&color=fff"},
                {name: "Evelone", img: "https://ui-avatars.com/api/?name=Evelone&background=ffa500&color=fff"},
                {name: "Nix", img: "https://ui-avatars.com/api/?name=Nix&background=333333&color=fff"},
                {name: "Dread", img: "https://ui-avatars.com/api/?name=Dread&background=8b0000&color=fff"}
            ],
            "bloggers": [
                {name: "Верити (Minecraft)", img: "https://ui-avatars.com/api/?name=Verity&background=2f4f4f&color=fff"},
                {name: "Влад Бумага", img: "https://ui-avatars.com/api/?name=Vlad+Bumaga&background=00bfff&color=fff"},
                {name: "Даня Милохин", img: "https://ui-avatars.com/api/?name=Danya&background=ffd700&color=000"},
                {name: "Валя Карнавал", img: "https://ui-avatars.com/api/?name=Valya&background=ff69b4&color=fff"},
                {name: "Иван Золо", img: "https://ui-avatars.com/api/?name=Ivan+Zolo&background=ff4500&color=fff"},
                {name: "Литвин", img: "https://ui-avatars.com/api/?name=Litvin&background=228b22&color=fff"},
                {name: "Дима Масленников", img: "https://ui-avatars.com/api/?name=Dima&background=4b0082&color=fff"},
                {name: "Хасбик", img: "https://ui-avatars.com/api/?name=Hasbulla&background=ff0000&color=fff"}
            ],
            "memes": [
                {name: "Тун Тун Сахур", img: "https://ui-avatars.com/api/?name=Tung+Sahur&background=8b4513&color=fff"},
                {name: "Котость Бурмалда", img: "https://ui-avatars.com/api/?name=Burmald&background=daa520&color=000"},
                {name: "Грязнулька", img: "https://ui-avatars.com/api/?name=Gryaznulka&background=556b2f&color=fff"},
                {name: "Вкусно и точка", img: "https://ui-avatars.com/api/?name=Vkusno&background=008000&color=fff"},
                {name: "Колобок", img: "https://ui-avatars.com/api/?name=Kolobok&background=ffd700&color=000"},
                {name: "Пингвин-нигилист", img: "https://ui-avatars.com/api/?name=Penguin&background=000&color=fff"},
                {name: "Сикс-севен", img: "https://ui-avatars.com/api/?name=Six+Seven&background=8a2be2&color=fff"},
                {name: "Вот такие дела", img: "https://ui-avatars.com/api/?name=Vot+takie&background=2f4f4f&color=fff"}
            ],
            "cs": [
                {name: "deko", img: "https://ui-avatars.com/api/?name=deko&background=ff0000&color=fff"},
                {name: "m0NESY", img: "https://ui-avatars.com/api/?name=m0NESY&background=000&color=fff"},
                {name: "kyousuke", img: "https://ui-avatars.com/api/?name=kyousuke&background=ff4500&color=fff"},
                {name: "donk", img: "https://ui-avatars.com/api/?name=donk&background=ffd700&color=000"},
                {name: "s1mple", img: "https://ui-avatars.com/api/?name=s1mple&background=ffff00&color=000"},
                {name: "ZywOo", img: "https://ui-avatars.com/api/?name=ZywOo&background=0000ff&color=fff"},
                {name: "NiKo", img: "https://ui-avatars.com/api/?name=NiKo&background=ffa500&color=fff"},
                {name: "Jame", img: "https://ui-avatars.com/api/?name=Jame&background=00ff00&color=000"}
            ],
            "dota": [
                {name: "Skiter", img: "https://ui-avatars.com/api/?name=Skiter&background=ff8c00&color=fff"},
                {name: "Kiyotaka", img: "https://ui-avatars.com/api/?name=Kiyotaka&background=4b0082&color=fff"},
                {name: "Yatoro", img: "https://ui-avatars.com/api/?name=Yatoro&background=ff4500&color=fff"},
                {name: "Larl", img: "https://ui-avatars.com/api/?name=Larl&background=dc143c&color=fff"},
                {name: "Collapse", img: "https://ui-avatars.com/api/?name=Collapse&background=8b0000&color=fff"},
                {name: "Miposhka", img: "https://ui-avatars.com/api/?name=Miposhka&background=006400&color=fff"},
                {name: "Dendi", img: "https://ui-avatars.com/api/?name=Dendi&background=00bfff&color=fff"},
                {name: "Ame", img: "https://ui-avatars.com/api/?name=Ame&background=ff69b4&color=fff"}
            ],
            "football": [
                {name: "Messi", img: "https://ui-avatars.com/api/?name=Messi&background=87ceeb&color=000"},
                {name: "Ronaldo", img: "https://ui-avatars.com/api/?name=Ronaldo&background=ff0000&color=fff"},
                {name: "Mbappe", img: "https://ui-avatars.com/api/?name=Mbappe&background=0000ff&color=fff"},
                {name: "Neymar", img: "https://ui-avatars.com/api/?name=Neymar&background=ffd700&color=000"},
                {name: "Haaland", img: "https://ui-avatars.com/api/?name=Haaland&background=00bfff&color=fff"},
                {name: "Benzema", img: "https://ui-avatars.com/api/?name=Benzema&background=ffffff&color=000"},
                {name: "Modric", img: "https://ui-avatars.com/api/?name=Modric&background=ff0000&color=fff"},
                {name: "Kane", img: "https://ui-avatars.com/api/?name=Kane&background=ffffff&color=000"}
            ],
            "gifts": [
                {name: "Toy Bear (Мишка)", img: "https://nft.fragment.com/gift/toybear-100.webp"},
                {name: "Scared Cat (Кот)", img: "https://nft.fragment.com/gift/scaredcat-100.webp"},
                {name: "Heart Locket (Сердце)", img: "https://nft.fragment.com/gift/heartlocket-100.webp"},
                {name: "Trapped Heart", img: "https://nft.fragment.com/gift/trappedheart-100.webp"},
                {name: "Plush Pepe", img: "https://nft.fragment.com/gift/plushpepe-100.webp"},
                {name: "Durov's Cap", img: "https://nft.fragment.com/gift/durovscap-100.webp"},
                {name: "Swiss Watch", img: "https://nft.fragment.com/gift/swisswatch-100.webp"},
                {name: "Resistance Dog", img: "https://nft.fragment.com/gift/resistancedog-100.webp"}
            ]
        };

        function selectCat(cat) { 
            currentCategory = cat; 
            document.querySelectorAll('.cat-btn').forEach(b => b.style.background = 'rgba(255,255,255,0.1)'); 
            if(event) event.target.style.background = '#3b82f6'; 
        }
        
        function supportAuthor() { tg.showAlert("Для поддержки вернись в чат с ботом и нажми кнопку под сообщением!"); }
        function createGame() { roomId = Math.floor(1000 + Math.random() * 9000).toString(); connectWS('p1'); }
        function joinGame() { roomId = document.getElementById('joinId').value; if (!roomId) return alert("Введите код"); connectWS('p2'); }

        function renderBoard(category) {
            const items = itemsData[category || 'streamers'];
            const board = document.getElementById('board');
            board.innerHTML = '';
            items.forEach((item) => {
                let card = document.createElement('div');
                card.className = 'card';
                // Если ссылка на NFT не загрузилась, подставит красивый аватар с названием
                card.innerHTML = `<img src="${item.img}" onerror="this.src='https://ui-avatars.com/api/?name=${item.name}&background=random&color=fff'"><div class="card-name">${item.name}</div>`;
                
                card.onclick = () => {
                    if (!myTarget) {
                        myTarget = item.name;
                        card.classList.add('my-secret');
                        ws.send(JSON.stringify({type: "set_target", target: item.name}));
                        document.getElementById('hint').innerText = "✅ Ты загадал: " + item.name + ". Ждем друга...";
                    } else if (isGuessing) {
                        ws.send(JSON.stringify({type: "guess", player: item.name}));
                        isGuessing = false;
                        document.getElementById('guess-btn').innerText = "Я УГАДАЛ!";
                    } else if (myTarget) {
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
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.type === 'connected') { document.getElementById('hint').innerText = "👇 Нажми на карточку, чтобы загадать!"; }
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
                if (data.type === 'turn_change') { isMyTurn = (data.turn === myRole); updateTurnUI(); }
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

        function activateGuess() { isGuessing = true; document.getElementById('guess-btn').innerText = "ВЫБЕРИ КАРТУ ВРАГА!"; tg.HapticFeedback.notificationOccurred('warning'); }
        function sendMsg() { const text = document.getElementById('msg').value; if (!text) return; ws.send(JSON.stringify({type: "chat", text: text})); document.getElementById('msg').value = ''; }
        function endTurn() { if (!isMyTurn) return alert("Сейчас не твой ход!"); ws.send(JSON.stringify({type: "end_turn"})); }
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