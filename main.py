import asyncio
import os
import json
import uvicorn

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    LabeledPrice,
    PreCheckoutQuery,
)
from contextlib import asynccontextmanager

# ================= НАСТРОЙКИ =================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
APP_URL = "https://tg-game-bot-4.onrender.com"

if not BOT_TOKEN:
    raise RuntimeError("Не задана переменная окружения BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
rooms = {}


async def run_bot():
    await dp.start_polling(bot)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(run_bot())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(lifespan=lifespan)


# ================= КОМАНДЫ TELEGRAM-БОТА =================
@dp.message(Command("start"))
async def cmd_start(message: Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🎮 Играть онлайн",
                web_app=WebAppInfo(url=APP_URL)
            )],
            [InlineKeyboardButton(
                text="⭐ Поддержать автора",
                callback_data="support"
            )],
        ]
    )
    await message.answer(
        "Привет! Нажми кнопку ниже, чтобы сыграть в «Угадай Кто?» с другом.",
        reply_markup=keyboard,
    )


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
        start_parameter="donate",
    )
    await call.answer()


@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout_q: PreCheckoutQuery):
    await pre_checkout_q.answer(ok=True)


@dp.message(lambda message: message.successful_payment is not None)
async def process_successful_payment(message: Message):
    amount = message.successful_payment.total_amount
    await message.answer(
        f"Огромное спасибо за поддержку! Ты оплатил {amount} звезд. ❤️"
    )


# ================= ЛОГИКА ОНЛАЙНА =================
@app.websocket("/ws/{room_id}/{role}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, role: str):
    if role not in ("p1", "p2"):
        await websocket.close(code=1008)
        return

    await websocket.accept()

    if room_id not in rooms:
        rooms[room_id] = {
            "p1": None,
            "p2": None,
            "p1_target": None,
            "p2_target": None,
            "turn": "p1",
            "started": False,
        }

    rooms[room_id][role] = websocket

    if rooms[room_id]["p1"] and rooms[room_id]["p2"]:
        for player_role in ("p1", "p2"):
            await rooms[room_id][player_role].send_text(
                json.dumps({"type": "connected"})
            )

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            other_role = "p2" if role == "p1" else "p1"

            if msg.get("type") == "set_target":
                rooms[room_id][f"{role}_target"] = msg.get("target")

                if (
                    rooms[room_id]["p1_target"]
                    and rooms[room_id]["p2_target"]
                ):
                    rooms[room_id]["started"] = True
                    for player_role in ("p1", "p2"):
                        player_socket = rooms[room_id][player_role]
                        if player_socket:
                            await player_socket.send_text(
                                json.dumps({
                                    "type": "start",
                                    "turn": rooms[room_id]["turn"],
                                })
                            )

            elif msg.get("type") == "chat":
                other_socket = rooms[room_id][other_role]
                if other_socket:
                    await other_socket.send_text(
                        json.dumps({
                            "type": "chat",
                            "text": str(msg.get("text", ""))[:500],
                            "sender": role,
                        })
                    )

            elif msg.get("type") == "end_turn":
                rooms[room_id]["turn"] = other_role
                for player_role in ("p1", "p2"):
                    player_socket = rooms[room_id][player_role]
                    if player_socket:
                        await player_socket.send_text(
                            json.dumps({
                                "type": "turn_change",
                                "turn": rooms[room_id]["turn"],
                            })
                        )

            elif msg.get("type") == "guess":
                target = rooms[room_id][f"{other_role}_target"]
                is_win = msg.get("player") == target
                result_msg = {
                    "type": "result",
                    "win": is_win,
                    "guessed": msg.get("player"),
                    "target": target,
                    "guesser": role,
                }
                for player_role in ("p1", "p2"):
                    player_socket = rooms[room_id][player_role]
                    if player_socket:
                        await player_socket.send_text(json.dumps(result_msg))

    except WebSocketDisconnect:
        if rooms.get(room_id):
            if rooms[room_id].get(role) == websocket:
                rooms[room_id][role] = None
            if not rooms[room_id]["p1"] and not rooms[room_id]["p2"]:
                del rooms[room_id]


# ================= HTML-ИГРА =================
HTML_CONTENT = r"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@500;700&display=swap');
        * { box-sizing: border-box; }
        body {
            background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
            color: #fff; padding: 10px; font-family: 'Montserrat', sans-serif;
            margin: 0; overflow-x: hidden;
        }
        .bg-icon {
            position: fixed; opacity: 0.05; font-size: 40px; z-index: -1;
            animation: float 15s infinite linear; pointer-events: none;
        }
        @keyframes float {
            0% { transform: translateY(0); }
            50% { transform: translateY(-30px); }
            100% { transform: translateY(0); }
        }
        .hidden { display: none !important; }
        .container {
            background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(10px);
            border-radius: 20px; padding: 15px;
            border: 1px solid rgba(255,255,255,0.1);
            box-shadow: 0 10px 25px rgba(0,0,0,0.5);
        }
        h2 {
            text-align: center; background: -webkit-linear-gradient(45deg, #60a5fa, #c084fc);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            font-size: 22px; margin-top: 0;
        }
        .grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 7px; }
        .card {
            background: #1e293b; border-radius: 10px; text-align: center;
            cursor: pointer; font-size: 9px; font-weight: 700;
            transition: transform 0.2s, opacity 0.2s;
            border: 2px solid #3b82f6; display: flex; flex-direction: column;
            align-items: center; overflow: hidden; height: 112px;
            min-width: 0; position: relative;
        }
        .card img {
            width: 100%; height: 88px; object-fit: cover;
            background: #0b1020; display: block;
        }
        .card-name {
            padding: 4px 2px; background: rgba(0,0,0,0.82);
            width: 100%; position: absolute; bottom: 0;
            text-overflow: ellipsis; overflow: hidden; white-space: nowrap;
        }
        .card:active { transform: scale(0.95); }
        .card.eliminated {
            opacity: 0.2; filter: grayscale(100%); transform: scale(0.9);
            border-color: #ef4444;
        }
        .card.my-secret {
            border-color: #eab308 !important;
            box-shadow: 0 0 10px #eab308;
        }
        #chat {
            height: 110px; overflow-y: auto;
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 12px; margin-top: 10px; padding: 8px;
            background: rgba(0,0,0,0.3); font-size: 12px;
            overflow-wrap: anywhere;
        }
        .btn {
            background: linear-gradient(45deg, #8b5cf6, #3b82f6);
            color: white; padding: 10px; border: none; border-radius: 12px;
            cursor: pointer; margin-top: 10px; width: 100%;
            font-size: 14px; font-weight: bold;
        }
        .btn-orange { background: linear-gradient(45deg, #f59e0b, #ef4444); }
        .btn-green { background: linear-gradient(45deg, #10b981, #059669); }
        input {
            width: 100%; padding: 10px; margin-top: 8px;
            border-radius: 10px; border: none;
            background: rgba(255,255,255,0.1); color: #fff;
            font-family: inherit; font-size: 14px;
        }
        .cat-btn {
            background: rgba(255,255,255,0.1); border: 1px solid #60a5fa;
            padding: 6px; margin: 2px; border-radius: 8px;
            display: inline-block; cursor: pointer; font-size: 11px;
        }
        .cat-btn.active { background: #3b82f6; }
        #hint {
            font-size: 14px; text-align: center; margin-bottom: 10px;
            font-weight: 500; color: #fbbf24;
        }
        .turn-indicator {
            text-align: center; font-size: 12px;
            margin-bottom: 8px; color: #a78bfa; font-weight: bold;
        }
        @media (max-width: 360px) {
            .grid { gap: 5px; }
            .card { height: 100px; }
            .card img { height: 76px; }
            .card-name { font-size: 8px; }
        }
    </style>
</head>
<body>
    <div class="bg-icon" style="top:10%;left:5%">🎮</div>
    <div class="bg-icon" style="top:20%;right:10%;animation-delay:2s">👾</div>
    <div class="bg-icon" style="bottom:15%;left:15%;animation-delay:4s">🎲</div>

    <div id="lobby" class="container">
        <h2>🕵️‍♂️ Угадай Кто?</h2>
        <div style="text-align:center;margin-bottom:10px">
            <div class="cat-btn active" onclick="selectCat('streamers', this)">🎮 Стримеры</div>
            <div class="cat-btn" onclick="selectCat('bloggers', this)">📱 Блогеры/Тикток</div>
            <div class="cat-btn" onclick="selectCat('memes', this)">😂 Мемы</div>
            <div class="cat-btn" onclick="selectCat('cs', this)">🎯 CS</div>
            <div class="cat-btn" onclick="selectCat('dota', this)">⚔️ Dota 2</div>
            <div class="cat-btn" onclick="selectCat('football', this)">⚽ Футбол</div>
            <div class="cat-btn" onclick="selectCat('gifts', this)">🎁 NFT Подарки</div>
        </div>
        <button class="btn" onclick="createGame()">Создать игру</button>
        <div style="margin-top:10px;border-top:1px solid rgba(255,255,255,0.1);padding-top:10px">
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
            <input type="text" id="msg" placeholder="Задай вопрос..." maxlength="500">
            <div style="display:flex;gap:8px">
                <button class="btn" onclick="sendMsg()">Спросить</button>
                <button class="btn btn-green" onclick="endTurn()">Передать ход</button>
            </div>
            <button class="btn btn-orange" onclick="activateGuess()" id="guess-btn">Я УГАДАЛ!</button>
        </div>
    </div>

<script>
    const tg = window.Telegram && window.Telegram.WebApp
        ? window.Telegram.WebApp : {
            ready: () => {}, expand: () => {}, showAlert: alert,
            HapticFeedback: { notificationOccurred: () => {} }
        };
    tg.ready();
    tg.expand();

    let ws, myRole, roomId, currentCategory = 'streamers';
    let myTarget = null, isMyTurn = false, isGuessing = false;

    // Для обычных людей фото подбираются через поиск изображений Wikimedia Commons.
    // NFT-картинки берутся с Fragment. Если фото не найдено, будет аккуратная заглушка.
    const itemsData = {
        streamers: [
            {name:"Мелстрой", search:"Mellstroy streamer"},
            {name:"Buster", search:"Buster streamer Russia"},
            {name:"Bratishkinoff", search:"Bratishkinoff streamer"},
            {name:"Kardi", search:"Kardi streamer"},
            {name:"Stray228", search:"Stray228 streamer"},
            {name:"Evelone", search:"Evelone streamer"},
            {name:"Nix", search:"Nix Dota streamer"},
            {name:"Dread", search:"Dread Dota streamer"}
        ],
        bloggers: [
            {name:"Верити (Minecraft)", search:"Verity Minecraft YouTuber"},
            {name:"Влад Бумага", search:"Vlad Bumaga A4"},
            {name:"Даня Милохин", search:"Danya Milokhin"},
            {name:"Валя Карнавал", search:"Valya Karnaval"},
            {name:"Иван Золо", search:"Ivan Zolo blogger"},
            {name:"Литвин", search:"Mikhail Litvin blogger"},
            {name:"Дима Масленников", search:"Dima Maslennikov blogger"},
            {name:"Хасбик", search:"Hasbulla"}
        ],
        memes: [
            {name:"Тун Тун Сахур", search:"Tung Tung Tung Sahur meme"},
            {name:"Котость Бурмалда", search:"Burmald meme cat"},
            {name:"Грязнулька", search:"Gryaznulya meme"},
            {name:"Вкусно и точка", search:"Vkusno i tochka logo"},
            {name:"Колобок", search:"Kolobok Russian fairy tale illustration"},
            {name:"Пингвин-нигилист", search:"nihilist penguin meme"},
            {name:"Сикс-севен", search:"six seven meme"},
            {name:"Вот такие дела", search:"Russian meme вот такие дела"}
        ],
        cs: [
            {name:"deko", search:"deko Counter Strike player"},
            {name:"m0NESY", search:"m0NESY Counter Strike player"},
            {name:"kyousuke", search:"kyousuke Counter Strike player"},
            {name:"donk", search:"donk Counter Strike player"},
            {name:"s1mple", search:"s1mple Counter Strike player"},
            {name:"ZywOo", search:"ZywOo Counter Strike player"},
            {name:"NiKo", search:"NiKo Counter Strike player"},
            {name:"Jame", search:"Jame Counter Strike player"}
        ],
        dota: [
            {name:"Skiter", search:"skiter Dota 2 player"},
            {name:"Kiyotaka", search:"Kiyotaka Dota 2 player"},
            {name:"Yatoro", search:"Yatoro Dota 2 player"},
            {name:"Larl", search:"Larl Dota 2 player"},
            {name:"Collapse", search:"Collapse Dota 2 player"},
            {name:"Miposhka", search:"Miposhka Dota 2 player"},
            {name:"Dendi", search:"Dendi Dota 2 player"},
            {name:"Ame", search:"Ame Dota 2 player"}
        ],
        football: [
            {name:"Messi", search:"Lionel Messi footballer"},
            {name:"Ronaldo", search:"Cristiano Ronaldo footballer"},
            {name:"Mbappe", search:"Kylian Mbappe footballer"},
            {name:"Neymar", search:"Neymar footballer"},
            {name:"Haaland", search:"Erling Haaland footballer"},
            {name:"Benzema", search:"Karim Benzema footballer"},
            {name:"Modric", search:"Luka Modric footballer"},
            {name:"Kane", search:"Harry Kane footballer"}
        ],
        gifts: [
            {name:"Toy Bear (Мишка)", img:"https://nft.fragment.com/gift/toybear-100.webp"},
            {name:"Scared Cat (Кот)", img:"https://nft.fragment.com/gift/scaredcat-100.webp"},
            {name:"Heart Locket (Сердце)", img:"https://nft.fragment.com/gift/heartlocket-100.webp"},
            {name:"Trapped Heart", img:"https://nft.fragment.com/gift/trappedheart-100.webp"},
            {name:"Plush Pepe", img:"https://nft.fragment.com/gift/plushpepe-100.webp"},
            {name:"Durov's Cap", img:"https://nft.fragment.com/gift/durovscap-100.webp"},
            {name:"Swiss Watch", img:"https://nft.fragment.com/gift/swisswatch-100.webp"},
            {name:"Resistance Dog", img:"https://nft.fragment.com/gift/resistancedog-100.webp"}
        ]
    };

    function fallbackImage(name) {
        return "https://ui-avatars.com/api/?name=" +
            encodeURIComponent(name) + "&background=26345b&color=ffffff&size=320&bold=true";
    }

    // Wikimedia отдаёт миниатюру найденного файла. Запросы кэшируются на время игры.
    const photoCache = new Map();

    async function findPhoto(item) {
        if (item.img) return item.img;
        if (photoCache.has(item.search)) return photoCache.get(item.search);

        const api = "https://commons.wikimedia.org/w/api.php?" +
            new URLSearchParams({
                action: "query",
                generator: "search",
                gsrsearch: item.search + " filetype:bitmap",
                gsrnamespace: "6",
                gsrlimit: "1",
                prop: "imageinfo",
                iiprop: "url",
                iiurlwidth: "320",
                format: "json",
                origin: "*"
            }).toString();

        try {
            const response = await fetch(api);
            if (!response.ok) throw new Error("Image search failed");
            const data = await response.json();
            const pages = data.query && data.query.pages
                ? Object.values(data.query.pages) : [];
            const imageUrl = pages[0] && pages[0].imageinfo &&
                pages[0].imageinfo[0]
                ? (pages[0].imageinfo[0].thumburl || pages[0].imageinfo[0].url)
                : null;
            const result = imageUrl || fallbackImage(item.name);
            photoCache.set(item.search, result);
            return result;
        } catch (error) {
            const result = fallbackImage(item.name);
            photoCache.set(item.search, result);
            return result;
        }
    }

    function selectCat(cat, button) {
        currentCategory = cat;
        document.querySelectorAll('.cat-btn').forEach(b => b.classList.remove('active'));
        if (button) button.classList.add('active');
    }

    function supportAuthor() {
        tg.showAlert("Для поддержки вернись в чат с ботом и нажми кнопку под сообщением!");
    }

    function createGame() {
        roomId = Math.floor(1000 + Math.random() * 9000).toString();
        connectWS('p1');
    }

    function joinGame() {
        roomId = document.getElementById('joinId').value.trim();
        if (!roomId) return alert("Введите код комнаты");
        connectWS('p2');
    }

    function renderBoard(category) {
        const items = itemsData[category] || itemsData.streamers;
        const board = document.getElementById('board');
        board.innerHTML = '';

        items.forEach((item) => {
            const card = document.createElement('div');
            card.className = 'card';

            const img = document.createElement('img');
            img.alt = item.name;
            img.loading = 'lazy';
            img.src = item.img || fallbackImage(item.name);
            img.onerror = () => {
                img.onerror = null;
                img.src = fallbackImage(item.name);
            };

            const name = document.createElement('div');
            name.className = 'card-name';
            name.textContent = item.name;

            card.appendChild(img);
            card.appendChild(name);

            // Фото подгружается отдельно, чтобы карточки сразу появились на экране.
            findPhoto(item).then(url => {
                if (url && card.isConnected) img.src = url;
            });

            card.onclick = () => {
                if (!myTarget) {
                    myTarget = item.name;
                    card.classList.add('my-secret');
                    ws.send(JSON.stringify({type:"set_target", target:item.name}));
                    document.getElementById('hint').innerText =
                        "✅ Ты загадал: " + item.name + ". Ждем друга...";
                } else if (isGuessing) {
                    ws.send(JSON.stringify({type:"guess", player:item.name}));
                    isGuessing = false;
                    document.getElementById('guess-btn').innerText = "Я УГАДАЛ!";
                } else {
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

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${protocol}//${window.location.host}/ws/${roomId}/${role}`);

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);

            if (data.type === 'connected') {
                document.getElementById('hint').innerText =
                    "👇 Каждый игрок должен выбрать секретную карточку!";
            }

            if (data.type === 'start') {
                isMyTurn = (data.turn === myRole);
                document.getElementById('controls').classList.remove('hidden');
                updateTurnUI();
                document.getElementById('hint').innerText = "Игра началась! Задавай вопросы.";
            }

            if (data.type === 'chat') {
                const chat = document.getElementById('chat');
                const line = document.createElement('div');
                line.style.marginBottom = '5px';

                const sender = document.createElement('b');
                sender.style.color = '#a78bfa';
                sender.textContent = data.sender === myRole ? "Вы: " : "Друг: ";

                const messageText = document.createTextNode(data.text || "");
                line.appendChild(sender);
                line.appendChild(messageText);
                chat.appendChild(line);
                chat.scrollTop = chat.scrollHeight;
            }

            if (data.type === 'turn_change') {
                isMyTurn = (data.turn === myRole);
                updateTurnUI();
            }

            if (data.type === 'result') {
                if (data.win) {
                    document.getElementById('hint').innerText =
                        `🎉 ${data.guesser === myRole ? 'ВЫ ПОБЕДИЛИ' : 'ДРУГ ПОБЕДИЛ'}! Это был ${data.target}`;
                } else {
                    document.getElementById('hint').innerText =
                        `💀 ${data.guesser === myRole ? 'ВЫ ПРОИГРАЛИ' : 'ДРУГ ПРОИГРАЛ'}! Он загадал ${data.target}`;
                }
                document.getElementById('controls').classList.add('hidden');
            }
        };

        ws.onclose = () => {
            document.getElementById('hint').innerText =
                "Соединение закрыто. Вернись в меню и создай новую комнату.";
        };

        ws.onerror = () => {
            document.getElementById('hint').innerText =
                "Не удалось подключиться. Проверь интернет и попробуй снова.";
        };
    }

    function updateTurnUI() {
        const indicator = document.getElementById('turn-indicator');
        if (isMyTurn) {
            indicator.innerText = "🟢 ТВОЙ ХОД";
            indicator.style.color = "#10b981";
        } else {
            indicator.innerText = "🔴 ХОД ДРУГА";
            indicator.style.color = "#ef4444";
        }
    }

    function activateGuess() {
        isGuessing = true;
        document.getElementById('guess-btn').innerText = "ВЫБЕРИ КАРТУ ДРУГА!";
        tg.HapticFeedback.notificationOccurred('warning');
    }

    function sendMsg() {
        const input = document.getElementById('msg');
        const text = input.value.trim();
        if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
        ws.send(JSON.stringify({type:"chat", text}));
        input.value = '';
    }

    function endTurn() {
        if (!isMyTurn) return alert("Сейчас не твой ход!");
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({type:"end_turn"}));
        }
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
